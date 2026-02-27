"""Tests for image.py — image loading, encoding, and resize."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from radslice.image import (
    MAX_DIMENSION,
    SUPPORTED_FORMATS,
    EncodedImage,
    encode_bytes,
    load_and_encode,
    resize_if_needed,
)


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
