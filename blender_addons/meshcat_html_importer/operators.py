# SPDX-License-Identifier: MIT
"""Blender operators for meshcat HTML import."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper, poll_file_object_drop

from .blender_impl.scene_builder import build_scene_from_file
from .parser import parse_html_recording


class MESHCAT_FH_html(bpy.types.FileHandler):
    """Meshcat HTML drag-and-drop file handler."""

    bl_idname = "MESHCAT_FH_html"
    bl_label = "Meshcat HTML"
    bl_import_operator = "import_scene.meshcat_html"
    bl_file_extensions = ".html;.htm"

    @classmethod
    def poll_drop(cls, context):
        """Check if file drop is allowed in current context."""
        return poll_file_object_drop(context)


class IMPORT_OT_meshcat_html(Operator, ImportHelper):
    """Import a meshcat HTML recording."""

    bl_idname = "import_scene.meshcat_html"
    bl_label = "Import Meshcat HTML"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".html"
    filter_glob: StringProperty(default="*.html;*.htm", options={"HIDDEN"})

    filepath: StringProperty(
        name="File Path",
        description="Path to the meshcat HTML file",
        subtype='FILE_PATH',
        options={'SKIP_SAVE', 'HIDDEN'}
    )

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

    def invoke(self, context, event):
        """Show properties popup when file is dropped."""
        # Only show popup for drag-and-drop (not for menu import which uses ImportHelper)
        if not self.filepath:
            # Menu import - use default ImportHelper behavior
            return ImportHelper.invoke(self, context, event)

        # Drag-and-drop import - show properties in popup
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        """Draw operator properties in popup dialog."""
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(self, "recording_fps")
        layout.prop(self, "target_fps")
        layout.prop(self, "start_frame")
        layout.prop(self, "clear_scene")
        layout.prop(self, "hierarchical_collections")
        layout.prop(self, "collection_root")

    def execute(self, context):
        # Validate file exists
        if not self.filepath:
            self.report({'ERROR'}, "No file selected")
            return {'CANCELLED'}

        # Quick validation: check if file contains meshcat patterns
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                content = f.read(1000)  # Read first 1KB for quick check
                # Check for meshcat-specific patterns
                has_meshcat = ('meshcat' in content.lower() or
                              'MeshCat' in content or
                              'meshcat-pane' in content)
                if not has_meshcat:
                    self.report({'ERROR'}, "Not a valid meshcat HTML recording")
                    return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read file: {str(e)}")
            return {'CANCELLED'}

        # Initialize progress indicator
        wm = context.window_manager
        wm.progress_begin(0, 100)

        try:
            recording_fps = self.recording_fps if self.recording_fps > 0 else None

            # Step 1: Parse HTML file (0-30%)
            wm.progress_update(0)
            print("[Meshcat Import] Parsing meshcat HTML file... (0%)")
            self.report({'INFO'}, "Parsing meshcat HTML file...")
            scene_data = parse_html_recording(self.filepath)
            wm.progress_update(30)
            print("[Meshcat Import] Parsing complete (30%)")

            # Step 2: Build scene with progress tracking (30-100%)
            self.report({'INFO'}, "Building Blender scene...")

            # Create progress callback
            def update_progress(stage, current, total):
                """Update progress based on stage and item count."""
                # Map stages to progress ranges and descriptions
                stage_info = {
                    'clear_scene': (30, 35, "Clearing scene"),
                    'build_graph': (35, 40, "Building scene graph"),
                    'create_objects': (40, 80, "Creating objects"),
                    'apply_animations': (80, 95, "Applying animations"),
                    'finalize': (95, 100, "Finalizing"),
                }
                if stage in stage_info:
                    start, end, description = stage_info[stage]
                    if total > 0:
                        progress = start + int((current / total) * (end - start))
                        # Print to console for visibility
                        print(f"[Meshcat Import] {description}: {current}/{total} ({progress}%)")
                        # Only report every 10% or at milestones to avoid UI spam
                        if current == 0 or current == total or progress % 10 == 0:
                            self.report({'INFO'}, f"{description}: {current}/{total}")
                    else:
                        progress = end
                        print(f"[Meshcat Import] {description}... ({progress}%)")
                    wm.progress_update(progress)

            created_objects = build_scene_from_file(
                self.filepath,
                recording_fps=recording_fps,
                target_fps=self.target_fps,
                start_frame=self.start_frame,
                clear_scene=self.clear_scene,
                hierarchical_collections=self.hierarchical_collections,
                collection_root=self.collection_root,
                progress_callback=update_progress,
            )
            wm.progress_update(100)

            # Count animations
            animation_count = sum(
                1
                for obj in created_objects.values()
                if obj.animation_data and obj.animation_data.action
            )

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
        finally:
            # Always end progress indicator
            wm.progress_end()
            print("[Meshcat Import] Complete!")


def register():
    """Register operator and file handler classes."""
    bpy.utils.register_class(MESHCAT_FH_html)
    bpy.utils.register_class(IMPORT_OT_meshcat_html)


def unregister():
    """Unregister operator and file handler classes."""
    bpy.utils.unregister_class(IMPORT_OT_meshcat_html)
    bpy.utils.unregister_class(MESHCAT_FH_html)
