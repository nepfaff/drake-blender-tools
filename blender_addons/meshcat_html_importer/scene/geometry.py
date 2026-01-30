# SPDX-License-Identifier: MIT
"""Geometry parsing for meshcat objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class GeometryType(Enum):
    """Types of geometry supported by meshcat."""

    BUFFER_GEOMETRY = "BufferGeometry"
    BOX = "BoxGeometry"
    SPHERE = "SphereGeometry"
    CYLINDER = "CylinderGeometry"
    PLANE = "PlaneGeometry"
    MESHFILE = "_meshfile_geometry"


@dataclass
class MeshGeometry:
    """A mesh geometry with vertices, normals, UVs, and indices."""

    positions: np.ndarray  # Nx3 array of vertex positions
    normals: np.ndarray | None = None  # Nx3 array of vertex normals
    uvs: np.ndarray | None = None  # Nx2 array of texture coordinates
    indices: np.ndarray | None = None  # Triangle indices

    def validate(self) -> bool:
        """Check if geometry data is valid."""
        if self.positions is None or len(self.positions) == 0:
            return False
        if len(self.positions.shape) != 2 or self.positions.shape[1] != 3:
            return False
        return True


@dataclass
class PrimitiveGeometry:
    """A primitive geometry (box, sphere, cylinder, etc.)."""

    geometry_type: GeometryType
    # Box parameters
    width: float = 1.0
    height: float = 1.0
    depth: float = 1.0
    # Sphere parameters
    radius: float = 1.0
    width_segments: int = 32
    height_segments: int = 16
    # Cylinder parameters
    radius_top: float = 1.0
    radius_bottom: float = 1.0
    radial_segments: int = 32
    # Plane parameters
    # (uses width, height)


@dataclass
class MeshFileGeometry:
    """A geometry loaded from an embedded mesh file (glTF, OBJ)."""

    format: str  # "gltf" or "obj"
    data: bytes
    resources: dict[str, bytes] = field(default_factory=dict)


def parse_geometry(
    geom_data: dict[str, Any],
    cas_assets: dict[str, str] | None = None,
) -> MeshGeometry | PrimitiveGeometry | MeshFileGeometry | None:
    """Parse geometry data from a meshcat object.

    Args:
        geom_data: Geometry dictionary from meshcat command
        cas_assets: Dictionary of CAS assets (hash -> data URI) for resolving
            external references in meshfile geometries

    Returns:
        Parsed geometry object or None if unsupported
    """
    geom_type = geom_data.get("type", "")

    if geom_type == "BufferGeometry":
        return _parse_buffer_geometry(geom_data)
    elif geom_type == "BoxGeometry":
        return _parse_box_geometry(geom_data)
    elif geom_type == "BoxBufferGeometry":
        return _parse_box_geometry(geom_data)
    elif geom_type == "SphereGeometry":
        return _parse_sphere_geometry(geom_data)
    elif geom_type == "SphereBufferGeometry":
        return _parse_sphere_geometry(geom_data)
    elif geom_type == "CylinderGeometry":
        return _parse_cylinder_geometry(geom_data)
    elif geom_type == "CylinderBufferGeometry":
        return _parse_cylinder_geometry(geom_data)
    elif geom_type == "PlaneGeometry":
        return _parse_plane_geometry(geom_data)
    elif geom_type == "PlaneBufferGeometry":
        return _parse_plane_geometry(geom_data)
    elif geom_type == "_meshfile_geometry":
        return _parse_meshfile_geometry(geom_data, cas_assets)
    else:
        print(f"Warning: Unsupported geometry type: {geom_type}")
        return None


def _parse_buffer_geometry(geom_data: dict[str, Any]) -> MeshGeometry | None:
    """Parse a BufferGeometry."""
    data = geom_data.get("data", {})
    attributes = data.get("attributes", {})

    # Extract position data
    position_attr = attributes.get("position", {})
    position_array = position_attr.get("array")

    if position_array is None:
        return None

    # Convert to numpy and reshape
    if isinstance(position_array, np.ndarray):
        positions = position_array.astype(np.float32)
    else:
        positions = np.array(position_array, dtype=np.float32)

    item_size = position_attr.get("itemSize", 3)
    positions = positions.reshape(-1, item_size)

    # Extract normals
    normals = None
    normal_attr = attributes.get("normal", {})
    normal_array = normal_attr.get("array")
    if normal_array is not None:
        if isinstance(normal_array, np.ndarray):
            normals = normal_array.astype(np.float32)
        else:
            normals = np.array(normal_array, dtype=np.float32)
        normals = normals.reshape(-1, 3)

    # Extract UVs
    uvs = None
    uv_attr = attributes.get("uv", {})
    uv_array = uv_attr.get("array")
    if uv_array is not None:
        if isinstance(uv_array, np.ndarray):
            uvs = uv_array.astype(np.float32)
        else:
            uvs = np.array(uv_array, dtype=np.float32)
        uvs = uvs.reshape(-1, 2)

    # Extract indices
    indices = None
    index_data = data.get("index", {})
    index_array = index_data.get("array")
    if index_array is not None:
        if isinstance(index_array, np.ndarray):
            indices = index_array.astype(np.int32)
        else:
            indices = np.array(index_array, dtype=np.int32)

    return MeshGeometry(
        positions=positions,
        normals=normals,
        uvs=uvs,
        indices=indices,
    )


def _parse_box_geometry(geom_data: dict[str, Any]) -> PrimitiveGeometry:
    """Parse a BoxGeometry."""
    return PrimitiveGeometry(
        geometry_type=GeometryType.BOX,
        width=geom_data.get("width", 1.0),
        height=geom_data.get("height", 1.0),
        depth=geom_data.get("depth", 1.0),
    )


def _parse_sphere_geometry(geom_data: dict[str, Any]) -> PrimitiveGeometry:
    """Parse a SphereGeometry."""
    return PrimitiveGeometry(
        geometry_type=GeometryType.SPHERE,
        radius=geom_data.get("radius", 1.0),
        width_segments=geom_data.get("widthSegments", 32),
        height_segments=geom_data.get("heightSegments", 16),
    )


def _parse_cylinder_geometry(geom_data: dict[str, Any]) -> PrimitiveGeometry:
    """Parse a CylinderGeometry."""
    return PrimitiveGeometry(
        geometry_type=GeometryType.CYLINDER,
        radius_top=geom_data.get("radiusTop", 1.0),
        radius_bottom=geom_data.get("radiusBottom", 1.0),
        height=geom_data.get("height", 1.0),
        radial_segments=geom_data.get("radialSegments", 32),
    )


def _parse_plane_geometry(geom_data: dict[str, Any]) -> PrimitiveGeometry:
    """Parse a PlaneGeometry."""
    return PrimitiveGeometry(
        geometry_type=GeometryType.PLANE,
        width=geom_data.get("width", 1.0),
        height=geom_data.get("height", 1.0),
    )


def _parse_meshfile_geometry(
    geom_data: dict[str, Any],
    cas_assets: dict[str, str] | None = None,
) -> MeshFileGeometry | None:
    """Parse a _meshfile_geometry (embedded glTF/OBJ).

    Args:
        geom_data: Geometry data dictionary
        cas_assets: Optional CAS assets dictionary for resolving external references
    """
    import base64
    import json

    fmt = geom_data.get("format", "")
    data = geom_data.get("data")

    if not data:
        return None

    # For glTF format, we need to resolve CAS asset references in the JSON
    resources = {}

    if fmt.lower() == "gltf" and isinstance(data, str) and cas_assets:
        try:
            gltf = json.loads(data)

            # Resolve buffer URIs that reference CAS assets
            buffers = gltf.get("buffers") or []
            for buffer in buffers:
                uri = buffer.get("uri", "")
                if uri.startswith(("cas-v1/", "cas-v1-")):
                    # Look up in CAS assets
                    if uri in cas_assets:
                        asset_data_uri = cas_assets[uri]
                        # Parse data URI and extract binary data
                        binary_data = _decode_data_uri(asset_data_uri)
                        if binary_data:
                            resources[uri] = binary_data
                            # Replace URI with the resource key for later resolution
                            buffer["uri"] = uri

            # Resolve image URIs that reference CAS assets
            images = gltf.get("images") or []
            for image in images:
                uri = image.get("uri", "")
                if uri.startswith(("cas-v1/", "cas-v1-")):
                    if uri in cas_assets:
                        asset_data_uri = cas_assets[uri]
                        binary_data = _decode_data_uri(asset_data_uri)
                        if binary_data:
                            resources[uri] = binary_data

            # Re-serialize the glTF JSON (it may have been modified)
            data = json.dumps(gltf).encode("utf-8")

        except json.JSONDecodeError:
            # Not valid JSON, treat as raw data
            pass

    # Convert data to bytes if it's a string
    if isinstance(data, str):
        try:
            # Use validate=True to reject non-base64 data (e.g., OBJ text).
            # Without validation, b64decode silently strips non-base64 chars
            # and can produce garbled output from plain text input.
            data = base64.b64decode(data, validate=True)
        except Exception:
            data = data.encode("utf-8")
    elif isinstance(data, (list, np.ndarray)):
        data = bytes(data)

    # Extract any explicit resources (for glTF with external files)
    resources_data = geom_data.get("resources", {})
    for key, value in resources_data.items():
        if isinstance(value, str):
            try:
                resources[key] = base64.b64decode(value, validate=True)
            except Exception:
                resources[key] = value.encode("utf-8")
        elif isinstance(value, (list, np.ndarray)):
            resources[key] = bytes(value)
        else:
            resources[key] = value

    return MeshFileGeometry(
        format=fmt,
        data=data,
        resources=resources,
    )


def _decode_data_uri(data_uri: str) -> bytes | None:
    """Decode a data URI to binary data.

    Args:
        data_uri: Data URI string (e.g., "data:application/octet-binary;base64,...")

    Returns:
        Decoded bytes or None if decoding fails
    """
    import base64

    if not data_uri.startswith("data:"):
        return None

    try:
        # Parse data URI format: data:[<mediatype>][;base64],<data>
        header, encoded_data = data_uri.split(",", 1)

        if ";base64" in header:
            return base64.b64decode(encoded_data)
        else:
            # URL-encoded data
            from urllib.parse import unquote

            return unquote(encoded_data).encode("utf-8")

    except Exception:
        return None
