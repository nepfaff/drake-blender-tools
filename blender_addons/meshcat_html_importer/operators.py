# SPDX-License-Identifier: MIT
"""Blender operators for meshcat HTML import."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from .blender_impl.scene_builder import build_scene_from_file
from .parser import parse_html_recording


class IMPORT_OT_meshcat_html(Operator, ImportHelper):
    """Import a meshcat HTML recording."""

    bl_idname = "import_scene.meshcat_html"
    bl_label = "Import Meshcat HTML"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".html"
    filter_glob: StringProperty(default="*.html;*.htm", options={"HIDDEN"})

    recording_fps: FloatProperty(
        name="Recording FPS",
        description=(
            "FPS of the original recording "
            "(0 = auto-detect from file, Drake default: 64)"
        ),
        default=0.0,
        min=0.0,
        max=10000.0,
    )

    target_fps: FloatProperty(
        name="Target FPS",
        description="Target FPS for Blender animation",
        default=30.0,
        min=1.0,
        max=120.0,
    )

    start_frame: IntProperty(
        name="Start Frame",
        description="Starting frame number",
        default=0,
        min=0,
    )

    clear_scene: BoolProperty(
        name="Clear Scene",
        description="Remove existing objects before import",
        default=True,
    )

    hierarchical_collections: BoolProperty(
        name="Hierarchical Collections",
        description="Create nested collections mirroring meshcat path structure",
        default=True,
    )

    collection_root: StringProperty(
        name="Collection Root",
        description=(
            "Custom prefix to strip from paths (leave empty for auto-detection)"
        ),
        default="",
    )

    def execute(self, context):
        try:
            recording_fps = self.recording_fps if self.recording_fps > 0 else None

            created_objects = build_scene_from_file(
                self.filepath,
                recording_fps=recording_fps,
                target_fps=self.target_fps,
                start_frame=self.start_frame,
                clear_scene=self.clear_scene,
                hierarchical_collections=self.hierarchical_collections,
                collection_root=self.collection_root,
            )

            animation_count = sum(
                1
                for obj in created_objects.values()
                if obj.animation_data and obj.animation_data.action
            )

            scene_data = parse_html_recording(self.filepath)
            actual_fps = recording_fps or scene_data.get("animation_fps", 64.0)

            self.report(
                {"INFO"},
                f"Imported {len(created_objects)} objects, "
                f"{animation_count} animations "
                f"(Recording: {actual_fps} FPS, Target: {self.target_fps} FPS)",
            )
            return {"FINISHED"}
        except Exception as e:
            self.report({"ERROR"}, f"Import failed: {str(e)}")
            import traceback

            traceback.print_exc()
            return {"CANCELLED"}


def register():
    bpy.utils.register_class(IMPORT_OT_meshcat_html)


def unregister():
    bpy.utils.unregister_class(IMPORT_OT_meshcat_html)
