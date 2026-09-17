"""
Host tests for document text extraction.

Real .docx and .odt archives are built in memory here rather than committed
as fixtures, so the tests document the file formats as well as exercise them.
"""

import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import docimport as D  # noqa: E402


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(paragraphs, tracked_deletion=None):
    """A minimal but genuinely valid .docx."""
    body = []
    for para in paragraphs:
        runs = "".join(
            "<w:tab/>" if part == "\t" else
            "<w:br/>" if part == "\n" else
            "<w:r><w:t xml:space='preserve'>%s</w:t></w:r>" % part
            for part in [para] if True)
        body.append("<w:p>%s</w:p>" % runs)
    if tracked_deletion:
        body.append(
            "<w:p><w:del><w:r><w:delText>%s</w:delText></w:r></w:del>"
            "<w:r><w:t>%s</w:t></w:r></w:p>" % tracked_deletion)
    document = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<w:document xmlns:w='%s'><w:body>%s</w:body></w:document>"
        % (W, "".join(body)))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
                    "<?xml version='1.0'?><Types xmlns='http://schemas."
                    "openxmlformats.org/package/2006/content-types'/>")
        zf.writestr("word/document.xml", document)
    return buf.getvalue()


def make_odt(paragraphs):
    ns = ("xmlns:office='urn:oasis:names:tc:opendocument:xmlns:office:1.0' "
          "xmlns:text='urn:oasis:names:tc:opendocument:xmlns:text:1.0'")
    body = "".join("<text:p>%s</text:p>" % p for p in paragraphs)
    content = ("<?xml version='1.0' encoding='UTF-8'?>"
               "<office:document-content %s><office:body><office:text>%s"
               "</office:text></office:body></office:document-content>"
               % (ns, body))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zf.writestr("content.xml", content)
    return buf.getvalue()


class DocxTests(unittest.TestCase):
    def test_paragraphs_survive(self):
        data = make_docx(["First paragraph.", "Second paragraph."])
        self.assertEqual(D.extract_bytes(data, ".docx"),
                         "First paragraph.\n\nSecond paragraph.")

    def test_unicode_survives(self):
        data = make_docx(["café — naïve “quotes” 🙂"])
        self.assertEqual(D.extract_bytes(data, ".docx"),
                         "café — naïve “quotes” 🙂")

    def test_tracked_deletions_are_not_imported(self):
        """Deleted text is not part of the document and must not be typed."""
        data = make_docx(["Kept."], tracked_deletion=("DELETED", "Survives."))
        out = D.extract_bytes(data, ".docx")
        self.assertNotIn("DELETED", out)
        self.assertIn("Survives.", out)

    def test_blank_paragraph_runs_are_collapsed(self):
        data = make_docx(["One.", "", "", "", "Two."])
        self.assertEqual(D.extract_bytes(data, ".docx"), "One.\n\nTwo.")

    def test_a_renamed_doc_is_reported_clearly(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("something/else.xml", "<a/>")
        with self.assertRaises(D.UnsupportedDocument) as cm:
            D.extract_bytes(buf.getvalue(), ".docx")
        self.assertIn("document.xml", str(cm.exception))

    def test_corrupt_archive_is_reported_clearly(self):
        with self.assertRaises(D.UnsupportedDocument) as cm:
            D.extract_bytes(b"not a zip at all", ".docx")
        self.assertIn("not a valid", str(cm.exception))


class OdtTests(unittest.TestCase):
    def test_paragraphs_survive(self):
        data = make_odt(["Alpha.", "Beta."])
        self.assertEqual(D.extract_bytes(data, ".odt"), "Alpha.\n\nBeta.")

    def test_missing_content_is_reported(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("mimetype", "x")
        with self.assertRaises(D.UnsupportedDocument):
            D.extract_bytes(buf.getvalue(), ".odt")


class RtfTests(unittest.TestCase):
    def test_control_words_are_stripped(self):
        rtf = (r"{\rtf1\ansi\deff0{\fonttbl{\f0 Times;}}"
               r"\f0\fs24 Hello world.\par Second line.\par}")
        out = D.extract_bytes(rtf.encode(), ".rtf")
        self.assertIn("Hello world.", out)
        self.assertIn("Second line.", out)
        self.assertNotIn("fonttbl", out)
        self.assertNotIn("Times", out)

    def test_escaped_characters_decode(self):
        rtf = r"{\rtf1\ansi caf\'e9 nights\par}"
        self.assertIn("café", D.extract_bytes(rtf.encode(), ".rtf"))

    def test_tabs_survive(self):
        rtf = r"{\rtf1\ansi a\tab b\par}"
        self.assertIn("\t", D.extract_bytes(rtf.encode(), ".rtf"))


class HtmlTests(unittest.TestCase):
    def test_tags_stripped_blocks_become_paragraphs(self):
        out = D.extract_bytes(
            b"<html><body><h1>Title</h1><p>One.</p><p>Two.</p></body></html>",
            ".html")
        self.assertEqual(out, "Title\n\nOne.\n\nTwo.")

    def test_scripts_and_styles_are_dropped(self):
        out = D.extract_bytes(
            b"<html><head><style>p{color:red}</style></head><body>"
            b"<script>alert(1)</script><p>Only this.</p></body></html>",
            ".html")
        self.assertEqual(out, "Only this.")

    def test_entities_are_decoded(self):
        out = D.extract_bytes(b"<p>caf&eacute; &amp; cream &mdash; yes</p>", ".html")
        self.assertEqual(out, "café & cream — yes")

    def test_br_is_a_single_line_break(self):
        out = D.extract_bytes(b"<p>one<br>two</p>", ".html")
        self.assertEqual(out, "one\ntwo")


class PlainTests(unittest.TestCase):
    def test_utf8_bom_is_removed(self):
        self.assertEqual(D.extract_bytes("﻿hello".encode("utf-8"), ".txt"),
                         "hello")

    def test_windows_line_endings_normalise(self):
        self.assertEqual(D.extract_bytes(b"a\r\nb\r\nc", ".txt"), "a\nb\nc")

    def test_trailing_whitespace_is_trimmed(self):
        """Invisible trailing spaces would cost real seconds to type."""
        self.assertEqual(D.extract_bytes(b"line one   \nline two\t\t", ".txt"),
                         "line one\nline two")

    def test_non_utf8_still_reads(self):
        self.assertIn("caf", D.extract_bytes("café".encode("cp1252"), ".txt"))

    def test_unknown_extension_is_tried_as_text(self):
        self.assertEqual(D.extract_bytes(b"plain content", ".weird"),
                         "plain content")

    def test_binary_is_refused(self):
        with self.assertRaises(D.UnsupportedDocument):
            D.extract_bytes(b"\x00\x01\x02binary\x00", ".weird")


class SafetyTests(unittest.TestCase):
    def test_oversized_file_is_refused(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as fh:
            fh.write(b"x" * 1024)
            path = fh.name
        try:
            original = D.MAX_FILE_BYTES
            D.MAX_FILE_BYTES = 100
            with self.assertRaises(D.DocumentTooLarge):
                D.extract(path)
        finally:
            D.MAX_FILE_BYTES = original
            os.unlink(path)

    def test_zip_bomb_member_is_refused(self):
        """A 1 GB member compresses to nothing; we must not unpack it."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("word/document.xml", b"\0" * (1024 * 1024))
        original = D.MAX_MEMBER_BYTES
        D.MAX_MEMBER_BYTES = 1024
        try:
            with self.assertRaises(D.DocumentTooLarge):
                D.extract_bytes(buf.getvalue(), ".docx")
        finally:
            D.MAX_MEMBER_BYTES = original

    def test_pdf_without_the_library_says_so_plainly(self):
        try:
            import pypdf  # noqa: F401
            self.skipTest("pypdf is installed, so the fallback cannot fire")
        except ImportError:
            pass
        with self.assertRaises(D.UnsupportedDocument) as cm:
            D.extract_bytes(b"%PDF-1.4", ".pdf")
        self.assertIn("pip install pypdf", str(cm.exception))


class HostileDocumentTests(unittest.TestCase):
    """Documents arrive from other people. These are the attacks that matter."""

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def _docx(self, document_xml):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("word/document.xml", document_xml)
        return buf.getvalue()

    def test_billion_laughs_is_refused(self):
        """Nested entities expand to gigabytes and exhaust memory."""
        bomb = ('<?xml version="1.0"?><!DOCTYPE lolz ['
                '<!ENTITY lol "lol">'
                '<!ENTITY lol1 "%s">'
                ']><w:document xmlns:w="%s"><w:body><w:p><w:r><w:t>&lol1;'
                '</w:t></w:r></w:p></w:body></w:document>'
                % ("&lol;" * 10, self.W))
        with self.assertRaises(D.UnsupportedDocument):
            D.extract_bytes(self._docx(bomb), ".docx")

    def test_external_entity_cannot_read_local_files(self):
        xxe = ('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY xxe SYSTEM '
               '"file:///etc/passwd">]><w:document xmlns:w="%s"><w:body><w:p>'
               '<w:r><w:t>&xxe;</w:t></w:r></w:p></w:body></w:document>'
               % self.W)
        with self.assertRaises(D.UnsupportedDocument):
            D.extract_bytes(self._docx(xxe), ".docx")

    def test_any_doctype_is_refused(self):
        """Real documents have none; it is only ever there to attack a parser."""
        doc = ('<?xml version="1.0"?><!DOCTYPE anything>'
               '<w:document xmlns:w="%s"><w:body><w:p><w:r><w:t>hi</w:t>'
               '</w:r></w:p></w:body></w:document>' % self.W)
        with self.assertRaises(D.UnsupportedDocument) as cm:
            D.extract_bytes(self._docx(doc), ".docx")
        self.assertIn("document type declaration", str(cm.exception))

    def test_deep_nesting_does_not_blow_the_stack(self):
        """A recursive walk raised RecursionError and took the app with it."""
        depth = 20000
        doc = ("<w:document xmlns:w='%s'><w:body>" % self.W
               + "<w:p>" * depth + "<w:r><w:t>x</w:t></w:r>"
               + "</w:p>" * depth + "</w:body></w:document>")
        with self.assertRaises(D.UnsupportedDocument) as cm:
            D.extract_bytes(self._docx(doc), ".docx")
        self.assertIn("levels deep", str(cm.exception))

    def test_ordinary_nesting_still_works(self):
        """The depth cap must not reject real documents."""
        doc = ("<w:document xmlns:w='%s'><w:body><w:tbl><w:tr><w:tc>"
               "<w:p><w:r><w:t>in a table</w:t></w:r></w:p>"
               "</w:tc></w:tr></w:tbl></w:body></w:document>" % self.W)
        self.assertEqual(D.extract_bytes(self._docx(doc), ".docx"), "in a table")

    def test_runs_come_out_in_document_order(self):
        """An iterative walk is easy to get subtly wrong."""
        doc = ("<w:document xmlns:w='%s'><w:body><w:p>"
               "<w:r><w:t>A</w:t></w:r><w:t>B</w:t><w:r><w:t>C</w:t></w:r>"
               "</w:p></w:body></w:document>" % self.W)
        self.assertEqual(D.extract_bytes(self._docx(doc), ".docx"), "ABC")

    def test_archive_members_outside_the_document_are_ignored(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../../../etc/passwd", "pwned")
            zf.writestr("word/document.xml",
                        "<w:document xmlns:w='%s'><w:body><w:p><w:r><w:t>safe"
                        "</w:t></w:r></w:p></w:body></w:document>" % self.W)
        self.assertEqual(D.extract_bytes(buf.getvalue(), ".docx"), "safe")

    def test_odt_doctype_is_refused_too(self):
        content = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "boom">]>'
                   "<office:document-content "
                   "xmlns:office='urn:oasis:names:tc:opendocument:xmlns:office:1.0' "
                   "xmlns:text='urn:oasis:names:tc:opendocument:xmlns:text:1.0'>"
                   "<office:body><office:text><text:p>&e;</text:p>"
                   "</office:text></office:body></office:document-content>")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("content.xml", content)
        with self.assertRaises(D.UnsupportedDocument):
            D.extract_bytes(buf.getvalue(), ".odt")

    def test_pathological_rtf_finishes_quickly(self):
        import time
        payload = b"{\\rtf1" + b"\\b0" * 100000 + b"}"
        start = time.time()
        D.extract_bytes(payload, ".rtf")
        self.assertLess(time.time() - start, 5.0, "RTF parsing is superlinear")

    def test_pathological_html_finishes_quickly(self):
        import time
        payload = b"<div>" * 20000 + b"x" + b"</div>" * 20000
        start = time.time()
        D.extract_bytes(payload, ".html")
        self.assertLess(time.time() - start, 5.0, "HTML parsing is superlinear")


class RoundTripTests(unittest.TestCase):
    def test_extract_reads_from_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sample.docx")
            with open(path, "wb") as fh:
                fh.write(make_docx(["From disk."]))
            self.assertEqual(D.extract(path), "From disk.")

    def test_every_supported_extension_has_a_path(self):
        for ext in D.SUPPORTED:
            self.assertTrue(ext in D._READERS or ext in D.PLAIN_EXTENSIONS,
                            "%s claims support but has no reader" % ext)


if __name__ == "__main__":
    unittest.main(verbosity=2)
