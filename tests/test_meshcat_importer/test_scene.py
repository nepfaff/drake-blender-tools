# SPDX-License-Identifier: MIT
"""Tests for scene module."""

import numpy as np


class TestTransforms:
    """Tests for transform utilities."""

    def test_identity_transform(self):
        """Test creating identity transform."""
        from meshcat_html_importer.scene.transforms import Transform

        t = Transform.identity()

        assert t.translation == (0.0, 0.0, 0.0)
        assert t.rotation == (0.0, 0.0, 0.0, 1.0)
        assert t.scale == (1.0, 1.0, 1.0)

    def test_parse_transform_matrix(self):
        """Test parsing column-major matrix."""
        from meshcat_html_importer.scene.transforms import parse_transform_matrix

        # Identity matrix in column-major order
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

        result = parse_transform_matrix(identity)

        assert result.shape == (4, 4)
        np.testing.assert_array_almost_equal(result, np.eye(4))

    def test_parse_transform_matrix_with_translation(self):
        """Test parsing matrix with translation."""
        from meshcat_html_importer.scene.transforms import parse_transform_matrix

        # Matrix with translation (1, 2, 3)
        # Column-major: last column contains translation
        matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 2, 3, 1]

        result = parse_transform_matrix(matrix)

        assert result[0, 3] == 1.0
        assert result[1, 3] == 2.0
        assert result[2, 3] == 3.0

    def test_matrix_to_trs(self):
        """Test decomposing matrix to TRS."""
        from meshcat_html_importer.scene.transforms import (
            matrix_to_trs,
            parse_transform_matrix,
        )

        # Matrix with translation (5, 0, 0)
        matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 5, 0, 0, 1]
        parsed = parse_transform_matrix(matrix)

        result = matrix_to_trs(parsed)

        assert abs(result.translation[0] - 5.0) < 1e-6
        assert abs(result.translation[1]) < 1e-6
        assert abs(result.translation[2]) < 1e-6

    def test_quaternion_multiply(self):
        """Test quaternion multiplication."""
        from meshcat_html_importer.scene.transforms import quaternion_multiply

        # Identity * Identity = Identity
        identity = (0.0, 0.0, 0.0, 1.0)
        result = quaternion_multiply(identity, identity)

        assert abs(result[0]) < 1e-6
        assert abs(result[1]) < 1e-6
        assert abs(result[2]) < 1e-6
        assert abs(result[3] - 1.0) < 1e-6


class TestGeometry:
    """Tests for geometry parsing."""

    def test_parse_box_geometry(self):
        """Test parsing BoxGeometry."""
        from meshcat_html_importer.scene.geometry import GeometryType, parse_geometry

        data = {
            "type": "BoxGeometry",
            "width": 2.0,
            "height": 3.0,
            "depth": 4.0,
        }

        result = parse_geometry(data)

        assert result is not None
        assert result.geometry_type == GeometryType.BOX
        assert result.width == 2.0
        assert result.height == 3.0
        assert result.depth == 4.0

    def test_parse_sphere_geometry(self):
        """Test parsing SphereGeometry."""
        from meshcat_html_importer.scene.geometry import GeometryType, parse_geometry

        data = {
            "type": "SphereGeometry",
            "radius": 1.5,
            "widthSegments": 16,
            "heightSegments": 8,
        }

        result = parse_geometry(data)

        assert result is not None
        assert result.geometry_type == GeometryType.SPHERE
        assert result.radius == 1.5
        assert result.width_segments == 16
        assert result.height_segments == 8

    def test_parse_buffer_geometry(self):
        """Test parsing BufferGeometry."""
        from meshcat_html_importer.scene.geometry import parse_geometry

        data = {
            "type": "BufferGeometry",
            "data": {
                "attributes": {
                    "position": {
                        "array": [0, 0, 0, 1, 0, 0, 0, 1, 0],
                        "itemSize": 3,
                    }
                }
            },
        }

        result = parse_geometry(data)

        assert result is not None
        assert result.positions is not None
        assert result.positions.shape == (3, 3)

    def test_mesh_geometry_validate(self):
        """Test MeshGeometry validation."""
        from meshcat_html_importer.scene.geometry import MeshGeometry

        # Valid geometry
        valid = MeshGeometry(positions=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]]))
        assert valid.validate()

        # Invalid - empty positions
        invalid = MeshGeometry(positions=np.array([]))
        assert not invalid.validate()

    def test_obj_meshfile_uses_mtl_library_resource(self):
        """Test OBJ meshfiles reconstruct the referenced MTL file."""
        from meshcat_html_importer.parser.command_types import Command
        from meshcat_html_importer.scene.scene_graph import SceneGraph

        cmd = Command.from_dict(
            {
                "type": "set_object",
                "path": "/test/object",
                "object": {
                    "object": {
                        "type": "_meshfile_object",
                        "uuid": "mesh-1",
                        "format": "obj",
                        "matrix": [
                            1,
                            0,
                            0,
                            0,
                            0,
                            1,
                            0,
                            0,
                            0,
                            0,
                            1,
                            0,
                            0,
                            0,
                            0,
                            1,
                        ],
                        "data": "mtllib tray.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
                        "mtl_library": "newmtl tray\nmap_Kd tray.png\n",
                        "resources": {
                            "tray.png": "data:image/png;base64,dGV4dHVyZS1ieXRlcw==",
                        },
                    }
                },
            }
        )

        scene_graph = SceneGraph()
        scene_graph.process_commands([cmd])

        node = next(n for n in scene_graph.get_mesh_nodes() if n.path == "/test/object")

        assert node.geometry is not None
        assert node.geometry.format == "obj"
        assert node.geometry.resources["tray.mtl"] == b"newmtl tray\nmap_Kd tray.png\n"
        assert node.geometry.resources["tray.png"] == b"texture-bytes"


class TestMaterials:
    """Tests for material parsing."""

    def test_color_from_int(self):
        """Test creating color from integer."""
        from meshcat_html_importer.scene.materials import Color

        # Red: 0xFF0000
        color = Color.from_int(0xFF0000)

        assert abs(color.r - 1.0) < 1e-6
        assert abs(color.g) < 1e-6
        assert abs(color.b) < 1e-6

    def test_color_from_hex(self):
        """Test creating color from hex string."""
        from meshcat_html_importer.scene.materials import Color

        color = Color.from_hex("#00FF00")

        assert abs(color.r) < 1e-6
        assert abs(color.g - 1.0) < 1e-6
        assert abs(color.b) < 1e-6

    def test_parse_standard_material(self):
        """Test parsing MeshStandardMaterial."""
        from meshcat_html_importer.scene.materials import MaterialType, parse_material

        data = {
            "type": "MeshStandardMaterial",
            "color": 0xFF0000,
            "metalness": 0.5,
            "roughness": 0.3,
        }

        result = parse_material(data)

        assert result is not None
        assert result.material_type == MaterialType.MESH_STANDARD
        assert result.metalness == 0.5
        assert result.roughness == 0.3

    def test_shininess_to_roughness(self):
        """Test shininess to roughness conversion."""
        from meshcat_html_importer.scene.materials import shininess_to_roughness

        # High shininess = low roughness
        assert shininess_to_roughness(100) < 0.5
        assert shininess_to_roughness(1000) < 0.1

        # Low shininess = high roughness
        assert shininess_to_roughness(1) > 0.7
        assert shininess_to_roughness(0) == 1.0
