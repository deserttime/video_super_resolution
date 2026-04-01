from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import subprocess


DEFAULT_ENGINE_DIR = Path(r"D:\tools\realesrgan-ncnn-vulkan")
DEFAULT_ENGINE_PATH = DEFAULT_ENGINE_DIR / "realesrgan-ncnn-vulkan.exe"

MODEL_SCALE_MAP = {
    "realesr-animevideov3": {
        2: "realesr-animevideov3-x2",
        3: "realesr-animevideov3-x3",
        4: "realesr-animevideov3-x4",
    },
    "realesrgan-x4plus": {
        4: "realesrgan-x4plus",
    },
    "realesrgan-x4plus-anime": {
        4: "realesrgan-x4plus-anime",
    },
}


class UpscaleBackend(ABC):
    @abstractmethod
    def upscale_image(self, input_path: Path, output_path: Path, scale: int) -> None:
        """Upscale a single image file."""

    def upscale_directory(self, input_dir: Path, output_dir: Path, scale: int) -> bool:
        """Upscale a whole directory.

        Returns True when the backend handled the whole directory itself.
        """
        return False


class BicubicBackend(UpscaleBackend):
    def upscale_image(self, input_path: Path, output_path: Path, scale: int) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError("bicubic 后端需要先安装 Pillow：python -m pip install -r requirements.txt") from exc

        with Image.open(input_path) as image:
            new_size = (image.width * scale, image.height * scale)
            resized = image.resize(new_size, Image.Resampling.BICUBIC)
            resized.save(output_path)


class RealEsrganNcnnBackend(UpscaleBackend):
    def __init__(self, engine_path: str | None = None, model: str = "realesr-animevideov3") -> None:
        resolved = self._resolve_engine_path(engine_path)
        self.engine_path = resolved
        self.model = model
        self.models_dir = Path(resolved).resolve().parent / "models"
        if not self.models_dir.exists():
            raise FileNotFoundError(f"未找到 models 目录: {self.models_dir}")

    def upscale_image(self, input_path: Path, output_path: Path, scale: int) -> None:
        model_name = resolve_model_name(self.model, scale)
        ensure_model_exists(self.models_dir, model_name)

        command = [
            self.engine_path,
            "-i",
            str(input_path),
            "-o",
            str(output_path),
            "-n",
            model_name,
            "-s",
            str(scale),
        ]
        subprocess.run(command, check=True)

    def upscale_directory(self, input_dir: Path, output_dir: Path, scale: int) -> bool:
        model_name = resolve_model_name(self.model, scale)
        ensure_model_exists(self.models_dir, model_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            self.engine_path,
            "-i",
            str(input_dir),
            "-o",
            str(output_dir),
            "-n",
            model_name,
            "-s",
            str(scale),
        ]
        subprocess.run(command, check=True)
        return True

    @staticmethod
    def _resolve_engine_path(engine_path: str | None) -> str:
        candidates = []
        if engine_path:
            candidates.append(Path(engine_path))
        candidates.append(DEFAULT_ENGINE_PATH)
        which_path = shutil.which("realesrgan-ncnn-vulkan")
        if which_path:
            candidates.append(Path(which_path))

        for candidate in candidates:
            if candidate and candidate.exists():
                return str(candidate)

        raise FileNotFoundError(
            "未找到 realesrgan-ncnn-vulkan 可执行文件，请通过 --engine-path 指定。"
        )


def resolve_model_name(model: str, scale: int) -> str:
    scale_mapping = MODEL_SCALE_MAP.get(model)
    if not scale_mapping:
        return model

    resolved = scale_mapping.get(scale)
    if not resolved:
        supported = ", ".join(str(item) for item in sorted(scale_mapping))
        raise ValueError(f"模型 {model} 仅支持这些倍率: {supported}")
    return resolved


def ensure_model_exists(models_dir: Path, model_name: str) -> None:
    param_file = models_dir / f"{model_name}.param"
    bin_file = models_dir / f"{model_name}.bin"
    if not param_file.exists() or not bin_file.exists():
        raise FileNotFoundError(f"模型文件缺失: {model_name}，请检查 {models_dir}")


def discover_models(engine_path: str | None = None) -> list[str]:
    try:
        resolved = RealEsrganNcnnBackend._resolve_engine_path(engine_path)
    except FileNotFoundError:
        return []

    models_dir = Path(resolved).resolve().parent / "models"
    if not models_dir.exists():
        return []

    model_names = sorted({path.stem for path in models_dir.glob("*.param")})
    preferred = ["realesr-animevideov3", "realesrgan-x4plus", "realesrgan-x4plus-anime"]
    discovered = []
    for base_name in preferred:
        if base_name == "realesr-animevideov3":
            if any(name.startswith("realesr-animevideov3-") for name in model_names):
                discovered.append(base_name)
        elif base_name in model_names:
            discovered.append(base_name)

    extras = [name for name in model_names if name not in discovered and not name.startswith("realesr-animevideov3-")]
    return discovered + extras


def build_backend(name: str, engine_path: str | None = None, model: str = "realesr-animevideov3") -> UpscaleBackend:
    normalized = name.strip().lower()
    if normalized == "bicubic":
        return BicubicBackend()
    if normalized == "realesrgan-ncnn-vulkan":
        return RealEsrganNcnnBackend(engine_path=engine_path, model=model)
    raise ValueError(f"不支持的后端: {name}")
