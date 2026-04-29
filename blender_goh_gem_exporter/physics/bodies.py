from __future__ import annotations

from dataclasses import dataclass, field

from mathutils import Vector


@dataclass(frozen=True)
class InertialBody:
    name: str = ""
    mass: float = 1.0
    inertia: Vector = field(default_factory=lambda: Vector((1.0, 1.0, 1.0)))
    center_of_mass_offset: Vector = field(default_factory=lambda: Vector((0.0, 0.0, 0.0)))

    def safe_mass(self) -> float:
        return max(0.001, float(self.mass))

    def safe_inertia(self) -> Vector:
        return Vector(tuple(max(0.001, float(value)) for value in self.inertia))
