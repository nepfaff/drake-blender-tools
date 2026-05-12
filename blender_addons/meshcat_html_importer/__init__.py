# SPDX-License-Identifier: MIT
"""Meshcat HTML Importer - Import meshcat recordings into Blender.

This extension imports meshcat HTML and StaticZip recordings and converts them
to Blender scenes with full animation support.
"""

import bpy

from . import operators

bl_info = {
    "name": "Meshcat HTML Importer",
    "author": "Nicholas Pfaff",
    "version": (0, 1, 3),
    "blender": (5, 0, 0),  # Blender 5.0+ only
    "location": "File > Import > Meshcat Recording (.html, .zip, .meshcat)",
    "description": "Import meshcat recordings with geometry and animation",
    "category": "Import-Export",
}


def menu_func_import(self, context):
    """Add import menu entry."""
    self.layout.operator(
        operators.IMPORT_OT_meshcat_html.bl_idname,
        text="Meshcat Recording (.html, .zip, .meshcat)",
    )


def register():
    """Register the extension."""
    operators.register()
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    """Unregister the extension."""
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    operators.unregister()


if __name__ == "__main__":
    register()
