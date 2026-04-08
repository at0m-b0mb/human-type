import threading
import time
import random
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import pyautogui
import pyperclip


class HumanTyperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Human Typer")
        self.root.geometry("760x560")

        self.stop_requested = False

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.02

        self.build_ui()

    def build_ui(self):
        main = tk.Frame(self.root, padx=12, pady=12)
        main.pack(fill="both", expand=True)

        title = tk.Label(main, text="Human Typer", font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w")

        subtitle = tk.Label(
            main,
            text="Load text from file, import clipboard, or paste manually. Then start typing into the active window.",
            fg="gray30"
        )
        subtitle.pack(anchor="w", pady=(0, 10))

        controls = tk.Frame(main)
        controls.pack(fill="x", pady=(0, 10))

        tk.Button(controls, text="Load .txt File", command=self.load_file).grid(row=0, column=0, padx=(0, 8), pady=4)
        tk.Button(controls, text="Import Clipboard", command=self.import_clipboard).grid(row=0, column=1, padx=(0, 8), pady=4)
        tk.Button(controls, text="Clear Text", command=self.clear_text).grid(row=0, column=2, padx=(0, 8), pady=4)

        settings = tk.LabelFrame(main, text="Typing Settings", padx=10, pady=10)
        settings.pack(fill="x", pady=(0, 10))

        tk.Label(settings, text="Start delay (seconds):").grid(row=0, column=0, sticky="w")
        self.start_delay_var = tk.StringVar(value="5")
        tk.Entry(settings, textvariable=self.start_delay_var, width=10).grid(row=0, column=1, sticky="w", padx=(8, 20))

        tk.Label(settings, text="Base delay per char (seconds):").grid(row=0, column=2, sticky="w")
        self.base_delay_var = tk.StringVar(value="0.08")
        tk.Entry(settings, textvariable=self.base_delay_var, width=10).grid(row=0, column=3, sticky="w", padx=(8, 20))

        tk.Label(settings, text="Random variation (+/- sec):").grid(row=1, column=0, sticky="w")
        self.variation_var = tk.StringVar(value="0.03")
        tk.Entry(settings, textvariable=self.variation_var, width=10).grid(row=1, column=1, sticky="w", padx=(8, 20))

        tk.Label(settings, text="Extra pause after punctuation:").grid(row=1, column=2, sticky="w")
        self.punctuation_pause_var = tk.StringVar(value="0.25")
        tk.Entry(settings, textvariable=self.punctuation_pause_var, width=10).grid(row=1, column=3, sticky="w", padx=(8, 20))

        self.press_enter_var = tk.BooleanVar(value=False)
        tk.Checkbutton(settings, text="Interpret new lines as Enter", variable=self.press_enter_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        self.text_box = tk.Text(main, wrap="word", font=("Consolas", 11))
        self.text_box.pack(fill="both", expand=True, pady=(0, 10))

        action_row = tk.Frame(main)
        action_row.pack(fill="x")

        tk.Button(action_row, text="Start Typing", bg="#1f6feb", fg="white", command=self.start_typing_thread).pack(side="left")
        tk.Button(action_row, text="Stop", command=self.stop_typing).pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(main, textvariable=self.status_var, anchor="w", fg="gray25").pack(fill="x", pady=(10, 0))

    def load_file(self):
        file_path = filedialog.askopenfilename(
            title="Select a text file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            text = Path(file_path).read_text(encoding="utf-8")
            self.text_box.delete("1.0", tk.END)
            self.text_box.insert("1.0", text)
            self.status_var.set(f"Loaded file: {Path(file_path).name}")
        except Exception as e:
            messagebox.showerror("File Error", f"Could not read file:\n{e}")

    def import_clipboard(self):
        try:
            text = pyperclip.paste()
            if not text:
                messagebox.showwarning("Clipboard Empty", "Clipboard does not contain text.")
                return
            self.text_box.delete("1.0", tk.END)
            self.text_box.insert("1.0", text)
            self.status_var.set("Imported text from clipboard.")
        except Exception as e:
            messagebox.showerror("Clipboard Error", f"Could not read clipboard:\n{e}")

    def clear_text(self):
        self.text_box.delete("1.0", tk.END)
        self.status_var.set("Text cleared.")

    def stop_typing(self):
        self.stop_requested = True
        self.status_var.set("Stop requested.")

    def start_typing_thread(self):
        text = self.text_box.get("1.0", tk.END).rstrip("\n")
        if not text.strip():
            messagebox.showwarning("No Text", "Please paste text, import clipboard text, or load a file first.")
            return

        try:
            start_delay = float(self.start_delay_var.get())
            base_delay = float(self.base_delay_var.get())
            variation = float(self.variation_var.get())
            punctuation_pause = float(self.punctuation_pause_var.get())
        except ValueError:
            messagebox.showerror("Invalid Settings", "Please enter valid numeric values.")
            return

        self.stop_requested = False
        worker = threading.Thread(
            target=self.type_text,
            args=(text, start_delay, base_delay, variation, punctuation_pause, self.press_enter_var.get()),
            daemon=True
        )
        worker.start()

    def type_text(self, text, start_delay, base_delay, variation, punctuation_pause, press_enter_for_newlines):
        try:
            self.status_var.set(f"Typing starts in {start_delay} seconds. Switch to target window now.")
            time.sleep(start_delay)

            for ch in text:
                if self.stop_requested:
                    self.status_var.set("Typing stopped.")
                    return

                if ch == "\n" and press_enter_for_newlines:
                    pyautogui.press("enter")
                else:
                    pyautogui.write(ch)

                delay = max(0, base_delay + random.uniform(-variation, variation))

                if ch in ".!?;:":
                    delay += punctuation_pause
                elif ch == ",":
                    delay += punctuation_pause / 2

                time.sleep(delay)

            self.status_var.set("Done typing.")
        except pyautogui.FailSafeException:
            self.status_var.set("Fail-safe triggered. Mouse moved to top-left corner.")
        except Exception as e:
            self.status_var.set(f"Error: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = HumanTyperApp(root)
    root.mainloop()
