from __future__ import annotations

from dataclasses import dataclass

from mathutils import Matrix, Quaternion, Vector


@dataclass(frozen=True)
class MotionSample:
    frame: int
    matrix_world: Matrix
    location: Vector
    rotation: Quaternion


def sample_object_motion(obj, frames: list[int], scene) -> list[MotionSample]:
    if obj is None or scene is None or not frames:
        return []
    current_frame = int(scene.frame_current)
    samples: list[MotionSample] = []
    try:
        for frame in frames:
            scene.frame_set(int(frame))
            matrix = obj.matrix_world.copy()
            samples.append(
                MotionSample(
                    frame=int(frame),
                    matrix_world=matrix,
                    location=matrix.to_translation(),
                    rotation=matrix.to_quaternion(),
                )
            )
    finally:
        scene.frame_set(current_frame)
    return samples


def sampled_linear_accelerations(samples: list[MotionSample], fps: float) -> list[Vector]:
    if not samples:
        return []
    dt = 1.0 / max(1.0, float(fps))
    result: list[Vector] = []
    for index, sample in enumerate(samples):
        if index == 0 or index == len(samples) - 1:
            result.append(Vector((0.0, 0.0, 0.0)))
            continue
        previous_location = samples[index - 1].location
        current_location = sample.location
        next_location = samples[index + 1].location
        result.append((next_location - current_location * 2.0 + previous_location) / (dt * dt))
    return result
