bl_info = {
    "name": "GOH GEM Exporter",
    "author": "Mika&Codex",
    "version": (1, 1, 0),
    "blender": (3, 6, 0),
    "location": "File > Export / Import > GOH, View3D > Sidebar > GOH",
    "description": "Import and export Gates of Hell GEM .mdl/.ply/.mtl/.vol/.anm assets from Blender",
    "category": "Import-Export",
}

from .blender_exporter import register, unregister


__all__ = ("register", "unregister")
