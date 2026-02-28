"""Tests for canary GUID system."""

from radslice.canary import (
    RADSLICE_CANARY_GUID,
    check_for_canary,
    embed_canary_in_json,
    get_canary_guid,
)


class TestCanaryGUID:
    """Test canary GUID operations."""

    def test_guid_format(self):
        guid = get_canary_guid()
        assert isinstance(guid, str)
        # UUID format: 8-4-4-4-12
        parts = guid.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_guid_is_constant(self):
        assert get_canary_guid() == get_canary_guid()
        assert get_canary_guid() == RADSLICE_CANARY_GUID

    def test_guid_distinct_from_scribegoat2(self):
        """RadSlice canary must be distinct from ScribeGoat2's."""
        scribegoat2_canary = "7f3a9c2e"  # prefix of ScribeGoat2's canary
        assert not get_canary_guid().startswith(scribegoat2_canary)

    def test_embed_canary(self):
        data = {"id": "XRAY-001", "metadata": {"key": "value"}}
        result = embed_canary_in_json(data)
        assert result["metadata"]["_canary"] == RADSLICE_CANARY_GUID
        # Original metadata preserved
        assert result["metadata"]["key"] == "value"
        # Original dict not modified
        assert "_canary" not in data["metadata"]

    def test_embed_canary_no_metadata(self):
        data = {"id": "XRAY-001"}
        result = embed_canary_in_json(data)
        assert result["metadata"]["_canary"] == RADSLICE_CANARY_GUID

    def test_check_for_canary_present(self):
        text = f"Some model output containing {RADSLICE_CANARY_GUID} leaked"
        assert check_for_canary(text) is True

    def test_check_for_canary_absent(self):
        text = "Normal model output without any canary"
        assert check_for_canary(text) is False

    def test_check_for_canary_empty(self):
        assert check_for_canary("") is False

    def test_embed_and_check_roundtrip(self):
        """Embedded canary should be detectable in serialized output."""
        import json

        data = {"id": "test"}
        embedded = embed_canary_in_json(data)
        serialized = json.dumps(embedded)
        assert check_for_canary(serialized) is True
