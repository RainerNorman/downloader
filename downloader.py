import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import yt_dlp

from downloader_theme import BORDER, ProgressTrack, configure_theme, make_icons

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None


YOUTUBE_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
)
SOURCES = {
    "youtube": (
        "YouTube", "Download video or MP3 audio from a YouTube link.", "Video link",
        "", "Download",
    ),
    "telegram": (
        "Telegram", "Save pictures from a public Telegram post.", "Post link",
        "Example: https://t.me/channel/123", "Download pictures",
    ),
    "sketchfab": (
        "Sketchfab", "Use your API token to download models enabled by the creator.", "Model link",
        "", "Download model",
    ),
    "adfocus": (
        "AdFoc.us", "Resolve an AdFoc.us link and save the destination file.", "AdFoc.us link",
        "Supports direct files and MediaFire downloads.", "Download file",
    ),
    "scribd": (
        "Scribd", "Open a document in your browser to use Scribd's official download.", "Document link",
        "Scribd controls availability and saves through your browser.", "Open in browser",
    ),
    "pages_pdf": (
        "Pages to PDF", "Turn page images into a single PDF.", "File, folder, or link",
        "Supports PDF links, images, and CBZ or ZIP archives.", "Create PDF",
    ),
}
UNSET = object()
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class YouTubeDownloaderApp:
    MIN_WIDTH = 820
    MIN_HEIGHT = 560

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Downloader")
        self.root.geometry("1016x608")
        self.root.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        configure_theme(root)
        self.icons = make_icons(root)
        root.iconphoto(True, self.icons["brand"])

        self.source_var = tk.StringVar(value="youtube")
        self.url_var = tk.StringVar()
        self.sketchfab_token_var = tk.StringVar()
        app_path = sys.executable if getattr(sys, "frozen", False) else __file__
        default_folder = Path(app_path).resolve().with_name("downloads")
        self.folder_var = tk.StringVar(value=str(default_folder))
        self.mode_var = tk.StringVar(value="video")
        self.quality_var = tk.StringVar(value="Best available")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text = tk.StringVar()
        self.download_thread = None
        self.is_downloading = False
        self.is_loading_formats = False
        self.loaded_url = ""
        self.video_choices: list[dict] = []
        self.audio_choices: list[dict] = []
        self.ffmpeg_path_cache: str | None | object = UNSET

        self._build_ui()
        self.source_var.trace_add("write", self._on_source_changed)
        self.mode_var.trace_add("write", self._on_mode_changed)
        self.url_var.trace_add("write", self._on_url_changed)
        self.progress_var.trace_add("write", self._update_progress_text)
        self.status_var.trace_add("write", self._update_progress_text)
        self._on_source_changed()

    def _build_ui(self) -> None:
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        rail = ttk.Frame(self.root, padding=(14, 26, 14, 18), style="Rail.TFrame")
        rail.grid(row=0, column=0, sticky="ns")
        brand = ttk.Label(
            rail, text="Downloader", image=self.icons["brand"], compound="left",
            style="Brand.TLabel",
        )
        brand.pack(anchor="w", padx=(7, 14), pady=(0, 33))
        ttk.Label(rail, text="SOURCES", style="RailTitle.TLabel").pack(
            anchor="w", padx=13, pady=(0, 8)
        )
        for source, (name, *_details) in SOURCES.items():
            ttk.Radiobutton(
                rail, text=name, image=self.icons[source], compound="left",
                style="Source.TRadiobutton", value=source, variable=self.source_var,
            ).pack(fill="x", pady=(0, 4))

        workspace = ttk.Frame(self.root, padding=(32, 30, 32, 22), style="Workspace.TFrame")
        workspace.grid(row=0, column=1, sticky="nsew")
        workspace.columnconfigure(0, weight=1)

        heading = ttk.Frame(workspace, style="Workspace.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 22))
        self.source_title = ttk.Label(heading, style="Heading.TLabel")
        self.source_title.pack(anchor="w")
        self.source_intro = ttk.Label(heading, style="Intro.TLabel", justify="left")
        self.source_intro.pack(fill="x", pady=(4, 0))
        heading.bind("<Configure>", lambda event: self.source_intro.configure(wraplength=event.width))

        form = ttk.Frame(workspace, padding=(24, 22, 24, 22), style="Card.TFrame")
        form.grid(row=1, column=0, sticky="new")
        form.columnconfigure(0, weight=1)

        self.url_label = ttk.Label(form, style="FieldLabel.TLabel")
        self.url_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.url_entry = ttk.Entry(form, textvariable=self.url_var)
        self.url_entry.grid(row=1, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda _: self.download_button.invoke())

        self.load_button = ttk.Button(form, text="Load qualities", command=self.load_qualities)
        self.load_button.grid(row=1, column=1, sticky="ne", padx=(8, 0))
        self.pages_input_buttons = ttk.Frame(form)
        self.pages_input_buttons.grid(row=1, column=1, sticky="ne", padx=(9, 0))
        ttk.Button(self.pages_input_buttons, text="File…", command=self._choose_pages_file).pack(side="left")
        ttk.Button(self.pages_input_buttons, text="Folder…", command=self._choose_pages_folder).pack(
            side="left", padx=(5, 0)
        )
        self.link_help_label = ttk.Label(form, style="Help.TLabel", justify="left")
        self.link_help_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(7, 0))
        form.bind("<Configure>", lambda event: self.link_help_label.configure(wraplength=max(1, event.width - 48)))

        self.token_frame = ttk.Frame(form)
        self.token_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        self.token_frame.columnconfigure(0, weight=1)
        ttk.Label(self.token_frame, text="Sketchfab API token", style="FieldLabel.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        ttk.Entry(self.token_frame, textvariable=self.sketchfab_token_var, show="•").grid(
            row=1, column=0, sticky="ew"
        )
        ttk.Button(
            self.token_frame, text="Get token",
            command=lambda: webbrowser.open("https://sketchfab.com/settings/password"),
        ).grid(row=1, column=1, padx=(9, 0))

        self.options_frame = ttk.Frame(form)
        self.options_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        self.options_frame.columnconfigure(1, weight=1)
        self.mode_group = ttk.Frame(self.options_frame)
        self.mode_group.grid(row=0, column=0, sticky="nw", padx=(0, 22))
        ttk.Label(self.mode_group, text="Media type", style="FieldLabel.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        ttk.Radiobutton(
            self.mode_group, text="Video", value="video", variable=self.mode_var,
            style="Choice.TRadiobutton",
        ).grid(row=1, column=0, sticky="w", padx=(0, 5))
        ttk.Radiobutton(
            self.mode_group, text="MP3 audio", value="audio", variable=self.mode_var,
            style="Choice.TRadiobutton",
        ).grid(row=1, column=1, sticky="w")

        self.quality_group = ttk.Frame(self.options_frame)
        self.quality_group.grid(row=0, column=1, sticky="ew")
        self.quality_group.columnconfigure(0, weight=1)
        self.quality_label = ttk.Label(self.quality_group, style="FieldLabel.TLabel")
        self.quality_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.quality_combo = ttk.Combobox(
            self.quality_group, textvariable=self.quality_var, state="readonly", width=12,
        )
        self.quality_combo.grid(row=1, column=0, sticky="ew")

        self.folder_frame = ttk.Frame(form)
        self.folder_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        self.folder_frame.columnconfigure(0, weight=1)
        ttk.Label(self.folder_frame, text="Save folder", style="FieldLabel.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        ttk.Entry(self.folder_frame, textvariable=self.folder_var).grid(row=1, column=0, sticky="ew")
        ttk.Button(self.folder_frame, text="Browse…", command=self.choose_folder).grid(
            row=1, column=1, sticky="ne", padx=(8, 0)
        )

        tk.Frame(form, height=1, background=BORDER).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(21, 16)
        )
        self.download_button = ttk.Button(
            form, image=self.icons["download"], compound="left", style="Primary.TButton",
            command=self.start_download,
        )
        self.download_button.grid(row=7, column=0, columnspan=2, sticky="w")

        status = ttk.Frame(workspace, style="Workspace.TFrame", padding=(1, 0))
        status.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        status.columnconfigure(0, weight=1)
        status_line = ttk.Label(status, textvariable=self.status_var, style="Status.TLabel", justify="left")
        status_line.grid(row=0, column=0, sticky="ew")
        status.bind("<Configure>", lambda event: status_line.configure(wraplength=max(120, event.width - 42)))
        ttk.Label(status, textvariable=self.progress_text, style="Percent.TLabel", anchor="e").grid(
            row=0, column=1, sticky="ne", padx=(7, 0)
        )
        self.progress_bar = ProgressTrack(status, self.progress_var)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.source_controls = {
            self.load_button: ("youtube",),
            self.pages_input_buttons: ("pages_pdf",),
            self.token_frame: ("sketchfab",),
            self.options_frame: ("youtube", "sketchfab"),
            self.mode_group: ("youtube",),
            self.quality_combo: ("youtube", "sketchfab"),
            self.folder_frame: tuple(source for source in SOURCES if source != "scribd"),
        }

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.cwd()))
        if folder:
            self.folder_var.set(folder)

    def load_qualities(self) -> None:
        if self.is_loading_formats or self.is_downloading:
            return

        url = self.url_var.get().strip()
        if not self._is_youtube_url(url):
            messagebox.showerror("Invalid link", "Please enter a valid YouTube link.")
            return

        if not self._yt_dlp_module_available():
            messagebox.showerror(
                "yt-dlp not found",
                "This app needs yt-dlp installed.\n\n"
                "Install it with:\n"
                "py -m pip install yt-dlp",
            )
            return

        self.is_loading_formats = True
        self.load_button.config(state="disabled")
        self.status_var.set("Loading available qualities...")

        threading.Thread(
            target=self._load_qualities_worker,
            args=(url,),
            daemon=True,
        ).start()

    def start_download(self) -> None:
        if self.is_downloading:
            return

        url = self.url_var.get().strip()
        if self.source_var.get() == "scribd":
            self._open_scribd_document(url)
            return

        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showerror("Missing folder", "Please choose a folder to save into.")
            return

        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not open save folder", str(exc))
            return

        if self.source_var.get() == "pages_pdf":
            if not url:
                messagebox.showerror("Missing pages", "Enter a document or page link, or choose a local file or folder.")
                return
            self.download_button.config(state="disabled")
            self.is_downloading = True
            self.progress_var.set(0)
            self.status_var.set("Preparing page images...")
            self.download_thread = threading.Thread(
                target=self._build_pages_pdf, args=(url.strip('"'), folder), daemon=True
            )
            self.download_thread.start()
            return

        if self.source_var.get() == "telegram":
            if not self._is_telegram_url(url):
                messagebox.showerror(
                    "Invalid link",
                    "Enter a public Telegram post link like:\nhttps://t.me/channel/123",
                )
                return
            self.download_button.config(state="disabled")
            self.is_downloading = True
            self.progress_var.set(0)
            self.status_var.set("Finding Telegram pictures...")
            self.download_thread = threading.Thread(
                target=self._download_telegram_pictures,
                args=(url, folder),
                daemon=True,
            )
            self.download_thread.start()
            return

        if self.source_var.get() == "sketchfab":
            if not self._is_sketchfab_url(url):
                messagebox.showerror(
                    "Invalid link",
                    "Enter a Sketchfab model link from sketchfab.com/3d-models/.",
                )
                return
            token = self.sketchfab_token_var.get().strip()
            if not token:
                messagebox.showerror(
                    "Token required",
                    "Sketchfab requires your account API token for model downloads.",
                )
                return
            self.download_button.config(state="disabled")
            self.is_downloading = True
            self.progress_var.set(0)
            self.status_var.set("Checking the Sketchfab model...")
            self.download_thread = threading.Thread(
                target=self._download_sketchfab_model,
                args=(url, folder, token, self.quality_var.get()),
                daemon=True,
            )
            self.download_thread.start()
            return

        if self.source_var.get() == "adfocus":
            if not self._is_adfocus_url(url):
                messagebox.showerror(
                    "Invalid link",
                    "Enter an AdFoc.us link like:\nhttps://adfoc.us/59811977746397",
                )
                return
            self.download_button.config(state="disabled")
            self.is_downloading = True
            self.progress_var.set(0)
            self.status_var.set("Resolving the AdFoc.us link...")
            self.download_thread = threading.Thread(
                target=self._download_adfocus_file,
                args=(url, folder),
                daemon=True,
            )
            self.download_thread.start()
            return

        if not self._is_youtube_url(url):
            messagebox.showerror("Invalid link", "Please enter a valid YouTube link.")
            return

        if not self._yt_dlp_module_available():
            messagebox.showerror(
                "yt-dlp not found",
                "This app needs yt-dlp installed.\n\n"
                "Install it with:\n"
                "py -m pip install yt-dlp",
            )
            return

        mode = self.mode_var.get()
        ffmpeg_path = self._resolve_ffmpeg_path()
        ffmpeg_available = ffmpeg_path is not None

        if mode == "audio" and not ffmpeg_available:
            messagebox.showerror(
                "ffmpeg not found",
                "Install FFmpeg and add it to PATH to convert audio to MP3.",
            )
            return

        selected_choice = self._get_selected_choice(mode, ffmpeg_available)
        if selected_choice.get("requires_ffmpeg") and not ffmpeg_available:
            messagebox.showerror(
                "ffmpeg not found",
                "That quality needs FFmpeg to merge separate streams. Install FFmpeg "
                "and add it to PATH, or choose a single-file quality.",
            )
            return

        self.download_button.config(state="disabled")
        self.load_button.config(state="disabled")
        self.is_downloading = True
        self.progress_var.set(0)
        self.status_var.set("Starting download...")

        self.download_thread = threading.Thread(
            target=self._download_video,
            args=(url, folder, selected_choice, ffmpeg_path),
            daemon=True,
        )
        self.download_thread.start()

    def _choose_pages_file(self) -> None:
        source = filedialog.askopenfilename(
            title="Choose a PDF, comic archive, or page image",
            filetypes=[("PDFs, archives and images", "*.pdf *.cbz *.zip *.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff")],
        )
        if source:
            self.url_var.set(source)

    def _choose_pages_folder(self) -> None:
        source = filedialog.askdirectory(title="Choose a folder of page images")
        if source:
            self.url_var.set(source)

    def _build_pages_pdf(self, source: str, folder: str) -> None:
        def report(message: str, progress: int) -> None:
            self.root.after(0, self.status_var.set, message)
            self.root.after(0, self.progress_var.set, progress)

        try:
            if self._is_scribd_url(source):
                raise ValueError(
                    "Use the Scribd source for this link, or enter a public PDF, "
                    "image, or CBZ/ZIP link here."
                )
            from pages_pdf import create_pages_pdf, source_name

            filename = self._safe_filename(source_name(source))
            destination = self._unused_path(Path(folder) / f"{filename} - pages.pdf")
            count = create_pages_pdf(source, destination, report)
        except Exception as exc:
            self._finish_download(False, f"Could not create PDF: {exc}")
            return

        page_summary = f" ({count} {'page' if count == 1 else 'pages'})" if count is not None else ""
        self._finish_download(True, f"Saved {destination.name}{page_summary}.")

    def _open_scribd_document(self, url: str) -> None:
        if not self._is_scribd_url(url):
            messagebox.showerror("Invalid link", "Enter an HTTPS Scribd document link.")
            return
        try:
            opened = webbrowser.open(url, new=2)
        except (OSError, webbrowser.Error):
            opened = False
        if not opened:
            messagebox.showerror("Could not open Scribd", "Open the link in your default browser.")
            return
        self.status_var.set("Use Scribd's Download button if it is available for this document.")

    def _download_sketchfab_model(
        self, url: str, folder: str, token: str, format_label: str
    ) -> None:
        try:
            model_uid = self._sketchfab_model_uid(url)
            model_url = f"https://api.sketchfab.com/v3/models/{model_uid}"
            model = self._read_json(model_url)
            if not model.get("isDownloadable"):
                raise ValueError(
                    "The creator has not enabled downloads for this Sketchfab model."
                )

            authorization = token if token.lower().startswith(("token ", "bearer ")) else f"Token {token}"
            download_info = self._read_json(
                f"{model_url}/download",
                headers={"Authorization": authorization},
            )
            format_key = "usdz" if format_label.startswith("USDZ") else "gltf"
            archive = download_info.get(format_key)
            if not isinstance(archive, dict) or not archive.get("url"):
                raise ValueError(f"This model is not available as {format_label}.")

            model_name = self._safe_filename(model.get("name") or f"sketchfab_{model_uid}")
            extension = ".usdz" if format_key == "usdz" else ".zip"
            destination = self._unused_path(Path(folder) / f"{model_name}{extension}")
            self.root.after(0, self.status_var.set, f"Downloading {model_name}{extension}...")
            self._stream_download(archive["url"], destination)
            self._write_sketchfab_attribution(destination, model, url)
        except HTTPError as exc:
            message = self._http_error_message(exc)
            self._finish_download(False, message)
            return
        except URLError as exc:
            self._finish_download(False, f"Sketchfab could not be reached: {exc.reason}")
            return
        except Exception as exc:
            self._finish_download(False, str(exc))
            return

        self._finish_download(
            True,
            f"Downloaded {destination.name} with its attribution file.",
        )

    @staticmethod
    def _read_json(url: str, headers: dict | None = None) -> dict:
        request_headers = {
            "User-Agent": "Video-Picture-Downloader/1.0",
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)
        request = Request(url, headers=request_headers)
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _stream_download(self, url: str, destination: Path) -> None:
        request = Request(url, headers={"User-Agent": BROWSER_USER_AGENT})
        try:
            with urlopen(request, timeout=60) as response, destination.open("wb") as output:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        self.root.after(
                            0,
                            self.progress_var.set,
                            min(downloaded / total * 100, 100),
                        )
        except Exception:
            if destination.exists():
                destination.unlink()
            raise

    def _download_adfocus_file(self, url: str, folder: str) -> None:
        try:
            target_url = self._resolve_adfocus_target(url)
            target_host = urlparse(target_url).netloc
            self.root.after(
                0,
                self.status_var.set,
                f"AdFoc.us target found ({target_host}). Preparing download...",
            )
            download_url, filename = self._resolve_file_target(target_url)
            destination = self._unused_path(
                Path(folder) / self._safe_filename(filename or "adfocus_download")
            )
            self.root.after(0, self.status_var.set, f"Downloading {destination.name}...")
            self._stream_download(download_url, destination)
        except subprocess.TimeoutExpired:
            self._finish_download(
                False,
                "AdFoc.us took too long to resolve. Check your internet connection and try again.",
            )
            return
        except (HTTPError, URLError) as exc:
            self._finish_download(False, f"The download server could not be reached: {exc}")
            return
        except Exception as exc:
            self._finish_download(False, str(exc))
            return

        self._finish_download(True, f"Downloaded {destination.name} successfully.")

    @classmethod
    def _resolve_adfocus_target(cls, url: str) -> str:
        page_html = cls._fetch_adfocus_html(url)
        if not page_html:
            raise RuntimeError(
                "AdFoc.us did not return a target link. Please try again."
            )

        script_match = re.search(
            r"var\s+click_url\s*=\s*\"((?:\\.|[^\"\\])*)\"",
            page_html,
            flags=re.IGNORECASE,
        )
        if script_match:
            try:
                target_url = json.loads(f'"{script_match.group(1)}"')
            except json.JSONDecodeError:
                target_url = script_match.group(1).replace(r"\/", "/")
        else:
            anchor_match = re.search(
                r'<a[^>]+(?:class=["\'][^"\']*skip[^"\']*["\'][^>]+href|href)=["\']([^"\']+)["\']',
                page_html,
                flags=re.IGNORECASE,
            )
            target_url = anchor_match.group(1) if anchor_match else ""

        target_url = html.unescape(target_url).strip()
        parsed = urlparse(target_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise RuntimeError(
                "No downloadable target was found on this AdFoc.us page. The link may have expired."
            )
        if parsed.netloc.lower() in ("adfoc.us", "www.adfoc.us"):
            raise RuntimeError("AdFoc.us redirected back to itself instead of a download.")
        return target_url

    @classmethod
    def _fetch_adfocus_html(cls, url: str) -> str:
        if curl_requests is not None:
            try:
                response = curl_requests.get(url, impersonate="chrome", timeout=30)
                response.raise_for_status()
                if response.text:
                    return response.text
            except Exception:
                pass

        edge_path = cls._find_edge_executable()
        if edge_path is None:
            return ""

        profile_dir = Path(tempfile.mkdtemp(prefix="adfocus_edge_"))
        try:
            command = [
                str(edge_path),
                "--headless=new",
                "--disable-gpu",
                "--disable-extensions",
                "--no-first-run",
                f"--user-data-dir={profile_dir}",
                "--virtual-time-budget=12000",
                "--dump-dom",
                url,
            ]
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=45,
                creationflags=creation_flags,
                check=False,
            )
            return result.stdout.decode("utf-8", errors="replace")
        finally:
            # Edge helper processes can keep the profile lockfile open briefly on Windows.
            shutil.rmtree(profile_dir, ignore_errors=True)
            if profile_dir.exists():
                threading.Thread(
                    target=cls._remove_temp_dir_when_available,
                    args=(profile_dir,),
                    daemon=True,
                ).start()

    @staticmethod
    def _remove_temp_dir_when_available(path: Path) -> None:
        for _attempt in range(20):
            shutil.rmtree(path, ignore_errors=True)
            if not path.exists():
                return
            time.sleep(0.5)

    @staticmethod
    def _find_edge_executable() -> Path | None:
        candidates = []
        for base in (
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("PROGRAMFILES"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if not base:
                continue
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
            edge_core = Path(base) / "Microsoft" / "EdgeCore"
            if edge_core.is_dir():
                candidates.extend(edge_core.glob("*/msedge.exe"))

        existing = [path for path in candidates if path.is_file()]
        if not existing:
            edge_from_path = shutil.which("msedge")
            return Path(edge_from_path) if edge_from_path else None
        return max(existing, key=lambda path: path.stat().st_mtime)

    @classmethod
    def _resolve_file_target(cls, target_url: str) -> tuple[str, str]:
        parsed = urlparse(target_url)
        host = parsed.netloc.lower().split(":", 1)[0]
        if host in ("mediafire.com", "www.mediafire.com"):
            return cls._resolve_mediafire_target(target_url)

        request = Request(target_url, headers={"User-Agent": BROWSER_USER_AGENT})
        with urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type().lower()
            final_url = response.geturl()
            disposition = response.headers.get("Content-Disposition", "")
        if content_type in ("text/html", "application/xhtml+xml"):
            raise RuntimeError(
                f"The AdFoc.us target opens a webpage on {host}, not a direct file. "
                "This host is not supported yet."
            )
        filename = cls._filename_from_response(disposition, final_url)
        return final_url, filename

    @classmethod
    def _resolve_mediafire_target(cls, page_url: str) -> tuple[str, str]:
        request = Request(page_url, headers={"User-Agent": BROWSER_USER_AGENT})
        with urlopen(request, timeout=30) as response:
            page_html = response.read().decode("utf-8", errors="replace")
        normalized_html = html.unescape(page_html.replace(r"\/", "/"))
        match = re.search(
            r'https?://download[^\s"\'<>]+\.mediafire\.com/[^\s"\'<>]+',
            normalized_html,
            flags=re.IGNORECASE,
        )
        if not match:
            raise RuntimeError(
                "MediaFire did not provide a download link. The file may be private or removed."
            )
        download_url = match.group(0)
        filename = unquote(Path(urlparse(download_url).path).name)
        return download_url, filename or "mediafire_download"

    @staticmethod
    def _filename_from_response(content_disposition: str, url: str) -> str:
        utf8_match = re.search(
            r"filename\*\s*=\s*(?:UTF-8'')?([^;]+)",
            content_disposition,
            flags=re.IGNORECASE,
        )
        if utf8_match:
            return unquote(utf8_match.group(1).strip().strip('"'))
        name_match = re.search(
            r'filename\s*=\s*(?:"([^"]+)"|([^;]+))',
            content_disposition,
            flags=re.IGNORECASE,
        )
        if name_match:
            return (name_match.group(1) or name_match.group(2)).strip()
        return unquote(Path(urlparse(url).path).name) or "adfocus_download"

    @staticmethod
    def _write_sketchfab_attribution(destination: Path, model: dict, source_url: str) -> None:
        user = model.get("user") or {}
        license_info = model.get("license") or {}
        author = user.get("displayName") or user.get("username") or "Unknown creator"
        license_name = license_info.get("label") or license_info.get("slug") or "See model page"
        license_url = license_info.get("url") or ""
        lines = [
            f"Model: {model.get('name') or destination.stem}",
            f"Creator: {author}",
            f"Source: {source_url}",
            f"License: {license_name}",
        ]
        if license_url:
            lines.append(f"License URL: {license_url}")
        lines.append("Downloaded through the official Sketchfab Download API.")
        attribution_path = destination.with_name(f"{destination.stem}_ATTRIBUTION.txt")
        attribution_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _safe_filename(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
        return cleaned[:120] or "sketchfab_model"

    @staticmethod
    def _http_error_message(exc: HTTPError) -> str:
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="replace"))
            detail = payload.get("detail") or payload.get("error")
            if detail:
                return f"Sketchfab: {detail}"
        except Exception:
            pass
        if exc.code == 401:
            return "Sketchfab rejected the API token. Check the token and try again."
        if exc.code == 403:
            return "Sketchfab did not allow this model to be downloaded."
        if exc.code == 404:
            return "The Sketchfab model could not be found."
        return f"Sketchfab returned HTTP {exc.code}: {exc.reason}"

    def _download_telegram_pictures(self, url: str, folder: str) -> None:
        try:
            channel, post_id = self._telegram_post_parts(url)
            page_url = f"https://t.me/s/{channel}/{post_id}"
            page_html = self._read_url(page_url).decode("utf-8", errors="replace")
            image_urls = self._telegram_image_urls(page_html, channel, post_id)

            if not image_urls:
                direct_html = self._read_url(f"https://t.me/{channel}/{post_id}").decode(
                    "utf-8", errors="replace"
                )
                image_urls = self._telegram_og_images(direct_html)

            if not image_urls:
                raise ValueError(
                    "No public picture was found in this post. The post may be private, "
                    "deleted, or contain a different media type."
                )

            saved_files = []
            for index, image_url in enumerate(image_urls, start=1):
                self.root.after(
                    0,
                    self.status_var.set,
                    f"Downloading Telegram picture {index} of {len(image_urls)}...",
                )
                image_data, content_type = self._download_url(image_url)
                extension = self._image_extension(content_type, image_url)
                base_name = f"telegram_{channel}_{post_id}"
                if len(image_urls) > 1:
                    base_name += f"_{index}"
                destination = self._unused_path(Path(folder) / f"{base_name}{extension}")
                destination.write_bytes(image_data)
                saved_files.append(destination)
                self.root.after(
                    0,
                    self.progress_var.set,
                    index / len(image_urls) * 100,
                )
        except (HTTPError, URLError) as exc:
            self._finish_download(False, f"Telegram could not be reached: {exc}")
            return
        except Exception as exc:
            self._finish_download(False, str(exc))
            return

        count = len(saved_files)
        noun = "picture" if count == 1 else "pictures"
        self._finish_download(True, f"Downloaded {count} Telegram {noun} successfully.")

    @staticmethod
    def _read_url(url: str) -> bytes:
        data, _content_type = YouTubeDownloaderApp._download_url(url)
        return data

    @staticmethod
    def _download_url(url: str) -> tuple[bytes, str]:
        for attempt in range(3):
            request = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Referer": "https://t.me/",
                },
            )
            try:
                with urlopen(request, timeout=30) as response:
                    content_type = response.headers.get_content_type()
                    return response.read(), content_type
            except HTTPError as exc:
                if exc.code < 500 or attempt == 2:
                    raise
                time.sleep(attempt + 1)
        raise RuntimeError("The download failed after several attempts.")

    @staticmethod
    def _telegram_image_urls(page_html: str, channel: str, post_id: str) -> list[str]:
        image_urls = []
        anchor_pattern = re.compile(
            r"<a\b[^>]*class=[\"'][^\"']*tgme_widget_message_photo_wrap[^\"']*[\"'][^>]*>",
            re.IGNORECASE,
        )
        expected_path = f"/{channel}/{post_id}".lower()
        for match in anchor_pattern.finditer(page_html):
            tag = html.unescape(match.group(0))
            href_match = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
            image_match = re.search(
                r"background-image\s*:\s*url\([\"']?(https?://[^\"')]+)",
                tag,
                re.IGNORECASE,
            )
            if not href_match or not image_match:
                continue
            if urlparse(href_match.group(1)).path.lower() != expected_path:
                continue
            image_url = image_match.group(1)
            if image_url not in image_urls:
                image_urls.append(image_url)
        return image_urls

    @staticmethod
    def _telegram_og_images(page_html: str) -> list[str]:
        matches = re.findall(
            r"<meta\s+property=[\"']og:image[\"']\s+content=[\"']([^\"']+)[\"']",
            page_html,
            re.IGNORECASE,
        )
        return list(dict.fromkeys(html.unescape(url) for url in matches))

    @staticmethod
    def _image_extension(content_type: str, image_url: str) -> str:
        extensions = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }
        if content_type in extensions:
            return extensions[content_type]
        suffix = Path(urlparse(image_url).path).suffix.lower()
        return suffix if suffix in extensions.values() else ".jpg"

    @staticmethod
    def _unused_path(path: Path) -> Path:
        if not path.exists():
            return path
        counter = 2
        while True:
            candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _download_video(self, url: str, folder: str, choice: dict, ffmpeg_path: str | None) -> None:
        last_message = "Downloading..."

        def set_status(message: str) -> None:
            nonlocal last_message
            if not message:
                return
            last_message = message
            self.root.after(0, self.status_var.set, message)

        def progress_hook(data: dict) -> None:
            status = data.get("status")
            if status == "downloading":
                total_bytes = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded_bytes = data.get("downloaded_bytes", 0)
                if total_bytes:
                    percent = downloaded_bytes / total_bytes * 100
                    self.root.after(0, self.progress_var.set, percent)
                eta = data.get("eta")
                speed = data.get("speed")
                pieces = ["Downloading..."]
                if eta is not None:
                    pieces.append(f"ETA {int(eta)}s")
                if speed:
                    pieces.append(f"{self._format_bytes(speed)}/s")
                set_status(" | ".join(pieces))
            elif status == "finished":
                self.root.after(0, self.progress_var.set, 100)
                set_status("Finalizing file...")

        class YdlLogger:
            def debug(self, message: str) -> None:
                message = YouTubeDownloaderApp._clean_message(message)
                if message.startswith("[download]") or message.startswith("[youtube]"):
                    set_status(message)

            def warning(self, message: str) -> None:
                set_status(YouTubeDownloaderApp._clean_message(message))

            def error(self, message: str) -> None:
                set_status(YouTubeDownloaderApp._clean_message(message))

        options = {
            "noplaylist": True,
            "outtmpl": str(Path(folder) / "%(title)s.%(ext)s"),
            "progress_hooks": [progress_hook],
            "logger": YdlLogger(),
            "quiet": True,
            "no_warnings": False,
            "format": choice["format"],
            "extractor_args": self._youtube_extractor_args(),
        }

        if "merge_output_format" in choice:
            options["merge_output_format"] = choice["merge_output_format"]
        if "postprocessors" in choice:
            options["postprocessors"] = choice["postprocessors"]
        if ffmpeg_path:
            options["ffmpeg_location"] = ffmpeg_path

        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                downloader.download([url])
        except yt_dlp.utils.DownloadError as exc:
            message = str(exc).removeprefix("ERROR: ").strip() or last_message
            self._finish_download(False, message)
            return
        except Exception as exc:
            self._finish_download(False, f"Unexpected error: {exc}")
            return

        self._finish_download(True, "Download finished successfully.")

    def _finish_download(self, success: bool, message: str) -> None:
        def update_ui() -> None:
            self.is_downloading = False
            self.download_button.config(state="normal")
            self.load_button.config(state="normal")
            self.status_var.set(message)
            if success:
                self.progress_var.set(100)
                messagebox.showinfo("Done", message)
            else:
                messagebox.showerror("Download failed", message)

        self.root.after(0, update_ui)

    def _load_qualities_worker(self, url: str) -> None:
        try:
            with yt_dlp.YoutubeDL(
                {
                    "noplaylist": True,
                    "quiet": True,
                    "skip_download": True,
                    "no_warnings": False,
                    "extractor_args": self._youtube_extractor_args(),
                }
            ) as downloader:
                info = downloader.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            message = self._clean_message(str(exc).removeprefix("ERROR: ").strip())
            self.root.after(0, self._handle_quality_load_error, message)
            return
        except Exception as exc:
            self.root.after(0, self._handle_quality_load_error, f"Unexpected error: {exc}")
            return

        ffmpeg_available = self._resolve_ffmpeg_path() is not None
        video_choices = self._build_video_choices(info, ffmpeg_available)
        audio_choices = self._build_audio_choices(info)
        title = info.get("title", "video")
        self.root.after(
            0,
            self._apply_loaded_qualities,
            url,
            title,
            video_choices,
            audio_choices,
            ffmpeg_available,
        )

    def _apply_loaded_qualities(
        self,
        url: str,
        title: str,
        video_choices: list[dict],
        audio_choices: list[dict],
        ffmpeg_available: bool,
    ) -> None:
        self.is_loading_formats = False
        self.loaded_url = url
        self.video_choices = video_choices
        self.audio_choices = audio_choices
        self.load_button.config(state="normal", text="Reload qualities")
        self._refresh_quality_dropdown()
        note = ""
        if not ffmpeg_available:
            note = " Some higher qualities need ffmpeg to combine video and audio."
        self.status_var.set(
            f"Loaded {max(len(video_choices) - 1, 0)} video qualities for {title}.{note}"
        )

    def _handle_quality_load_error(self, message: str) -> None:
        self.is_loading_formats = False
        self.load_button.config(state="normal")
        self.status_var.set(message)
        messagebox.showerror("Could not load qualities", message)

    def _on_source_changed(self, *_args) -> None:
        source = self.source_var.get()
        name, intro, link_label, hint, action = SOURCES[source]
        self.url_var.set("")
        self.progress_var.set(0)
        self.source_title.configure(text=name)
        self.source_intro.configure(text=intro)
        self.url_label.configure(text=link_label)
        self.link_help_label.configure(text=hint)
        if hint:
            self.link_help_label.grid()
        else:
            self.link_help_label.grid_remove()
        icon = self.icons["external" if source == "scribd" else "download"]
        self.download_button.configure(text=action, image=icon)
        self.status_var.set("Ready")

        for widget, sources in self.source_controls.items():
            if source in sources:
                widget.grid()
            else:
                widget.grid_remove()

        if source == "scribd":
            self.progress_bar.grid_remove()
        else:
            self.progress_bar.grid()

        if source == "youtube":
            self.quality_group.grid(column=1, columnspan=1)
            self.quality_label.configure(text="Quality")
            self._refresh_quality_dropdown()
        elif source == "sketchfab":
            self.quality_group.grid(column=0, columnspan=2)
            self.quality_label.configure(text="Model format")
            self.quality_combo["values"] = ["glTF (.zip)", "USDZ (.usdz)"]
            self.quality_var.set("glTF (.zip)")

        self.root.after_idle(self._fit_minimum_size)

    def _fit_minimum_size(self) -> None:
        self.root.update_idletasks()
        width = min(self.root.winfo_reqwidth(), self.root.winfo_screenwidth() - 32)
        height = min(self.root.winfo_reqheight(), self.root.winfo_screenheight() - 64)
        self.root.minsize(max(self.MIN_WIDTH, width), max(self.MIN_HEIGHT, height))

    def _update_progress_text(self, *_args) -> None:
        progress = self.progress_var.get()
        self.progress_text.set(f"{progress:.0f}%" if self.is_downloading or progress else "")

    def _on_mode_changed(self, *_args) -> None:
        if self.source_var.get() == "youtube":
            self._refresh_quality_dropdown()

    def _on_url_changed(self, *_args) -> None:
        if self.url_var.get().strip() == self.loaded_url:
            return
        self.loaded_url = ""
        self.video_choices = []
        self.audio_choices = []
        self.load_button.config(text="Load qualities")
        if self.source_var.get() == "youtube":
            self._refresh_quality_dropdown()

    def _refresh_quality_dropdown(self) -> None:
        if self.source_var.get() != "youtube":
            return
        ffmpeg_available = self._resolve_ffmpeg_path() is not None
        mode = self.mode_var.get()
        choices = self._active_choices(mode, ffmpeg_available)
        labels = [choice["label"] for choice in choices]
        current = self.quality_var.get()
        self.quality_combo["values"] = labels
        if current in labels:
            self.quality_var.set(current)
        elif labels:
            self.quality_var.set(labels[0])
        else:
            self.quality_var.set("")

    def _active_choices(self, mode: str, ffmpeg_available: bool) -> list[dict]:
        if mode == "audio":
            return self.audio_choices or [self._default_audio_choice()]
        return self.video_choices or [self._default_video_choice(ffmpeg_available)]

    def _get_selected_choice(self, mode: str, ffmpeg_available: bool) -> dict:
        selected_label = self.quality_var.get()
        for choice in self._active_choices(mode, ffmpeg_available):
            if choice["label"] == selected_label:
                return choice
        return self._default_audio_choice() if mode == "audio" else self._default_video_choice(ffmpeg_available)

    def _build_video_choices(self, info: dict, ffmpeg_available: bool) -> list[dict]:
        choices = [self._default_video_choice(ffmpeg_available)]
        formats = info.get("formats", [])
        video_formats = [fmt for fmt in formats if fmt.get("vcodec") not in (None, "none")]
        grouped_formats: dict[tuple[int, int], dict] = {}

        for fmt in video_formats:
            format_id = fmt.get("format_id")
            height = fmt.get("height")
            if not format_id or not height:
                continue

            key = (int(height), int(fmt.get("fps") or 30))
            existing = grouped_formats.get(key)
            if existing is None or self._is_better_video_candidate(fmt, existing):
                grouped_formats[key] = fmt

        sorted_formats = sorted(
            grouped_formats.values(),
            key=lambda fmt: (
                fmt.get("height") or 0,
                fmt.get("fps") or 0,
                fmt.get("tbr") or 0,
            ),
            reverse=True,
        )

        for fmt in sorted_formats:
            has_audio = fmt.get("acodec") not in (None, "none")
            requires_ffmpeg = not has_audio
            choice = {
                "label": self._build_video_label(fmt, has_audio, ffmpeg_available),
                "format": str(fmt["format_id"]) if has_audio else f"{fmt['format_id']}+bestaudio/best",
                "requires_ffmpeg": requires_ffmpeg,
            }
            if requires_ffmpeg:
                choice["merge_output_format"] = "mp4"
            choices.append(choice)

        return choices

    def _build_audio_choices(self, info: dict) -> list[dict]:
        choices = [self._default_audio_choice()]
        formats = info.get("formats", [])
        audio_formats = [
            fmt
            for fmt in formats
            if fmt.get("vcodec") in (None, "none") and fmt.get("acodec") not in (None, "none")
        ]
        audio_formats.sort(
            key=lambda fmt: (fmt.get("abr") or 0, fmt.get("tbr") or 0),
            reverse=True,
        )

        for fmt in audio_formats:
            format_id = fmt.get("format_id")
            if not format_id:
                continue
            choices.append(
                {
                    "label": self._build_audio_label(fmt),
                    "format": str(format_id),
                    "postprocessors": [self._mp3_postprocessor()],
                    "requires_ffmpeg": True,
                }
            )

        return choices

    @staticmethod
    def _default_video_choice(ffmpeg_available: bool) -> dict:
        if ffmpeg_available:
            return {
                "label": "Best available",
                "format": "bestvideo+bestaudio/best",
                "requires_ffmpeg": True,
                "merge_output_format": "mp4",
            }
        return {
            "label": "Best available (single file)",
            "format": "best",
            "requires_ffmpeg": False,
        }

    @staticmethod
    def _default_audio_choice() -> dict:
        return {
            "label": "Best audio (MP3)",
            "format": "bestaudio/best",
            "postprocessors": [YouTubeDownloaderApp._mp3_postprocessor()],
            "requires_ffmpeg": True,
        }

    @staticmethod
    def _mp3_postprocessor() -> dict:
        return {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }

    @staticmethod
    def _yt_dlp_module_available() -> bool:
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            return False
        return True

    @staticmethod
    def _youtube_extractor_args() -> dict:
        return {
            "youtube": {
                "player_client": ["default", "-web"],
            }
        }

    def _resolve_ffmpeg_path(self) -> str | None:
        if self.ffmpeg_path_cache is not UNSET:
            return self.ffmpeg_path_cache  # type: ignore[return-value]

        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            self.ffmpeg_path_cache = ffmpeg_path
            return ffmpeg_path

        try:
            import imageio_ffmpeg

            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_path = None

        self.ffmpeg_path_cache = ffmpeg_path
        return ffmpeg_path

    @staticmethod
    def _is_youtube_url(url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        return host in YOUTUBE_HOSTS

    @staticmethod
    def _is_telegram_url(url: str) -> bool:
        try:
            YouTubeDownloaderApp._telegram_post_parts(url)
        except ValueError:
            return False
        return True

    @staticmethod
    def _telegram_post_parts(url: str) -> tuple[str, str]:
        if not url.startswith(("http://", "https://")):
            raise ValueError("Invalid Telegram link.")
        parsed = urlparse(url)
        if parsed.netloc.lower() not in ("t.me", "www.t.me", "telegram.me", "www.telegram.me"):
            raise ValueError("Invalid Telegram link.")
        match = re.fullmatch(r"/(?:s/)?([A-Za-z0-9_]+)/([0-9]+)/?", parsed.path)
        if not match:
            raise ValueError("The link must point to a public Telegram channel post.")
        return match.group(1), match.group(2)

    @staticmethod
    def _is_sketchfab_url(url: str) -> bool:
        try:
            YouTubeDownloaderApp._sketchfab_model_uid(url)
        except ValueError:
            return False
        return True

    @staticmethod
    def _is_adfocus_url(url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        parsed = urlparse(url)
        return (
            parsed.netloc.lower() in ("adfoc.us", "www.adfoc.us")
            and bool(parsed.path.strip("/"))
        )

    @staticmethod
    def _is_scribd_url(url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        return (
            parsed.scheme == "https"
            and re.fullmatch(r"(?:(?:www|[a-z]{2}(?:-[a-z]{2})?)\.)?scribd\.com", parsed.netloc.lower()) is not None
            and re.fullmatch(r"/(?:doc|document)/[0-9]+(?:/[^/]+)?/?", parsed.path) is not None
        )

    @staticmethod
    def _sketchfab_model_uid(url: str) -> str:
        if not url.startswith(("http://", "https://")):
            raise ValueError("Invalid Sketchfab link.")
        parsed = urlparse(url)
        if parsed.netloc.lower() not in ("sketchfab.com", "www.sketchfab.com"):
            raise ValueError("Invalid Sketchfab link.")
        matches = re.findall(r"(?<![0-9a-fA-F])([0-9a-fA-F]{32})(?![0-9a-fA-F])", parsed.path)
        if not matches:
            raise ValueError("The link does not contain a Sketchfab model ID.")
        return matches[-1].lower()

    @staticmethod
    def _format_bytes(byte_count: float) -> str:
        size = float(byte_count)
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        return f"{size:.1f} {units[unit_index]}"

    @classmethod
    def _build_video_label(cls, fmt: dict, has_audio: bool, ffmpeg_available: bool) -> str:
        height = fmt.get("height")
        resolution = cls._resolution_label(height)
        fps = f"{int(fmt['fps'])} fps" if fmt.get("fps") else "30 fps"
        ext = (fmt.get("ext") or "?").upper()
        size = cls._format_filesize(fmt)
        if has_audio:
            stream_note = "ready to save"
        elif ffmpeg_available:
            stream_note = "best audio will be merged"
        else:
            stream_note = "needs ffmpeg to merge audio"
        return f"{resolution} | {ext} | {fps} | {size} | {stream_note}"

    @classmethod
    def _build_audio_label(cls, fmt: dict) -> str:
        abr = fmt.get("abr") or fmt.get("tbr")
        bitrate = f"{int(abr)} kbps" if abr else "unknown bitrate"
        ext = (fmt.get("ext") or "?").upper()
        size = cls._format_filesize(fmt)
        return f"{bitrate} | {ext} | {size} [id {fmt['format_id']}]"

    @staticmethod
    def _format_filesize(fmt: dict) -> str:
        file_size = fmt.get("filesize") or fmt.get("filesize_approx")
        if not file_size:
            return "size unknown"
        return YouTubeDownloaderApp._format_bytes(file_size)

    @staticmethod
    def _clean_message(message: str) -> str:
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
        cleaned = ansi_pattern.sub("", message or "")
        return " ".join(cleaned.split())

    @staticmethod
    def _is_better_video_candidate(candidate: dict, current: dict) -> bool:
        candidate_has_audio = candidate.get("acodec") not in (None, "none")
        current_has_audio = current.get("acodec") not in (None, "none")
        candidate_score = (
            1 if str(candidate.get("ext", "")).lower() == "mp4" else 0,
            1 if candidate_has_audio else 0,
            candidate.get("tbr") or 0,
            candidate.get("filesize") or candidate.get("filesize_approx") or 0,
        )
        current_score = (
            1 if str(current.get("ext", "")).lower() == "mp4" else 0,
            1 if current_has_audio else 0,
            current.get("tbr") or 0,
            current.get("filesize") or current.get("filesize_approx") or 0,
        )
        return candidate_score > current_score

    @staticmethod
    def _resolution_label(height: int | None) -> str:
        if not height:
            return "Unknown quality"
        special_names = {
            144: "144p",
            240: "240p",
            360: "360p",
            480: "480p",
            720: "720p HD",
            1080: "1080p Full HD",
            1440: "1440p 2K",
            2160: "2160p 4K",
            4320: "4320p 8K",
        }
        return special_names.get(int(height), f"{int(height)}p")


def main() -> None:
    root = tk.Tk()
    YouTubeDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
