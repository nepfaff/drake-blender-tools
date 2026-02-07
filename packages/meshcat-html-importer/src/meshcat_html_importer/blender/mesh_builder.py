# SPDX-License-Identifier: MIT
"""Build Blender mesh objects from meshcat geometry."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import bpy
import numpy as np

from meshcat_html_importer.scene.geometry import (
    GeometryType,
    MeshFileGeometry,
    MeshGeometry,
    PrimitiveGeometry,
)

if TYPE_CHECKING:
    import mathutils

    from meshcat_html_importer.scene.scene_graph import SceneNode


def create_mesh_object(
    node: SceneNode,
    name: str | None = None,
) -> bpy.types.Object | None:
    """Create a Blender mesh object from a scene node.

    Args:
        node: SceneNode with geometry
        name: Optional name override

    Returns:
        Blender object or None if creation fails
    """
    if node.geometry is None:
        return None

    obj_name = name or node.name

    if isinstance(node.geometry, MeshGeometry):
        return _create_from_mesh_geometry(node.geometry, obj_name)
    elif isinstance(node.geometry, PrimitiveGeometry):
        return _create_from_primitive(node.geometry, obj_name)
    elif isinstance(node.geometry, MeshFileGeometry):
        result = _create_from_mesh_file(node.geometry, obj_name)
        # _create_from_mesh_file returns (obj, import_matrix) tuple
        return result[0] if result[0] is not None else None

    return None


def create_mesh_file_object(
    node: SceneNode,
    name: str | None = None,
) -> tuple[bpy.types.Object, "mathutils.Matrix | None"] | tuple[None, None]:
    """Create a Blender mesh object from a MeshFileGeometry node.

    Like create_mesh_object, but also returns the import coordinate conversion
    matrix (for glTF imports) needed to correctly apply the meshcat world transform.

    Args:
        node: SceneNode with MeshFileGeometry
        name: Optional name override

    Returns:
        Tuple of (object, import_matrix). import_matrix is non-None for glTF.
    """
    if node.geometry is None or not isinstance(node.geometry, MeshFileGeometry):
        return None, None

    obj_name = name or node.name
    return _create_from_mesh_file(node.geometry, obj_name)


def _create_from_mesh_geometry(
    geom: MeshGeometry,
    name: str,
) -> bpy.types.Object | None:
    """Create mesh from BufferGeometry data."""
    if not geom.validate():
        return None

    # Create mesh
    mesh = bpy.data.meshes.new(name)

    # Prepare vertex data
    vertices = geom.positions.tolist()

    # Prepare face data
    if geom.indices is not None:
        # Indexed geometry - reshape indices to triangles
        indices = geom.indices.flatten()
        num_tris = len(indices) // 3
        faces = [tuple(indices[i * 3 : i * 3 + 3]) for i in range(num_tris)]
    else:
        # Non-indexed - every 3 vertices form a triangle
        num_verts = len(vertices)
        num_tris = num_verts // 3
        faces = [tuple(range(i * 3, i * 3 + 3)) for i in range(num_tris)]

    # Create mesh from data
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    # Add normals
    if geom.normals is not None:
        mesh.normals_split_custom_set_from_vertices(geom.normals.tolist())

    # Add UVs
    if geom.uvs is not None and len(geom.uvs) > 0:
        _add_uv_layer(mesh, geom.uvs, geom.indices)

    # Validate mesh
    mesh.validate()
    mesh.update()

    # Create object
    obj = bpy.data.objects.new(name, mesh)
    return obj


def _add_uv_layer(
    mesh: bpy.types.Mesh,
    uvs: np.ndarray,
    indices: np.ndarray | None,
) -> None:
    """Add UV coordinates to a mesh.

    Args:
        mesh: Blender mesh
        uvs: UV coordinates per vertex
        indices: Optional face indices
    """
    if len(mesh.loops) == 0:
        return

    uv_layer = mesh.uv_layers.new(name="UVMap")

    if indices is not None:
        # Map UVs through indices
        for loop_idx, loop in enumerate(mesh.loops):
            vert_idx = loop.vertex_index
            if vert_idx < len(uvs):
                uv_layer.data[loop_idx].uv = uvs[vert_idx].tolist()
    else:
        # Direct mapping
        for loop_idx, loop in enumerate(mesh.loops):
            vert_idx = loop.vertex_index
            if vert_idx < len(uvs):
                uv_layer.data[loop_idx].uv = uvs[vert_idx].tolist()


def _create_from_primitive(
    geom: PrimitiveGeometry,
    name: str,
) -> bpy.types.Object | None:
    """Create mesh from primitive geometry."""
    mesh = bpy.data.meshes.new(name)

    if geom.geometry_type == GeometryType.BOX:
        _create_box_mesh(mesh, geom.width, geom.height, geom.depth)
    elif geom.geometry_type == GeometryType.SPHERE:
        _create_sphere_mesh(
            mesh, geom.radius, geom.width_segments, geom.height_segments
        )
    elif geom.geometry_type == GeometryType.CYLINDER:
        _create_cylinder_mesh(
            mesh,
            geom.radius_top,
            geom.radius_bottom,
            geom.height,
            geom.radial_segments,
        )
    elif geom.geometry_type == GeometryType.PLANE:
        _create_plane_mesh(mesh, geom.width, geom.height)
    else:
        return None

    obj = bpy.data.objects.new(name, mesh)
    return obj


def _create_box_mesh(
    mesh: bpy.types.Mesh,
    width: float,
    height: float,
    depth: float,
) -> None:
    """Create a box mesh."""
    w, h, d = width / 2, height / 2, depth / 2

    vertices = [
        (-w, -h, -d),
        (w, -h, -d),
        (w, h, -d),
        (-w, h, -d),
        (-w, -h, d),
        (w, -h, d),
        (w, h, d),
        (-w, h, d),
    ]

    faces = [
        (0, 1, 2, 3),  # Back
        (4, 7, 6, 5),  # Front
        (0, 4, 5, 1),  # Bottom
        (2, 6, 7, 3),  # Top
        (0, 3, 7, 4),  # Left
        (1, 5, 6, 2),  # Right
    ]

    mesh.from_pydata(vertices, [], faces)
    mesh.update()


def _create_sphere_mesh(
    mesh: bpy.types.Mesh,
    radius: float,
    width_segments: int,
    height_segments: int,
) -> None:
    """Create a UV sphere mesh."""
    import bmesh

    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm,
        u_segments=int(width_segments),
        v_segments=int(height_segments),
        radius=radius,
    )
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def _create_cylinder_mesh(
    mesh: bpy.types.Mesh,
    radius_top: float,
    radius_bottom: float,
    height: float,
    radial_segments: int,
) -> None:
    """Create a cylinder mesh.

    Three.js CylinderGeometry extends along the Y-axis, but Blender's
    create_cone extends along Z. We rotate the mesh by -90° around X
    to match Three.js convention, so that meshcat quaternions work correctly.
    """
    import bmesh
    import mathutils

    bm = bmesh.new()

    # For tapered cylinders, we use create_cone
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=int(radial_segments),
        radius1=radius_bottom,
        radius2=radius_top,
        depth=height,
    )

    # Rotate -90° around X to convert from Blender Z-up to Three.js Y-up.
    # This makes the cylinder extend along Y in local space, matching Three.js.
    import math

    rot_matrix = mathutils.Matrix.Rotation(-math.pi / 2, 4, "X")
    bmesh.ops.transform(bm, matrix=rot_matrix, verts=bm.verts[:])

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def _create_plane_mesh(
    mesh: bpy.types.Mesh,
    width: float,
    height: float,
) -> None:
    """Create a plane mesh."""
    w, h = width / 2, height / 2

    vertices = [
        (-w, -h, 0),
        (w, -h, 0),
        (w, h, 0),
        (-w, h, 0),
    ]

    faces = [(0, 1, 2, 3)]

    mesh.from_pydata(vertices, [], faces)
    mesh.update()


def _create_from_mesh_file(
    geom: MeshFileGeometry,
    name: str,
) -> tuple[bpy.types.Object, "mathutils.Matrix"] | tuple[None, None]:
    """Create mesh by importing embedded mesh file.

    Returns:
        Tuple of (object, import_matrix) where import_matrix is the coordinate
        system conversion matrix from the importer (e.g., glTF Y-up to Z-up).
        For OBJ imports, import_matrix is None. Returns (None, None) on failure.
    """

    # Write mesh data to temp file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        if geom.format.lower() in ("gltf", "glb"):
            # Determine extension
            ext = ".glb" if geom.data[:4] == b"glTF" else ".gltf"
            mesh_file = temp_path / f"{name}{ext}"
            mesh_file.write_bytes(geom.data)

            # Write any resources
            for res_name, res_data in geom.resources.items():
                res_path = temp_path / res_name
                res_path.parent.mkdir(parents=True, exist_ok=True)
                res_path.write_bytes(res_data)

            # Import glTF
            old_objects = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=str(mesh_file))
            new_objects = list(set(bpy.data.objects) - old_objects)

            if new_objects:
                # Capture the import's coordinate conversion matrix before cleanup.
                # The glTF importer applies a rotation to convert from glTF's
                # coordinate system to Blender's. We need to preserve this when
                # applying the meshcat world transform later.
                import_matrix = _get_import_rotation_matrix(new_objects)

                # Find the main mesh object and clean up extras
                main_obj = _select_main_object_and_cleanup(new_objects, name)
                return main_obj, import_matrix

        elif geom.format.lower() == "obj":
            mesh_file = temp_path / f"{name}.obj"
            mesh_file.write_bytes(geom.data)

            # Write MTL and textures
            for res_name, res_data in geom.resources.items():
                res_path = temp_path / res_name
                res_path.parent.mkdir(parents=True, exist_ok=True)
                res_path.write_bytes(res_data)

            # Import OBJ
            old_objects = set(bpy.data.objects)
            bpy.ops.wm.obj_import(filepath=str(mesh_file))
            new_objects = list(set(bpy.data.objects) - old_objects)

            if new_objects:
                # Find the main mesh object and clean up extras
                main_obj = _select_main_object_and_cleanup(new_objects, name)
                return main_obj, None

    return None, None


def _get_import_rotation_matrix(
    objects: list[bpy.types.Object],
) -> "mathutils.Matrix":
    """Extract the coordinate conversion rotation from imported objects.

    The glTF importer applies a rotation to convert from glTF/Three.js coordinate
    system to Blender's. This captures that rotation so it can be combined with
    the meshcat world transform.

    Args:
        objects: List of newly imported objects

    Returns:
        The import rotation as a 4x4 matrix (translation zeroed, pure rotation)
    """
    import mathutils

    # Find a root object (no parent) - the importer's coordinate conversion
    # is typically on the root object or the first mesh
    for obj in objects:
        if obj.parent is None:
            mat = obj.matrix_world.copy()
            # Zero out translation - we only want the rotation component
            mat[0][3] = 0.0
            mat[1][3] = 0.0
            mat[2][3] = 0.0
            return mat

    return mathutils.Matrix.Identity(4)


def _select_main_object_and_cleanup(
    objects: list[bpy.types.Object],
    name: str,
) -> bpy.types.Object | None:
    """Select and combine mesh objects from imported objects, clean up extras.

    glTF imports can create multiple objects (root nodes, mesh objects, etc.).
    We want to keep all mesh geometry, joining multiple meshes if needed.

    Args:
        objects: List of newly imported objects
        name: Desired name for the main object

    Returns:
        The combined mesh object, or None
    """
    if not objects:
        return None

    # Separate objects into mesh objects and empties/other
    mesh_objects = [o for o in objects if o.type == "MESH" and o.data]
    empty_objects = [o for o in objects if o.type == "EMPTY" or not o.data]

    if not mesh_objects:
        # No mesh objects, just return the first object
        obj = objects[0]
        obj.name = name
        return obj

    # If there's only one mesh, use it directly
    if len(mesh_objects) == 1:
        main_obj = mesh_objects[0]
        # Store world matrix before unparenting
        world_matrix = main_obj.matrix_world.copy()
        if main_obj.parent is not None:
            main_obj.parent = None
            main_obj.matrix_world = world_matrix
    else:
        # Multiple meshes - join them all into one object
        # First, unparent all and apply world transforms
        for obj in mesh_objects:
            world_matrix = obj.matrix_world.copy()
            if obj.parent is not None:
                obj.parent = None
            obj.matrix_world = world_matrix

        # Select all mesh objects for joining
        bpy.ops.object.select_all(action="DESELECT")
        for obj in mesh_objects:
            obj.select_set(True)

        # Set the first mesh as active (will be the target for join)
        main_obj = mesh_objects[0]
        bpy.context.view_layer.objects.active = main_obj

        # Join all selected objects into the active one
        bpy.ops.object.join()

        # After join, only main_obj remains with combined geometry
        # Clear the mesh_objects list references as they're now invalid
        mesh_objects = [main_obj]

    # Rename
    main_obj.name = name

    # Delete empty parent objects
    for obj in empty_objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)

    return main_obj
