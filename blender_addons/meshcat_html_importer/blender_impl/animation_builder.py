# SPDX-License-Identifier: MIT
"""Build Blender animations from meshcat keyframe data.

Supports Blender 5.0's new animation system with Actions, Slots, and Layers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import bpy

from ..animation.keyframe_converter import (
    BlenderKeyframe,
    convert_keyframes_to_blender,
    get_animation_range,
)

if TYPE_CHECKING:
    from ..scene.scene_graph import SceneNode


def apply_animation(
    obj: bpy.types.Object,
    node: SceneNode,
    recording_fps: float = 1000.0,
    target_fps: float = 30.0,
    start_frame: int = 0,
    local_offset: tuple[tuple[float, float, float], tuple[float, float, float, float]]
    | None = None,
    import_matrix: "mathutils.Matrix | None" = None,
) -> None:
    """Apply animation keyframes to a Blender object.

    Uses Blender 5.0's animation system with Actions and Slots.

    Args:
        obj: Blender object to animate
        node: SceneNode with keyframe data
        recording_fps: FPS of the original recording
        target_fps: Target FPS for Blender animation
        start_frame: Starting frame number
        local_offset: Optional (position, rotation) offset to apply when animation
                     is inherited from a parent node
        import_matrix: Optional coordinate conversion matrix from glTF importer.
                      When provided, each keyframe transform is combined with this
                      matrix to preserve correct mesh orientation.
    """
    if not node.keyframes:
        return

    # Convert keyframes to Blender format with downsampling
    blender_keyframes = convert_keyframes_to_blender(
        node.keyframes,
        recording_fps=recording_fps,
        target_fps=target_fps,
        start_frame=start_frame,
        downsample=True,
    )

    if not blender_keyframes:
        return

    # Apply local offset if animation is inherited from parent
    if local_offset is not None:
        blender_keyframes = _apply_local_offset_to_keyframes(
            blender_keyframes, local_offset
        )

    # Apply import matrix for glTF objects (coordinate system conversion)
    if import_matrix is not None:
        blender_keyframes = _apply_import_matrix_to_keyframes(
            blender_keyframes, import_matrix
        )

    # Create or get animation data
    if obj.animation_data is None:
        obj.animation_data_create()

    # Create action for this object
    action_name = f"{obj.name}Action"
    action = bpy.data.actions.new(name=action_name)

    # Blender 5.0: Create a slot for the object
    # The slot links the action to a specific object type
    try:
        # Blender 5.0+ API
        slot = action.slots.new(id_type="OBJECT", name=obj.name)
        obj.animation_data.action = action
        obj.animation_data.action_slot = slot
    except AttributeError:
        # Fallback for older Blender versions
        obj.animation_data.action = action

    # Set rotation mode to quaternion
    obj.rotation_mode = "QUATERNION"

    # Insert keyframes
    for kf in blender_keyframes:
        _insert_keyframe(obj, kf)


def _apply_local_offset_to_keyframes(
    keyframes: list[BlenderKeyframe],
    local_offset: tuple[tuple[float, float, float], tuple[float, float, float, float]],
) -> list[BlenderKeyframe]:
    """Apply local offset to keyframes for inherited animations.

    When animation is inherited from a parent node, we need to transform
    the parent's keyframes by the child's local offset.

    Args:
        keyframes: List of BlenderKeyframe
        local_offset: (position_offset, rotation_offset) in (x,y,z), (x,y,z,w) format

    Returns:
        New list of keyframes with offset applied
    """
    from ..scene.transforms import (
        Transform,
        combine_transforms,
    )
    from ..animation.keyframe_converter import (
        convert_quaternion_to_blender,
    )

    pos_offset, rot_offset = local_offset
    offset_transform = Transform(
        translation=pos_offset,
        rotation=rot_offset,
        scale=(1.0, 1.0, 1.0),
    )

    result = []
    for kf in keyframes:
        # Build parent transform from keyframe
        # Note: Blender keyframes have rotation in (w,x,y,z), need to convert to (x,y,z,w)
        parent_pos = kf.location or (0.0, 0.0, 0.0)
        if kf.rotation_quaternion:
            # Blender format is (w,x,y,z), convert to internal (x,y,z,w)
            w, x, y, z = kf.rotation_quaternion
            parent_rot = (x, y, z, w)
        else:
            parent_rot = (0.0, 0.0, 0.0, 1.0)
        parent_scale = kf.scale or (1.0, 1.0, 1.0)

        parent_transform = Transform(
            translation=parent_pos,
            rotation=parent_rot,
            scale=parent_scale,
        )

        # Combine: child_world = parent * local_offset
        combined = combine_transforms(parent_transform, offset_transform)

        # Convert rotation back to Blender format (w,x,y,z)
        new_rot = convert_quaternion_to_blender(combined.rotation)

        result.append(
            BlenderKeyframe(
                frame=kf.frame,
                location=combined.translation,
                rotation_quaternion=new_rot,
                scale=combined.scale if kf.scale else None,
            )
        )

    return result


def _apply_import_matrix_to_keyframes(
    keyframes: list[BlenderKeyframe],
    import_matrix: "mathutils.Matrix",
) -> list[BlenderKeyframe]:
    """Apply glTF import coordinate conversion to keyframes.

    For glTF objects, the importer applies a coordinate conversion rotation
    (e.g., Y-up to Z-up). When animating, each keyframe's meshcat transform
    must be combined with this import matrix to preserve correct orientation.

    The final transform is: meshcat_keyframe_matrix @ import_matrix

    Args:
        keyframes: List of BlenderKeyframe (already in Blender convention)
        import_matrix: Coordinate conversion matrix from glTF importer

    Returns:
        New list of keyframes with import matrix applied
    """
    import mathutils

    result = []
    for kf in keyframes:
        loc = kf.location or (0.0, 0.0, 0.0)
        scale = kf.scale or (1.0, 1.0, 1.0)

        if kf.rotation_quaternion:
            quat = mathutils.Quaternion(kf.rotation_quaternion)
        else:
            quat = mathutils.Quaternion()  # identity

        # Build meshcat keyframe matrix
        meshcat_matrix = mathutils.Matrix.LocRotScale(
            mathutils.Vector(loc),
            quat,
            mathutils.Vector(scale),
        )

        # Combine: meshcat positioning × import coordinate conversion
        combined = meshcat_matrix @ import_matrix

        # Decompose back to loc, rot, scale
        new_loc, new_rot, new_scale = combined.decompose()

        result.append(
            BlenderKeyframe(
                frame=kf.frame,
                location=tuple(new_loc),
                rotation_quaternion=(new_rot.w, new_rot.x, new_rot.y, new_rot.z),
                scale=tuple(new_scale) if kf.scale else None,
            )
        )

    return result


def _insert_keyframe(obj: bpy.types.Object, kf: BlenderKeyframe) -> None:
    """Insert a single keyframe.

    Args:
        obj: Blender object
        kf: BlenderKeyframe with transform data
    """
    frame = kf.frame

    if kf.location is not None:
        obj.location = kf.location
        obj.keyframe_insert(data_path="location", frame=frame)

    if kf.rotation_quaternion is not None:
        obj.rotation_quaternion = kf.rotation_quaternion
        obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    if kf.scale is not None:
        obj.scale = kf.scale
        obj.keyframe_insert(data_path="scale", frame=frame)


def apply_animation_batch(
    objects: dict[str, bpy.types.Object],
    nodes: list[SceneNode],
    fps: float = 30.0,
    start_frame: int = 0,
) -> None:
    """Apply animations to multiple objects efficiently.

    Args:
        objects: Dictionary mapping node paths to Blender objects
        nodes: List of SceneNodes with keyframe data
        fps: Frames per second
        start_frame: Starting frame number
    """
    animated_nodes = [n for n in nodes if n.keyframes]

    for node in animated_nodes:
        obj = objects.get(node.path)
        if obj is not None:
            apply_animation(obj, node, fps, start_frame)


def set_animation_range(
    nodes: list[SceneNode],
    recording_fps: float = 1000.0,
    target_fps: float = 30.0,
    start_frame: int = 0,
) -> tuple[int, int]:
    """Set the scene's animation range based on keyframe data.

    Args:
        nodes: List of SceneNodes with keyframe data
        recording_fps: FPS of the original recording
        target_fps: Target FPS for Blender animation
        start_frame: Starting frame number

    Returns:
        Tuple of (start_frame, end_frame)
    """
    frame_start, frame_end = get_animation_range(
        nodes,
        recording_fps=recording_fps,
        target_fps=target_fps,
        start_frame=start_frame,
    )

    # Set scene frame range
    bpy.context.scene.frame_start = frame_start
    bpy.context.scene.frame_end = frame_end
    bpy.context.scene.frame_current = frame_start

    return (frame_start, frame_end)


def create_shared_action(
    name: str,
    objects: list[bpy.types.Object],
    nodes: list[SceneNode],
    fps: float = 30.0,
    start_frame: int = 0,
) -> bpy.types.Action | None:
    """Create a single action with multiple slots for related objects.

    This is useful when objects should share timing but have different transforms.

    Args:
        name: Action name
        objects: List of Blender objects
        nodes: List of corresponding SceneNodes
        fps: Frames per second
        start_frame: Starting frame number

    Returns:
        The created Action, or None if no animations
    """
    if not objects or not nodes:
        return None

    # Check if any nodes have keyframes
    if not any(n.keyframes for n in nodes):
        return None

    # Create single action
    action = bpy.data.actions.new(name=name)

    for obj, node in zip(objects, nodes):
        if not node.keyframes:
            continue

        # Create animation data if needed
        if obj.animation_data is None:
            obj.animation_data_create()

        try:
            # Blender 5.0: Create slot for each object
            slot = action.slots.new(id_type="OBJECT", name=obj.name)
            obj.animation_data.action = action
            obj.animation_data.action_slot = slot
        except AttributeError:
            # Older Blender: Each object needs its own action
            obj_action = bpy.data.actions.new(name=f"{obj.name}Action")
            obj.animation_data.action = obj_action

        # Set rotation mode
        obj.rotation_mode = "QUATERNION"

        # Convert and insert keyframes
        blender_keyframes = convert_keyframes_to_blender(
            node.keyframes, fps, start_frame
        )

        for kf in blender_keyframes:
            _insert_keyframe(obj, kf)

    return action
