import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image
from pypdf import PdfReader

from downloader import YouTubeDownloaderApp
from pages_pdf import _native_pdf_helper, create_pages_pdf


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

    @unittest.skipUnless(_native_pdf_helper(), "Rust helper has not been built")
    def test_native_export_preserves_jpeg_bytes_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "book.cbz"
            output = root / "Seiten-\u00fc.pdf"
            expected = []
            with ZipFile(archive_path, "w") as archive:
                for number, size, mode in ((2, (80, 40), "RGB"), (1, (40, 80), "L")):
                    path = root / f"{number}.jpg"
                    with Image.new(mode, size) as image:
                        image.save(path)
                    expected.insert(0, path.read_bytes())
                    archive.write(path, path.name)

            with patch("pages_pdf.Canvas", side_effect=AssertionError("Expected Rust writer")):
                self.assertEqual(create_pages_pdf(str(archive_path), output, lambda *_: None), 2)
            with output.open("rb") as file:
                reader = PdfReader(file, strict=True)
                self.assertEqual(reader.metadata.title, output.stem)
                self.assertEqual([float(page.mediabox.width) for page in reader.pages], [421, 842])
                self.assertEqual(
                    [page.images[0].data for page in reader.pages],
                    expected,
                )

    @unittest.skipUnless(_native_pdf_helper(), "Rust helper has not been built")
    def test_rotated_jpeg_uses_normal_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "rotated.jpg"
            with Image.new("RGB", (40, 80)) as image:
                exif = image.getexif()
                exif[274] = 6
                image.save(path, exif=exif)
            output = root / "rotated.pdf"
            self.assertEqual(create_pages_pdf(str(path), output, lambda *_: None), 1)
            with output.open("rb") as file:
                self.assertEqual(float(PdfReader(file).pages[0].mediabox.width), 842)
