from __future__ import annotations

import argparse
from pathlib import Path

from video_sr.backends import build_backend
from video_sr.pipeline import VideoJob, VideoSuperResolutionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="视频超分辨率 MVP")
    parser.add_argument("--input", required=True, help="输入视频路径")
    parser.add_argument("--output", required=True, help="输出视频路径")
    parser.add_argument("--scale", type=int, default=2, choices=[2, 3, 4], help="放大倍数")
    parser.add_argument(
        "--backend",
        default="bicubic",
        choices=["bicubic", "realesrgan-ncnn-vulkan"],
        help="超分后端",
    )
    parser.add_argument("--engine-path", help="外部超分引擎路径")
    parser.add_argument("--model", default="realesr-animevideov3", help="模型名称")
    parser.add_argument("--no-audio", action="store_true", help="不保留原视频音频")
    parser.add_argument("--fps", type=float, help="手动指定输出帧率")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    backend = build_backend(
        name=args.backend,
        engine_path=args.engine_path,
        model=args.model,
    )

    job = VideoJob(
        input_path=Path(args.input).expanduser().resolve(),
        output_path=Path(args.output).expanduser().resolve(),
        scale=args.scale,
        keep_audio=not args.no_audio,
        fps=args.fps,
    )

    pipeline = VideoSuperResolutionPipeline(backend=backend, log_callback=print)
    pipeline.run(job)


if __name__ == "__main__":
    main()
