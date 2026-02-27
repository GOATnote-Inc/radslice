"""Image loading, base64 encoding, and resize for multimodal LLM APIs."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

MAX_DIMENSION = 2048
SUPPORTED_FORMATS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff"}


@dataclass(frozen=True)
class EncodedImage:
    """A base64-encoded image ready for LLM API submission."""

    base64_data: str
    media_type: str  # e.g. "image/png"
    width: int
    height: int
    original_path: str


def _media_type(suffix: str) -> str:
    """Map file suffix to MIME type."""
    suffix = suffix.lower().lstrip(".")
    mapping = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
    }
    return mapping.get(suffix, "image/png")


def resize_if_needed(img: Image.Image, max_dim: int = MAX_DIMENSION) -> Image.Image:
    """Resize image if either dimension exceeds max_dim, preserving aspect ratio."""
    w, h = img.size
    if w <= max_dim and h <= max_dim:
        return img
    scale = max_dim / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return img.resize((new_w, new_h), Image.LANCZOS)


def load_and_encode(
    path: str | Path, max_dim: int = MAX_DIMENSION, output_format: str = "PNG"
) -> EncodedImage:
    """Load an image, resize if needed, and return base64-encoded."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    suffix = path.suffix.lstrip(".")
    if suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported image format: {suffix}")

    img = Image.open(path)
    if img.mode == "RGBA" and output_format.upper() == "JPEG":
        img = img.convert("RGB")
    elif img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    img = resize_if_needed(img, max_dim)

    buf = io.BytesIO()
    img.save(buf, format=output_format)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return EncodedImage(
        base64_data=b64,
        media_type=_media_type(output_format.lower()),
        width=img.size[0],
        height=img.size[1],
        original_path=str(path),
    )


def encode_bytes(
    data: bytes, media_type: str = "image/png", max_dim: int = MAX_DIMENSION
) -> EncodedImage:
    """Encode raw image bytes to base64 with optional resize."""
    img = Image.open(io.BytesIO(data))
    img = resize_if_needed(img, max_dim)

    buf = io.BytesIO()
    fmt = media_type.split("/")[-1].upper()
    if fmt == "JPEG":
        if img.mode == "RGBA":
            img = img.convert("RGB")
    img.save(buf, format=fmt if fmt != "JPG" else "JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return EncodedImage(
        base64_data=b64,
        media_type=media_type,
        width=img.size[0],
        height=img.size[1],
        original_path="<bytes>",
    )
