"""Verify CTX/local, HiRISE and regional runtime arrays from their SHA-256 manifest.

Hydrate files using authenticated git lfs pull first. Anonymous GitHub media
downloads returned HTTP 404 in this environment and are deliberately not used.
"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def prepare(root=ROOT):
    manifest=json.loads((root/"data/runtime_manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path=root/item["path"]
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe manifest path")
        prefix=path.read_bytes()[:128] if path.exists() and path.stat().st_size<1024 else b""
        pointer=prefix.startswith(b"version https://git-lfs.github.com/spec/v1")
        if not path.exists() or pointer:
            raise ValueError(f"Missing data/LFS pointer: {path}. Run authenticated git lfs pull before building.")
        if path.stat().st_size!=item["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
            raise ValueError(f"Runtime grid altered: {item['path']}")
        print(f"Verified runtime data: {item['path']}")
    # These exact source geometries are also LFS-managed; display JSON is not a
    # replacement for proximity analysis. Fail early on tiny pointer files.
    for name in ["geology","points_of_interest"]:
        path=root/f"data/processed/regional/{name}.geojson"
        if not path.exists() or path.stat().st_size<1024:
            raise ValueError(f"Missing regional scientific geometry: {path}. Run git lfs pull.")


if __name__=="__main__":
    prepare()
