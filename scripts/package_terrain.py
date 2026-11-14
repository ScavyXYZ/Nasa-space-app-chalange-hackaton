"""Create a local shareable processed-data bundle, never upload automatically."""
import json
import zipfile
from pathlib import Path

from download_nasa_data import checksum

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = []
    for directory in [ROOT/"data/processed",ROOT/"data/processed/hirise",ROOT/"data/processed/gis",
                      ROOT/"data/processed/regional",ROOT/"data/processed/globe"]:
        files.extend(p for p in directory.glob("*") if p.is_file())
    files.extend(ROOT/p for p in ["data/sources.json","data/download_manifest.json",
                                  "data/hirise_download_manifest.json","science/points_of_interest.geojson"])
    for relative in ["data/processed/jezero_elevation.npy",
                     "data/processed/hirise/jezero_hirise_elevation.npy"]:
        if not (ROOT/relative).is_file():
            raise FileNotFoundError(f"Missing {relative}; prepare both terrain grids first")
    records = [{"path":p.relative_to(ROOT).as_posix(),"bytes":p.stat().st_size,"sha256":checksum(p)} for p in sorted(set(files))]
    out = ROOT/"artifacts/mars-explorer-terrain.zip"
    out.parent.mkdir(exist_ok=True)
    temp = out.with_suffix(".part.zip")
    with zipfile.ZipFile(temp,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for item in records:
            z.write(ROOT/item["path"],item["path"])
        z.writestr("bundle_manifest.json",json.dumps({
            "contents":"Processed Mars terrain and GIS assets; raw originals excluded. Extract in a clone of the repository.",
            "files":records},indent=2))
    with zipfile.ZipFile(temp) as z:
        if z.testzip():
            raise ValueError("Corrupted data archive")
    temp.replace(out)
    print(f"Local handoff bundle: {out} ({out.stat().st_size:,} bytes)")
    print(f"SHA256: {checksum(out)}")
    print("Not uploaded. Share through the team's agreed storage; raw source validators require separate raw downloads.")


if __name__=="__main__":
    main()
