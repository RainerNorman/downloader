# Downloader

A Windows desktop app for saving media from links and turning page images into PDFs. Choose a source in the sidebar, paste a link or select a file, and pick where to save the result.

[Windows releases](https://github.com/RainerNorman/downloader/releases) · [Builds and checks](https://github.com/RainerNorman/downloader/actions) · [Report a problem](https://github.com/RainerNorman/downloader/issues)

## Sources

| Source | What it does |
| --- | --- |
| YouTube | Load available resolutions, download video, or save audio as MP3. Available formats depend on the video. |
| Telegram | Save pictures from a public post, including photo albums. Use a link such as https://t.me/channel/123. |
| Sketchfab | Download creator-enabled models as glTF or USDZ using your Sketchfab API token. The app also saves attribution information. |
| AdFoc.us | Follow an AdFoc.us link to a direct file or a supported MediaFire download. Microsoft Edge can be used as a fallback to resolve the link. |
| Scribd | Open the document in your default browser. Use Scribd's own download option if it is available to you. |
| Pages to PDF | Combine images into one PDF from a folder, a CBZ/ZIP archive, or direct image links. You can also save a direct PDF or a PDF explicitly published by a document page. |

## Quick start

1. Get **Downloader.exe** from a [Windows release](https://github.com/RainerNorman/downloader/releases) and run it from a folder you can write to.
2. Select a source and paste the link. For **Pages to PDF**, you can also browse for a local file or folder.
3. Pick a save folder and use the main action button. The default is the `downloads` folder beside the app. For the Scribd browser flow, use the browser's save options.

**YouTube:** Install [FFmpeg](https://ffmpeg.org/download.html) and make sure `ffmpeg -version` works in PowerShell before choosing MP3 or a quality with separate audio and video. A combined video stream can be saved without FFmpeg when YouTube offers one. Check **Load qualities** to see the available options.

**Sketchfab:** Open your [account settings](https://sketchfab.com/settings/password) or use **Get token** in the app. Paste the API token into the app and keep it out of screenshots, logs, and issues. The selected format must be enabled for the model.

**Pages to PDF:** Files in folders and archives sort numerically within their names (for example, `1.jpg`, `2.jpg`, `10.jpg`). Direct image links separated by spaces keep the order you enter. Each image fills its own PDF page without cropping.

The Windows release contains a Rust writer that streams JPEG-only exports into the PDF without re-encoding the images. Mixed formats and JPEGs with EXIF rotation use the standard image exporter. Running from source also works without the Rust helper.

## Run from source

Use 64-bit Python 3.14 for Windows with Tcl/Tk enabled. These commands use the virtual environment directly, so activation is optional.

~~~powershell
git clone https://github.com/RainerNorman/downloader.git
cd downloader
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe downloader.py
~~~

## Test and build

~~~powershell
cargo +1.100.0 build --locked --release --manifest-path native/Cargo.toml
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm "YouTube Downloader.spec"
~~~

To compile the helper, install [Rust with rustup](https://www.rust-lang.org/tools/install) and run `rustup toolchain install 1.100.0 --profile minimal` first. The Cargo command is optional for local builds. GitHub Actions includes the helper in the Windows release.

The build produces `dist\Downloader.exe`. The executable uses system FFmpeg when needed. GitHub Actions runs the offline tests and builds the Windows executable. A version tag such as `v0.1.0` also publishes the executable under **Releases**.

## Troubleshooting

- **YouTube format unavailable:** Reload the quality list after changing links. Service changes can affect format availability. If a file has separate streams, check that FFmpeg is on `PATH`.
- **Telegram or Sketchfab file missing:** The post must be public. Sketchfab also requires a valid API token and a model with downloads enabled.
- **Pages to PDF reports a webpage:** Provide a direct file link or a page that explicitly links to a PDF. For other sites, use the site's download feature and open the saved file locally.

Download and share only content you have permission to use. This project is independent of the services listed above.
