# SPDX-License-Identifier: MIT
"""Extract msgpack commands and assets from meshcat HTML recordings."""

from __future__ import annotations

import base64
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .command_types import Command
from .msgpack_decoder import decode_msgpack

# Pattern to match base64 msgpack data URIs
# fetch("data:application/octet-binary;base64,<DATA>")
FETCH_PATTERN = re.compile(
    r'fetch\s*\(\s*["\']data:application/octet-binary;base64,([A-Za-z0-9+/=]+)["\']\s*\)'
)

# Pattern to match casAssets dictionary (old format)
# var casAssets = {"sha256-hash": "data:..."};
CAS_ASSETS_DICT_PATTERN = re.compile(r"var\s+casAssets\s*=\s*(\{.*?\})\s*;", re.DOTALL)

# Pattern to extract individual asset entries from object literal
ASSET_ENTRY_PATTERN = re.compile(r'"([^"]+)"\s*:\s*"([^"]*)"')

# Pattern to match individual casAssets assignments (new format)
# casAssets["cas-v1/hash"] = "data:...";
CAS_ASSETS_ASSIGNMENT_PATTERN = re.compile(r'casAssets\["([^"]+)"\]\s*=\s*"([^"]*)"')

HTML_SUFFIXES = (".html", ".htm")
STATIC_CAS_DIR = "cas-v1"


def extract_commands_from_html(html_content: str) -> list[bytes]:
    """Extract base64-encoded msgpack commands from HTML.

    Args:
        html_content: The HTML file content as a string

    Returns:
        List of decoded msgpack bytes
    """
    matches = FETCH_PATTERN.findall(html_content)
    commands = []

    for base64_data in matches:
        try:
            decoded = base64.b64decode(base64_data)
            commands.append(decoded)
        except Exception as e:
            print(f"Warning: Failed to decode base64 data: {e}")
            continue

    return commands


def extract_cas_assets(html_content: str) -> dict[str, str]:
    """Extract the casAssets dictionary from HTML.

    casAssets contains embedded textures and mesh files as data URIs,
    keyed by their SHA256 hash.

    Supports two formats:
    1. Object literal: var casAssets = {"hash": "data:...", ...};
    2. Individual assignments: casAssets["hash"] = "data:...";

    Args:
        html_content: The HTML file content as a string

    Returns:
        Dictionary mapping hash strings to data URIs
    """
    assets = {}

    # Try object literal format first
    match = CAS_ASSETS_DICT_PATTERN.search(html_content)
    if match:
        assets_str = match.group(1)
        for entry_match in ASSET_ENTRY_PATTERN.finditer(assets_str):
            key = entry_match.group(1)
            value = entry_match.group(2)
            assets[key] = value

    # Also try individual assignment format
    for entry_match in CAS_ASSETS_ASSIGNMENT_PATTERN.finditer(html_content):
        key = entry_match.group(1)
        value = entry_match.group(2)
        assets[key] = value

    return assets


def load_external_cas_assets(html_path: Path | str) -> dict[str, bytes]:
    """Load sibling ``cas-v1`` assets for Drake ``Meshcat::StaticZip`` output.

    StaticZip recordings can be unpacked to an HTML file next to a ``cas-v1``
    directory. Meshcat commands reference those files by relative URI, e.g.
    ``cas-v1/<hash>``.

    Args:
        html_path: Path to the HTML file inside the unpacked StaticZip output

    Returns:
        Dictionary mapping relative CAS paths to raw bytes
    """
    html_path = Path(html_path)
    cas_dir = html_path.parent / STATIC_CAS_DIR
    if not cas_dir.is_dir():
        return {}

    assets: dict[str, bytes] = {}
    for asset_path in cas_dir.rglob("*"):
        if not asset_path.is_file():
            continue

        key = asset_path.relative_to(html_path.parent).as_posix()
        assets[key] = asset_path.read_bytes()

    return assets


def parse_commands(raw_commands: list[bytes]) -> list[Command]:
    """Parse raw msgpack bytes into Command objects.

    Args:
        raw_commands: List of msgpack-encoded command bytes

    Returns:
        List of parsed Command objects
    """
    commands = []

    for raw in raw_commands:
        try:
            decoded = decode_msgpack(raw)
            if isinstance(decoded, dict):
                cmd = Command.from_dict(decoded)
                commands.append(cmd)
        except Exception as e:
            print(f"Warning: Failed to parse command: {e}")
            continue

    return commands


def parse_html_recording(recording_path: Path | str) -> dict[str, Any]:
    """Parse a complete meshcat HTML or StaticZip recording.

    Args:
        recording_path: Path to the HTML file or Drake ``Meshcat::StaticZip`` file

    Returns:
        Dictionary containing:
        - commands: List of parsed Command objects
        - assets: Dictionary of casAssets (hash -> data URI or raw bytes)
        - raw_commands: List of raw decoded command dicts (for debugging)
    """
    recording_path = Path(recording_path)
    html_content, external_assets = _read_recording_content(recording_path)

    # Extract raw command bytes
    raw_bytes = extract_commands_from_html(html_content)

    # Decode commands to dicts for inspection
    raw_commands = []
    for raw in raw_bytes:
        try:
            decoded = decode_msgpack(raw)
            raw_commands.append(decoded)
        except Exception:
            continue

    # Parse into Command objects
    commands = parse_commands(raw_bytes)

    # Extract assets. Embedded assets take precedence over same-named external
    # files to preserve the legacy single-file HTML behavior.
    assets: dict[str, str | bytes] = dict(external_assets)
    assets.update(extract_cas_assets(html_content))

    # Extract animation FPS from set_animation commands
    animation_fps = 64.0  # Drake default
    for cmd in commands:
        if cmd.type.value == "set_animation":
            options = cmd.data.get("options", {})
            # Check options first: Drake uses "fps", meshcat.js uses "play_fps"
            fps = options.get("fps") or options.get("play_fps")
            # Fall back to the clip-level fps from the first animation
            if not fps:
                animations = cmd.data.get("animations", [])
                if animations:
                    fps = animations[0].get("clip", {}).get("fps")
            if fps:
                animation_fps = float(fps)
                break

    return {
        "commands": commands,
        "assets": assets,
        "raw_commands": raw_commands,
        "animation_fps": animation_fps,
    }


def _read_recording_content(recording_path: Path) -> tuple[str, dict[str, bytes]]:
    """Read HTML content and external CAS assets from an HTML or ZIP recording."""
    if zipfile.is_zipfile(recording_path):
        return _read_static_zip_recording(recording_path)

    html_content = recording_path.read_text(encoding="utf-8")
    return html_content, load_external_cas_assets(recording_path)


def _read_static_zip_recording(zip_path: Path) -> tuple[str, dict[str, bytes]]:
    """Read a Drake StaticZip recording without extracting it to disk."""
    with zipfile.ZipFile(zip_path) as zf:
        html_member = _select_html_member(zf.namelist())
        html_content = zf.read(html_member).decode("utf-8")
        assets = _load_zip_cas_assets(zf, html_member)

    return html_content, assets


def _select_html_member(names: list[str]) -> str:
    """Choose the meshcat HTML member from a StaticZip archive."""
    html_members = [
        name
        for name in names
        if not name.endswith("/")
        and not name.startswith("__MACOSX/")
        and PurePosixPath(name).suffix.lower() in HTML_SUFFIXES
    ]

    if not html_members:
        raise ValueError("StaticZip archive does not contain an HTML file")

    if len(html_members) == 1:
        return html_members[0]

    for preferred_name in ("meshcat.html", "index.html"):
        preferred = [
            name
            for name in html_members
            if PurePosixPath(name).name.lower() == preferred_name
        ]
        if len(preferred) == 1:
            return preferred[0]

    return sorted(html_members, key=lambda name: (name.count("/"), len(name), name))[0]


def _load_zip_cas_assets(
    zf: zipfile.ZipFile,
    html_member: str,
) -> dict[str, bytes]:
    """Load ``cas-v1`` files from the same ZIP directory as the HTML member."""
    html_parent = PurePosixPath(html_member).parent
    html_parent_prefix = "" if str(html_parent) == "." else f"{html_parent.as_posix()}/"

    assets: dict[str, bytes] = {}
    for name in zf.namelist():
        if name.endswith("/") or not name.startswith(html_parent_prefix):
            continue

        relative_name = name[len(html_parent_prefix) :]
        if not relative_name.startswith(f"{STATIC_CAS_DIR}/"):
            continue

        assets[relative_name] = zf.read(name)

    return assets
