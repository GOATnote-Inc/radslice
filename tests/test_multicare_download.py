"""Tests for MultiCaRe downloader with mocked HTTP."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from corpus.download import (
    _download_multicare,
    compute_sha256,
    verify_checksum,
)


@pytest.fixture
def output_dir(tmp_path) -> Path:
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    return img_dir


@pytest.fixture
def sample_images() -> dict[str, dict]:
    return {
        "ct/multicare/hepatic-steatosis.png": {
            "source": "multicare",
            "source_id": "PMC7890123_fig2",
            "url": "https://example.com/pmc/fig2.png",
            "license": "CC-BY-4.0",
        },
        "ct/multicare/pulmonary-nodule.png": {
            "source": "multicare",
            "source_id": "PMC8901234_fig1",
            "url": "https://example.com/pmc/fig1.png",
            "sha256": "abcd1234",
            "license": "CC-BY-4.0",
        },
        # Should be ignored — different source
        "ct/openem/test.png": {
            "source": "omnimedvqa-open",
            "url": "https://example.com/omni.png",
        },
    }


class TestMultiCareDownloader:
    """Tests for _download_multicare function."""

    def test_dry_run_skips_download(self, sample_images, output_dir):
        stats = _download_multicare(sample_images, output_dir, dry_run=True)
        assert stats["downloaded"] == 0
        assert stats["skipped"] == 2
        assert stats["failed"] == 0

    def test_filters_to_multicare_source(self, output_dir):
        images = {
            "ct/other/test.png": {
                "source": "omnimedvqa-open",
                "url": "https://example.com/test.png",
            },
        }
        stats = _download_multicare(images, output_dir)
        assert stats == {"downloaded": 0, "skipped": 0, "failed": 0}

    def test_skips_existing_files(self, sample_images, output_dir):
        # Create the file so it gets skipped (no sha256 on first entry)
        dest = output_dir / "ct/multicare/hepatic-steatosis.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake image data")

        stats = _download_multicare(
            {"ct/multicare/hepatic-steatosis.png": sample_images["ct/multicare/hepatic-steatosis.png"]},
            output_dir,
        )
        assert stats["skipped"] == 1
        assert stats["downloaded"] == 0

    @patch("corpus.download._download_url")
    def test_successful_download(self, mock_dl, sample_images, output_dir):
        mock_dl.return_value = True

        # Only the entry without sha256
        images = {"ct/multicare/hepatic-steatosis.png": sample_images["ct/multicare/hepatic-steatosis.png"]}
        stats = _download_multicare(images, output_dir)

        assert stats["downloaded"] == 1
        assert mock_dl.called

    @patch("corpus.download._download_url")
    def test_failed_download(self, mock_dl, output_dir):
        mock_dl.return_value = False

        images = {
            "ct/multicare/test.png": {
                "source": "multicare",
                "url": "https://example.com/fail.png",
            },
        }
        stats = _download_multicare(images, output_dir)
        assert stats["failed"] == 1
        assert stats["downloaded"] == 0

    def test_no_url_fails(self, output_dir):
        images = {
            "ct/multicare/no-url.png": {
                "source": "multicare",
                # No url!
            },
        }
        stats = _download_multicare(images, output_dir)
        assert stats["failed"] == 1

    @patch("corpus.download._download_url")
    def test_checksum_verification_after_download(self, mock_dl, output_dir):
        """When sha256 is specified and doesn't match, file is deleted."""
        mock_dl.return_value = True

        images = {
            "ct/multicare/bad-hash.png": {
                "source": "multicare",
                "url": "https://example.com/bad.png",
                "sha256": "definitely_not_matching",
            },
        }

        # Create the file that _download_url would "write"
        dest = output_dir / "ct/multicare/bad-hash.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"bad data")

        stats = _download_multicare(images, output_dir)
        assert stats["failed"] == 1
        assert not dest.exists()  # Should be cleaned up

    def test_empty_images_dict(self, output_dir):
        stats = _download_multicare({}, output_dir)
        assert stats == {"downloaded": 0, "skipped": 0, "failed": 0}
