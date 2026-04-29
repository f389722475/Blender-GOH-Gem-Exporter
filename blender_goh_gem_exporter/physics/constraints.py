from __future__ import annotations

from dataclasses import dataclass, field

from mathutils import Vector


@dataclass(frozen=True)
class D6LiteLimit:
    linear_axes: Vector = field(default_factory=lambda: Vector((1.0, 1.0, 1.0)))
    angular_axes: Vector = field(default_factory=lambda: Vector((1.0, 1.0, 1.0)))
    max_offset: Vector = field(default_factory=lambda: Vector((0.25, 0.25, 0.25)))
    max_angle: Vector = field(default_factory=lambda: Vector((0.15, 0.15, 0.15)))


def _axis_weight(weight: float) -> float:
    return 0.0 if abs(float(weight)) <= 1e-8 else float(weight)


def _limit_component(value: float, enabled: float, limit: float) -> float:
    weight = _axis_weight(enabled)
    if weight == 0.0:
        return 0.0
    scaled = float(value) * weight
    limit = abs(float(limit))
    if limit <= 1e-8:
        return 0.0
    return max(-limit, min(limit, scaled))


def apply_d6_lite_limits(offset: Vector, angle: Vector, limits: D6LiteLimit) -> tuple[Vector, Vector]:
    return (
        Vector(
            (
                _limit_component(offset.x, limits.linear_axes.x, limits.max_offset.x),
                _limit_component(offset.y, limits.linear_axes.y, limits.max_offset.y),
                _limit_component(offset.z, limits.linear_axes.z, limits.max_offset.z),
            )
        ),
        Vector(
            (
                _limit_component(angle.x, limits.angular_axes.x, limits.max_angle.x),
                _limit_component(angle.y, limits.angular_axes.y, limits.max_angle.y),
                _limit_component(angle.z, limits.angular_axes.z, limits.max_angle.z),
            )
        ),
    )
