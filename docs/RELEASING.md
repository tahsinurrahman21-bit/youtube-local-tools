# Releasing YouTube Local Tools

## 1. Before every release

- [ ] Bump the version in `bootstrap/install.py` (`version='1.1'`, `CFBundleVersion`, the User-Agent and the READ-ME text). Also bump the setup banner and User-Agent in `bootstrap/setup.ps1`.
- [ ] If you changed pinned packages, update both `BASE`/`CUDA`/`APPLE` in `install.py` and, if needed, `bootstrap/assets.json` (URL **and** SHA-256).
- [ ] Do a **clean test install** on a Windows PC (ideally one with an NVIDIA GPU and one without): extract the release zip, run `Setup.bat`, then open both apps and process one short public video in each.
- [ ] Run `git status` and confirm no logs, settings, `runtime/`, `tools/`, `data/`, `.exe`, `.lnk` or media files are staged. The root `.gitignore` uses an allow-list for this.

## 2. Build the release zip

From the repository folder:

```bat
python scripts\build_release.py
```

If you don't have a system Python, use the one from an existing installation:
`<install folder>\runtime\env\Scripts\python.exe scripts\build_release.py`

This creates `dist\YouTubeLocalTools-<version>-Windows-Setup.zip` and a `.sha256` file. The zip contains only source and setup scripts (about 100 KB).

## 3. Publish on GitHub

1. Commit and push all changes (GitHub Desktop: **Commit to main** → **Push origin**).
2. On GitHub, open **Releases → Draft a new release**.
3. **Choose a tag**: type `v1.1.0` and pick *Create new tag on publish*.
4. Title: `YouTube Local Tools 1.1.0`.
5. Drag `YouTubeLocalTools-<version>-Windows-Setup.zip` (and optionally the `.sha256` file) into the assets box.
6. Paste release notes, for example:

   ```markdown
   ## Download
   **YouTubeLocalTools-1.1.0-Windows-Setup.zip**: extract it, then double-click `Setup.bat`.
   Windows 10/11 64-bit. No Python or admin rights needed. See the README for step-by-step help.

   ## What's included
   - YouTube Screenshots to PDF
   - YouTube Local Transcriber (CPU, or NVIDIA GPU with automatic CPU fallback)
   ```

7. Click **Publish release**.

## 4. What must never be attached to a release or committed

| Item | Why |
|---|---|
| `tools\ffmpeg.exe` | GPL binary. Redistributing it brings source-offer obligations. Setup downloads it via imageio-ffmpeg instead. |
| `runtime\` (NVIDIA cuBLAS/cuDNN, Python, PySide6…) | Several GB in total. NVIDIA libraries are under NVIDIA's EULA. |
| `tools\deno.exe`, `bootstrap\uv*.exe` | About 140 MB. Setup downloads and checksum-verifies them. |
| `Uninstall YouTube Local Tools.exe` | Built by the earlier installer. Its source isn't in this repository. |
| `settings\`, `*.log`, `setup.log`, `installation.json`, `shortcuts.json` | They contain local paths, the Windows user name, video titles and URLs. |
| `data\` | Downloaded videos, Whisper model weights (75 MB to 3 GB), test media and outputs. |

## 5. Optional: standalone PyInstaller build

`apps\<app>\build_exe.bat` creates a folder build in `apps\<app>\dist\`. If you ever publish one:

- Test it on a clean PC without Python.
- Don't bundle FFmpeg or CUDA libraries unless you meet their license terms (GPL source offer for FFmpeg; NVIDIA redistribution terms for CUDA/cuDNN).
- Include `THIRD-PARTY-NOTICES.txt`, and note that PySide6/Qt is LGPLv3: keep the Qt libraries as separate, replaceable files, which a PyInstaller *onedir* build does.
