"""DICOM loading, windowing, metadata extraction, and multi-frame handling.

Converts DICOM files to PIL Images with radiologically-correct windowing
for submission to multimodal LLM APIs (which require PNG/JPEG).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    import pydicom  # noqa: F401

    HAS_PYDICOM = True
except ImportError:
    HAS_PYDICOM = False

# Standard CT window presets (center, width) in Hounsfield Units.
# None means: use DICOM-embedded window or auto-derive from pixel data.
WINDOW_PRESETS: dict[str, dict[str, float] | None] = {
    "ct_soft_tissue": {"center": 50, "width": 350},
    "ct_lung": {"center": -600, "width": 1500},
    "ct_bone": {"center": 300, "width": 2000},
    "ct_brain": {"center": 40, "width": 80},
    "ct_liver": {"center": 60, "width": 150},
    "ct_abdomen": {"center": 40, "width": 400},
    "xray_default": None,  # use DICOM-embedded window or auto
    "mri_default": None,  # use min-max normalization
    "us_default": None,  # no windowing needed
}


@dataclass(frozen=True)
class DICOMStudy:
    """Parsed DICOM data with pixel array and extracted metadata."""

    pixel_array: np.ndarray  # Raw pixel data (HU for CT after rescale)
    metadata: dict[str, Any]  # Extracted DICOM tags
    window_center: float | None  # From DICOM tags or preset
    window_width: float | None  # From DICOM tags or preset
    modality: str  # CT, MR, CR, US, etc.
    photometric: str  # MONOCHROME1, MONOCHROME2, RGB
    bits_stored: int
    n_frames: int  # 1 for single-frame, >1 for cine/volume
    original_path: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DICOMStudy):
            return NotImplemented
        return (
            np.array_equal(self.pixel_array, other.pixel_array)
            and self.metadata == other.metadata
            and self.window_center == other.window_center
            and self.window_width == other.window_width
            and self.modality == other.modality
            and self.photometric == other.photometric
            and self.bits_stored == other.bits_stored
            and self.n_frames == other.n_frames
            and self.original_path == other.original_path
        )

    def __hash__(self) -> int:
        return hash((self.modality, self.photometric, self.bits_stored, self.original_path))


def _require_pydicom() -> None:
    if not HAS_PYDICOM:
        raise ImportError(
            "pydicom is required for DICOM support. Install with: pip install pydicom"
        )


def load_dicom(path: str | Path) -> DICOMStudy:
    """Parse a DICOM file and return a DICOMStudy with pixel array + metadata."""
    _require_pydicom()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DICOM file not found: {path}")

    ds = pydicom.dcmread(str(path))
    if not hasattr(ds, "pixel_array"):
        raise ValueError(f"DICOM file has no pixel data: {path}")

    try:
        pixels = ds.pixel_array.astype(np.float64)
    except Exception as e:
        msg = str(e).lower()
        if "unable to decompress" in msg or "no available image handler" in msg:
            raise RuntimeError(
                f"Cannot decode compressed DICOM pixels: {e}. "
                "Install codec support with: pip install radslice[dicom-codecs]"
            ) from e
        raise

    # Apply rescale slope/intercept (converts to Hounsfield Units for CT)
    slope = float(getattr(ds, "RescaleSlope", 1))
    intercept = float(getattr(ds, "RescaleIntercept", 0))
    if slope != 1 or intercept != 0:
        pixels = pixels * slope + intercept

    modality = str(getattr(ds, "Modality", "OT"))
    photometric = str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2"))
    bits_stored = int(getattr(ds, "BitsStored", 8))

    # Determine number of frames
    n_frames = int(getattr(ds, "NumberOfFrames", 1))
    if pixels.ndim == 3 and photometric in ("MONOCHROME1", "MONOCHROME2"):
        n_frames = pixels.shape[0]

    # Extract window from DICOM tags
    wc, ww = _read_dicom_window(ds)

    metadata = extract_metadata(ds)

    return DICOMStudy(
        pixel_array=pixels,
        metadata=metadata,
        window_center=wc,
        window_width=ww,
        modality=modality,
        photometric=photometric,
        bits_stored=bits_stored,
        n_frames=n_frames,
        original_path=str(path),
    )


def _read_dicom_window(ds: Any) -> tuple[float | None, float | None]:
    """Read Window Center/Width from DICOM tags. Returns (center, width) or (None, None)."""
    wc = getattr(ds, "WindowCenter", None)
    ww = getattr(ds, "WindowWidth", None)
    if wc is None or ww is None:
        return None, None
    # Can be a list (multi-value) — take the first
    if hasattr(wc, "__iter__") and not isinstance(wc, str):
        wc = float(list(wc)[0])
    else:
        wc = float(wc)
    if hasattr(ww, "__iter__") and not isinstance(ww, str):
        ww = float(list(ww)[0])
    else:
        ww = float(ww)
    return wc, ww


def apply_window(pixels: np.ndarray, center: float, width: float) -> np.ndarray:
    """Apply window/level transform to pixel array, returning uint8 [0, 255].

    Uses the standard DICOM VOI LUT linear function:
        if pixel <= center - width/2: output = 0
        if pixel >= center + width/2: output = 255
        otherwise: linear interpolation
    """
    if width <= 0:
        raise ValueError(f"Window width must be positive, got {width}")
    lower = center - width / 2
    upper = center + width / 2
    windowed = np.clip((pixels - lower) / (upper - lower) * 255, 0, 255)
    return windowed.astype(np.uint8)


def auto_window(ds: Any) -> tuple[float, float]:
    """Determine window center/width from DICOM tags, falling back to histogram.

    Priority:
    1. DICOM WindowCenter/WindowWidth tags
    2. Percentile-based (1st–99th) from pixel data
    """
    wc, ww = _read_dicom_window(ds)
    if wc is not None and ww is not None:
        return wc, ww

    # Fallback: histogram-based (1st to 99th percentile)
    try:
        pixels = ds.pixel_array.astype(np.float64)
    except Exception as e:
        msg = str(e).lower()
        if "unable to decompress" in msg or "no available image handler" in msg:
            raise RuntimeError(
                f"Cannot decode compressed DICOM pixels: {e}. "
                "Install codec support with: pip install radslice[dicom-codecs]"
            ) from e
        raise
    slope = float(getattr(ds, "RescaleSlope", 1))
    intercept = float(getattr(ds, "RescaleIntercept", 0))
    if slope != 1 or intercept != 0:
        pixels = pixels * slope + intercept

    p1 = float(np.percentile(pixels, 1))
    p99 = float(np.percentile(pixels, 99))
    center = (p1 + p99) / 2
    width = max(p99 - p1, 1.0)  # Avoid zero width
    return center, width


def select_window_preset(modality: str, anatomy: str | None = None) -> dict[str, float] | None:
    """Pick a standard window preset based on modality and optional anatomy.

    Returns a dict with 'center' and 'width' keys, or None (use auto/DICOM-embedded).
    """
    modality_upper = modality.upper()

    # CT presets — anatomy-specific when available
    if modality_upper == "CT":
        anatomy_lower = (anatomy or "").lower()
        anatomy_map = {
            "chest": "ct_lung",
            "lung": "ct_lung",
            "brain": "ct_brain",
            "head": "ct_brain",
            "liver": "ct_liver",
            "abdomen": "ct_abdomen",
            "pelvis": "ct_abdomen",
            "bone": "ct_bone",
            "spine": "ct_bone",
            "extremity": "ct_soft_tissue",
        }
        preset_key = anatomy_map.get(anatomy_lower, "ct_soft_tissue")
        return WINDOW_PRESETS[preset_key]

    # Non-CT modalities: use modality defaults (returns None → auto)
    modality_defaults = {
        "CR": "xray_default",
        "DX": "xray_default",
        "MR": "mri_default",
        "US": "us_default",
    }
    preset_key = modality_defaults.get(modality_upper)
    if preset_key:
        return WINDOW_PRESETS[preset_key]

    return None


def select_frame(pixels: np.ndarray, frame_index: int | None = None) -> np.ndarray:
    """Select a single frame from a multi-frame pixel array.

    For single-frame data (2D), returns as-is.
    For multi-frame (3D with grayscale), selects the specified frame or middle frame.
    """
    if pixels.ndim == 2:
        return pixels

    if pixels.ndim == 3:
        n_frames = pixels.shape[0]
        # Could be RGB single-frame (rows, cols, 3) — check last dim
        if pixels.shape[2] in (3, 4):
            # Likely RGB/RGBA single frame
            return pixels

        # Multi-frame grayscale: (frames, rows, cols)
        if frame_index is not None:
            if frame_index < 0 or frame_index >= n_frames:
                raise IndexError(f"Frame index {frame_index} out of range [0, {n_frames - 1}]")
            return pixels[frame_index]
        # Default: middle frame
        return pixels[n_frames // 2]

    raise ValueError(f"Unexpected pixel array shape: {pixels.shape}")


def dicom_to_pil(ds: Any, window: dict[str, float] | None = None) -> Image.Image:
    """Convert a DICOM dataset to a PIL Image with proper windowing.

    Args:
        ds: pydicom Dataset with pixel_array
        window: Optional dict with 'center' and 'width' keys.
                If None, uses auto_window (DICOM tags → histogram fallback).
    """
    _require_pydicom()
    try:
        pixels = ds.pixel_array.astype(np.float64)
    except Exception as e:
        msg = str(e).lower()
        if "unable to decompress" in msg or "no available image handler" in msg:
            raise RuntimeError(
                f"Cannot decode compressed DICOM pixels: {e}. "
                "Install codec support with: pip install radslice[dicom-codecs]"
            ) from e
        raise

    # Rescale to Hounsfield Units (CT) or real values
    slope = float(getattr(ds, "RescaleSlope", 1))
    intercept = float(getattr(ds, "RescaleIntercept", 0))
    if slope != 1 or intercept != 0:
        pixels = pixels * slope + intercept

    photometric = str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2"))

    # Handle multi-frame: pick single frame
    if pixels.ndim == 3 and photometric in ("MONOCHROME1", "MONOCHROME2"):
        pixels = select_frame(pixels)

    # RGB images: no windowing, just normalize to uint8
    if photometric == "RGB" or (pixels.ndim == 3 and pixels.shape[2] in (3, 4)):
        if pixels.max() > 255:
            pixels = (pixels / pixels.max() * 255).astype(np.uint8)
        else:
            pixels = pixels.astype(np.uint8)
        return Image.fromarray(pixels, mode="RGB")

    # Grayscale: apply windowing
    if window is not None:
        img_array = apply_window(pixels, window["center"], window["width"])
    else:
        wc, ww = auto_window(ds)
        img_array = apply_window(pixels, wc, ww)

    # MONOCHROME1: 0 = white, invert
    if photometric == "MONOCHROME1":
        img_array = 255 - img_array

    return Image.fromarray(img_array, mode="L")


def extract_metadata(ds: Any) -> dict[str, Any]:
    """Extract clinically relevant DICOM tags into a plain dict."""
    _require_pydicom()

    def _safe_get(attr: str) -> Any:
        val = getattr(ds, attr, None)
        if val is None:
            return None
        # Convert pydicom types to plain Python
        if hasattr(val, "original_string"):
            return str(val)
        if hasattr(val, "__iter__") and not isinstance(val, (str, bytes)):
            return [str(v) for v in val]
        return str(val) if not isinstance(val, (int, float)) else val

    return {
        "modality": _safe_get("Modality"),
        "body_part": _safe_get("BodyPartExamined"),
        "study_description": _safe_get("StudyDescription"),
        "series_description": _safe_get("SeriesDescription"),
        "patient_position": _safe_get("PatientPosition"),
        "pixel_spacing": _safe_get("PixelSpacing"),
        "slice_thickness": _safe_get("SliceThickness"),
        "rows": _safe_get("Rows"),
        "columns": _safe_get("Columns"),
        "bits_stored": _safe_get("BitsStored"),
        "bits_allocated": _safe_get("BitsAllocated"),
        "photometric_interpretation": _safe_get("PhotometricInterpretation"),
        "rescale_slope": _safe_get("RescaleSlope"),
        "rescale_intercept": _safe_get("RescaleIntercept"),
        "window_center": _safe_get("WindowCenter"),
        "window_width": _safe_get("WindowWidth"),
        "number_of_frames": _safe_get("NumberOfFrames"),
        "manufacturer": _safe_get("Manufacturer"),
        "institution_name": _safe_get("InstitutionName"),
        "sop_class_uid": _safe_get("SOPClassUID"),
    }
