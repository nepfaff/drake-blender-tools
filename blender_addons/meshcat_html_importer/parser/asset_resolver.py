# SPDX-License-Identifier: MIT
"""Resolve asset references in meshcat commands."""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
from dataclasses import dataclass
from typing import Any

# Data URI pattern: data:<mimetype>;base64,<data>
DATA_URI_PATTERN = re.compile(r"data:([^;,]+)(?:;([^,]+))?,(.+)", re.DOTALL)


@dataclass
class ResolvedAsset:
    """A resolved asset with its decoded data."""

    mime_type: str
    data: bytes
    hash: str


class AssetResolver:
    """Resolves asset references from casAssets dictionary."""

    def __init__(self, cas_assets: dict[str, str | bytes]):
        """Initialize with casAssets dictionary.

        Args:
            cas_assets: Dictionary mapping hash -> data URI or raw bytes
        """
        self._assets = cas_assets
        self._cache: dict[str, ResolvedAsset] = {}

    def resolve(self, key: str) -> ResolvedAsset | None:
        """Resolve an asset by its hash key.

        Args:
            key: The hash key (e.g., "sha256-...")

        Returns:
            ResolvedAsset with decoded data, or None if not found
        """
        if key in self._cache:
            return self._cache[key]

        asset = self._assets.get(key)
        if asset is None:
            return None

        if isinstance(asset, bytes):
            resolved = ResolvedAsset(
                mime_type=_guess_mime_type(key),
                data=asset,
                hash=key,
            )
        else:
            resolved = self._parse_data_uri(asset, key)

        if resolved:
            self._cache[key] = resolved

        return resolved

    def resolve_data_uri(self, data_uri: str) -> ResolvedAsset | None:
        """Resolve a data URI directly.

        Args:
            data_uri: A data URI string

        Returns:
            ResolvedAsset with decoded data, or None if invalid
        """
        # Generate hash for caching
        hash_key = hashlib.sha256(data_uri.encode()).hexdigest()[:16]

        if hash_key in self._cache:
            return self._cache[hash_key]

        resolved = self._parse_data_uri(data_uri, hash_key)
        if resolved:
            self._cache[hash_key] = resolved

        return resolved

    def _parse_data_uri(self, data_uri: str, hash_key: str) -> ResolvedAsset | None:
        """Parse a data URI into its components.

        Args:
            data_uri: The data URI string
            hash_key: Hash key for the asset

        Returns:
            ResolvedAsset or None if parsing fails
        """
        match = DATA_URI_PATTERN.match(data_uri)
        if not match:
            return None

        mime_type = match.group(1)
        encoding = match.group(2)  # Usually "base64"
        data_str = match.group(3)

        try:
            if encoding == "base64":
                data = base64.b64decode(data_str)
            else:
                # Assume URL-encoded or raw
                data = data_str.encode("utf-8")
        except Exception as e:
            print(f"Warning: Failed to decode asset {hash_key}: {e}")
            return None

        return ResolvedAsset(
            mime_type=mime_type,
            data=data,
            hash=hash_key,
        )

    def get_all_keys(self) -> list[str]:
        """Get all available asset keys."""
        return list(self._assets.keys())


def _guess_mime_type(key: str) -> str:
    """Guess a MIME type for raw external StaticZip assets."""
    mime_type, _ = mimetypes.guess_type(key)
    return mime_type or "application/octet-binary"


def extract_texture_uuid(material_data: dict[str, Any]) -> str | None:
    """Extract texture UUID from material data if present.

    Args:
        material_data: Material dictionary from meshcat

    Returns:
        UUID string or None
    """
    # Check for map property (diffuse texture)
    map_data = material_data.get("map")
    if isinstance(map_data, dict):
        return map_data.get("uuid")

    return None


def extract_image_from_texture(
    texture_data: dict[str, Any],
    resolver: AssetResolver,
) -> bytes | None:
    """Extract image data from a texture definition.

    Args:
        texture_data: Texture dictionary from meshcat
        resolver: AssetResolver for loading assets

    Returns:
        Raw image bytes or None
    """
    # Texture may have an image property with a URL or data URI
    image_data = texture_data.get("image")
    if not image_data:
        return None

    url = image_data.get("url")
    if not url:
        return None

    # Check if it's a data URI
    if url.startswith("data:"):
        resolved = resolver.resolve_data_uri(url)
        if resolved:
            return resolved.data

    # Check if it's a casAssets reference
    resolved = resolver.resolve(url)
    if resolved:
        return resolved.data

    return None
