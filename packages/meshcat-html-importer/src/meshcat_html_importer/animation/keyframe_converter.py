# SPDX-License-Identifier: MIT
"""Convert animation keyframes between formats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meshcat_html_importer.scene.scene_graph import AnimationKeyframe, SceneNode


@dataclass
class BlenderKeyframe:
    """A keyframe in Blender format."""

    frame: int
    location: tuple[float, float, float] | None = None
    rotation_quaternion: tuple[float, float, float, float] | None = None  # (w,x,y,z)
    scale: tuple[float, float, float] | None = None


def convert_quaternion_to_blender(
    quat: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Convert quaternion from Three.js (x,y,z,w) to Blender (w,x,y,z).

    Args:
        quat: Quaternion in Three.js format (x, y, z, w)

    Returns:
        Quaternion in Blender format (w, x, y, z)
    """
    x, y, z, w = quat
    return (w, x, y, z)


def time_to_frame(
    time_value: float,
    recording_fps: float,
    target_fps: float,
    start_frame: int = 0,
) -> int:
    """Convert recording time to target frame number.

    Args:
        time_value: Time value from recording (frame number at recording_fps)
        recording_fps: FPS of the original recording
        target_fps: Target FPS for Blender
        start_frame: Starting frame offset

    Returns:
        Frame number at target FPS
    """
    # Convert recording frame to seconds, then to target frame
    time_seconds = time_value / recording_fps
    return start_frame + int(round(time_seconds * target_fps))


def downsample_keyframes(
    keyframes: list[AnimationKeyframe],
    recording_fps: float,
    target_fps: float,
) -> list[AnimationKeyframe]:
    """Downsample keyframes from recording FPS to target FPS.

    Uses linear interpolation between keyframes to match Three.js behavior.
    Position and scale are linearly interpolated; rotation uses normalized
    linear interpolation (nlerp).

    Args:
        keyframes: Original keyframes at recording_fps
        recording_fps: FPS of the original recording
        target_fps: Target FPS for output

    Returns:
        Downsampled list of keyframes
    """
    if not keyframes or target_fps >= recording_fps:
        return keyframes

    # Sort by time
    sorted_kfs = sorted(keyframes, key=lambda kf: kf.time)

    if len(sorted_kfs) < 2:
        return sorted_kfs

    # Use absolute time (from 0) so all nodes share the same time base.
    # This prevents time-shifting when a node's keyframes start later than t=0.
    min_time = 0.0
    max_time = sorted_kfs[-1].time
    duration_seconds = max_time / recording_fps

    # Calculate target frame count
    target_frame_count = int(duration_seconds * target_fps) + 1

    # Build list of times for binary search
    all_times = [kf.time for kf in sorted_kfs]

    import bisect

    from meshcat_html_importer.scene.scene_graph import AnimationKeyframe

    result = []
    for target_frame in range(target_frame_count):
        target_time_seconds = target_frame / target_fps
        target_recording_time = min_time + target_time_seconds * recording_fps

        # Find bracketing keyframes using binary search
        idx = bisect.bisect_right(all_times, target_recording_time)

        if idx == 0:
            # Before first keyframe - use first
            kf = sorted_kfs[0]
            result.append(
                AnimationKeyframe(
                    time=float(target_frame),
                    position=kf.position,
                    rotation=kf.rotation,
                    scale=kf.scale,
                )
            )
        elif idx >= len(sorted_kfs):
            # After last keyframe - use last
            kf = sorted_kfs[-1]
            result.append(
                AnimationKeyframe(
                    time=float(target_frame),
                    position=kf.position,
                    rotation=kf.rotation,
                    scale=kf.scale,
                )
            )
        else:
            # Interpolate between kf_a and kf_b
            kf_a = sorted_kfs[idx - 1]
            kf_b = sorted_kfs[idx]
            dt = kf_b.time - kf_a.time
            t = (target_recording_time - kf_a.time) / dt if dt > 0 else 0.0

            pos = _lerp_tuple3(kf_a.position, kf_b.position, t)
            rot = _nlerp_quat(kf_a.rotation, kf_b.rotation, t)
            sc = _lerp_tuple3(kf_a.scale, kf_b.scale, t)

            result.append(
                AnimationKeyframe(
                    time=float(target_frame),
                    position=pos,
                    rotation=rot,
                    scale=sc,
                )
            )

    return result


def _lerp_tuple3(
    a: tuple[float, float, float] | None,
    b: tuple[float, float, float] | None,
    t: float,
) -> tuple[float, float, float] | None:
    """Linearly interpolate between two 3-tuples."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _nlerp_quat(
    a: tuple[float, float, float, float] | None,
    b: tuple[float, float, float, float] | None,
    t: float,
) -> tuple[float, float, float, float] | None:
    """Normalized linear interpolation for quaternions (x,y,z,w)."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    import math

    # Ensure shortest path (flip b if dot product is negative)
    dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
    if dot < 0:
        b = (-b[0], -b[1], -b[2], -b[3])

    # Lerp
    x = a[0] + (b[0] - a[0]) * t
    y = a[1] + (b[1] - a[1]) * t
    z = a[2] + (b[2] - a[2]) * t
    w = a[3] + (b[3] - a[3]) * t

    # Normalize
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length > 0:
        x /= length
        y /= length
        z /= length
        w /= length

    return (x, y, z, w)


def convert_keyframes_to_blender(
    keyframes: list[AnimationKeyframe],
    recording_fps: float = 1000.0,
    target_fps: float = 30.0,
    start_frame: int = 0,
    downsample: bool = True,
) -> list[BlenderKeyframe]:
    """Convert meshcat keyframes to Blender format.

    Args:
        keyframes: List of AnimationKeyframe from scene node
        recording_fps: FPS of the original recording
                      (default 1000 for Drake simulations)
        target_fps: Target FPS for Blender animation
        start_frame: Starting frame number
        downsample: Whether to downsample to target FPS

    Returns:
        List of BlenderKeyframe objects
    """
    if not keyframes:
        return []

    # Downsample if requested
    if downsample:
        processed_kfs = downsample_keyframes(keyframes, recording_fps, target_fps)
    else:
        processed_kfs = keyframes

    blender_keyframes = []

    for kf in processed_kfs:
        # After downsampling, time is already in target frames
        if downsample:
            frame = start_frame + int(round(kf.time))
        else:
            frame = time_to_frame(kf.time, recording_fps, target_fps, start_frame)

        # Convert quaternion format
        rotation = None
        if kf.rotation is not None:
            rotation = convert_quaternion_to_blender(kf.rotation)

        blender_kf = BlenderKeyframe(
            frame=frame,
            location=kf.position,
            rotation_quaternion=rotation,
            scale=kf.scale,
        )
        blender_keyframes.append(blender_kf)

    return blender_keyframes


def get_animation_range(
    nodes: list[SceneNode],
    recording_fps: float = 1000.0,
    target_fps: float = 30.0,
    start_frame: int = 0,
) -> tuple[int, int]:
    """Get the frame range for all animations at target FPS.

    Args:
        nodes: List of scene nodes with keyframes
        recording_fps: FPS of the original recording
        target_fps: Target FPS for Blender
        start_frame: Starting frame number

    Returns:
        Tuple of (start_frame, end_frame)
    """
    min_frame = start_frame
    max_time = 0

    for node in nodes:
        for kf in node.keyframes:
            max_time = max(max_time, kf.time)

    # Convert max time to target frame
    duration_seconds = max_time / recording_fps
    max_frame = start_frame + int(round(duration_seconds * target_fps))

    return (min_frame, max_frame)
