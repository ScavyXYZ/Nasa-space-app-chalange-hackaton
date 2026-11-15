"""Reproduce the global MOLA 4 pixel/degree runtime product from NASA PDS.

The official product includes interpolated bins. Counts are retained so that
the application can distinguish those bins from bins with laser observations.
"""
import hashlib
import json
import argparse
from pathlib import Path

import numpy as np
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg004/"
PAGE = "https://pds-geosciences.wustl.edu/missions/mgs/megdr.html"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppd", type=int, choices=[4, 16], default=4)
    ppd = parser.parse_args().ppd
    rows, cols = 180*ppd, 360*ppd
    base = BASE.replace("meg004", f"meg{ppd:03}")
    suffix = "cb" if ppd == 4 else "eb"
    raw = ROOT / "data/raw/mola"
    out = ROOT / "data/processed/global"
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    arrays, sources = {}, []
    for kind, name in [("elevation", f"megt90n000{suffix}"), ("counts", f"megc90n000{suffix}")]:
        for extension in ("lbl", "img"):
            path = raw / f"{name}.{extension}"
            if not path.exists():
                response = requests.get(base + path.name, timeout=(20, 120))
                response.raise_for_status()
                if extension == "img" and len(response.content) != rows * cols * 2:
                    raise ValueError("Unexpected MOLA image size")
                path.write_bytes(response.content)
        label = (raw / f"{name}.lbl").read_text()
        for expected in ("MSB_INTEGER", "PLANETOCENTRIC", 'PRODUCT_VERSION_ID            = "2.0"'):
            if expected not in label:
                raise ValueError(f"Unexpected PDS label: {name}")
        content = (raw / f"{name}.img").read_bytes()
        arrays[kind] = np.frombuffer(content, dtype=">i2").reshape(rows, cols).astype(np.int16)
        sources.append({"url": base + name + ".img", "label_url": base + name + ".lbl",
                        "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
    if arrays["elevation"].min() < -9000 or arrays["elevation"].max() > 22000:
        raise ValueError("Unexpected MOLA topography range or byte order")
    if arrays["counts"].min() < 0:
        raise ValueError("Unexpected negative observation counts")
    archive = f"mola_{ppd}ppd.npz"
    np.savez_compressed(out / archive, **arrays)
    # Texture convention is -180..180; source convention is 0..360.
    heights = np.roll(arrays["elevation"], cols//2, axis=1)
    stops = np.array([-8500, -4500, -1000, 2000, 7000, 14000, 22000])
    colors = np.array([[17, 35, 65], [38, 91, 115], [87, 137, 133],
                       [185, 154, 111], [201, 108, 66], [236, 174, 114], [255, 242, 211]])
    rgb = np.stack([np.interp(heights, stops, colors[:, c]) for c in range(3)], axis=-1)
    Image.fromarray(rgb.astype(np.uint8)).resize((2880,1440),Image.Resampling.LANCZOS).save(out / "mola-topography.jpg", quality=93)
    metadata = {
        "title": "MGS MOLA MEGDR · global topography", "product": f"MEGT90N000{suffix.upper()} v2.0",
        "source_page": PAGE, "sources": sources, "shape": [rows, cols],
        "resolution_deg": 1/ppd, "equatorial_spacing_m": 59272/ppd,
        "coordinate_system": "Mars planetocentric latitude, east-positive longitude",
        "vertical_datum": "MOLA areoid GMM3 (mgm1025), degree/order 50",
        "radius_m": 3396000, "height_range_m": [int(heights.min()), int(heights.max())],
        "observed_fraction": float((arrays["counts"] > 0).mean()),
        "texture_url": "/api/assets/mola-topography.jpg",
        "runtime_archive": archive,
        "runtime_sha256": hashlib.sha256((out / archive).read_bytes()).hexdigest(),
        "notice": f"{1/ppd} degree global planning model (~{59.272/ppd:.2f} km north-south). "
                  "Bins without observations contain PDS-supplied interpolation. "
                  "Not a local traversability or astronaut navigation model.",
    }
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
