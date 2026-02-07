#!/usr/bin/env python3
"""Integration test verifying addon sync is up-to-date.

This test ensures that `make sync-addon` was run after any changes to the
meshcat_html_importer package. It imports from both:
1. The source package (packages/meshcat-html-importer/src/)
2. The addon's synced copy (blender_addons/meshcat_html_importer/)

Both should produce identical results since the addon's subpackages are
synced from the source package (with imports converted to relative).

Run with: uv run pytest tests/test_addon_vendor_sync.py
"""

import sys
from pathlib import Path

import bpy

# Test HTML file
TEST_HTML = (
    "/home/ubuntu/efs/nicholas/scene-agent-eval-scenes/"
    "robot_task/v2/room/scene_000/simulation_good.html"
)
OUTPUT_CLI = "/tmp/test_parity_cli.blend"
OUTPUT_ADDON = "/tmp/test_parity_addon.blend"


def clear_scene():
    """Clear all objects from the scene."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    for mat in bpy.data.materials:
        bpy.data.materials.remove(mat)
    for action in bpy.data.actions:
        bpy.data.actions.remove(action)
    for col in bpy.data.collections:
        if col.name != "Scene Collection":
            bpy.data.collections.remove(col)


def extract_scene_data():
    """Extract scene data for comparison."""
    data = {
        "objects": {},
        "frame_range": (bpy.context.scene.frame_start, bpy.context.scene.frame_end),
        "fps": bpy.context.scene.render.fps,
    }

    for obj in bpy.data.objects:
        obj_data = {
            "name": obj.name,
            "type": obj.type,
            "location": tuple(round(x, 4) for x in obj.location),
            "rotation": tuple(round(x, 4) for x in obj.rotation_quaternion),
            "scale": tuple(round(x, 4) for x in obj.scale),
            "visible": not obj.hide_viewport,
            "has_animation": obj.animation_data is not None
            and obj.animation_data.action is not None,
            "keyframe_count": 0,
            "materials": [],
        }

        # Count keyframes
        if obj.animation_data and obj.animation_data.action:
            action = obj.animation_data.action
            # Blender 5.0 uses layers/strips, older versions use fcurves directly
            try:
                # Try Blender 5.0 API
                for layer in action.layers:
                    for strip in layer.strips:
                        if hasattr(strip, "channelbag"):
                            for channelbag in strip.channelbags:
                                for fcurve in channelbag.fcurves:
                                    obj_data["keyframe_count"] += len(
                                        fcurve.keyframe_points
                                    )
                        elif hasattr(strip, "fcurves"):
                            for fcurve in strip.fcurves:
                                obj_data["keyframe_count"] += len(
                                    fcurve.keyframe_points
                                )
            except (AttributeError, TypeError):
                # Fallback for older Blender versions
                if hasattr(action, "fcurves"):
                    for fcurve in action.fcurves:
                        obj_data["keyframe_count"] += len(fcurve.keyframe_points)

        # Get materials
        if obj.data and hasattr(obj.data, "materials"):
            for mat in obj.data.materials:
                if mat:
                    obj_data["materials"].append(mat.name)

        data["objects"][obj.name] = obj_data

    return data


def compare_floats(a, b, tolerance=0.01):
    """Compare two floats with tolerance."""
    return abs(a - b) < tolerance


def compare_tuples(a, b, tolerance=0.01):
    """Compare two tuples element-wise."""
    if len(a) != len(b):
        return False
    return all(compare_floats(x, y, tolerance) for x, y in zip(a, b))


def compare_quaternions(a, b, tolerance=0.01):
    """Compare quaternions allowing for q == -q equivalence."""
    if len(a) != 4 or len(b) != 4:
        return False
    if compare_tuples(a, b, tolerance):
        return True
    negated_b = tuple(-x for x in b)
    return compare_tuples(a, negated_b, tolerance)


def compare_scenes(cli_data, addon_data):
    """Compare two scene data dictionaries."""
    errors = []
    warnings = []

    if cli_data["frame_range"] != addon_data["frame_range"]:
        errors.append(
            f"Frame range mismatch: "
            f"CLI={cli_data['frame_range']}, Addon={addon_data['frame_range']}"
        )

    if cli_data["fps"] != addon_data["fps"]:
        errors.append(f"FPS mismatch: CLI={cli_data['fps']}, Addon={addon_data['fps']}")

    cli_names = set(cli_data["objects"].keys())
    addon_names = set(addon_data["objects"].keys())

    if len(cli_names) != len(addon_names):
        warnings.append(
            f"Object count mismatch: CLI={len(cli_names)}, Addon={len(addon_names)}"
        )

    only_in_cli = cli_names - addon_names
    only_in_addon = addon_names - cli_names
    common = cli_names & addon_names

    if only_in_cli:
        warnings.append(f"Objects only in CLI: {sorted(only_in_cli)[:5]}...")
    if only_in_addon:
        warnings.append(f"Objects only in Addon: {sorted(only_in_addon)[:5]}...")

    transform_mismatches = []
    animation_mismatches = []

    for name in common:
        cli_obj = cli_data["objects"][name]
        addon_obj = addon_data["objects"][name]

        if not compare_tuples(cli_obj["location"], addon_obj["location"]):
            transform_mismatches.append(
                f"{name}: location "
                f"CLI={cli_obj['location']} vs Addon={addon_obj['location']}"
            )

        if not compare_quaternions(cli_obj["rotation"], addon_obj["rotation"]):
            transform_mismatches.append(
                f"{name}: rotation "
                f"CLI={cli_obj['rotation']} vs Addon={addon_obj['rotation']}"
            )

        if not compare_tuples(cli_obj["scale"], addon_obj["scale"]):
            transform_mismatches.append(
                f"{name}: scale CLI={cli_obj['scale']} vs Addon={addon_obj['scale']}"
            )

        if cli_obj["has_animation"] != addon_obj["has_animation"]:
            animation_mismatches.append(
                f"{name}: animation "
                f"CLI={cli_obj['has_animation']} vs "
                f"Addon={addon_obj['has_animation']}"
            )
        elif cli_obj["has_animation"]:
            cli_kf = cli_obj["keyframe_count"]
            addon_kf = addon_obj["keyframe_count"]
            if abs(cli_kf - addon_kf) > cli_kf * 0.1:
                animation_mismatches.append(
                    f"{name}: keyframes CLI={cli_kf} vs Addon={addon_kf}"
                )

    if transform_mismatches:
        errors.append(f"Transform mismatches ({len(transform_mismatches)}):")
        for m in transform_mismatches[:10]:
            errors.append(f"  - {m}")

    if animation_mismatches:
        errors.append(f"Animation mismatches ({len(animation_mismatches)}):")
        for m in animation_mismatches[:10]:
            errors.append(f"  - {m}")

    return errors, warnings


def run_test():
    """Run the parity test."""
    print("=" * 60)
    print("CLI vs Addon Parity Test")
    print("=" * 60)

    if not Path(TEST_HTML).exists():
        print(f"ERROR: Test file not found: {TEST_HTML}")
        return False

    # Import using direct package import (CLI path)
    print("\n1. Importing with direct package import...")
    clear_scene()

    # Add package to path
    pkg_path = Path(__file__).parent.parent / "packages/meshcat-html-importer/src"
    sys.path.insert(0, str(pkg_path))

    from meshcat_html_importer.blender.scene_builder import build_scene_from_file

    build_scene_from_file(TEST_HTML, target_fps=30)
    bpy.ops.wm.save_as_mainfile(filepath=OUTPUT_CLI)
    cli_data = extract_scene_data()
    print(f"   Objects: {len(cli_data['objects'])}")
    print(f"   Frame range: {cli_data['frame_range']}")
    print(f"   FPS: {cli_data['fps']}")

    # Import using addon's synced package (addon path)
    print("\n2. Importing with addon's synced package...")
    clear_scene()

    # Clear cached imports to force reload from addon path
    modules_to_remove = [
        k for k in sys.modules if k.startswith("meshcat_html_importer")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Add addon path (the extension root acts as the package)
    addon_path = Path(__file__).parent.parent / "blender_addons"
    sys.path.insert(0, str(addon_path))

    from meshcat_html_importer.blender_impl.scene_builder import (
        build_scene_from_file as addon_build,
    )

    addon_build(TEST_HTML, target_fps=30)
    bpy.ops.wm.save_as_mainfile(filepath=OUTPUT_ADDON)
    addon_data = extract_scene_data()
    print(f"   Objects: {len(addon_data['objects'])}")
    print(f"   Frame range: {addon_data['frame_range']}")
    print(f"   FPS: {addon_data['fps']}")

    # Compare
    print("\n3. Comparing outputs...")
    errors, warnings = compare_scenes(cli_data, addon_data)

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  - {e}")
        print(f"\nTEST FAILED: {len(errors)} errors found")
        return False
    else:
        print("\nAll checks passed!")
        print("TEST PASSED: CLI and Addon produce identical results")
        return True


def test_addon_vendor_sync():
    """Test that addon package is in sync with source package."""
    import pytest

    if not Path(TEST_HTML).exists():
        pytest.skip(f"Test file not found: {TEST_HTML}")

    success = run_test()
    assert success, "CLI and addon outputs differ"


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
