"""Acquire the published Robbins/Hynek catalogue; preserve provenance/caveats."""
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import subprocess
import zipfile

import numpy as np
import requests

ROOT=Path(__file__).resolve().parents[1]
URL="https://craters.sjrdesign.net/RobbinsCraterDatabase_20140829.tsv.zip"


def main():
    folder=ROOT/"data/raw/craters";folder.mkdir(parents=True,exist_ok=True)
    path=folder/"robbins_2014.zip"
    if not path.exists():
        pending=path.with_suffix(".part")
        subprocess.run(["curl.exe" if sys.platform=="win32" else "curl","-L","--fail","--max-time","120",
                        "--output",str(pending),URL],check=True)
        if pending.stat().st_size>150_000_000:raise ValueError("Unexpected catalogue size")
        pending.replace(path)
    with zipfile.ZipFile(path) as archive:
        name=next(n for n in archive.namelist() if n.startswith("Combined Catalog - 2014"))
        text=archive.read(name).decode("latin1").replace("\r\n","\n").replace("\r","\n")
    sample=text.splitlines()[0]
    delimiter="\t" if sample.count("\t")>sample.count(",") else ","
    rows=csv.DictReader(io.StringIO(text),delimiter=delimiter)
    records=[]
    for row in rows:
        try:
            lat=float(row["LATITUDE_CIRCLE_IMAGE"]);lon=float(row["LONGITUDE_CIRCLE_IMAGE"])
            diameter=float(row["DIAM_CIRCLE_IMAGE"])
            if not (-90<=lat<=90 and -180<=lon<=360 and 1<=diameter<=3000):continue
            records.append((row["CRATER_ID"],(lon+180)%360-180,lat,diameter,
                            row.get("CRATER_NAME","").strip()))
        except (ValueError,TypeError):continue
    out=ROOT/"data/processed/craters";out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out/"robbins.npz",ids=np.array([r[0] for r in records]),
                        lon=np.array([r[1] for r in records]),lat=np.array([r[2] for r in records]),
                        diameter_km=np.array([r[3] for r in records]),names=np.array([r[4] for r in records]))
    metadata={"title":"Robbins & Hynek Mars crater catalogue, 2014 release","source":"https://craters.sjrdesign.net/",
              "download_url":URL,"doi":"10.1029/2011JE003966","records":len(records),
              "archive_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
              "runtime_sha256":hashlib.sha256((out/"robbins.npz").read_bytes()).hexdigest(),
              "minimum_diameter_km":1,
              "geometry":"Published image-fitted circle centres and diameters; not exact rim polygons.",
              "caveats":["Catalogue contains omissions and false positives; not a complete hazard map.",
                         "Ellipse tilt has published fitting issues; only circle parameters are used.",
                         "Depths of small craters are unreliable and are not used as rover slopes.",
                         "Conservative exclusion of a footprint is a planning policy, not proof every rim is impassable."]}
    (out/"metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps(metadata,indent=2))


if __name__=="__main__":
    main()
