"""Image loading, base64 encoding, and resize for multimodal LLM APIs.

Supports both standard raster formats (PNG, JPEG, etc.) and DICOM files.
DICOM files are converted to raster with radiologically-correct windowing
before encoding for LLM submission.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

MAX_DIMENSION = 2048
SUPPORTED_FORMATS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff", "dcm", "dicom"}

# Magic bytes for DICOM: "DICM" at offset 128
_DICOM_MAGIC_OFFSET = 128
_DICOM_MAGIC = b"DICM"


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


def detect_format(path: str | Path) -> str:
    """Detect whether a file is DICOM or standard raster based on extension or magic bytes.

    Returns "dicom" or "raster".
    """
    path = Path(path)
    suffix = path.suffix.lower().lstrip(".")
    if suffix in ("dcm", "dicom"):
        return "dicom"

    # Check magic bytes for extensionless DICOM files
    if path.exists() and path.stat().st_size > _DICOM_MAGIC_OFFSET + len(_DICOM_MAGIC):
        with open(path, "rb") as f:
            f.seek(_DICOM_MAGIC_OFFSET)
            if f.read(len(_DICOM_MAGIC)) == _DICOM_MAGIC:
                return "dicom"

    return "raster"


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
    path: str | Path,
    max_dim: int = MAX_DIMENSION,
    output_format: str = "PNG",
    window_preset: str | None = None,
) -> EncodedImage:
    """Load an image (raster or DICOM), resize if needed, and return base64-encoded.

    DICOM files are automatically detected and converted with proper windowing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    fmt = detect_format(path)

    if fmt == "dicom":
        return load_and_encode_dicom(
            path, max_dim=max_dim, output_format=output_format, window_preset=window_preset
        )

    # Standard raster path
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


def load_and_encode_dicom(
    path: str | Path,
    max_dim: int = MAX_DIMENSION,
    output_format: str = "PNG",
    window_preset: str | None = None,
) -> EncodedImage:
    """Load a DICOM file, apply windowing, and return base64-encoded image.

    Args:
        path: Path to DICOM file
        max_dim: Maximum dimension for resize
        output_format: Output format (PNG recommended for grayscale)
        window_preset: Optional preset name from dicom.WINDOW_PRESETS
    """
    from radslice.dicom import WINDOW_PRESETS, dicom_to_pil

    try:
        import pydicom
    except ImportError:
        raise ImportError(
            "pydicom is required for DICOM support. Install with: pip install pydicom"
        )

    path = Path(path)
    ds = pydicom.dcmread(str(path))

    # Resolve window preset
    window = None
    if window_preset:
        window = WINDOW_PRESETS.get(window_preset)

    img = dicom_to_pil(ds, window=window)

    # Convert grayscale to RGB if needed for JPEG output
    if img.mode == "L" and output_format.upper() == "JPEG":
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
