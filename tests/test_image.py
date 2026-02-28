"""Tests for image.py — image loading, encoding, and resize."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from radslice.image import (
    MAX_DIMENSION,
    SUPPORTED_FORMATS,
    EncodedImage,
    detect_format,
    encode_bytes,
    load_and_encode,
    resize_if_needed,
)

pydicom = pytest.importorskip("pydicom")
from pydicom.dataset import Dataset, FileDataset  # noqa: E402
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian  # noqa: E402


@pytest.fixture
def small_image(tmp_path):
    """Create a small test image."""
    img = Image.new("RGB", (100, 100), color="red")
    path = tmp_path / "small.png"
    img.save(path)
    return path


@pytest.fixture
def large_image(tmp_path):
    """Create a large test image that needs resizing."""
    img = Image.new("RGB", (4096, 3072), color="blue")
    path = tmp_path / "large.png"
    img.save(path)
    return path


@pytest.fixture
def rgba_image(tmp_path):
    """Create an RGBA test image."""
    img = Image.new("RGBA", (200, 200), color=(255, 0, 0, 128))
    path = tmp_path / "rgba.png"
    img.save(path)
    return path


class TestResizeIfNeeded:
    def test_no_resize_small(self):
        img = Image.new("RGB", (100, 100))
        result = resize_if_needed(img)
        assert result.size == (100, 100)

    def test_resize_large_width(self):
        img = Image.new("RGB", (4000, 2000))
        result = resize_if_needed(img)
        assert result.size[0] <= MAX_DIMENSION
        assert result.size[1] <= MAX_DIMENSION

    def test_resize_large_height(self):
        img = Image.new("RGB", (1000, 4000))
        result = resize_if_needed(img)
        assert result.size[0] <= MAX_DIMENSION
        assert result.size[1] <= MAX_DIMENSION

    def test_preserves_aspect_ratio(self):
        img = Image.new("RGB", (4000, 2000))
        result = resize_if_needed(img)
        original_ratio = 4000 / 2000
        result_ratio = result.size[0] / result.size[1]
        assert abs(original_ratio - result_ratio) < 0.01

    def test_exact_boundary(self):
        img = Image.new("RGB", (MAX_DIMENSION, MAX_DIMENSION))
        result = resize_if_needed(img)
        assert result.size == (MAX_DIMENSION, MAX_DIMENSION)

    def test_custom_max_dim(self):
        img = Image.new("RGB", (500, 500))
        result = resize_if_needed(img, max_dim=200)
        assert result.size[0] <= 200
        assert result.size[1] <= 200


class TestLoadAndEncode:
    def test_small_image(self, small_image):
        encoded = load_and_encode(small_image)
        assert isinstance(encoded, EncodedImage)
        assert encoded.width == 100
        assert encoded.height == 100
        assert encoded.media_type == "image/png"
        assert len(encoded.base64_data) > 0
        # Verify base64 is valid
        decoded = base64.b64decode(encoded.base64_data)
        assert len(decoded) > 0

    def test_large_image_resized(self, large_image):
        encoded = load_and_encode(large_image)
        assert encoded.width <= MAX_DIMENSION
        assert encoded.height <= MAX_DIMENSION

    def test_rgba_to_png(self, rgba_image):
        encoded = load_and_encode(rgba_image, output_format="PNG")
        assert encoded.media_type == "image/png"

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_and_encode(tmp_path / "nonexistent.png")

    def test_unsupported_format(self, tmp_path):
        path = tmp_path / "test.xyz"
        path.write_bytes(b"not an image")
        with pytest.raises(ValueError, match="Unsupported"):
            load_and_encode(path)

    def test_original_path_stored(self, small_image):
        encoded = load_and_encode(small_image)
        assert encoded.original_path == str(small_image)


class TestEncodeBytes:
    def test_encode_png_bytes(self):
        img = Image.new("RGB", (50, 50), color="green")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded = encode_bytes(buf.getvalue(), media_type="image/png")
        assert encoded.width == 50
        assert encoded.height == 50
        assert encoded.media_type == "image/png"
        assert encoded.original_path == "<bytes>"

    def test_encode_with_resize(self):
        img = Image.new("RGB", (5000, 3000), color="yellow")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded = encode_bytes(buf.getvalue(), max_dim=1024)
        assert encoded.width <= 1024
        assert encoded.height <= 1024


class TestEncodedImageFrozen:
    def test_frozen(self):
        enc = EncodedImage(
            base64_data="abc",
            media_type="image/png",
            width=100,
            height=100,
            original_path="test.png",
        )
        with pytest.raises(AttributeError):
            enc.width = 200


class TestSupportedFormats:
    def test_common_formats(self):
        assert "png" in SUPPORTED_FORMATS
        assert "jpg" in SUPPORTED_FORMATS
        assert "jpeg" in SUPPORTED_FORMATS
        assert "gif" in SUPPORTED_FORMATS
        assert "webp" in SUPPORTED_FORMATS

    def test_dicom_formats(self):
        assert "dcm" in SUPPORTED_FORMATS
        assert "dicom" in SUPPORTED_FORMATS


# --- DICOM integration helpers ---


def _make_and_save_dicom(tmp_path: Path, filename: str = "test.dcm") -> Path:
    """Create a minimal synthetic DICOM and save to disk."""
    ds = Dataset()
    ds.Modality = "CT"
    ds.Rows = 32
    ds.Columns = 32
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.SamplesPerPixel = 1
    ds.RescaleSlope = 1.0
    ds.RescaleIntercept = -1024.0
    ds.WindowCenter = 40.0
    ds.WindowWidth = 80.0

    arr = np.random.randint(-100, 1000, (32, 32), dtype=np.int16)
    ds.PixelData = arr.tobytes()

    ds.SOPClassUID = CTImageStorage
    ds.file_meta = pydicom.Dataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    path = tmp_path / filename
    fds = FileDataset(str(path), ds, file_meta=ds.file_meta, preamble=b"\x00" * 128)
    fds.save_as(str(path))
    return path


class TestDetectFormat:
    def test_dcm_extension(self, tmp_path):
        path = tmp_path / "test.dcm"
        path.write_bytes(b"dummy")
        assert detect_format(path) == "dicom"

    def test_dicom_extension(self, tmp_path):
        path = tmp_path / "test.dicom"
        path.write_bytes(b"dummy")
        assert detect_format(path) == "dicom"

    def test_png_extension(self, tmp_path):
        path = tmp_path / "test.png"
        path.write_bytes(b"dummy")
        assert detect_format(path) == "raster"

    def test_dicom_magic_bytes(self, tmp_path):
        """File with DICOM magic bytes but no .dcm extension."""
        path = tmp_path / "test.img"
        data = b"\x00" * 128 + b"DICM" + b"\x00" * 100
        path.write_bytes(data)
        assert detect_format(path) == "dicom"


class TestLoadAndEncodeDicom:
    def test_load_dicom_file(self, tmp_path):
        path = _make_and_save_dicom(tmp_path)
        encoded = load_and_encode(path)
        assert isinstance(encoded, EncodedImage)
        assert encoded.width == 32
        assert encoded.height == 32
        assert encoded.media_type == "image/png"
        assert len(encoded.base64_data) > 0

    def test_load_dicom_with_window_preset(self, tmp_path):
        path = _make_and_save_dicom(tmp_path)
        encoded = load_and_encode(path, window_preset="ct_brain")
        assert isinstance(encoded, EncodedImage)
        # Verify it produces valid base64
        decoded = base64.b64decode(encoded.base64_data)
        assert len(decoded) > 0

    def test_dicom_roundtrip(self, tmp_path):
        """DICOM → EncodedImage → base64 → decode → verify pixel range."""
        path = _make_and_save_dicom(tmp_path)
        encoded = load_and_encode(path)
        decoded_bytes = base64.b64decode(encoded.base64_data)
        img = Image.open(io.BytesIO(decoded_bytes))
        arr = np.array(img)
        assert arr.min() >= 0
        assert arr.max() <= 255

    def test_dicom_original_path(self, tmp_path):
        path = _make_and_save_dicom(tmp_path)
        encoded = load_and_encode(path)
        assert encoded.original_path == str(path)
