"""Cache all official 128 ppd numerical topography/count tiles, never imagery.

About 3.1 GB, streamed and atomically published after label/size validation.
The source covers -88..88 degrees. Polar gaps are not filled with fake heights.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re

import requests

ROOT=Path(__file__).resolve().parents[1]
BASE="https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/"
FOLDER=ROOT/"data/processed/mola128_global"


def acquire(product):
    image=FOLDER/(product+".img")
    meta_path=FOLDER/(product+".json")
    if image.exists() and meta_path.exists():
        metadata=json.loads(meta_path.read_text())
        if image.stat().st_size==metadata["bytes"]:
            return metadata
        raise ValueError(f"Unexpected existing file size: {image}")
    label=requests.get(BASE+product+".lbl",timeout=(15,45))
    label.raise_for_status()
    text=label.text
    def number(name):
        return int(re.search(rf"^\s*{name}\s*=\s*(\d+)",text,re.M)[1])
    rows,cols,bits=number("LINES"),number("LINE_SAMPLES"),number("SAMPLE_BITS")
    if (rows,cols)!=(5632,11520) or bits!=(16 if product[3]=="t" else 8):
        raise ValueError("Unexpected PDS numeric layout")
    size=rows*cols*bits//8
    pending=image.with_suffix(".img.part")
    digest=hashlib.sha256();written=0
    with requests.get(BASE+product+".img",stream=True,timeout=(20,90)) as response:
        response.raise_for_status()
        if response.status_code!=200:
            raise ValueError("A full numerical tile was requested")
        with pending.open("wb") as handle:
            for chunk in response.iter_content(1024*1024):
                written+=len(chunk)
                if written>size:raise ValueError("Unexpected PDS response size")
                digest.update(chunk);handle.write(chunk)
    if written!=size:raise ValueError("Truncated numeric MOLA tile")
    metadata={"product":product.upper(),"url":BASE+product+".img",
              "label_url":BASE+product+".lbl","bytes":size,"sha256":digest.hexdigest(),
              "shape":[rows,cols],"dtype":">i2" if bits==16 else "u1",
              "notice":"Numeric MOLA MEGDR 128 ppd; counts=0 is official interpolation."}
    pending.replace(image)
    (FOLDER/(product+".lbl")).write_text(text,encoding="utf-8")
    meta_path.write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(f"Ready: {product} ({size/1e6:.1f} MB)",flush=True)
    return metadata


def main():
    FOLDER.mkdir(parents=True,exist_ok=True)
    # Equatorial, then higher-latitude coverage. Every tile contains the same
    # official spacing and datum; no endpoint-specific hardcoded AOIs.
    jobs=[f"meg{kind}{band}{west:03}hb" for band in ["44n","00n","88n","44s"]
          for west in [180,90,270,0] for kind in ["t","c"]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(acquire,jobs))
    manifest={"title":"NASA PDS MOLA MEGDR 128 ppd numerical terrain",
              "source":"https://pds-geosciences.wustl.edu/missions/mgs/megdr.html",
              "ppd":128,"coverage_latitude":[-88,88],"files":records,
              "notice":"463 m north/south spacing, not rover-scale accuracy. Interpolation retained."}
    pending=FOLDER/"manifest.json.part"
    pending.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    pending.replace(FOLDER/"manifest.json")
    print(f"Complete: {len(records)} numeric tiles, {sum(r['bytes'] for r in records)/1e9:.3f} GB",flush=True)


if __name__=="__main__":main()
