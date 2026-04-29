from __future__ import annotations

from mathutils import Vector


def combine_offset(primary_axis: Vector, side_axis: Vector, up_axis: Vector, values: Vector) -> Vector:
    return primary_axis * float(values.x) + side_axis * float(values.y) + up_axis * float(values.z)
