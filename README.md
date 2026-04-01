# Video Super Resolution

Desktop video super-resolution tool built with Python and PySide6.

This project provides a GUI and CLI for upscaling videos with either a simple bicubic backend or `realesrgan-ncnn-vulkan`, plus side-by-side comparison tools for checking the final quality.

## Highlights

- Desktop GUI for input/output selection, model selection, and progress tracking
- CLI mode for scripted runs
- Real-ESRGAN batch frame processing for faster video handling
- Side-by-side compare preview generation
- Frame-by-frame inspection and comparison screenshot export
- Works well for anime and general video experiments

## Tech Stack

- Python
- PySide6
- FFmpeg / FFprobe
- Pillow
- tqdm
- Real-ESRGAN ncnn Vulkan (optional but recommended)

## Project Structure

```text
video_sr/
  __init__.py
  backends.py
  cli.py
  gui.py
  pipeline.py
README.md
requirements.txt
```

## Requirements

- Python 3.11+
- FFmpeg and FFprobe available on the machine
- PySide6
- Pillow
- tqdm
- Optional: `realesrgan-ncnn-vulkan`

## Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install PySide6
```

## Run The GUI

```powershell
python -m video_sr.gui
```

## Run The CLI

Bicubic example:

```powershell
python -m video_sr.cli --input input.mp4 --output output.mp4 --scale 2 --backend bicubic
```

Real-ESRGAN example:

```powershell
python -m video_sr.cli `
  --input input.mp4 `
  --output output.mp4 `
  --backend realesrgan-ncnn-vulkan `
  --engine-path D:\tools\realesrgan-ncnn-vulkan\realesrgan-ncnn-vulkan.exe `
  --model realesr-animevideov3 `
  --scale 2
```

## Recommended Real-ESRGAN Setup

Recommended engine path:

```text
D:\tools\realesrgan-ncnn-vulkan\realesrgan-ncnn-vulkan.exe
```

Recommended models:

- `realesr-animevideov3` for anime video
- `realesrgan-x4plus` for general video
- `realesrgan-x4plus-anime` for anime-style image content

Notes:

- `realesr-animevideov3` is automatically mapped to `x2`, `x3`, or `x4` model variants based on the selected scale
- `realesrgan-x4plus` and `realesrgan-x4plus-anime` only support 4x

## Packaging

A Windows packaging guide is available in [BUILD.md](BUILD.md).

Typical packaging flow:

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name VideoSuperResolution --collect-all PySide6 video_sr\gui.py
```

## Current Limitations

- The pipeline still relies on frame extraction and reassembly through FFmpeg
- Real-ESRGAN quality may vary depending on source material
- The compare preview is generated as a separate video for stable playback

## License

No license file has been added yet. If you plan to open-source or redistribute it broadly, add one explicitly.
