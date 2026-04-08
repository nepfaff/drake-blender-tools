# SPDX-License-Identifier: MIT
"""Regression tests for Blender meshfile imports."""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

import pytest

try:
    import bpy
except ModuleNotFoundError:
    bpy = None

if bpy is not None:
    from meshcat_html_importer.blender.mesh_builder import create_mesh_file_object
    from meshcat_html_importer.blender.scene_builder import _apply_world_transform
    from meshcat_html_importer.scene.geometry import MeshFileGeometry
    from meshcat_html_importer.scene.scene_graph import SceneNode


pytestmark = pytest.mark.skipif(bpy is None, reason="bpy is not installed")


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
    "iZk9HQAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
def reset_blender_state():
    """Reset Blender to an empty factory scene before and after each test."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    yield
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _make_translated_gltf_geometry() -> MeshFileGeometry:
    """Create a tiny glTF mesh with a static node translation."""
    positions = struct.pack(
        "<9f",
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        1.0,
    )
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "mesh.bin", "byteLength": len(positions)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 1.0],
            }
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "mode": 4}]}],
        # glTF is Y-up. Blender's importer maps glTF Y to Blender Z.
        "nodes": [{"mesh": 0, "translation": [0.0, -0.5, 0.0]}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    return MeshFileGeometry(
        format="gltf",
        data=json.dumps(gltf).encode("utf-8"),
        resources={"mesh.bin": positions},
    )


def _make_textured_obj_geometry() -> MeshFileGeometry:
    """Create a tiny textured OBJ mesh."""
    obj_data = "\n".join(
        [
            "mtllib test.mtl",
            "o Triangle",
            "v 0.0 0.0 0.0",
            "v 1.0 0.0 0.0",
            "v 0.0 1.0 0.0",
            "vt 0.0 0.0",
            "vt 1.0 0.0",
            "vt 0.0 1.0",
            "usemtl material_0",
            "f 1/1 2/2 3/3",
            "",
        ]
    ).encode("utf-8")
    mtl_data = "\n".join(
        [
            "newmtl material_0",
            "Ka 1.000000 1.000000 1.000000",
            "Kd 1.000000 1.000000 1.000000",
            "Ks 0.000000 0.000000 0.000000",
            "d 1.000000",
            "illum 1",
            "map_Kd test.png",
            "",
        ]
    ).encode("utf-8")
    return MeshFileGeometry(
        format="obj",
        data=obj_data,
        resources={
            "test.mtl": mtl_data,
            "test.png": TINY_PNG,
        },
    )


class TestBlenderMeshfileImport:
    """Blender-backed regression tests for meshfile imports."""

    def test_gltf_import_preserves_static_node_translation(self):
        """glTF node translations should survive post-import world transforms."""
        node = SceneNode(
            path="/floor",
            name="floor",
            geometry=_make_translated_gltf_geometry(),
        )

        obj, import_matrix = create_mesh_file_object(node, name="floor")

        assert obj is not None
        assert import_matrix is not None
        assert import_matrix[2][3] == pytest.approx(-0.5)

        _apply_world_transform(obj, node, import_matrix=import_matrix)

        assert obj.matrix_world.translation.z == pytest.approx(-0.5)

    def test_obj_import_packs_texture_before_tempdir_cleanup(self):
        """OBJ textures should remain valid after the import tempdir is deleted."""
        node = SceneNode(
            path="/tray",
            name="tray",
            geometry=_make_textured_obj_geometry(),
        )

        obj, import_matrix = create_mesh_file_object(node, name="tray")

        assert obj is not None
        assert import_matrix is None
        assert len(bpy.data.images) == 1

        image = bpy.data.images[0]
        image_path = Path(bpy.path.abspath(image.filepath, library=image.library))

        assert image.packed_file is not None
        assert tuple(image.size) == (1, 1)
        assert not image_path.exists()

        material = obj.data.materials[0]
        assert material is not None
        assert material.node_tree is not None
        assert any(
            getattr(node, "image", None) == image for node in material.node_tree.nodes
        )
