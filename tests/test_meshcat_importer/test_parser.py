# SPDX-License-Identifier: MIT
"""Tests for meshcat HTML parser."""

import base64
import struct
import zipfile

import pytest


class TestMsgpackDecoder:
    """Tests for msgpack decoder."""

    def test_decode_float32_array(self):
        """Test decoding Float32Array extension type."""
        from meshcat_html_importer.parser.msgpack_decoder import decode_typed_array

        # Create test float32 data
        floats = [1.0, 2.0, 3.0]
        data = struct.pack("<3f", *floats)

        result = decode_typed_array(0x17, data)  # EXT_FLOAT32_ARRAY

        assert len(result) == 3
        assert abs(result[0] - 1.0) < 1e-6
        assert abs(result[1] - 2.0) < 1e-6
        assert abs(result[2] - 3.0) < 1e-6

    def test_decode_int32_array(self):
        """Test decoding Int32Array extension type."""
        from meshcat_html_importer.parser.msgpack_decoder import decode_typed_array

        # Create test int32 data
        ints = [10, 20, 30]
        data = struct.pack("<3i", *ints)

        result = decode_typed_array(0x15, data)  # EXT_INT32_ARRAY

        assert list(result) == [10, 20, 30]

    def test_decode_uint32_array(self):
        """Test decoding Uint32Array extension type."""
        from meshcat_html_importer.parser.msgpack_decoder import decode_typed_array

        # Create test uint32 data
        ints = [100, 200, 300]
        data = struct.pack("<3I", *ints)

        result = decode_typed_array(0x16, data)  # EXT_UINT32_ARRAY

        assert list(result) == [100, 200, 300]


class TestHtmlExtractor:
    """Tests for HTML command extraction."""

    def test_extract_commands_simple(self):
        """Test extracting commands from simple HTML."""
        from meshcat_html_importer.parser.html_extractor import (
            extract_commands_from_html,
        )

        # Create minimal test data
        test_data = b"\x81\xa4type\xa6delete"  # msgpack: {"type": "delete"}
        b64_data = base64.b64encode(test_data).decode()

        html = f'fetch("data:application/octet-binary;base64,{b64_data}")'

        commands = extract_commands_from_html(html)

        assert len(commands) == 1
        assert commands[0] == test_data

    def test_extract_cas_assets(self):
        """Test extracting casAssets dictionary."""
        from meshcat_html_importer.parser.html_extractor import extract_cas_assets

        html = """
        var casAssets = {"sha256-abc": "data:image/png;base64,test123"};
        """

        assets = extract_cas_assets(html)

        assert "sha256-abc" in assets
        assert assets["sha256-abc"] == "data:image/png;base64,test123"

    def test_extract_cas_assets_empty(self):
        """Test extracting when no casAssets present."""
        from meshcat_html_importer.parser.html_extractor import extract_cas_assets

        html = "<html><body>No assets here</body></html>"

        assets = extract_cas_assets(html)

        assert assets == {}

    def test_extract_cas_assets_assignment_format(self):
        """Test extracting casAssets in individual assignment format.

        This format is used by Drake's meshcat recordings:
        casAssets["cas-v1/hash"] = "data:...";
        """
        from meshcat_html_importer.parser.html_extractor import extract_cas_assets

        html = """
        <script>
        casAssets["cas-v1/abc123"] = "data:application/octet-binary;base64,dGVzdA==";
        casAssets["cas-v1/def456"] = "data:image/png;base64,aW1hZ2U=";
        </script>
        """

        assets = extract_cas_assets(html)

        assert len(assets) == 2
        assert "cas-v1/abc123" in assets
        assert (
            assets["cas-v1/abc123"] == "data:application/octet-binary;base64,dGVzdA=="
        )
        assert "cas-v1/def456" in assets
        assert assets["cas-v1/def456"] == "data:image/png;base64,aW1hZ2U="

    def test_load_external_cas_assets(self, tmp_path):
        """Test loading unpacked StaticZip CAS assets next to an HTML file."""
        from meshcat_html_importer.parser.html_extractor import load_external_cas_assets

        html_path = tmp_path / "recording.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        cas_dir = tmp_path / "cas-v1"
        cas_dir.mkdir()
        (cas_dir / "abc123").write_bytes(b"asset-bytes")

        assets = load_external_cas_assets(html_path)

        assert assets == {"cas-v1/abc123": b"asset-bytes"}

    def test_parse_static_zip_recording(self, tmp_path):
        """Test parsing Drake Meshcat::StaticZip recordings directly."""
        from meshcat_html_importer.parser.html_extractor import parse_html_recording

        test_data = b"\x81\xa4type\xa6delete"  # msgpack: {"type": "delete"}
        b64_data = base64.b64encode(test_data).decode()
        html = f'fetch("data:application/octet-binary;base64,{b64_data}")'

        zip_path = tmp_path / "recording.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("recording/scene.html", html)
            zf.writestr("recording/cas-v1/abc123", b"asset-bytes")

        scene_data = parse_html_recording(zip_path)

        assert len(scene_data["commands"]) == 1
        assert scene_data["assets"] == {"cas-v1/abc123": b"asset-bytes"}

    def test_parse_static_zip_recording_with_meshcat_suffix(self, tmp_path):
        """Test parsing renamed StaticZip archives for Blender drag-and-drop."""
        from meshcat_html_importer.parser.html_extractor import parse_html_recording

        test_data = b"\x81\xa4type\xa6delete"  # msgpack: {"type": "delete"}
        b64_data = base64.b64encode(test_data).decode()
        html = f'fetch("data:application/octet-binary;base64,{b64_data}")'

        recording_path = tmp_path / "recording.meshcat"
        with zipfile.ZipFile(recording_path, "w") as zf:
            zf.writestr("recording/scene.html", html)
            zf.writestr("recording/cas-v1/abc123", b"asset-bytes")

        scene_data = parse_html_recording(recording_path)

        assert len(scene_data["commands"]) == 1
        assert scene_data["assets"] == {"cas-v1/abc123": b"asset-bytes"}


class TestCommandTypes:
    """Tests for command type parsing."""

    def test_command_from_dict_set_object(self):
        """Test parsing set_object command."""
        from meshcat_html_importer.parser.command_types import Command, CommandType

        data = {
            "type": "set_object",
            "path": "/meshcat/box",
            "object": {"type": "Mesh"},
        }

        cmd = Command.from_dict(data)

        assert cmd.type == CommandType.SET_OBJECT
        assert cmd.path == "/meshcat/box"

    def test_command_from_dict_set_transform(self):
        """Test parsing set_transform command."""
        from meshcat_html_importer.parser.command_types import Command, CommandType

        data = {
            "type": "set_transform",
            "path": "/meshcat/box",
            "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        }

        cmd = Command.from_dict(data)

        assert cmd.type == CommandType.SET_TRANSFORM
        assert cmd.path == "/meshcat/box"

    def test_command_from_dict_unknown_type(self):
        """Test parsing unknown command type raises error."""
        from meshcat_html_importer.parser.command_types import Command

        data = {"type": "unknown_command", "path": "/test"}

        with pytest.raises(ValueError):
            Command.from_dict(data)


class TestAssetResolver:
    """Tests for asset resolver."""

    def test_resolve_data_uri(self):
        """Test resolving a data URI."""
        from meshcat_html_importer.parser.asset_resolver import AssetResolver

        assets = {"test-hash": "data:text/plain;base64,SGVsbG8="}
        resolver = AssetResolver(assets)

        result = resolver.resolve("test-hash")

        assert result is not None
        assert result.data == b"Hello"
        assert result.mime_type == "text/plain"

    def test_resolve_missing_asset(self):
        """Test resolving missing asset returns None."""
        from meshcat_html_importer.parser.asset_resolver import AssetResolver

        resolver = AssetResolver({})

        result = resolver.resolve("nonexistent")

        assert result is None
