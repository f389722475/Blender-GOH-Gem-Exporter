from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mathutils import Matrix, Vector


class SolverSpace(str, Enum):
    WORLD = "WORLD"
    PARENT_LOCAL = "PARENT_LOCAL"
    SOURCE_LOCAL = "SOURCE_LOCAL"
    OBJECT_LOCAL = "OBJECT_LOCAL"
    CUSTOM_OBJECT = "CUSTOM_OBJECT"


@dataclass(frozen=True)
class SolverSpaceFrame:
    mode: SolverSpace
    matrix_world: Matrix

    @property
    def rotation_world(self) -> Matrix:
        return self.matrix_world.to_3x3()

    def world_vector_to_solver(self, vector: Vector) -> Vector:
        return self.rotation_world.inverted_safe() @ vector

    def solver_vector_to_world(self, vector: Vector) -> Vector:
        return self.rotation_world @ vector


def _identity_matrix() -> Matrix:
    return Matrix.Identity(4)


def _coerce_mode(mode: str | SolverSpace | None) -> SolverSpace:
    value = str(mode or SolverSpace.PARENT_LOCAL.value).strip().upper()
    for candidate in SolverSpace:
        if value == candidate.value:
            return candidate
    return SolverSpace.PARENT_LOCAL


def resolve_solver_space_frame(
    mode: str | SolverSpace | None,
    *,
    driven_obj=None,
    source_obj=None,
    custom_obj=None,
    source_matrix_world: Matrix | None = None,
) -> SolverSpaceFrame:
    resolved = _coerce_mode(mode)
    if resolved == SolverSpace.WORLD:
        return SolverSpaceFrame(resolved, _identity_matrix())
    if resolved == SolverSpace.SOURCE_LOCAL and source_obj is not None:
        return SolverSpaceFrame(resolved, source_matrix_world.copy() if source_matrix_world is not None else source_obj.matrix_world.copy())
    if resolved == SolverSpace.OBJECT_LOCAL and driven_obj is not None:
        return SolverSpaceFrame(resolved, driven_obj.matrix_world.copy())
    if resolved == SolverSpace.CUSTOM_OBJECT and custom_obj is not None:
        return SolverSpaceFrame(resolved, custom_obj.matrix_world.copy())
    parent = getattr(driven_obj, "parent", None) if driven_obj is not None else None
    if parent is not None:
        return SolverSpaceFrame(SolverSpace.PARENT_LOCAL, parent.matrix_world.copy())
    if source_obj is not None:
        return SolverSpaceFrame(SolverSpace.PARENT_LOCAL, source_matrix_world.copy() if source_matrix_world is not None else source_obj.matrix_world.copy())
    return SolverSpaceFrame(SolverSpace.PARENT_LOCAL, _identity_matrix())
