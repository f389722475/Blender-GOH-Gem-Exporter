from __future__ import annotations

from mathutils import Vector


def finite_vector(vector: Vector) -> bool:
    return all(abs(float(value)) < 1.0e20 and float(value) == float(value) for value in vector)
