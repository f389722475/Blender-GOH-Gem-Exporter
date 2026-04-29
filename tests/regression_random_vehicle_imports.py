from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os
import random
import sys
import traceback

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PARENT = ROOT
if str(ADDON_PARENT) not in sys.path:
    sys.path.insert(0, str(ADDON_PARENT))
for module_name in list(sys.modules):
    if module_name == "blender_goh_gem_exporter" or module_name.startswith("blender_goh_gem_exporter."):
        del sys.modules[module_name]

import blender_goh_gem_exporter as addon  # noqa: E402


MODS_ROOT = Path(r"D:\Steam\steamapps\common\Call to Arms - Gates of Hell\mods")
MOD_DIRS = (
    "123",
    "macecopy",
    "shellhole",
    "shellholefire",
    "War Thunder Allies Tanks",
    "WTREBUILD",
)
SAMPLE_COUNT = 12
ITERATIONS = max(1, int(os.environ.get("GOH_REGRESSION_ITERATIONS", "10")))
SEED = 13003121
REPORT_PATH = ROOT / "runtime_test_output" / "self_learning_import_regression.json"


@dataclass
class SampleResult:
    iteration: int
    mdl: str
    status: str
    score: int
    object_count: int = 0
    mesh_count: int = 0
    material_count: int = 0
    custom_normal_meshes: int = 0
    mirrored_basis_ok: bool = True
    warnings: list[str] | None = None
    error: str | None = None


def _collect_vehicle_mdls() -> list[Path]:
    roots = [MODS_ROOT / name for name in MOD_DIRS if (MODS_ROOT / name).exists()]
    candidates: list[Path] = []
    for root in roots:
        for path in root.rglob("*.mdl"):
            lowered = str(path).lower()
            if "\\template\\" in lowered or "\\tools\\" in lowered:
                continue
            if "\\vehicle\\" not in lowered and "\\-vehicle\\" not in lowered:
                continue
            if path.stat().st_size < 512:
                continue
            sibling_ply = any(path.parent.glob("*.ply"))
            if not sibling_ply:
                continue
            candidates.append(path)
    return sorted(candidates, key=lambda item: str(item).lower())


def _sample_mdls() -> list[Path]:
    candidates = _collect_vehicle_mdls()
    if len(candidates) <= SAMPLE_COUNT:
        return candidates
    rng = random.Random(SEED)
    return sorted(rng.sample(candidates, SAMPLE_COUNT), key=lambda item: str(item).lower())


def _determinant(obj: bpy.types.Object) -> float:
    return float(obj.matrix_local.to_3x3().determinant())


def _score_import(mdl: Path, iteration: int) -> SampleResult:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    before_materials = set(bpy.data.materials)
    try:
        result = bpy.ops.import_scene.goh_model(
            filepath=str(mdl),
            axis_mode="NONE",
            scale_factor=20.0,
            flip_v=True,
            import_materials=True,
            load_textures=False,
            import_volumes=True,
            import_shapes=True,
            import_lod0_only=True,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"operator returned {result}")
        imported = [obj for obj in bpy.data.objects if str(obj.get("goh_source_mdl") or "") == str(mdl)]
        meshes = [obj for obj in imported if obj.type == "MESH" and obj.get("goh_import_ply")]
        materials = [mat for mat in bpy.data.materials if mat not in before_materials and mat.get("goh_import_mtl")]
        custom_normals = [obj for obj in meshes if obj.data.get("goh_imported_custom_normals")]
        mirrored_basis_ok = True
        basis = bpy.data.objects.get("basis") or bpy.data.objects.get("Basis")
        if basis is not None and basis.get("goh_rest_matrix_local") is not None:
            rest_values = [float(v) for v in basis.get("goh_rest_matrix_local", [])]
            if len(rest_values) == 16:
                rest_det_hint = rest_values[0] * ((rest_values[5] * rest_values[10]) - (rest_values[6] * rest_values[9]))
                if rest_det_hint < 0.0:
                    mirrored_basis_ok = _determinant(basis) < -1e-5
        score = 100
        warnings: list[str] = []
        if not imported:
            score -= 80
            warnings.append("no tagged objects")
        if not meshes:
            score -= 60
            warnings.append("no visual meshes")
        if meshes and len(custom_normals) != len(meshes):
            score -= min(30, 3 * (len(meshes) - len(custom_normals)))
            warnings.append("some meshes skipped custom normals")
        if materials and any(mat.get("goh_specular") and not mat.get("goh_specular_role") for mat in materials):
            score -= 5
            warnings.append("bump material missing specular role metadata")
        if not mirrored_basis_ok:
            score -= 40
            warnings.append("mirrored basis determinant lost")
        status = "pass" if score >= 85 else "warn"
        return SampleResult(
            iteration=iteration,
            mdl=str(mdl),
            status=status,
            score=max(0, score),
            object_count=len(imported),
            mesh_count=len(meshes),
            material_count=len(materials),
            custom_normal_meshes=len(custom_normals),
            mirrored_basis_ok=mirrored_basis_ok,
            warnings=warnings,
        )
    except Exception as exc:
        return SampleResult(
            iteration=iteration,
            mdl=str(mdl),
            status="fail",
            score=0,
            warnings=[],
            error=f"{exc}\n{traceback.format_exc(limit=6)}",
        )


def main() -> None:
    samples = _sample_mdls()
    if not samples:
        print("SKIP random vehicle import regression: no model samples found")
        return
    addon.register()
    results: list[SampleResult] = []
    try:
        for iteration in range(1, ITERATIONS + 1):
            ordered = sorted(
                samples,
                key=lambda mdl: (
                    min((r.score for r in results if r.mdl == str(mdl)), default=100),
                    str(mdl).lower(),
                ),
            )
            for mdl in ordered:
                result = _score_import(mdl, iteration)
                results.append(result)
                print(
                    f"ITER {iteration:02d} {result.status.upper():4s} "
                    f"{result.score:03d} {Path(result.mdl).name}"
                )
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "seed": SEED,
            "sample_count": len(samples),
            "iterations": ITERATIONS,
            "samples": [str(path) for path in samples],
            "results": [asdict(result) for result in results],
        }
        REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        failures = [result for result in results if result.status == "fail"]
        low_scores = [result for result in results if result.score < 85]
        if failures or low_scores:
            raise RuntimeError(
                f"Random vehicle import regression had {len(failures)} failures and {len(low_scores)} low-score samples. "
                f"Report: {REPORT_PATH}"
            )
        print(f"OK random vehicle import regression: {len(samples)} samples x {ITERATIONS} iterations")
        print(f"Report: {REPORT_PATH}")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
