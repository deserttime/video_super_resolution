# Video Super Resolution

Desktop video super-resolution tool built with Python and PySide6.

## Features

- Upscale videos with `bicubic` or `realesrgan-ncnn-vulkan`
- Batch-process extracted frames with Real-ESRGAN for better performance
- GUI for choosing videos, models, scale, and output path
- Progress log and output preview
- Side-by-side compare preview generation
- Frame-by-frame comparison and screenshot export

## Requirements

- Python 3.11+
- FFmpeg and FFprobe
- PySide6
- Pillow
- tqdm
- Optional: `realesrgan-ncnn-vulkan`

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install PySide6
```

## Run GUI

```powershell
python -m video_sr.gui
```

## Run CLI

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

## Project Structure

```text
video_sr/
  backends.py
  cli.py
  gui.py
  pipeline.py
```
