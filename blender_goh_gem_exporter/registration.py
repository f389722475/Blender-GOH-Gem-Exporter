from __future__ import annotations


def register() -> None:
    from . import blender_exporter as legacy

    legacy._legacy_register()


def unregister() -> None:
    from . import blender_exporter as legacy

    legacy._legacy_unregister()
