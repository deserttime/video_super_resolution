from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from typing import Callable

from video_sr.backends import UpscaleBackend

try:
    from tqdm import tqdm
except ModuleNotFoundError:
    def tqdm(iterable, **_: object):
        return iterable


DEFAULT_FFMPEG_BIN = Path(r"D:\tools\ffmpeg\ffmpeg-8.1-essentials_build\bin")
DEFAULT_FFMPEG = DEFAULT_FFMPEG_BIN / "ffmpeg.exe"
DEFAULT_FFPROBE = DEFAULT_FFMPEG_BIN / "ffprobe.exe"

ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


@dataclass
class VideoJob:
    input_path: Path
    output_path: Path
    scale: int
    keep_audio: bool = True
    fps: float | None = None


class VideoSuperResolutionPipeline:
    def __init__(
        self,
        backend: UpscaleBackend,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> None:
        self.backend = backend
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.ffmpeg_path, self.ffprobe_path, self.process_env = self._resolve_ffmpeg_tools()

    def run(self, job: VideoJob) -> None:
        self._ensure_ffmpeg()
        self._log("开始处理视频")

        with tempfile.TemporaryDirectory(prefix="video_sr_") as temp_dir:
            workspace = Path(temp_dir)
            frames_in = workspace / "frames_in"
            frames_out = workspace / "frames_out"
            audio_path = workspace / "audio.aac"

            frames_in.mkdir(parents=True, exist_ok=True)
            frames_out.mkdir(parents=True, exist_ok=True)

            fps = job.fps or self._probe_fps(job.input_path)
            self._log(f"检测到视频帧率: {fps:.3f}")
            self._log("正在提取视频帧")
            self._extract_frames(job.input_path, frames_in)

            if job.keep_audio:
                self._log("正在提取音频")
                self._extract_audio(job.input_path, audio_path)

            frame_files = sorted(frames_in.glob("frame_*.png"))
            if not frame_files:
                raise RuntimeError("没有从输入视频中提取到任何帧。")

            total_frames = len(frame_files)
            self._report_progress(0, total_frames, "已开始")

            if self._run_batch_upscale(frames_in, frames_out, job.scale, total_frames):
                self._report_progress(total_frames, total_frames, f"已批量处理 {total_frames} 帧")
            else:
                for index, frame_path in enumerate(tqdm(frame_files, desc="Upscaling frames"), start=1):
                    target = frames_out / frame_path.name
                    self.backend.upscale_image(frame_path, target, job.scale)
                    self._report_progress(index, total_frames, f"正在处理第 {index}/{total_frames} 帧")

            self._log("正在合成输出视频")
            self._assemble_video(
                frames_dir=frames_out,
                audio_path=audio_path if job.keep_audio and audio_path.exists() else None,
                output_path=job.output_path,
                fps=fps,
            )
            self._log("处理完成")

    def _ensure_ffmpeg(self) -> None:
        if not self.ffmpeg_path.exists() or not self.ffprobe_path.exists():
            raise FileNotFoundError("未找到 ffmpeg，请先安装并加入 PATH。")

    def _probe_fps(self, input_path: Path) -> float:
        command = [
            str(self.ffprobe_path),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True, env=self.process_env)
        rate = result.stdout.strip()
        if "/" in rate:
            numerator, denominator = rate.split("/", maxsplit=1)
            return float(numerator) / float(denominator)
        return float(rate)

    def _extract_frames(self, input_path: Path, frames_dir: Path) -> None:
        command = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            str(frames_dir / "frame_%06d.png"),
        ]
        subprocess.run(command, check=True, env=self.process_env)

    def _extract_audio(self, input_path: Path, audio_path: Path) -> None:
        command = [
            str(self.ffmpeg_path),
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-acodec",
            "copy",
            str(audio_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, env=self.process_env)
        if completed.returncode != 0:
            self._log("未能直接复制音频轨，将输出无音频视频。")
            return

    def _assemble_video(
        self,
        frames_dir: Path,
        audio_path: Path | None,
        output_path: Path,
        fps: float,
    ) -> None:
        command = [
            str(self.ffmpeg_path),
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%06d.png"),
        ]

        if audio_path is not None:
            command.extend(["-i", str(audio_path)])

        command.extend(
            [
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
            ]
        )

        if audio_path is not None:
            command.extend(["-c:a", "copy", "-shortest"])

        command.append(str(output_path))
        subprocess.run(command, check=True, env=self.process_env)

    def _run_batch_upscale(self, frames_in: Path, frames_out: Path, scale: int, total_frames: int) -> bool:
        if not hasattr(self.backend, "upscale_directory"):
            return False

        self._log(f"尝试批量超分 {total_frames} 帧")
        handled = self.backend.upscale_directory(frames_in, frames_out, scale)
        if handled:
            self._log("已切换到目录批处理模式")
        return handled

    def _report_progress(self, current: int, total: int, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(current, total, message)
        self._log(message)

    def _log(self, message: str) -> None:
        if self.log_callback is not None:
            self.log_callback(message)

    def _resolve_ffmpeg_tools(self) -> tuple[Path, Path, dict[str, str]]:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        env = os.environ.copy()

        if ffmpeg and ffprobe:
            return Path(ffmpeg), Path(ffprobe), env

        if DEFAULT_FFMPEG.exists() and DEFAULT_FFPROBE.exists():
            existing_path = env.get("PATH", "")
            env["PATH"] = f"{DEFAULT_FFMPEG_BIN}{os.pathsep}{existing_path}" if existing_path else str(DEFAULT_FFMPEG_BIN)
            return DEFAULT_FFMPEG, DEFAULT_FFPROBE, env

        return Path(ffmpeg or "ffmpeg"), Path(ffprobe or "ffprobe"), env
