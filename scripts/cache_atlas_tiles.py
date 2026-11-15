"""Cache only low-zoom official imagery for a resilient local demonstration."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    catalog=json.loads((ROOT/"data/processed/atlas/tiles.json").read_text())
    jobs=[(c,z,y,x) for c in catalog for z in range(3) for y in range(2**z) for x in range(2**(z+1))]
    def fetch(job):
        c,z,y,x=job
        path=ROOT/f"data/processed/atlas/tiles/{c['id']}/{z}/{y}/{x}.tile"
        if path.exists():
            return True
        url=c["template"].format(Style=c["style"],TileMatrixSet=c["matrix_set"],
                                  TileMatrix=c["matrices"][z],TileRow=y,TileCol=x)
        try:
            r=requests.get(url,timeout=(15,45))
            r.raise_for_status()
            if len(r.content)>1_000_000 or not r.headers.get("content-type","").startswith("image/"):
                raise ValueError("Invalid image")
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(r.content)
            return True
        except (requests.RequestException,ValueError) as exc:
            print(f"Not cached {c['id']}/{z}/{y}/{x}: {exc}")
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(fetch,jobs))
    print(f"Cached {sum(results)}/{len(results)} tiles; high zoom needs NASA network access.")


if __name__=="__main__":
    main()
