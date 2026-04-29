from __future__ import annotations

from dataclasses import dataclass, field

from mathutils import Vector

from .frames import SolverSpace


@dataclass(frozen=True)
class RoleInertiaPreset:
    solver_space: SolverSpace = SolverSpace.PARENT_LOCAL
    reaction_sign: float = 1.0
    inertial_lag_sign: float = -1.0
    linear_axes: Vector = field(default_factory=lambda: Vector((1.0, 0.35, 0.25)))
    angular_axes: Vector = field(default_factory=lambda: Vector((0.0, 1.0, 0.0)))
    max_offset_factor: Vector = field(default_factory=lambda: Vector((0.85, 0.18, 0.20)))
    max_angle_factor: Vector = field(default_factory=lambda: Vector((0.15, 1.0, 0.20)))
    linear_gain: float = 1.0
    angular_gain: float = 0.45
    side_coupling: float = 0.08
    vertical_coupling: float = 0.12
    rotation_coupling: float = 0.42


def role_inertia_preset(role: str) -> RoleInertiaPreset:
    role = str(role or "").strip().upper()
    if role == "BODY_SPRING":
        return RoleInertiaPreset(
            solver_space=SolverSpace.PARENT_LOCAL,
            reaction_sign=1.0,
            linear_axes=Vector((1.0, 0.28, 0.22)),
            angular_axes=Vector((0.0, 1.0, 0.20)),
            max_offset_factor=Vector((0.90, 0.16, 0.18)),
            max_angle_factor=Vector((0.10, 1.0, 0.18)),
            linear_gain=1.10,
            angular_gain=0.52,
            side_coupling=0.12,
            vertical_coupling=-0.18,
            rotation_coupling=0.58,
        )
    if role == "ACCESSORY_JITTER":
        return RoleInertiaPreset(
            solver_space=SolverSpace.PARENT_LOCAL,
            reaction_sign=0.72,
            linear_axes=Vector((0.75, 0.65, 0.45)),
            angular_axes=Vector((0.35, 0.85, 0.45)),
            max_offset_factor=Vector((0.42, 0.28, 0.20)),
            max_angle_factor=Vector((0.35, 0.75, 0.45)),
            linear_gain=0.78,
            angular_gain=0.48,
            side_coupling=0.32,
            vertical_coupling=0.18,
            rotation_coupling=0.45,
        )
    if role == "SUSPENSION_BOUNCE":
        return RoleInertiaPreset(
            solver_space=SolverSpace.PARENT_LOCAL,
            reaction_sign=0.55,
            linear_axes=Vector((0.35, 0.10, 0.90)),
            angular_axes=Vector((0.25, 0.80, 0.15)),
            max_offset_factor=Vector((0.24, 0.08, 0.44)),
            max_angle_factor=Vector((0.20, 0.85, 0.12)),
            linear_gain=0.92,
            angular_gain=0.42,
            side_coupling=0.05,
            vertical_coupling=-0.42,
            rotation_coupling=0.36,
        )
    if role == "TRACK_RUMBLE":
        return RoleInertiaPreset(
            solver_space=SolverSpace.PARENT_LOCAL,
            reaction_sign=0.38,
            linear_axes=Vector((0.35, 0.22, 0.32)),
            angular_axes=Vector((0.14, 0.30, 0.20)),
            max_offset_factor=Vector((0.18, 0.12, 0.14)),
            max_angle_factor=Vector((0.12, 0.32, 0.16)),
            linear_gain=0.44,
            angular_gain=0.24,
            side_coupling=0.20,
            vertical_coupling=0.16,
            rotation_coupling=0.20,
        )
    return RoleInertiaPreset(
        solver_space=SolverSpace.PARENT_LOCAL,
        reaction_sign=0.62,
        linear_axes=Vector((0.65, 0.20, 0.16)),
        angular_axes=Vector((0.08, 0.55, 0.12)),
        max_offset_factor=Vector((0.34, 0.12, 0.10)),
        max_angle_factor=Vector((0.10, 0.55, 0.12)),
        linear_gain=0.62,
        angular_gain=0.30,
        side_coupling=0.08,
        vertical_coupling=0.05,
        rotation_coupling=0.24,
    )
