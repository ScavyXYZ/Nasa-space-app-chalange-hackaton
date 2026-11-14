"""Reproducible bounded downloads from official USGS hosts, with SHA-256.

Never replaces a completed original. ZIP extraction is limited to the GIS
geodatabase; the regional ZIP is retained as the unchanged source archive.
"""
import hashlib
import json
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://astrogeology.usgs.gov/ckan/dataset/f8ef46b8-d512-4c46-b825-fe9633c38e1c/resource"
FILES = [
    ("data/raw/dem/M20_JezeroCrater_CTXDEM_20m.tif",
     "https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif"),
    ("data/raw/dem/m20_jezerocrater_ctxdem_20m.xml",
     BASE + "/5691ea08-1db4-4018-a341-e415e716add7/download/m20_jezerocrater_ctxdem_20m.xml"),
    ("data/raw/imagery/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif",
     "https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif"),
    ("data/raw/geology/sim3464_database.zip", "https://pubs.usgs.gov/sim/3464/sim3464_database.zip"),
    ("data/raw/geology/sim3464_readme.txt", "https://pubs.usgs.gov/sim/3464/sim3464_readme.txt"),
    ("data/raw/geology/sim3464_metadata.xml", "https://pubs.usgs.gov/sim/3464/sim3464_metadata.xml"),
]


def checksum(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    records = []
    for relative, url in FILES:
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with requests.get(url, stream=True, timeout=(20, 180)) as response:
                response.raise_for_status()
                size = int(response.headers.get("Content-Length", 0))
                if size > 400_000_000:
                    raise ValueError("Download exceeds regional dataset size budget.")
                tmp = path.with_suffix(path.suffix + ".part")
                count = 0
                with tmp.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        count += len(chunk)
                        if count > 400_000_000:
                            raise ValueError("Download exceeded size budget")
                        stream.write(chunk)
                if size and count != size:
                    raise ValueError("Truncated download")
                tmp.rename(path)
        records.append({"path": relative, "url": url, "bytes": path.stat().st_size,
                        "sha256": checksum(path)})
        print(f"Verified original: {relative} ({path.stat().st_size:,} bytes)")
    archive = ROOT / "data/raw/geology/sim3464_database.zip"
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if "/Geodatabase/" in name and not name.endswith(".lock"):
                target = (ROOT / "data/raw/geology/extracted" / name).resolve()
                if not target.is_relative_to((ROOT / "data/raw/geology/extracted").resolve()):
                    raise ValueError("Unsafe ZIP path")
                z.extract(name, ROOT / "data/raw/geology/extracted")
    (ROOT / "data/download_manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
