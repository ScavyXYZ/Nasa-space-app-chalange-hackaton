"""Build a complete LOCAL Viking display pyramid from the retained official browse.

No external acquisition, no sharpening or generated detail. Max 16384x8192
preserves about 1.3km/pixel, not the 232m resolution of the original product.
"""
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS = 240_000_000


def prepare(root=ROOT, max_level=5):
    raw = root / "data/raw/globe/mars_viking_mdim21_colorized_1km.jpg"
    folder = root / "data/processed/globe/imagery"
    folder.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
    count = 0
    with Image.open(raw) as source:
        original = source.size
        source.load()
        for level in range(max_level + 1):
            rows, cols = 2**level, 2**(level + 1)
            display = source.resize((cols * 256, rows * 256), Image.Resampling.LANCZOS)
            for y in range(rows):
                target = folder / str(level) / str(y)
                target.mkdir(parents=True, exist_ok=True)
                for x in range(cols):
                    display.crop((x*256, y*256, (x+1)*256, (y+1)*256)).save(
                        target / f"{x}.jpg", quality=90, optimize=True)
                    count += 1
            display.close()
    metadata = {
        "id": "viking-local", "title": "Viking · локальна суцільна мозаїка",
        "max_level": max_level, "tile_size": 256, "tiles": count,
        "display_dimensions": [256*2**(max_level+1), 256*2**max_level],
        "source_dimensions": list(original), "source_sha256": source_hash,
        "equatorial_m_per_pixel": 2*3.141592653589793*3396000/(256*2**(max_level+1)),
        "note": "Official colorized 1km Viking browse, downsampled; no generated detail. "
                "Internal local chunks are composed into one surface texture.",
    }
    (folder / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    prepare()
