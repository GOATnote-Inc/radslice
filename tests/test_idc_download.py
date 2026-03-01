"""Tests for IDC downloader with mocked HTTP and idc-index."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from corpus.download import _download_idc


@pytest.fixture
def output_dir(tmp_path) -> Path:
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    return img_dir


@pytest.fixture
def sample_idc_images() -> dict[str, dict]:
    return {
        "ct/idc/chest-ct-nodule.dcm": {
            "source": "idc",
            "source_id": "LIDC-IDRI-0001",
            "series_uid": "1.3.6.1.4.1.14519.5.2.1.6279.6001.179049373636438705059720603192",
            "url": "https://example.com/idc/lidc.dcm",
            "license": "CC-BY-4.0",
        },
        "ct/idc/abdomen-ct-liver.dcm": {
            "source": "idc",
            "source_id": "TCGA-LIHC-0001",
            "url": "https://example.com/idc/tcga.dcm",
            "license": "CC-BY-4.0",
        },
        # Should be ignored — different source
        "ct/openem/test.png": {
            "source": "omnimedvqa-open",
            "url": "https://example.com/omni.png",
        },
    }


class TestIDCDownloader:
    """Tests for _download_idc function."""

    def test_dry_run_skips_download(self, sample_idc_images, output_dir):
        stats = _download_idc(sample_idc_images, output_dir, dry_run=True)
        assert stats["downloaded"] == 0
        assert stats["skipped"] == 2
        assert stats["failed"] == 0

    def test_filters_to_idc_source(self, output_dir):
        images = {
            "ct/other/test.png": {
                "source": "omnimedvqa-open",
                "url": "https://example.com/test.png",
            },
        }
        stats = _download_idc(images, output_dir)
        assert stats == {"downloaded": 0, "skipped": 0, "failed": 0}

    def test_skips_existing_files(self, sample_idc_images, output_dir):
        dest = output_dir / "ct/idc/abdomen-ct-liver.dcm"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake dicom data")

        images = {
            "ct/idc/abdomen-ct-liver.dcm": sample_idc_images["ct/idc/abdomen-ct-liver.dcm"]
        }
        stats = _download_idc(images, output_dir)
        assert stats["skipped"] == 1

    @patch("corpus.download._download_url")
    def test_fallback_to_url_without_idc_index(self, mock_dl, sample_idc_images, output_dir):
        """When idc-index is not installed, falls back to URL download."""
        mock_dl.return_value = True

        images = {
            "ct/idc/abdomen-ct-liver.dcm": sample_idc_images["ct/idc/abdomen-ct-liver.dcm"]
        }
        stats = _download_idc(images, output_dir)
        assert stats["downloaded"] == 1
        assert mock_dl.called

    @patch("corpus.download._download_url")
    def test_url_download_failure(self, mock_dl, output_dir):
        mock_dl.return_value = False

        images = {
            "ct/idc/test.dcm": {
                "source": "idc",
                "url": "https://example.com/fail.dcm",
            },
        }
        stats = _download_idc(images, output_dir)
        assert stats["failed"] == 1

    def test_no_url_and_no_idc_client_fails(self, output_dir):
        images = {
            "ct/idc/no-url.dcm": {
                "source": "idc",
                # No url, no series_uid
            },
        }
        stats = _download_idc(images, output_dir)
        assert stats["failed"] == 1

    @patch("corpus.download._download_url")
    def test_checksum_verification(self, mock_dl, output_dir):
        mock_dl.return_value = True

        images = {
            "ct/idc/bad-hash.dcm": {
                "source": "idc",
                "url": "https://example.com/bad.dcm",
                "sha256": "wrong_hash",
            },
        }

        dest = output_dir / "ct/idc/bad-hash.dcm"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"bad data")

        stats = _download_idc(images, output_dir)
        assert stats["failed"] == 1
        assert not dest.exists()

    def test_empty_images_dict(self, output_dir):
        stats = _download_idc({}, output_dir)
        assert stats == {"downloaded": 0, "skipped": 0, "failed": 0}

    @patch("corpus.download._download_url")
    def test_idc_index_import_graceful(self, mock_dl, sample_idc_images, output_dir):
        """idc-index import failure should be handled gracefully."""
        mock_dl.return_value = True

        # The function should work even when idc_index is not installed
        images = {
            "ct/idc/abdomen-ct-liver.dcm": sample_idc_images["ct/idc/abdomen-ct-liver.dcm"]
        }
        stats = _download_idc(images, output_dir)
        assert stats["downloaded"] == 1
