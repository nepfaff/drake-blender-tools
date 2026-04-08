# SPDX-License-Identifier: MIT
"""Meshcat HTML Importer - Import meshcat recordings into Blender."""

from meshcat_html_importer.parser import parse_html_recording
from meshcat_html_importer.scene import SceneGraph

__version__ = "0.1.2"
__all__ = ["parse_html_recording", "SceneGraph"]
