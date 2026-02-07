# SPDX-License-Identifier: MIT
"""Command-line interface for meshcat HTML importer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    """Import a meshcat HTML recording into Blender."""
    parser = argparse.ArgumentParser(
        description="Import meshcat HTML recordings into Blender"
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input HTML file from meshcat recording",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output.blend"),
        help="Output Blender file path (default: output.blend)",
    )
    parser.add_argument(
        "--recording-fps",
        type=float,
        default=None,
        help=(
            "FPS of the original recording "
            "(default: auto-detect from file, fallback 64)"
        ),
    )
    parser.add_argument(
        "--target-fps",
        type=float,
        default=30.0,
        help="Target FPS for Blender animation (default: 30)",
    )
    parser.add_argument(
        "--start-frame",
        type=int,
        default=0,
        help="Starting frame number (default: 0)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    if args.output.suffix != ".blend":
        print(
            f"Error: Output file must have .blend extension, got: {args.output.suffix}",
            file=sys.stderr,
        )
        return 1

    # Import here to allow CLI help without bpy
    try:
        import bpy
    except ImportError:
        print(
            "Error: This command must be run inside Blender.\n"
            "Use: blender --background --python -m meshcat_html_importer <args>",
            file=sys.stderr,
        )
        return 1

    from meshcat_html_importer.blender import build_scene
    from meshcat_html_importer.parser import parse_html_recording

    print(f"Parsing {args.input}...")
    scene_data = parse_html_recording(args.input)

    # Determine recording FPS (from file or argument)
    recording_fps = args.recording_fps
    if recording_fps is None:
        # Try to extract from scene data
        recording_fps = scene_data.get("animation_fps", 64.0)
    print(f"Recording FPS: {recording_fps}, Target FPS: {args.target_fps}")

    print("Building Blender scene...")
    build_scene(
        scene_data,
        recording_fps=recording_fps,
        target_fps=args.target_fps,
        start_frame=args.start_frame,
    )

    print(f"Saving to {args.output}...")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.absolute()))

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
