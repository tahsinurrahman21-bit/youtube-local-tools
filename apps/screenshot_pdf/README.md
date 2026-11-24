# YouTube Screenshot PDF

Turn multiple YouTube videos into **one PDF**, with an editable screenshot interval, one title page per video, and optional captions below the images.

## Using the app

1. Paste the URLs, one per line.
2. Enter a positive interval in seconds, such as `0.5`, `2`, `10`, or `60`. Use a dot for decimals.
3. Leave JPEG quality at `2` for clear slides and text; higher numbers make smaller files.
4. Choose the download/cache, temporary-processing, and output folders.
5. Press **Start**. The window shows the current video, download/extraction/PDF status, and overall progress.
6. When it finishes, use **Open output folder** to find **youtube_screenshots.pdf**.

The PDF uses A4 landscape pages. It preserves each screenshot's aspect ratio. Videos appear in pasted order, and each video's screenshots appear chronologically. Separator pages show video number, title, original URL, and available duration. A failed video gets an error page, while other videos continue.

FFmpeg samples at the first available video frame crossing each interval boundary, starting at time zero. The exact source-frame time is printed in the caption; real timestamps can differ slightly from multiples of the requested interval. If the interval is smaller than the source frame spacing, each source frame appears at most once. No artificial duplicate ending frame is added.

The program decodes video sequentially. It stores frames on your chosen temp drive, processes only one video at a time, and copies each JPEG into the PDF without another lossy re-encoding. It does not keep every image in RAM. The small page index and filenames do grow with the number of pages.

Title pages and captions use Windows fonts, including Bengali/Hindi font fallback. The labels are rendered as images for reliable shaping, so they are **not selectable or searchable PDF text**. The screenshots themselves are also images. For very long titles, separator text is reduced to fit. Large PDFs can be slow to open in some viewers.

At 10-second intervals a two-hour lecture produces about 720 screenshots, plus its title page. At 0.5 seconds it produces about 14,400. The app logs an estimated count after reading metadata. Allow enough disk space and expect long processing times at small intervals.

## Project files

```text
screenshot_pdf/
  main.py               Starts the desktop app
  gui.py                URL input, controls, progress, cancellation
  batch.py              One-video-at-a-time batch processing
  youtube.py            yt-dlp downloads and shared saved-video reuse
  frames.py             FFmpeg extraction and actual timestamps
  pdf_builder.py        Streaming PDF creation
  fonts.py              Windows font registration for PDF labels
  storage.py            Folder checks, safe cleanup, output publication
  settings.py           Local preferences and rolling logs
  dependencies.py       FFmpeg/runtime/package detection
  processes.py          Cancellable FFmpeg process runner
  utils.py              URLs, filenames, timestamps, validation
  app_config.py         Application identity
  requirements.txt
  requirements-dev.txt
  setup.bat / run.bat / run_tests.bat / build_exe.bat
  tools/                Optional portable FFmpeg/Deno executables
  tests/
```

## First-time setup on Windows

These instructions target 64-bit Windows 10/11. Python 3.11 (64-bit) was used for verification. Python 3.12/3.13 can also be used when all dependency wheels are available.

1. Extract the entire ZIP to a normal writable folder on any drive. Do not run files from inside the ZIP. You can copy this application's folder away from the other application; it works independently.
2. If Python is missing, open [Python for Windows](https://www.python.org/downloads/windows/), download a **Windows installer (64-bit)**, and run it. Include the Python launcher and select **Add Python to PATH**. Close and reopen any terminal windows afterward. To check, open PowerShell and run `py --version`.
3. Install FFmpeg using the instructions below.
4. Install Deno using the instructions below. A recent Node.js 22+ already on PATH also works and is detected automatically.
5. Open this application's folder in File Explorer and double-click **setup.bat**. It creates a private `.venv` folder and installs the Python packages. This needs internet access during setup. Wait for “Python packages are ready.” If setup fails, the window stays open so you can read the error. Run it again after resolving the problem.
6. Double-click **run.bat** whenever you want to use this program.

If you prefer PowerShell, open it in this application's folder and run:

```powershell
.\setup.bat
.\run.bat
```

After setup, the equivalent direct Python command is:

```powershell
.\.venv\Scripts\python.exe main.py
```

There is no need to activate the environment, edit Python code, or enter an API key. Keep your `.venv` in its original folder. If you move the project after setup, delete only its `.venv` and run setup.bat again to recreate it.

### Installing FFmpeg

The app needs the real **ffmpeg.exe** program, not a Python package named “ffmpeg.”

1. Open the [official FFmpeg download page](https://ffmpeg.org/download.html).
2. Under **Windows EXE Files**, follow the link to **Windows builds from gyan.dev**. Download a release essentials ZIP, then use File Explorer → Extract All.
3. Open the extracted folder's `bin` folder. It contains `ffmpeg.exe` and `ffprobe.exe`.
4. For the easiest portable setup, copy both files into this application's existing **tools** folder. Repeat for the second app. The apps look there automatically.

Alternatively, keep FFmpeg in a shared location on any drive and add its `bin` folder to your user **Path**: search Windows for “Edit environment variables for your account,” select Path → Edit → New, paste that folder, and press OK. Reopen the app and terminal. Running `ffmpeg -version` in a new PowerShell window should display version information. Use FFmpeg 6 or newer.

### Installing Deno for YouTube

Current yt-dlp uses a JavaScript runtime to handle YouTube's player challenges. The Python setup includes the matching `yt-dlp-ejs` package. No cloud JavaScript service is used. See the [yt-dlp EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

The convenient installation command in PowerShell is:

```powershell
winget install --id DenoLand.Deno -e
```

Then close and reopen the app. If Windows does not have winget, follow [Deno's Windows installation instructions](https://docs.deno.com/runtime/getting_started/installation/). You can also obtain the Windows x64 `deno.exe` release and place it in this application's `tools` folder. Use Deno 2.3 or newer. Use the full Deno executable, not `denort`.

## Storage, reuse, and cleanup

Use the three **Browse…** buttons before starting:

| Folder | What goes there |
|---|---|
| Download / cache | In-progress downloads in marked work folders; yt-dlp cache; optional saved videos in `media`; transcription models in `models` |
| Temporary processing | Frames and working transcript files in marked work folders |
| Final output | The one completed PDF or TXT; a temporary marked staging folder while that result is being assembled |

Choose any writable internal drive, external SSD, or other Windows volume. For example, downloads and output can be on D: while processing files are on E:. The programs do not hard-code a drive letter. Defaults are based on your Windows Documents location.

The apps create missing folders, check that they can write there, and report free-space warnings. More specific space estimates are logged when metadata is available. Estimates are approximate; keep enough free space on every selected drive. Small screenshot intervals can require many gigabytes. Do not unplug an external drive while a job is running.

The final file is staged on the **output** volume so completion uses an atomic rename. This is the only work file that intentionally stays on the output volume. Media and frame processing use the selected cache/temp volumes. Nothing relies on the system's default temporary directory for large processing files.

**Keep downloaded videos after processing** is off by default. When off, newly downloaded media and processing files are removed after success, failure, or cancellation. A completed saved video already in the cache is preserved. When on, either app saves a video with audio at up to 1080p, with a safe filename and a small JSON index. This uses more bandwidth in the transcription app than its normal audio-only download, but makes the video reusable by both programs.

To reuse saved videos across the apps, point both at the same **Download / cache** folder. Matching videos are read locally before any YouTube request. Keep the accompanying `.json` index with each saved video. Model files are also kept for future use; unchecking “Keep downloaded videos” does not delete models.

Cleanup only removes application-owned, marked `.ytt-work-*` directories. It never deletes original local files, existing saved cache videos, or final outputs. Following a crash or power loss, orphaned work folders are cleaned when another batch starts with those same folder selections. Active jobs are protected by process identity. Work folders on drives that are disconnected cannot be cleaned until those drives return.

Folder choices and options are remembered separately for each app in:

```text
%LOCALAPPDATA%\YouTubeLocalTools\screenshot_pdf\settings.json
```

The same location holds rotating diagnostic logs. `%LOCALAPPDATA%` is your Windows local application-data folder. Paste it into File Explorer's address bar to find it. Logs can contain video titles, URLs, and local paths; they stay on your computer. URLs themselves are not saved in the preferences file.

## URLs, errors, and cancellation

Paste one video URL per line. Empty lines are ignored. Watch links, short `youtu.be` links, Shorts, embed links, and individual live-video links are recognized; a live recording must have finished. Tracking parameters and start times do not create duplicates. All videos are processed from their beginning. Playlist-only URLs are rejected, and playlist parameters attached to a video do not trigger playlist downloads.

Malformed links are listed as skipped. Other links are processed in the pasted order. If a video is deleted, private, restricted, or fails to download, its error is logged and processing continues. The result includes a failure section/page at that video's position. The completion display lists successful, failed, and unprocessed videos. If all accepted videos fail, the combined output contains their failure reports.

**Cancel** first requests a clean stop. If a native operation or network request does not respond, the worker and its child processes are stopped after a short grace period (normally within about 8 seconds, plus cleanup). Closing the window while busy follows the same procedure. A cancelled run does **not** publish an incomplete combined output; earlier completed outputs and explicitly saved videos remain intact. To save completed work, let a batch finish or split a very large list into smaller batches.

An existing output is never overwritten. Repeated runs create `_2`, `_3`, and so on after the base filename.

## Troubleshooting

- **“FFmpeg was not found”**: put `ffmpeg.exe` and `ffprobe.exe` in `tools`, or correct PATH and reopen the app.
- **YouTube challenge / JavaScript warning**: install current Deno, then reopen the app. `setup.bat` installs the matching yt-dlp EJS package.
- **YouTube suddenly stops working**: YouTube changes frequently. With the app closed, run `.\.venv\Scripts\python.exe -m pip install --upgrade "yt-dlp[default]"` in this folder. This update is an explicit maintenance action; the app does not auto-update during processing.
- **Private, sign-in-required, age-restricted, region-restricted, or bot-check errors**: those videos may be inaccessible. This version does not manage browser cookies or bypass access restrictions. Other URLs continue.
- **Python “DLL load failed”**: install Microsoft's [Visual C++ 2015–2022 Redistributable, x64](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist), then reopen the app. If the installed Python is 32-bit, use 64-bit Python.
- **Not enough disk space**: choose a larger cache/temp/output volume or free space. A process cannot safely continue writing when its drive is full.
- **Blocked corporate network, firewall, or antivirus**: permit the Python app, FFmpeg, Deno, YouTube access, and (for first-time models) Hugging Face downloads according to your local policy.
- **No useful explanation in the window**: inspect `app-worker.log` and, for transcription, `app-inference.log` in the settings folder. Technical tracebacks are logged there.

## Tests and optional EXE packaging

Double-click **run_tests.bat** to install test tools and run the included non-network tests. They use generated local media. Test packages are separate from normal requirements. The repository's `TEST_REPORT.md` describes the real processing tests performed during delivery and the limits of those checks.

Once `run.bat` works, double-click **build_exe.bat**. It installs PyInstaller and creates a **folder-based** Windows application in `dist\YouTubeScreenshotPDF`. Keep that whole folder together, including `_internal`. Start `YouTubeScreenshotPDF.exe` inside it. The build script collects yt-dlp's EJS assets and the transcriber's model-engine assets when applicable.

FFmpeg and Deno remain external: put their executables in a `tools` folder beside the built EXE, or keep them on PATH. CUDA/cuDNN libraries also remain external. Whisper models stay in the user-selected cache. Do not blindly add these tools, CUDA libraries, and gigabytes of model weights to one enormous executable. Test packaged applications on their destination machine; packaging recipes are included, but a redistributable EXE was not built or certified in this delivery. Review third-party licenses if you redistribute binaries.

## Network and privacy

Processing runs on your own computer with open-source tools. These applications have no OpenAI, ChatGPT, Gemini, Claude, or other cloud AI API integration and consume **zero LLM/API tokens**. Package installation needs internet once. Normal network access is for YouTube media retrieval and the first download of a chosen local Whisper model. Cached media and complete cached models can be processed offline. Audio and transcripts are not uploaded. Hugging Face telemetry is disabled. A different model selection needs its own initial model download.

Use only videos you have permission or rights to download and process.
