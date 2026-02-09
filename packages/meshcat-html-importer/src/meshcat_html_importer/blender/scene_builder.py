# SPDX-License-Identifier: MIT
"""Build complete Blender scenes from meshcat data."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import bpy

if TYPE_CHECKING:
    import mathutils

from ..parser import parse_html_recording
from ..scene import SceneGraph, SceneNode
from .animation_builder import (
    apply_animation,
    set_animation_range,
)
from .material_builder import (
    apply_material_to_object,
    create_default_material,
    create_material,
)
from .mesh_builder import (
    create_mesh_file_object,
    create_mesh_object,
)

# Path prefixes to exclude (contact forces, collision geometry, inertia visualizers)
EXCLUDED_PATH_PREFIXES = (
    "/drake/contact_forces/",
    "/drake/proximity/",
    "/drake/inertia/",
)

# Path prefix for visual/illustration geometry
ILLUSTRATION_PREFIX = "/drake/illustration/"

# Path prefix for trajectory/paths geometry
PATHS_PREFIX = "/drake/paths/"

# Default collection name for imported objects
DEFAULT_COLLECTION_NAME = "MeshcatObjects"


def build_scene(
    scene_data: dict[str, Any],
    recording_fps: float = 1000.0,
    target_fps: float = 30.0,
    start_frame: int = 0,
    clear_scene: bool = True,
    hierarchical_collections: bool = False,
    collection_root: str = "",
) -> dict[str, bpy.types.Object]:
    """Build a complete Blender scene from parsed meshcat data.

    Args:
        scene_data: Parsed data from parse_html_recording()
        recording_fps: FPS of the original recording
                      (default 1000 for Drake simulations)
        target_fps: Target FPS for Blender animation (default 30)
        start_frame: Starting frame number
        clear_scene: Whether to clear existing objects
        hierarchical_collections: If True, create nested collections
                                 mirroring path structure
        collection_root: Custom prefix to strip from paths
                        (auto-detected if empty)

    Returns:
        Dictionary mapping node paths to created Blender objects
    """
    if clear_scene:
        _clear_scene()

    # Build scene graph from commands, passing CAS assets for resource resolution
    assets = scene_data.get("assets", {})
    scene_graph = SceneGraph(assets=assets)
    scene_graph.process_commands(scene_data["commands"])

    # Get or create root collection for meshcat objects
    root_collection = _get_or_create_root_collection()

    # Create objects for each node with geometry (filtering excluded paths)
    created_objects: dict[str, bpy.types.Object] = {}
    import_matrices: dict[str, "mathutils.Matrix"] = {}  # glTF coordinate conversion

    for node in scene_graph.get_mesh_nodes():
        # Skip excluded paths (contact forces, proximity/collision geometry)
        if _should_skip_path(node.path):
            continue

        obj, import_matrix = _create_object_from_node(node, scene_graph)
        if obj is not None:
            created_objects[node.path] = obj
            if import_matrix is not None:
                import_matrices[node.path] = import_matrix
            _link_object_to_scene(
                obj,
                path=node.path,
                hierarchical=hierarchical_collections,
                path_prefix=collection_root,
                root_collection=root_collection,
            )

    # Apply animations - check both direct animations and parent animations
    all_nodes = {n.path: n for n in scene_graph.get_all_nodes()}
    for path, obj in created_objects.items():
        # Find animation data for this object or its ancestors
        anim_node = _find_animation_node(scene_graph, path)
        if anim_node is not None:
            # Get the object's own node to calculate local offset from animation source
            obj_node = all_nodes.get(path)
            local_offset = _get_local_offset_from_ancestor(obj_node, anim_node)
            apply_animation(
                obj,
                anim_node,
                recording_fps=recording_fps,
                target_fps=target_fps,
                start_frame=start_frame,
                local_offset=local_offset,
                import_matrix=import_matrices.get(path),
            )

    # Set scene frame range based on all animated nodes (excluding contact forces, etc.)
    animated_nodes = [
        n
        for n in scene_graph.get_animated_nodes()
        if not _should_skip_path(n.path)
    ]
    if animated_nodes:
        set_animation_range(
            animated_nodes,
            recording_fps=recording_fps,
            target_fps=target_fps,
            start_frame=start_frame,
        )

    # Set scene FPS
    bpy.context.scene.render.fps = int(target_fps)

    return created_objects


def _should_skip_path(path: str) -> bool:
    """Check if a path should be skipped during import.

    Args:
        path: The node path

    Returns:
        True if the path should be skipped
    """
    for prefix in EXCLUDED_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _determine_path_prefix(path: str) -> str:
    """Determine the appropriate prefix to strip from a path.

    Args:
        path: The node path

    Returns:
        The prefix to strip (e.g., "/drake/illustration/" or "/drake/paths/")
    """
    if path.startswith(ILLUSTRATION_PREFIX):
        return ILLUSTRATION_PREFIX
    if path.startswith(PATHS_PREFIX):
        return PATHS_PREFIX
    return ""


def _get_or_create_root_collection() -> bpy.types.Collection:
    """Get or create the root collection for meshcat objects.

    Returns:
        The root MeshcatObjects collection
    """
    if DEFAULT_COLLECTION_NAME not in bpy.data.collections:
        collection = bpy.data.collections.new(DEFAULT_COLLECTION_NAME)
        bpy.context.scene.collection.children.link(collection)
    else:
        collection = bpy.data.collections[DEFAULT_COLLECTION_NAME]
    return collection


def _get_or_create_collection_hierarchy(
    path: str,
    root_collection: bpy.types.Collection,
    path_prefix: str = "",
) -> bpy.types.Collection:
    """Get or create a collection hierarchy based on a path.

    Creates nested collections for each path component (except the leaf/object name).

    Args:
        path: The full meshcat path (e.g., "/drake/paths/move_1/optimized/red/e_0")
        root_collection: The root collection to build hierarchy under
        path_prefix: Custom prefix to strip (auto-detected if empty)

    Returns:
        The collection where the object should be linked
    """
    # Determine prefix to strip
    if path_prefix:
        prefix = path_prefix
    else:
        prefix = _determine_path_prefix(path)

    # Strip prefix from path
    if prefix and path.startswith(prefix):
        relative_path = path[len(prefix):]
    else:
        relative_path = path.lstrip("/")

    # Split into components and remove the leaf (object name)
    parts = relative_path.strip("/").split("/")
    if len(parts) <= 1:
        # No hierarchy needed, link directly to root
        return root_collection

    # Remove the leaf component (the object itself)
    collection_parts = parts[:-1]

    # Create nested collections
    current_collection = root_collection
    for part in collection_parts:
        # Check if child collection already exists
        child_collection = None
        for child in current_collection.children:
            if child.name == part:
                child_collection = child
                break

        if child_collection is None:
            # Create new child collection
            child_collection = bpy.data.collections.new(part)
            current_collection.children.link(child_collection)

        current_collection = child_collection

    return current_collection


def _derive_object_name(path: str) -> str:
    """Derive a descriptive object name from a scene graph path.

    Path formats:
    - /drake/illustration/<model_name>/base_link/<model_name>/visual
    - /drake/illustration/<model_name>/<link_name>/<model_name>/<part_name>
    - /drake/illustration/room_geometry_dining_room/room_geometry_body_link/<wall_name>

    Args:
        path: Full scene graph path

    Returns:
        Descriptive object name
    """
    parts = path.strip("/").split("/")

    # Skip common prefixes
    if parts and parts[0] == "drake":
        parts = parts[1:]
    if parts and parts[0] == "illustration":
        parts = parts[1:]

    if not parts:
        return "Object"

    # For paths like <model>/base_link/<model>/visual, use the model name
    # and possibly the visual part name
    model_name = parts[0] if parts else "Object"

    # Check if the last part is descriptive (not just "visual" or similar)
    if len(parts) > 1:
        last_part = parts[-1]
        if last_part not in ("visual", "collision", "base_link"):
            # For room geometry, use the last part (wall names, etc.)
            if "room_geometry" in model_name:
                return last_part
            # Otherwise combine model + part if different
            if last_part != model_name:
                return f"{model_name}_{last_part}"

    return model_name


def _find_animation_node(scene_graph: SceneGraph, path: str) -> SceneNode | None:
    """Find the animation node for a given path.

    Searches the path and its ancestors for animation data.
    In Drake/meshcat, animations are often on parent nodes (e.g., base_link)
    while geometry is on child nodes (e.g., visual).

    Args:
        scene_graph: The scene graph
        path: The path to search from

    Returns:
        SceneNode with keyframes, or None if not found
    """
    # Check the node itself first
    all_nodes = {n.path: n for n in scene_graph.get_all_nodes()}

    if path in all_nodes and all_nodes[path].keyframes:
        return all_nodes[path]

    # Search ancestors
    parts = path.strip("/").split("/")
    for i in range(len(parts) - 1, 0, -1):
        ancestor_path = "/" + "/".join(parts[:i])
        if ancestor_path in all_nodes and all_nodes[ancestor_path].keyframes:
            return all_nodes[ancestor_path]

    return None


def _get_local_offset_from_ancestor(
    obj_node: SceneNode | None,
    anim_node: SceneNode | None,
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]] | None:
    """Get the local transform offset from animation node to object node.

    When animation is inherited from a parent, we need to apply the relative
    transform between the animation source and the object.

    Args:
        obj_node: The object's scene node
        anim_node: The animation source node (may be ancestor)

    Returns:
        Tuple of (position_offset, rotation_offset) or None if same node
    """
    if obj_node is None or anim_node is None:
        return None

    if obj_node.path == anim_node.path:
        # Same node, no offset needed
        return None

    # Compute the relative transform from anim_node to obj_node
    # This is: obj_world = anim_world * local_offset
    # So: local_offset = inverse(anim_world) * obj_world
    # For simplicity, we collect transforms from anim_node to obj_node
    from ..scene.transforms import Transform, combine_transforms

    # Start from animation node, walk down to object node
    # Collect all transforms between them
    obj_path_parts = obj_node.path.strip("/").split("/")
    anim_path_parts = anim_node.path.strip("/").split("/")

    # Object path should be longer (descendant of anim node)
    if len(obj_path_parts) <= len(anim_path_parts):
        return None

    # Collect transforms from nodes between anim_node and obj_node
    # (exclusive of anim, inclusive of obj)
    combined = Transform.identity()
    current = obj_node

    # Include the object's own local matrix first (innermost transform)
    combined = combine_transforms(obj_node.object_matrix, combined)

    while current is not None and current.path != anim_node.path:
        combined = combine_transforms(current.transform, combined)
        current = current.parent

    if current is None:
        # anim_node is not an ancestor of obj_node
        return None

    return (combined.translation, combined.rotation)


def _clear_scene() -> None:
    """Clear all objects from the scene."""
    # Deselect all
    bpy.ops.object.select_all(action="DESELECT")

    # Select all mesh objects
    for obj in bpy.data.objects:
        obj.select_set(True)

    # Delete selected
    bpy.ops.object.delete()

    # Clean up orphaned data
    for mesh in bpy.data.meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    for mat in bpy.data.materials:
        if mat.users == 0:
            bpy.data.materials.remove(mat)

    for action in bpy.data.actions:
        if action.users == 0:
            bpy.data.actions.remove(action)


def _create_object_from_node(
    node: SceneNode,
    scene_graph: SceneGraph | None = None,
) -> tuple[bpy.types.Object, "mathutils.Matrix | None"] | tuple[None, None]:
    """Create a Blender object from a scene node.

    Args:
        node: SceneNode with geometry
        scene_graph: Optional scene graph for deriving better names

    Returns:
        Tuple of (Blender object, import_matrix). import_matrix is non-None for
        glTF imports and captures the coordinate conversion rotation.
    """
    from ..scene.geometry import MeshFileGeometry

    # Derive a descriptive name from the path
    # Path format: /drake/illustration/<model_name>/base_link/<model_name>/visual
    # We want to extract the model name
    obj_name = _derive_object_name(node.path)

    # Check if this is a mesh file (glTF/OBJ) - these are handled specially
    is_meshfile = isinstance(node.geometry, MeshFileGeometry)
    is_gltf = is_meshfile and node.geometry.format.lower() in ("gltf", "glb")

    import_matrix = None
    if is_meshfile:
        # Use create_mesh_file_object to get the import coordinate conversion matrix
        obj, import_matrix = create_mesh_file_object(node, name=obj_name)
    else:
        obj = create_mesh_object(node, name=obj_name)

    if obj is None:
        return None, None

    # Apply world transform (combining all parent transforms)
    _apply_world_transform(obj, node, import_matrix=import_matrix)

    # Apply material for non-glTF geometry.
    # glTF imports have their own embedded materials, but OBJ files may not
    # (they depend on MTL files which may be missing). For OBJ meshfile geometry
    # and non-meshfile geometry, apply materials from the scene graph.
    if not is_gltf:
        if node.material is not None:
            mat_name = f"{node.name}_material"
            material = create_material(node.material, mat_name)
            apply_material_to_object(obj, material)
        elif not is_meshfile:
            # Apply default material only for non-meshfile geometry
            default_mat = create_default_material(f"{node.name}_default")
            apply_material_to_object(obj, default_mat)

    # Set visibility
    obj.hide_viewport = not node.visible
    obj.hide_render = not node.visible

    return obj, import_matrix


def _apply_world_transform(
    obj: bpy.types.Object,
    node: SceneNode,
    import_matrix: "mathutils.Matrix | None" = None,
) -> None:
    """Apply world transform to Blender object.

    Computes the full world transform by combining all parent transforms.
    For glTF imports, also incorporates the importer's coordinate conversion
    matrix to preserve correct mesh orientation.

    Args:
        obj: Blender object
        node: SceneNode with transform
        import_matrix: Optional coordinate conversion matrix from glTF importer.
            When provided, the final world matrix is: meshcat_world × import_matrix
    """
    import mathutils

    # Get world transform (combines all parent transforms)
    transform = node.get_world_transform()

    if import_matrix is not None:
        # For glTF: combine meshcat world transform with the importer's
        # coordinate conversion. The import_matrix handles the conversion
        # from glTF model space to Blender's coordinate system (e.g., Y-up
        # to Z-up). The meshcat transform positions the object in the scene.
        # Build meshcat world matrix
        x, y, z, w = transform.rotation
        quat = mathutils.Quaternion((w, x, y, z))
        meshcat_matrix = mathutils.Matrix.LocRotScale(
            mathutils.Vector(transform.translation),
            quat,
            mathutils.Vector(transform.scale),
        )
        # Combine: meshcat positioning × import coordinate conversion
        obj.matrix_world = meshcat_matrix @ import_matrix
    else:
        # Standard path: set location, rotation, scale directly
        obj.location = transform.translation

        obj.rotation_mode = "QUATERNION"
        # Convert from (x, y, z, w) to Blender's (w, x, y, z)
        x, y, z, w = transform.rotation
        obj.rotation_quaternion = (w, x, y, z)

        obj.scale = transform.scale


def _apply_transform(obj: bpy.types.Object, node: SceneNode) -> None:
    """Apply node's local transform to Blender object.

    Args:
        obj: Blender object
        node: SceneNode with transform
    """
    transform = node.transform

    # Set location
    obj.location = transform.translation

    # Set rotation (quaternion)
    obj.rotation_mode = "QUATERNION"
    # Convert from (x, y, z, w) to Blender's (w, x, y, z)
    x, y, z, w = transform.rotation
    obj.rotation_quaternion = (w, x, y, z)

    # Set scale
    obj.scale = transform.scale


def _link_object_to_scene(
    obj: bpy.types.Object,
    path: str = "",
    hierarchical: bool = False,
    path_prefix: str = "",
    root_collection: bpy.types.Collection | None = None,
) -> None:
    """Link an object to the current scene.

    Args:
        obj: Blender object to link
        path: The meshcat path for the object (used for hierarchical collections)
        hierarchical: If True, create nested collections mirroring path structure
        path_prefix: Custom prefix to strip from paths (auto-detected if empty)
        root_collection: Pre-created root collection (created if None)
    """
    # Get or create root collection
    if root_collection is None:
        root_collection = _get_or_create_root_collection()

    if hierarchical and path:
        # Create hierarchy and get target collection
        collection = _get_or_create_collection_hierarchy(
            path, root_collection, path_prefix
        )
    else:
        # Link directly to root collection
        collection = root_collection

    # Link object to collection
    collection.objects.link(obj)


def build_scene_from_file(
    html_path: str,
    recording_fps: float | None = None,
    target_fps: float = 30.0,
    start_frame: int = 0,
    clear_scene: bool = True,
    hierarchical_collections: bool = False,
    collection_root: str = "",
) -> dict[str, bpy.types.Object]:
    """Build a Blender scene directly from an HTML file.

    Args:
        html_path: Path to meshcat HTML recording
        recording_fps: FPS of the original recording (None = auto-detect from file,
            typically 64 for Drake simulations)
        target_fps: Target FPS for Blender animation (default 30)
        start_frame: Starting frame number
        clear_scene: Whether to clear existing objects
        hierarchical_collections: If True, create nested collections
                                 mirroring path structure
        collection_root: Custom prefix to strip from paths
                        (auto-detected if empty)

    Returns:
        Dictionary mapping node paths to created Blender objects
    """
    scene_data = parse_html_recording(html_path)

    # Auto-detect recording FPS from file if not specified
    if recording_fps is None:
        recording_fps = float(scene_data.get("animation_fps", 64.0))

    return build_scene(
        scene_data,
        recording_fps=recording_fps,
        target_fps=target_fps,
        start_frame=start_frame,
        clear_scene=clear_scene,
        hierarchical_collections=hierarchical_collections,
        collection_root=collection_root,
    )
