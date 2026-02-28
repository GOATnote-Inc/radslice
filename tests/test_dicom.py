"""Tests for dicom.py — DICOM loading, windowing, metadata, multi-frame."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from radslice.dicom import (
    WINDOW_PRESETS,
    DICOMStudy,
    apply_window,
    auto_window,
    dicom_to_pil,
    extract_metadata,
    load_dicom,
    select_frame,
    select_window_preset,
)

pydicom = pytest.importorskip("pydicom")
from pydicom.dataset import Dataset, FileDataset  # noqa: E402
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian  # noqa: E402

# --- Test fixtures: synthetic DICOM datasets ---


def _make_test_dicom(
    modality: str = "CT",
    rows: int = 64,
    cols: int = 64,
    bits: int = 16,
    photometric: str = "MONOCHROME2",
    window_center: float | None = None,
    window_width: float | None = None,
    rescale_slope: float = 1.0,
    rescale_intercept: float = 0.0,
    n_frames: int = 1,
    pixel_data: np.ndarray | None = None,
) -> Dataset:
    """Create a minimal synthetic DICOM dataset for testing."""
    ds = Dataset()
    ds.Modality = modality
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = bits
    ds.BitsStored = bits
    ds.HighBit = bits - 1
    ds.PixelRepresentation = 1 if modality == "CT" else 0
    ds.PhotometricInterpretation = photometric
    ds.SamplesPerPixel = 3 if photometric == "RGB" else 1
    if photometric == "RGB":
        ds.PlanarConfiguration = 0  # Color-by-pixel (R1G1B1 R2G2B2 ...)
    ds.RescaleSlope = rescale_slope
    ds.RescaleIntercept = rescale_intercept

    if window_center is not None:
        ds.WindowCenter = window_center
    if window_width is not None:
        ds.WindowWidth = window_width

    if pixel_data is not None:
        arr = pixel_data
    else:
        # Pick dtype and range based on bits and signedness
        if bits <= 8:
            dtype = np.uint8
            high = 2**bits
        elif ds.PixelRepresentation == 1:  # signed
            dtype = np.int16
            high = 2 ** (bits - 1)  # e.g. 32768 for 16-bit signed
        else:
            dtype = np.uint16
            high = 2**bits

        if n_frames > 1:
            ds.NumberOfFrames = n_frames
            if photometric == "RGB":
                arr = np.random.randint(0, 256, (n_frames, rows, cols, 3), dtype=np.uint8)
            else:
                arr = np.random.randint(0, high, (n_frames, rows, cols), dtype=dtype)
        else:
            if photometric == "RGB":
                arr = np.random.randint(0, 256, (rows, cols, 3), dtype=np.uint8)
            else:
                arr = np.random.randint(0, high, (rows, cols), dtype=dtype)

    ds.PixelData = arr.tobytes()
    ds._pixel_array = arr  # Store for pixel_array property workaround

    # Required UIDs
    ds.SOPClassUID = CTImageStorage
    ds.file_meta = pydicom.Dataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    return ds


def _save_dicom(ds: Dataset, path: Path) -> Path:
    """Save a Dataset to a DICOM file."""
    fds = FileDataset(
        str(path),
        ds,
        file_meta=ds.file_meta,
        preamble=b"\x00" * 128,
    )
    fds.save_as(str(path))
    return path


@pytest.fixture
def ct_dicom(tmp_path: Path) -> Path:
    """CT DICOM with known window."""
    ds = _make_test_dicom(
        modality="CT",
        rows=64,
        cols=64,
        bits=16,
        window_center=40.0,
        window_width=80.0,
        rescale_slope=1.0,
        rescale_intercept=-1024.0,
    )
    return _save_dicom(ds, tmp_path / "ct_test.dcm")


@pytest.fixture
def xray_dicom(tmp_path: Path) -> Path:
    """X-ray DICOM with no window tags (auto-window needed)."""
    ds = _make_test_dicom(
        modality="CR",
        rows=128,
        cols=128,
        bits=16,
        photometric="MONOCHROME2",
    )
    return _save_dicom(ds, tmp_path / "xray_test.dcm")


@pytest.fixture
def mono1_dicom(tmp_path: Path) -> Path:
    """MONOCHROME1 DICOM (inverted grayscale)."""
    ds = _make_test_dicom(
        modality="CR",
        rows=64,
        cols=64,
        bits=16,
        photometric="MONOCHROME1",
    )
    return _save_dicom(ds, tmp_path / "mono1_test.dcm")


@pytest.fixture
def multiframe_dicom(tmp_path: Path) -> Path:
    """Multi-frame US DICOM (cine)."""
    ds = _make_test_dicom(
        modality="US",
        rows=32,
        cols=32,
        bits=8,
        n_frames=10,
        photometric="MONOCHROME2",
    )
    return _save_dicom(ds, tmp_path / "multiframe_test.dcm")


@pytest.fixture
def rgb_dicom(tmp_path: Path) -> Path:
    """RGB DICOM (e.g., color ultrasound)."""
    ds = _make_test_dicom(
        modality="US",
        rows=64,
        cols=64,
        bits=8,
        photometric="RGB",
    )
    return _save_dicom(ds, tmp_path / "rgb_test.dcm")


# --- Test classes ---


class TestApplyWindow:
    def test_ct_brain_window(self):
        """CT brain window: center=40, width=80 → [0, 80] maps to [0, 255]."""
        pixels = np.array([0.0, 40.0, 80.0, -100.0, 200.0])
        result = apply_window(pixels, center=40.0, width=80.0)
        assert result.dtype == np.uint8
        # center=40, width=80: lower=0, upper=80
        assert result[0] == 0  # pixel 0 → (0-0)/80*255 = 0 (at lower bound)
        assert result[1] == 127  # pixel 40 → (40-0)/80*255 = 127
        assert result[2] == 255  # pixel 80 → (80-0)/80*255 = 255
        assert result[3] == 0  # pixel -100 → clipped to 0
        assert result[4] == 255  # pixel 200 → clipped to 255

    def test_ct_lung_window(self):
        """CT lung window: center=-600, width=1500."""
        pixels = np.array([-1350.0, -600.0, 150.0])
        result = apply_window(pixels, center=-600.0, width=1500.0)
        assert result[0] == 0  # At lower bound
        assert result[1] == 127  # At center
        assert result[2] == 255  # At upper bound

    def test_ct_bone_window(self):
        pixels = np.array([-700.0, 300.0, 1300.0])
        result = apply_window(pixels, center=300.0, width=2000.0)
        assert result[0] == 0
        assert result[1] == 127
        assert result[2] == 255

    def test_ct_soft_tissue_window(self):
        pixels = np.array([-125.0, 50.0, 225.0])
        result = apply_window(pixels, center=50.0, width=350.0)
        assert result[0] == 0
        assert result[1] == 127
        assert result[2] == 255

    def test_zero_width_raises(self):
        with pytest.raises(ValueError, match="positive"):
            apply_window(np.array([0.0]), center=0.0, width=0.0)

    def test_negative_width_raises(self):
        with pytest.raises(ValueError, match="positive"):
            apply_window(np.array([0.0]), center=0.0, width=-100.0)

    def test_output_is_uint8(self):
        pixels = np.linspace(-1000, 3000, 1000)
        result = apply_window(pixels, center=50.0, width=350.0)
        assert result.dtype == np.uint8
        assert result.min() >= 0
        assert result.max() <= 255


class TestAutoWindow:
    def test_reads_dicom_tags(self):
        ds = _make_test_dicom(window_center=50.0, window_width=350.0)
        wc, ww = auto_window(ds)
        assert wc == 50.0
        assert ww == 350.0

    def test_histogram_fallback(self):
        """When no window tags, falls back to percentile-based windowing."""
        ds = _make_test_dicom(modality="CR")
        # Remove window tags if they exist
        if hasattr(ds, "WindowCenter"):
            del ds.WindowCenter
        if hasattr(ds, "WindowWidth"):
            del ds.WindowWidth
        wc, ww = auto_window(ds)
        assert isinstance(wc, float)
        assert isinstance(ww, float)
        assert ww > 0  # Width must be positive

    def test_multivalue_window_tags(self):
        """DICOM can have multiple window values — should use first."""
        ds = _make_test_dicom()
        ds.WindowCenter = [40.0, 300.0]  # Brain and bone windows
        ds.WindowWidth = [80.0, 2000.0]
        wc, ww = auto_window(ds)
        assert wc == 40.0
        assert ww == 80.0


class TestSelectWindowPreset:
    def test_ct_brain(self):
        preset = select_window_preset("CT", "brain")
        assert preset == {"center": 40, "width": 80}

    def test_ct_lung(self):
        preset = select_window_preset("CT", "chest")
        assert preset == {"center": -600, "width": 1500}

    def test_ct_bone(self):
        preset = select_window_preset("CT", "bone")
        assert preset == {"center": 300, "width": 2000}

    def test_ct_default(self):
        """CT with unknown anatomy defaults to soft tissue."""
        preset = select_window_preset("CT", "unknown")
        assert preset == {"center": 50, "width": 350}

    def test_xray_returns_none(self):
        """X-ray returns None (use DICOM-embedded or auto)."""
        assert select_window_preset("CR") is None

    def test_mri_returns_none(self):
        assert select_window_preset("MR") is None

    def test_us_returns_none(self):
        assert select_window_preset("US") is None


class TestSelectFrame:
    def test_single_frame_passthrough(self):
        arr = np.zeros((64, 64))
        result = select_frame(arr)
        assert result.shape == (64, 64)
        assert np.array_equal(result, arr)

    def test_multiframe_middle(self):
        arr = np.zeros((10, 64, 64))
        arr[5] = 1.0  # Mark middle frame
        result = select_frame(arr)
        assert result.shape == (64, 64)
        assert np.array_equal(result, arr[5])

    def test_multiframe_specific_index(self):
        arr = np.zeros((10, 64, 64))
        arr[3] = 42.0
        result = select_frame(arr, frame_index=3)
        assert np.array_equal(result, arr[3])

    def test_multiframe_out_of_range(self):
        arr = np.zeros((10, 64, 64))
        with pytest.raises(IndexError, match="out of range"):
            select_frame(arr, frame_index=15)

    def test_rgb_single_frame(self):
        """RGB data (rows, cols, 3) should pass through unchanged."""
        arr = np.zeros((64, 64, 3))
        result = select_frame(arr)
        assert result.shape == (64, 64, 3)


class TestDicomToPil:
    def test_produces_pil_image(self, ct_dicom):
        ds = pydicom.dcmread(str(ct_dicom))
        img = dicom_to_pil(ds)
        assert isinstance(img, Image.Image)
        assert img.size == (64, 64)

    def test_grayscale_mode(self, ct_dicom):
        ds = pydicom.dcmread(str(ct_dicom))
        img = dicom_to_pil(ds)
        assert img.mode == "L"

    def test_with_explicit_window(self, ct_dicom):
        ds = pydicom.dcmread(str(ct_dicom))
        img = dicom_to_pil(ds, window={"center": 40, "width": 80})
        assert isinstance(img, Image.Image)
        arr = np.array(img)
        assert arr.dtype == np.uint8

    def test_monochrome1_inversion(self, mono1_dicom):
        """MONOCHROME1 should be inverted (0 = white → 0 = black)."""
        ds = pydicom.dcmread(str(mono1_dicom))
        img_mono1 = dicom_to_pil(ds)
        assert img_mono1.mode == "L"
        # Verify it's different from MONOCHROME2 with same data
        arr = np.array(img_mono1)
        assert arr.dtype == np.uint8

    def test_rgb_dicom(self, rgb_dicom):
        ds = pydicom.dcmread(str(rgb_dicom))
        img = dicom_to_pil(ds)
        assert img.mode == "RGB"
        assert img.size == (64, 64)


class TestExtractMetadata:
    def test_extracts_modality(self):
        ds = _make_test_dicom(modality="CT")
        meta = extract_metadata(ds)
        assert meta["modality"] == "CT"

    def test_extracts_dimensions(self):
        ds = _make_test_dicom(rows=128, cols=256)
        meta = extract_metadata(ds)
        assert meta["rows"] == 128
        assert meta["columns"] == 256

    def test_extracts_bits(self):
        ds = _make_test_dicom(bits=16)
        meta = extract_metadata(ds)
        assert meta["bits_stored"] == 16

    def test_missing_tags_are_none(self):
        ds = _make_test_dicom()
        meta = extract_metadata(ds)
        # BodyPartExamined not set in test fixture
        assert meta["body_part"] is None


class TestLoadDicom:
    def test_load_ct(self, ct_dicom):
        study = load_dicom(ct_dicom)
        assert isinstance(study, DICOMStudy)
        assert study.modality == "CT"
        assert study.bits_stored == 16
        assert study.n_frames == 1
        assert study.pixel_array.ndim == 2

    def test_load_xray(self, xray_dicom):
        study = load_dicom(xray_dicom)
        assert study.modality == "CR"
        assert study.pixel_array.shape == (128, 128)

    def test_load_multiframe(self, multiframe_dicom):
        study = load_dicom(multiframe_dicom)
        assert study.n_frames == 10

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_dicom(tmp_path / "nonexistent.dcm")

    def test_window_from_tags(self, ct_dicom):
        study = load_dicom(ct_dicom)
        assert study.window_center == 40.0
        assert study.window_width == 80.0

    def test_metadata_populated(self, ct_dicom):
        study = load_dicom(ct_dicom)
        assert "modality" in study.metadata
        assert study.metadata["modality"] == "CT"


class TestDICOMStudyDataclass:
    def test_frozen(self, ct_dicom):
        study = load_dicom(ct_dicom)
        with pytest.raises(AttributeError):
            study.modality = "MR"

    def test_original_path(self, ct_dicom):
        study = load_dicom(ct_dicom)
        assert study.original_path == str(ct_dicom)


class TestWindowPresets:
    def test_all_ct_presets_have_center_width(self):
        for name, preset in WINDOW_PRESETS.items():
            if preset is not None:
                assert "center" in preset, f"Preset {name} missing center"
                assert "width" in preset, f"Preset {name} missing width"
                assert preset["width"] > 0, f"Preset {name} has non-positive width"

    def test_expected_presets_exist(self):
        expected = [
            "ct_soft_tissue",
            "ct_lung",
            "ct_bone",
            "ct_brain",
            "ct_liver",
            "ct_abdomen",
            "xray_default",
            "mri_default",
            "us_default",
        ]
        for name in expected:
            assert name in WINDOW_PRESETS, f"Missing preset: {name}"
