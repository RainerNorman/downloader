import io
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from contextlib import ExitStack
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, urlopen

from PIL import Image, ImageOps
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
MAX_DOWNLOAD = 512 * 1024 * 1024
MAX_IMAGE = 32 * 1024 * 1024
MAX_PAGES = 1500
MAX_HTML = 2 * 1024 * 1024
JPEG_EXTENSIONS = {".jpg", ".jpeg"}


class _PublishedPdfLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        media_type = (fields.get("type") or "").split(";", 1)[0].strip().lower()
        if media_type != "application/pdf":
            return
        alternate = tag == "link" and "alternate" in (fields.get("rel") or "").lower().split()
        downloadable = tag == "a" and "download" in fields
        if (alternate or downloadable) and (href := fields.get("href")):
            self.links.append(href)


def source_name(source: str) -> str:
    if source.startswith(("https://", "http://")):
        path = unquote(urlsplit(source.split()[0]).path)
        return PurePosixPath(path).stem or "Online pages"
    return Path(source).stem or "Local pages"


def create_pages_pdf(
    source: str, destination: Path, report: Callable[[str, int], None]
) -> int | None:
    with tempfile.TemporaryDirectory(prefix="pages_pdf_") as work_dir, ExitStack() as stack:
        if source.startswith(("https://", "http://")):
            links = source.split()
            if len(links) > MAX_PAGES:
                raise ValueError(f"Use up to {MAX_PAGES} page links per PDF.")
            inputs = []
            remaining = MAX_DOWNLOAD
            for index, link in enumerate(links, start=1):
                limit = remaining if len(links) == 1 else min(remaining, MAX_IMAGE)
                path = Path(work_dir) / str(index)
                _download(link, path, index, len(links), limit, report, allow_document_page=len(links) == 1)
                remaining -= path.stat().st_size
                inputs.append(path)
        else:
            inputs = [Path(source).expanduser()]

        if len(inputs) == 1 and inputs[0].is_file():
            with inputs[0].open("rb") as file:
                is_pdf = file.read(5) == b"%PDF-"
            if is_pdf:
                report("Checking the PDF...", 80)
                return _save_published_pdf(inputs[0], destination)

        archive = None
        if len(inputs) == 1 and zipfile.is_zipfile(inputs[0]):
            archive = stack.enter_context(zipfile.ZipFile(inputs[0]))
            pages = sorted(
                (entry for entry in archive.infolist() if not entry.is_dir() and _is_page(entry.filename)),
                key=lambda entry: _natural_order(entry.filename),
            )
        elif len(inputs) == 1 and inputs[0].is_dir():
            directory = inputs[0]
            pages = sorted(
                (path for path in directory.rglob("*")
                 if path.is_file() and _is_page(path.relative_to(directory).as_posix())),
                key=lambda path: _natural_order(path.relative_to(directory).as_posix()),
            )
        else:
            pages = inputs

        if not pages:
            raise ValueError("No page images were found in this folder or archive.")
        if len(pages) > MAX_PAGES:
            raise ValueError(f"Use up to {MAX_PAGES} images per PDF.")

        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as file:
            temporary_pdf = Path(file.name)
        try:
            title = destination.stem
            if not _write_jpeg_pdf(pages, archive, temporary_pdf, title, report):
                pdf = Canvas(str(temporary_pdf), pageCompression=1)
                pdf.setTitle(title)
                for index, page in enumerate(pages, start=1):
                    report(f"Building PDF page {index} of {len(pages)}...", 35 + 64 * index // len(pages))
                    try:
                        _add_page(pdf, _read_page(page, archive))
                    except (OSError, RuntimeError, ValueError) as exc:
                        name = page.filename if archive else page.name
                        raise ValueError(f"Page {index} ({name}): {exc}") from exc
                pdf.save()
            temporary_pdf.rename(destination)
        finally:
            temporary_pdf.unlink(missing_ok=True)
        return len(pages)


def _read_page(page: Path | zipfile.ZipInfo, archive: zipfile.ZipFile | None) -> bytes:
    with (archive.open(page) if archive else page.open("rb")) as image_file:
        data = image_file.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise ValueError("Image exceeds the 32 MB page limit.")
    return data


def _native_pdf_helper() -> Path | None:
    root = Path(__file__).resolve().parent
    executable = "jpeg-pages-pdf.exe" if os.name == "nt" else "jpeg-pages-pdf"
    for candidate in (root / executable, root / "native" / "target" / "release" / executable):
        if candidate.is_file():
            return candidate
    return None


def _write_jpeg_pdf(
    pages: list[Path | zipfile.ZipInfo], archive: zipfile.ZipFile | None, path: Path, title: str,
    report: Callable[[str, int], None],
) -> bool:
    helper = _native_pdf_helper()
    if helper is None:
        return False
    suffixes = {PurePosixPath(page.filename if archive else page.name).suffix.lower() for page in pages}
    if suffixes - JPEG_EXTENSIONS - {""}:
        return False

    try:
        with subprocess.Popen(
            [str(helper), str(path), title, str(len(pages))],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) as process:
            try:
                assert process.stdin is not None
                for index, page in enumerate(pages, start=1):
                    data = _read_page(page, archive)
                    with Image.open(io.BytesIO(data)) as image:
                        if (
                            image.format != "JPEG"
                            or image.mode not in ("L", "RGB")
                            or image.getexif().get(274, 1) != 1
                            or image.width * image.height > 25_000_000
                        ):
                            return False
                        image.load()
                        header = struct.pack("<4I", image.width, image.height, len(image.getbands()), len(data))
                    process.stdin.write(header)
                    process.stdin.write(data)
                    report(f"Writing PDF page {index} of {len(pages)}...", 35 + 64 * index // len(pages))
                process.stdin.close()
                return process.wait(timeout=15) == 0
            finally:
                if process.poll() is None:
                    process.kill()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, Image.DecompressionBombError, subprocess.TimeoutExpired):
        return False


def _download(
    url: str, path: Path, index: int, count: int, limit: int,
    report: Callable[[str, int], None], *, allow_document_page: bool,
) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter an HTTP or HTTPS link to a PDF, page image, or archive.")
    report(f"Downloading input {index} of {count}...", 34 * (index - 1) // count)
    request = Request(url, headers={"User-Agent": "MediaDownloader/1.0"})
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        if content_type in ("text/html", "application/xhtml+xml"):
            if not allow_document_page:
                raise ValueError("Expected a file. The link returned a webpage instead.")
            markup = response.read(MAX_HTML + 1)
            if len(markup) > MAX_HTML:
                raise ValueError("This page is too large to inspect. Use its direct PDF link.")
            encoding = response.headers.get_content_charset() or "utf-8"
            pdf_url = _published_pdf_url(response.geturl(), markup.decode(encoding, errors="replace"))
        else:
            total = int(response.headers.get("Content-Length") or 0)
            if total > limit:
                raise ValueError(f"Input exceeds the {limit // (1024 * 1024)} MB download limit.")
            with path.open("wb") as output:
                received = 0
                last_progress = -1
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > limit:
                        raise ValueError(f"Input exceeds the {limit // (1024 * 1024)} MB download limit.")
                    output.write(chunk)
                    if total:
                        progress = min(34, int(34 * (index - 1 + received / total) / count))
                        if progress != last_progress:
                            report(f"Downloading input {index} of {count}...", progress)
                            last_progress = progress
                if total and received != total:
                    raise ValueError("The server closed the download before it was complete.")
            return

    _download(pdf_url, path, index, count, limit, report, allow_document_page=False)
    with path.open("rb") as downloaded:
        if downloaded.read(5) != b"%PDF-":
            raise ValueError("The published PDF link did not return a PDF file.")


def _published_pdf_url(page_url: str, markup: str) -> str:
    parser = _PublishedPdfLinks()
    parser.feed(markup)
    page = urlsplit(page_url)
    candidates = set()
    for href in parser.links:
        try:
            target = urlsplit(urljoin(page_url, href))
        except ValueError:
            continue
        if (target.scheme, target.netloc.lower()) == (page.scheme, page.netloc.lower()):
            candidates.add(target._replace(fragment="").geturl())
    if not candidates:
        raise ValueError("This webpage does not publish a direct PDF link. Enter a file link instead.")
    if len(candidates) > 1:
        raise ValueError("This webpage publishes several PDFs. Enter the specific file link.")
    return candidates.pop()


def _save_published_pdf(source: Path, destination: Path) -> int | None:
    with source.open("rb") as input_file:
        try:
            reader = PdfReader(input_file, strict=True)
            page_count = None if reader.is_encrypted else len(reader.pages)
        except PdfReadError as exc:
            raise ValueError("The downloaded PDF is incomplete or invalid.") from exc
        if page_count == 0:
            raise ValueError("The PDF does not contain any pages.")

        input_file.seek(0)
        temporary_pdf = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as output:
                temporary_pdf = Path(output.name)
                shutil.copyfileobj(input_file, output, length=1024 * 1024)
            temporary_pdf.rename(destination)
        finally:
            if temporary_pdf is not None:
                temporary_pdf.unlink(missing_ok=True)
    return page_count


def _is_page(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        path.suffix.lower() in IMAGE_EXTENSIONS
        and not any(part.startswith(".") or part == "__MACOSX" for part in path.parts)
    )


def _natural_order(name: str) -> tuple:
    normalized = name.casefold()
    parts = tuple(int(part) if index % 2 else part
                  for index, part in enumerate(re.split(r"([0-9]+)", normalized)))
    return parts, normalized, name


def _add_page(pdf: Canvas, data: bytes) -> None:
    with Image.open(io.BytesIO(data)) as original:
        if original.width * original.height > 25_000_000:
            raise ValueError("Image exceeds the 25 megapixel page limit.")
        original.load()
        if original.format == "JPEG" and original.mode in ("L", "RGB") and original.getexif().get(274, 1) == 1:
            image = ImageReader(io.BytesIO(data))
        else:
            source = ImageOps.exif_transpose(original)
            if "A" in source.getbands() or "transparency" in source.info:
                rgba = source.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                source = background
            elif source.mode not in ("L", "RGB"):
                source = source.convert("RGB")
            image = ImageReader(source)
        width, height = image.getSize()
        scale = 842 / max(width, height)
        width, height = width * scale, height * scale
        pdf.setPageSize((width, height))
        pdf.drawImage(image, 0, 0, width, height)
        pdf.showPage()
