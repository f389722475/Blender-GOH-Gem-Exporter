from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


SKIP_DIRS = {
    ".git",
    ".tools",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "dist",
    "release",
    "runtime_test_output",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".zip"}
ROOT_DOCS = ("README.md", "README.zh-CN.md", "CHANGELOG.md", "LICENSE")
REQUIRED_ADDON_MEMBERS = (
    "blender_goh_gem_exporter/tools/_profile_ce2013dd87.py",
    "blender_goh_gem_exporter/resources/profile_ce2013dd87.bin",
    "blender_goh_gem_exporter/importers/model_importer.py",
    "blender_goh_gem_exporter/importers/animation_importer.py",
)


def should_skip(repo: Path, path: Path) -> bool:
    rel_parts = path.relative_to(repo).parts
    if any(part in SKIP_DIRS for part in rel_parts):
        return True
    if path.name.endswith(".blend1"):
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    return path.name.lower() in {"thumbs.db", "desktop.ini"}


def add_file(zf: zipfile.ZipFile, src: Path, arcname: Path | str) -> None:
    zf.write(src, str(arcname).replace("\\", "/"))


def assert_protected_loader(repo: Path) -> None:
    tool_dir = repo / "blender_goh_gem_exporter" / "tools"
    for name in ("collision_cage.py", "physics_bake.py"):
        path = tool_dir / name
        text = path.read_text(encoding="utf-8")
        if "_profile_ce2013dd87" not in text or len(text) > 4096:
            raise RuntimeError(
                f"{path} does not look like the protected release loader. "
                "Package from the Git mirror or pass --allow-unprotected intentionally."
            )


def build_addon_zip(repo: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        addon_root = repo / "blender_goh_gem_exporter"
        for path in sorted(addon_root.rglob("*")):
            if path.is_file() and not should_skip(repo, path):
                add_file(zf, path, path.relative_to(repo))
        for name in ROOT_DOCS:
            add_file(zf, repo / name, name)


def build_full_zip(repo: Path, output: Path, version: str) -> None:
    root_name = Path(f"Blender GOH Gem Exporter {version}")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(repo.rglob("*")):
            if path.is_file() and not should_skip(repo, path):
                add_file(zf, path, root_name / path.relative_to(repo))


def verify_zip(path: Path, required_members: tuple[str, ...] = ()) -> tuple[int, int]:
    with zipfile.ZipFile(path, "r") as zf:
        bad_member = zf.testzip()
        if bad_member:
            raise RuntimeError(f"{path} has a bad zip member: {bad_member}")
        names = set(zf.namelist())
        missing = [member for member in required_members if member not in names]
        if missing:
            raise RuntimeError(f"{path} is missing required members: {missing}")
        return path.stat().st_size, len(names)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local GOH addon release zips.")
    parser.add_argument("--repo", required=True, type=Path, help="Release Git mirror root.")
    parser.add_argument("--dist", required=True, type=Path, help="Output dist directory.")
    parser.add_argument("--version", required=True, help="Release version, for example 1.4.2.")
    parser.add_argument("--clean", action="store_true", help="Delete existing zip files in dist first.")
    parser.add_argument(
        "--allow-unprotected",
        action="store_true",
        help="Allow full source tool modules in the install zip. Off by default.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = args.repo.resolve()
    dist = args.dist.resolve()
    if not repo.exists():
        raise RuntimeError(f"Repo root does not exist: {repo}")
    if not (repo / "blender_goh_gem_exporter").exists():
        raise RuntimeError(f"Repo root does not contain the addon package: {repo}")
    if not args.allow_unprotected:
        assert_protected_loader(repo)

    dist.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for old_zip in dist.glob("*.zip"):
            old_zip.unlink()

    addon_zip = dist / f"blender_goh_gem_exporter-{args.version}.zip"
    full_zip = dist / f"blender_goh_gem_exporter-{args.version}-full.zip"
    build_addon_zip(repo, addon_zip)
    build_full_zip(repo, full_zip, args.version)

    for path, required in (
        (addon_zip, REQUIRED_ADDON_MEMBERS),
        (full_zip, ()),
    ):
        size, count = verify_zip(path, required)
        print(f"{path}\t{size}\t{count} files")


if __name__ == "__main__":
    main()
