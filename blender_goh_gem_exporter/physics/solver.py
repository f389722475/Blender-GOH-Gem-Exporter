from __future__ import annotations

from dataclasses import dataclass, field
import math

from mathutils import Vector

from .constraints import D6LiteLimit, apply_d6_lite_limits


def _zero_vector() -> Vector:
    return Vector((0.0, 0.0, 0.0))


@dataclass
class InertiaState:
    offset: Vector = field(default_factory=_zero_vector)
    velocity: Vector = field(default_factory=_zero_vector)
    angle: Vector = field(default_factory=_zero_vector)
    angular_velocity: Vector = field(default_factory=_zero_vector)


@dataclass(frozen=True)
class InertiaSolverSettings:
    frequency: float = 2.0
    damping_ratio: float = 0.22
    mass: float = 1.0
    inertia: Vector = field(default_factory=lambda: Vector((1.0, 1.0, 1.0)))
    linear_gain: float = 1.0
    angular_gain: float = 1.0
    substeps: int = 4
    force_limit: float = 0.0
    end_fade: float = 0.16
    d6_limit: D6LiteLimit = field(default_factory=D6LiteLimit)


def _safe_axis(vector: Vector, fallback: float = 1.0) -> Vector:
    return Vector(tuple(float(value) if abs(float(value)) > 1e-8 else fallback for value in vector))


def smootherstep(t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _soft_force_limit(vector: Vector, limit: float) -> Vector:
    limit = abs(float(limit))
    if limit <= 1e-8 or vector.length <= limit:
        return vector.copy()
    return vector.normalized() * limit


def _anti_windup_velocity(raw: Vector, clamped: Vector, velocity: Vector, axes: Vector) -> Vector:
    values = []
    for raw_value, clamped_value, velocity_value, axis_weight in zip(raw, clamped, velocity, axes):
        if abs(float(axis_weight)) <= 1e-8:
            values.append(0.0)
            continue
        if abs(float(raw_value) - float(clamped_value)) > 1e-7 and float(raw_value) * float(velocity_value) > 0.0:
            values.append(0.0)
            continue
        values.append(float(velocity_value))
    return Vector(tuple(values))


def step_inertia(
    state: InertiaState,
    anchor_acceleration: Vector,
    anchor_angular_acceleration: Vector,
    settings: InertiaSolverSettings,
    dt: float,
) -> InertiaState:
    dt = max(1e-5, float(dt))
    omega = 2.0 * math.pi * max(0.01, float(settings.frequency))
    stiffness = omega * omega
    damping = 2.0 * max(0.0, float(settings.damping_ratio)) * omega
    mass = max(0.001, float(settings.mass))
    inertia = _safe_axis(settings.inertia, 1.0)

    linear_drive = _soft_force_limit(anchor_acceleration * float(settings.linear_gain), settings.force_limit)
    angular_drive = _soft_force_limit(anchor_angular_acceleration * float(settings.angular_gain), settings.force_limit)

    linear_accel = (linear_drive - state.velocity * damping - state.offset * stiffness) / mass
    angular_accel = Vector(
        (
            (angular_drive.x - state.angular_velocity.x * damping - state.angle.x * stiffness) / max(0.001, inertia.x),
            (angular_drive.y - state.angular_velocity.y * damping - state.angle.y * stiffness) / max(0.001, inertia.y),
            (angular_drive.z - state.angular_velocity.z * damping - state.angle.z * stiffness) / max(0.001, inertia.z),
        )
    )

    next_state = InertiaState(
        offset=state.offset.copy(),
        velocity=state.velocity + linear_accel * dt,
        angle=state.angle.copy(),
        angular_velocity=state.angular_velocity + angular_accel * dt,
    )
    next_state.offset += next_state.velocity * dt
    next_state.angle += next_state.angular_velocity * dt
    raw_offset = next_state.offset.copy()
    raw_angle = next_state.angle.copy()
    next_state.offset, next_state.angle = apply_d6_lite_limits(next_state.offset, next_state.angle, settings.d6_limit)
    next_state.velocity = _anti_windup_velocity(raw_offset, next_state.offset, next_state.velocity, settings.d6_limit.linear_axes)
    next_state.angular_velocity = _anti_windup_velocity(raw_angle, next_state.angle, next_state.angular_velocity, settings.d6_limit.angular_axes)
    return next_state


def integrate_inertia_samples(
    linear_accelerations: list[Vector],
    angular_accelerations: list[Vector] | None,
    settings: InertiaSolverSettings,
    fps: float,
) -> list[tuple[Vector, Vector]]:
    if not linear_accelerations:
        return []
    angular_accelerations = angular_accelerations or [_zero_vector() for _ in linear_accelerations]
    substeps = max(1, int(settings.substeps))
    dt = 1.0 / max(1.0, float(fps)) / float(substeps)
    state = InertiaState()
    result: list[tuple[Vector, Vector]] = []
    for index, linear_accel in enumerate(linear_accelerations):
        angular_accel = angular_accelerations[min(index, len(angular_accelerations) - 1)]
        for _substep in range(substeps):
            state = step_inertia(state, linear_accel, angular_accel, settings, dt)
        result.append((state.offset.copy(), state.angle.copy()))
    fade_window = max(0.0, min(0.95, float(settings.end_fade)))
    if fade_window > 0.0 and len(result) > 1:
        start_t = 1.0 - fade_window
        denom = max(1e-5, fade_window)
        faded: list[tuple[Vector, Vector]] = []
        for index, (offset, angle) in enumerate(result):
            t = index / float(max(1, len(result) - 1))
            fade = 1.0 - smootherstep((t - start_t) / denom)
            if index == len(result) - 1:
                fade = 0.0
            faded.append((offset * fade, angle * fade))
        result = faded
    return result
