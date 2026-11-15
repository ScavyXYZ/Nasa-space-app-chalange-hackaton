"""Fetch exact PDS byte ranges, not rendered hillshade, for endpoint regions."""
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
import requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
BASE="https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/"
POINTS={"a":(-97.150761,24.024217),"b":(150.624967,9.070396)}


def main():
    raw=ROOT/"data/raw/mola128";raw.mkdir(parents=True,exist_ok=True)
    out=ROOT/"data/processed/mola128";out.mkdir(parents=True,exist_ok=True)
    for name,(lon,lat) in POINTS.items():
        west_tile=int((lon%360)//90)*90
        north_tile=44 if 0<=lat<44 else 88
        rows=cols=512
        first_row=int((north_tile-lat)*128)-rows//2
        first_col=int(((lon%360)-west_tile)*128)-cols//2
        if min(first_row,first_col)<0 or first_row+rows>5632 or first_col+cols>11520:
            raise ValueError("Patch crosses a PDS tile boundary; explicit stitching is required")
        arrays={};sources=[]
        for kind,dtype,size in [("t",">i2",2),("c","u1",1)]:
            product=f"meg{kind}{north_tile:02}n{west_tile:03}hb"
            label=requests.get(BASE+product+".lbl",timeout=30);label.raise_for_status()
            text=label.text
            if not re.search(rf"SAMPLE_BITS\s*=\s*{size*8}\b",text) or not re.search(r"LINE_SAMPLES\s*=\s*11520\b",text):
                raise ValueError("Unexpected numeric PDS layout")
            start=first_row*11520*size;end=(first_row+rows)*11520*size-1
            path=raw/f"{name}-{product}-{start}-{end}.bin"
            if not path.exists():
                response=requests.get(BASE+product+".img",headers={"Range":f"bytes={start}-{end}"},timeout=(15,120))
                if response.status_code!=206 or response.headers.get("Content-Range","").split("/")[0]!=f"bytes {start}-{end}":
                    raise ValueError("PDS server did not honour exact numeric byte range")
                if len(response.content)!=end-start+1:raise ValueError("Truncated numeric DEM range")
                path.write_bytes(response.content)
            band=path.read_bytes()
            if len(band)!=end-start+1:raise ValueError("Bad saved numeric range")
            arrays[kind]=np.frombuffer(band,dtype=dtype).reshape(rows,11520)[:,first_col:first_col+cols].copy()
            (raw/(product+".lbl")).write_text(text,encoding="utf-8")
            sources.append({"url":BASE+product+".img","range":[start,end],"sha256":hashlib.sha256(band).hexdigest()})
        west=west_tile+first_col/128
        if west>=180:west-=360
        north=north_tile-first_row/128
        archive=out/f"{name}.npz"
        np.savez_compressed(archive,elevation=arrays["t"].astype(np.float32),counts=arrays["c"])
        meta={"id":name,"bounds":[west,north-rows/128,west+cols/128,north],
              "shape":[rows,cols],"ppd":128,"spacing_equator_m":2*math.pi*3396000/(360*128),
              "vertical_datum":"MOLA GMM3 areoid, PDS MEGDR v2",
              "source":"https://pds-geosciences.wustl.edu/missions/mgs/megdr.html",
              "sources":sources,"runtime_sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),
              "notice":"463 m bins, not 463 m measurement accuracy. Counts=0 identifies official interpolation."}
        (out/f"{name}.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
        print(json.dumps(meta),flush=True)


if __name__=="__main__":main()
