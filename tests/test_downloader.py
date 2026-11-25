import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
from pypdf import PdfReader

from downloader import YouTubeDownloaderApp
from pages_pdf import create_pages_pdf


class SourceLinksTest(unittest.TestCase):
    def test_scribd_accepts_document_links(self):
        valid = YouTubeDownloaderApp._is_scribd_url
        self.assertTrue(valid("https://de.scribd.com/document/123456/Example"))
        self.assertTrue(valid("https://www.scribd.com/doc/123456"))
        self.assertFalse(valid("https://scribd.com.example.org/document/123456"))
        self.assertFalse(valid("https://scribd.com@elsewhere.example/document/123456"))
        self.assertFalse(valid("https://www.scribd.com/"))

    def test_platform_links(self):
        self.assertTrue(YouTubeDownloaderApp._is_youtube_url("https://youtu.be/example"))
        self.assertTrue(YouTubeDownloaderApp._is_telegram_url("https://t.me/channel/123"))
        self.assertFalse(YouTubeDownloaderApp._is_telegram_url("https://t.me/channel"))

    def test_default_video_format_without_ffmpeg_is_combined(self):
        choice = YouTubeDownloaderApp._default_video_choice(False)
        self.assertFalse(choice["requires_ffmpeg"])
        self.assertEqual(choice["format"], "best")


class PagesPdfTest(unittest.TestCase):
    def test_archive_pages_are_sorted_numerically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "chapter.cbz"
            output = root / "chapter.pdf"
            with ZipFile(archive_path, "w") as archive:
                for number, width in ((10, 60), (2, 30), (1, 15)):
                    image = root / f"{number}.png"
                    with Image.new("RGB", (width, 100), "white") as page:
                        page.save(image)
                    archive.write(image, f"chapter/{image.name}")
                archive.writestr("readme.txt", "Not an image")

            self.assertEqual(create_pages_pdf(str(archive_path), output, lambda *_: None), 3)
            with output.open("rb") as source:
                widths = [float(page.mediabox.width) for page in PdfReader(source).pages]
                self.assertEqual(widths, sorted(widths))
                self.assertEqual(len(set(widths)), 3)

    def test_invalid_image_does_not_leave_a_partial_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "page.png"
            image.write_bytes(b"not an image")
            output = root / "chapter.pdf"
            with self.assertRaisesRegex(ValueError, "Page 1"):
                create_pages_pdf(str(image), output, lambda *_: None)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob("*.part")), [])
