"""
Document text extraction.

Pulls the *words* out of a document so they can be typed somewhere else.
Formatting is deliberately not carried across: a keyboard can only produce
characters, so bold, headings, fonts, tables, images and page layout have no
keystroke equivalent. What you get back is the prose, with paragraph breaks
intact.

Everything here is standard library — .docx and .odt are zip archives of XML,
.rtf and .html are markup — so importing a Word document adds no dependency.
PDF is the exception and is only supported when `pypdf` happens to be
installed, because there is no reasonable stdlib PDF parser.

Untrusted files are treated as untrusted: archive members are size-capped
before extraction so a zip bomb cannot exhaust memory.
"""

import html
import io
import os
import re
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

__all__ = [
    "SUPPORTED", "FILE_TYPES", "extract", "extract_bytes",
    "describe_support", "UnsupportedDocument", "DocumentTooLarge",
]


class UnsupportedDocument(Exception):
    """The file is not a format we can read text out of."""


class DocumentTooLarge(Exception):
    """The file, or something inside it, is larger than we will unpack."""


# A document you would sit and retype is not 200 MB.
MAX_FILE_BYTES = 64 * 1024 * 1024
# Cap on the uncompressed size of any single member of a .docx/.odt archive.
MAX_MEMBER_BYTES = 128 * 1024 * 1024

PLAIN_EXTENSIONS = {
    ".txt", ".text", ".md", ".markdown", ".mdown", ".rst", ".log",
    ".csv", ".tsv", ".json", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".py", ".js", ".ts", ".java", ".c", ".h", ".cpp", ".cs", ".go", ".rs",
    ".rb", ".php", ".sh", ".sql", ".xml", ".tex", ".srt", ".vtt",
}

RICH_EXTENSIONS = {".docx", ".odt", ".rtf", ".html", ".htm", ".pdf"}

SUPPORTED = PLAIN_EXTENSIONS | RICH_EXTENSIONS

# For the file-picker dialog.
FILE_TYPES = [
    ("All supported", " ".join("*" + e for e in sorted(SUPPORTED))),
    ("Text and Markdown", "*.txt *.md *.markdown *.rst *.log"),
    ("Word document", "*.docx"),
    ("OpenDocument text", "*.odt"),
    ("Rich text", "*.rtf"),
    ("Web page", "*.html *.htm"),
    ("PDF", "*.pdf"),
    ("All files", "*.*"),
]


def describe_support():
    """One line per format, for the About tab and the docs."""
    rows = [
        (".txt .md .csv .json …", "read directly"),
        (".docx", "Word — text and paragraph breaks"),
        (".odt", "OpenDocument / LibreOffice — text and paragraph breaks"),
        (".rtf", "Rich text — control words stripped"),
        (".html .htm", "Web page — tags stripped, blocks become paragraphs"),
        (".pdf", "only if pypdf is installed (pip install pypdf)"),
    ]
    return rows


# ---------------------------------------------------------------------------
# Shared clean-up
# ---------------------------------------------------------------------------
def _tidy(text):
    """Normalise whitespace without destroying the author's paragraphing."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = text.replace("\ufeff", "")   # byte-order mark, invisible but real
    # Trailing spaces on a line are invisible and cost real typing time.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Collapse runs of blank lines to a single blank line.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def _safe_read(zf, name):
    info = zf.getinfo(name)
    if info.file_size > MAX_MEMBER_BYTES:
        raise DocumentTooLarge(
            "%s unpacks to %.0f MB, which is more than this will open."
            % (name, info.file_size / 1e6))
    return zf.read(name)


def _localname(tag):
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------------------
# .docx  —  Office Open XML
# ---------------------------------------------------------------------------
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _from_docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if "word/document.xml" not in zf.namelist():
            raise UnsupportedDocument(
                "This .docx has no word/document.xml — it may be a .doc "
                "renamed, which is a different format entirely.")
        xml = _safe_read(zf, "word/document.xml")

    root = ET.fromstring(xml)

    def para_text(node):
        """Text of one <w:p>, walking runs but stepping over deletions."""
        parts = []

        def walk(n):
            for child in n:
                name = _localname(child.tag)
                if name == "del":
                    # Tracked deletion: this text is not in the document.
                    continue
                if name == "t":
                    parts.append(child.text or "")
                elif name == "tab":
                    parts.append("\t")
                elif name in ("br", "cr"):
                    parts.append("\n")
                else:
                    walk(child)

        walk(node)
        return "".join(parts)

    paragraphs = [para_text(p) for p in root.iter(_W_NS + "p")]
    return _tidy("\n\n".join(paragraphs))


# ---------------------------------------------------------------------------
# .odt  —  OpenDocument
# ---------------------------------------------------------------------------
def _from_odt(data):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if "content.xml" not in zf.namelist():
            raise UnsupportedDocument("This .odt has no content.xml.")
        xml = _safe_read(zf, "content.xml")

    root = ET.fromstring(xml)

    def text_of(node):
        out = []
        for child in node.iter():
            name = _localname(child.tag)
            if name == "s":                       # collapsed spaces
                count = 1
                for k, v in child.attrib.items():
                    if _localname(k) == "c":
                        try:
                            count = int(v)
                        except ValueError:
                            count = 1
                out.append(" " * count)
            elif name == "tab":
                out.append("\t")
            elif name == "line-break":
                out.append("\n")
            if child is not node and child.text:
                out.append(child.text)
            if child is not node and child.tail:
                out.append(child.tail)
        if node.text:
            out.insert(0, node.text)
        return "".join(out)

    paragraphs = []
    for node in root.iter():
        if _localname(node.tag) in ("p", "h"):
            paragraphs.append(text_of(node))
    return _tidy("\n\n".join(paragraphs))


# ---------------------------------------------------------------------------
# .rtf
# ---------------------------------------------------------------------------
_RTF_SKIP_GROUPS = (
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object",
    "themedata", "colorschememapping", "latentstyles", "datastore",
    "generator", "listtable", "listoverridetable", "rsidtbl",
)


def _from_rtf(data):
    text = data.decode("latin-1", errors="replace") if isinstance(data, bytes) else data

    # Drop groups whose contents are metadata rather than document text.
    for name in _RTF_SKIP_GROUPS:
        text = re.sub(r"\{(?:\\\*)?\\" + name + r"\b", "{\\*\\__drop", text)
    out = []
    depth = 0
    drop_at = None
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
            if text.startswith("{\\*\\__drop", i) and drop_at is None:
                drop_at = depth
            i += 1
        elif c == "}":
            if drop_at is not None and depth == drop_at:
                drop_at = None
            depth -= 1
            i += 1
        elif c == "\\":
            m = re.match(r"\\([a-zA-Z]+)(-?\d+)? ?", text[i:])
            if m:
                word, arg = m.group(1), m.group(2)
                if drop_at is None:
                    if word in ("par", "pard"):
                        out.append("\n")
                    elif word == "line":
                        out.append("\n")
                    elif word == "tab":
                        out.append("\t")
                    elif word == "u" and arg:
                        try:
                            out.append(chr(int(arg) % 65536))
                        except ValueError:
                            pass
                i += m.end()
            elif text[i:i + 2] == "\\'":
                try:
                    if drop_at is None:
                        out.append(bytes([int(text[i + 2:i + 4], 16)])
                                   .decode("cp1252", errors="replace"))
                except ValueError:
                    pass
                i += 4
            else:
                if drop_at is None and i + 1 < n:
                    out.append(text[i + 1])
                i += 2
        else:
            if drop_at is None and c not in "\r\n":
                out.append(c)
            i += 1
    return _tidy("".join(out))


# ---------------------------------------------------------------------------
# .html
# ---------------------------------------------------------------------------
_BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "section", "article", "header", "footer", "hr",
    "table", "ul", "ol", "dl", "dd", "dt", "figure", "figcaption",
}


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._muted = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "noscript", "template"):
            self._muted += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n" if tag != "br" else "\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "noscript", "template"):
            self._muted = max(0, self._muted - 1)
        elif tag in _BLOCK_TAGS and tag != "br":
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self._muted:
            self.parts.append(data)


def _from_html(data):
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    parser = _HTMLText()
    parser.feed(text)
    parser.close()
    joined = "".join(parser.parts)
    joined = re.sub(r"[ \t]+", " ", joined)
    joined = html.unescape(joined)
    return _tidy(joined)


# ---------------------------------------------------------------------------
# .pdf  —  optional
# ---------------------------------------------------------------------------
def _from_pdf(data):
    try:
        import pypdf
    except ImportError:
        try:
            import PyPDF2 as pypdf  # older name, same API for our purposes
        except ImportError:
            raise UnsupportedDocument(
                "Reading PDFs needs the pypdf package, which is not "
                "installed.\n\nRun:  pip install pypdf\n\n"
                "Everything else — .docx, .odt, .rtf, .html and plain text — "
                "works without it.")
    reader = pypdf.PdfReader(io.BytesIO(data))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            raise UnsupportedDocument(
                "This PDF is password-protected, so its text cannot be read.")
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = _tidy("\n\n".join(pages))
    if not text.strip():
        raise UnsupportedDocument(
            "No text could be extracted. This PDF is most likely a scan — "
            "an image of a page rather than characters — which would need OCR.")
    return text


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------
def _from_plain(data):
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return _tidy(data.decode(encoding))
        except UnicodeDecodeError:
            continue
    return _tidy(data.decode("utf-8", errors="replace"))


_READERS = {
    ".docx": _from_docx,
    ".odt": _from_odt,
    ".rtf": _from_rtf,
    ".html": _from_html,
    ".htm": _from_html,
    ".pdf": _from_pdf,
}


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def extract_bytes(data, extension):
    """Text out of `data`, read according to `extension` (e.g. '.docx')."""
    ext = (extension or "").lower()
    if ext in _READERS:
        try:
            return _READERS[ext](data)
        except (UnsupportedDocument, DocumentTooLarge):
            raise
        except zipfile.BadZipFile:
            raise UnsupportedDocument(
                "This file is not a valid %s archive — it may be corrupt, or "
                "an older format wearing a newer extension." % ext)
        except ET.ParseError as exc:
            raise UnsupportedDocument(
                "The XML inside this %s could not be parsed: %s" % (ext, exc))
    if ext in PLAIN_EXTENSIONS or not ext:
        return _from_plain(data)
    # Unknown extension: it may still be text, so try rather than refuse.
    text = _from_plain(data)
    if "\x00" in text[:4096]:
        raise UnsupportedDocument(
            "%s looks like a binary file, not a document." % (ext or "This file"))
    return text


def extract(path):
    """Text out of the file at `path`.

    Raises UnsupportedDocument or DocumentTooLarge with a message written for
    a person rather than a stack trace.
    """
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        raise DocumentTooLarge(
            "That file is %.0f MB. Anything over %d MB is almost certainly not "
            "something you meant to retype."
            % (size / 1e6, MAX_FILE_BYTES // (1024 * 1024)))
    with open(path, "rb") as fh:
        data = fh.read()
    return extract_bytes(data, os.path.splitext(path)[1])
