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
    folder=root/"data/processed/global"
    metadata=json.loads((folder/"metadata.json").read_text(encoding="utf-8"))
    if hashlib.sha256((folder/metadata.get("runtime_archive","mola_4ppd.npz")).read_bytes()).hexdigest()!=metadata["runtime_sha256"]:
        raise ValueError("Global MOLA runtime checksum mismatch")
    for relative in ["data/processed/global/mola-topography.jpg","data/processed/globe/mars_viking_colorized.jpg"]:
        if not (root/relative).is_file():
            raise ValueError(f"Missing global display asset: {relative}")
    print("Verified global MOLA archive and globe display assets")
    atlas=root/"data/processed/atlas"
    metadata=json.loads((atlas/"metadata.json").read_text(encoding="utf-8"))
    for name,expected in metadata["sha256"].items():
        path=atlas/name
        if not path.resolve().is_relative_to(atlas.resolve()):
            raise ValueError("Unsafe atlas manifest path")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError(f"Atlas resource changed: {name}")
    for relative in ["tiles.json","missions.json","media/perseverance.jpg","media/jezero-delta.jpg","media/curiosity.jpg"]:
        if not (atlas/relative).is_file():
            raise ValueError(f"Missing atlas asset: {relative}")
    print("Verified atlas geology source/display assets and mission media")
    for metadata_path,archive_name in [
        (root/"data/processed/craters/metadata.json","robbins.npz"),
        (root/"data/processed/mola128/a.json","a.npz"),
        (root/"data/processed/mola128/b.json","b.npz")]:
        metadata=json.loads(metadata_path.read_text(encoding="utf-8"))
        archive=metadata_path.parent/archive_name
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=metadata["runtime_sha256"]:
            raise ValueError(f"Terrain hazard data checksum mismatch: {archive}")
    print("Verified crater catalogue and both numeric MOLA 128 ppd patches")
    folder=root/"data/processed/mola128_global"
    native=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if len(native["files"])!=32:
        raise ValueError("Incomplete native MOLA topography/count coverage")
    for item in native["files"]:
        name=item["url"].rsplit("/",1)[-1]
        path=folder/name
        if path.parent!=folder or path.stat().st_size!=item["bytes"]:
            raise ValueError("Invalid native MOLA file size/path")
        digest=hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda:handle.read(4*1024*1024),b""):digest.update(chunk)
        if digest.hexdigest()!=item["sha256"]:
            raise ValueError(f"Native MOLA checksum mismatch: {name}")
    print("Verified all 32 native MOLA 128 ppd topography/count tiles")


if __name__=="__main__":
    prepare()
