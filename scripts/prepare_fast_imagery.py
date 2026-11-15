"""Bounded validated warm cache: global overview levels + demo endpoint regions."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import requests
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from algorithms.imagery_validation import valid_tile


def main():
    jobs={(z,y,x) for z in range(4) for y in range(2**z) for x in range(2**(z+1))}
    for lon,lat in [(-105,15),(-97.150761,24.024217),(150.624967,9.070396),(77.45,18.44)]:
        for z in range(5,12):
            step=180/2**z;x=int((lon+180)/step);y=int((90-lat)/step)
            jobs.update((z,ny,nx%(2**(z+1))) for ny in range(max(0,y-1),min(2**z,y+2)) for nx in range(x-1,x+2))
    def fetch(job):
        z,y,x=job
        path=ROOT/f"data/processed/atlas/tiles/ctx-global/{z}/{y}/{x}.tile"
        if path.is_file() and valid_tile(path.read_bytes(),512,"ctx-global"):return True
        try:
            response=requests.get(f"http://127.0.0.1:8003/api/atlas/tiles/ctx-global/{z}/{y}/{x}?v=validated-3",timeout=35)
            if not response.ok or not valid_tile(response.content,512,"ctx-global"):return False
            path.parent.mkdir(parents=True,exist_ok=True)
            pending=path.with_suffix(".part");pending.write_bytes(response.content);pending.replace(path)
            return True
        except requests.RequestException:return False
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(fetch,sorted(jobs)))
    report={"requested_tiles":len(jobs),"cached_tiles":sum(results),"unavailable":len(jobs)-sum(results),
            "scope":"CTX global levels 0–3, 3×3 neighbourhoods at levels 5–11 for four focus regions. Not full native Mars."}
    folder=ROOT/"artifacts/zoom";folder.mkdir(parents=True,exist_ok=True)
    (folder/"warm-cache-report.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
