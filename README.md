# SnapIt

A lightweight Windows screenshot utility that runs in the background and captures on configurable hotkeys. Built as a personal Snagit alternative you can extend over time.

## Features

- **Background tray app** — no main window; lives in the system tray
- **Configurable hotkeys** — pick a capture type, press Assign, then press your key combo
- **Reliable hotkeys** — dual registration (Win32 `RegisterHotKey` + `keyboard` hooks) plus a low-level `WH_KEYBOARD_LL` hook; optional **strong hotkey override** suppresses keys from other apps
- **Conflict warnings** — alerts when a combo is already used in SnapIt or cannot be registered
- **Capture delay** — wait 0–10 seconds before capture (countdown overlay) so you can hover tooltips or switch windows
- **Capture modes**
  - Drawable region (click-drag rectangle with magnifier)
  - Active window
  - Full screen (primary monitor)
  - All monitors
- **Auto-save** — PNG files to a configurable folder (`~/Pictures/SnapIt` by default)
- **Clipboard** — copies each capture to the clipboard (optional)
- **Image editor** — icon toolbar with select/move, line, arrow, square, circle, free draw, text, crop, color pickers, copy image, save-as (PNG/JPEG/BMP/GIF/WebP)
- **Editable annotations** — markup saved as a `.png.snapit.json` sidecar so you can reopen and edit later
- **Snap library** — browse previous captures in the editor; click a thumbnail to load it
- **Video capture (hooks)** — tray and editor menus for region/active-window/fullscreen video; region recording to MP4 is implemented; active-window and fullscreen hooks are wired for future work
- **Standalone build** — `build.ps1` produces `dist\SnapIt.exe` via PyInstaller

## Default hotkeys

| Capture type | Default hotkey |
|--------------|----------------|
| Drawable region | `Ctrl+Shift+1` |
| Active window | `Ctrl+Shift+2` |
| Full screen | `Ctrl+Shift+3` |
| All monitors | *(not set)* |
| Record region (video) | *(not set)* |
| Record active window (video) | *(not set)* |
| Record full screen (video) | *(not set)* |

Change these in **Settings** (right-click tray icon → Settings → Hotkeys).

**Region capture (`Ctrl+Shift+1`):** click to pin a corner, move the mouse, **Space** to swap which corner is pinned (the selection is preserved), **Arrow keys** nudge the free corner by 1px, **Enter** or click again to capture. A magnifier follows the active corner.

**In games:** many titles block global hotkeys in exclusive fullscreen. Use tray → **Capture → Region…** instead (Alt+Tab to tray if needed). Try borderless/windowed mode if you want hotkeys in-game. Enable **Strong hotkey override** in Settings → General if another app is stealing your combos.

## Quick start

### Option A — Download the app (recommended)

1. Open the [latest GitHub Release](/releases/latest)
2. Download `SnapIt.exe`
3. Run it — no Python install required

### Option B — Run from source

```powershell
git clone https://github.com/<owner>/SnapIt.git
cd SnapIt
.\run.ps1
```

Or double-click `run.bat`. On first run, a virtual environment is created and dependencies are installed.

Settings (save folder, hotkeys, etc.) are stored per machine at `%APPDATA%\SnapIt\config.json`.

## Run at Windows login

SnapIt enables **Start with Windows** by default. Toggle it in **Settings → General**.

The app creates a shortcut in your Windows Startup folder pointing to `dist\SnapIt.exe` (after building) or the dev launcher.

### Build standalone .exe

```powershell
.\build.ps1
```

Output: `dist\SnapIt.exe` — no Python or terminal required. Quit any running SnapIt instance before rebuilding (the exe is locked while running).

### Dev mode (detached from terminal)

```powershell
.\run.ps1
```

Uses `pythonw.exe` and starts detached, so closing the terminal won't quit SnapIt.

## Image editor

Enable **Open image editor after each capture** in Settings → General, or use tray → **Edit last capture**.

| Tool | What it does |
|------|--------------|
| Select | Click annotations to select; drag to move; resize with handles |
| Line / Arrow | Click-drag to draw |
| Square / Circle | Click-drag rectangles and ellipses |
| Free draw | Pen tool for freehand strokes |
| Text | Click, enter text; optional sampled background color |
| Crop | Drag rectangle, then **Apply crop** |
| Pick color | Sample a pixel to set draw color |
| Sample text BG | Sample a pixel for text background (or **Clear text BG** for transparent) |

**Copy image** puts the full rendered image (base + annotations) on the clipboard. **Save as…** writes to your SnapIt save folder. Annotations are stored alongside the image in `filename.png.snapit.json`.

The editor image scales when you resize the window. Use the collapsible **snap library** pane at the bottom to browse previous captures — click a thumbnail to load it.

The editor **Capture ▾** menu can trigger new screenshots or video captures without returning to the tray.

## Video capture

Tray → **Video** and the editor **Capture ▾** menu expose:

- **Record region (video)** — select a region, then records for the configured duration (default 5s) to MP4 via `imageio` + ffmpeg
- **Record active window (video)** — hook present; full implementation pending
- **Record full screen (video)** — hook present; full implementation pending

Configure **Video record length** in Settings → General. Requires `imageio[ffmpeg]` (included in `requirements.txt`).

## Project layout

| Path | Role |
|------|------|
| `snapit/app.py` | Main orchestrator (tray, hotkeys, capture, editor) |
| `snapit/hotkeys.py`, `win32_hotkeys.py`, `win32_ll_hook.py` | Hotkey registration and low-level hook |
| `snapit/capture.py`, `region_selector.py`, `capture_delay.py` | Screenshot capture |
| `snapit/editor.py`, `editor_render.py`, `tool_icons.py`, `annotation_io.py` | Image editor and sidecar I/O |
| `snapit/video_capture.py` | Video capture hooks |
| `snapit/settings_ui.py`, `config.py` | Settings UI and `%APPDATA%` config |
| `build.ps1`, `run.ps1`, `run.bat` | Build and dev launchers |

## Roadmap ideas

- [ ] Scrolling capture
- [ ] Active-window and fullscreen video recording
- [ ] Per-monitor selection
- [x] Pre-built release binaries on GitHub

## Requirements

- Windows 10/11
- Python 3.11+ (3.13 tested)

## License

MIT — see [LICENSE](LICENSE).