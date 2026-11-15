"""Small local NASA image collection with provenance, no invented photo coordinates."""
import hashlib
import io
import json
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PAGE = "https://science.nasa.gov/mission/mars-2020-perseverance/"
ITEMS = [
    {"id": "perseverance", "title": "Perseverance · Cheyava Falls",
     "description": "Селфі Perseverance біля Cheyava Falls, 23 липня 2024 року. Потенційні біосигнатури потребують подальшої перевірки; це не доказ життя.",
     "credit": "NASA/JPL-Caltech/MSSS", "source": PAGE,
     "image": "https://assets.science.nasa.gov/dynamicimage/assets/science/cds/general/images/2024/07/pia26344-figa-2500x.jpg?w=1200&fit=clip",
     "region": "Jezero", "lon": 77.4508, "lat": 18.4447,
     "location_note": "Оглядова координата Jezero; не точка знімання і не поточна позиція марсохода."},
    {"id": "jezero-delta", "title": "Jezero · сліди давньої води",
     "description": "Уступ дельти, знятий Mastcam-Z 17 квітня 2021 року. Шаруваті відклади допомагають досліджувати водне минуле Jezero.",
     "credit": "NASA/JPL-Caltech/ASU/MSSS", "source": PAGE,
     "image": "https://assets.science.nasa.gov/dynamicimage/assets/science/psd/photojournal/pia/pia24/pia24813/PIA24813.jpg?w=1200&fit=clip",
     "region": "Jezero", "lon": 77.4508, "lat": 18.4447,
     "location_note": "Прив’язка до регіону, не до точного положення камери."},
    {"id": "curiosity", "title": "Curiosity · Gale Crater",
     "description": "Curiosity досліджує осадові породи кратера Gale й гори Mount Sharp: історію давнього середовища та його придатності для життя.",
     "credit": "NASA/JPL-Caltech/MSSS", "source": "https://science.nasa.gov/mission/msl-curiosity/",
     "image": "https://assets.science.nasa.gov/dynamicimage/assets/science/cds/general/images/2024/03/pia24173-crop.jpg?w=1200&fit=clip",
     "region": "Gale", "lon": 137.4, "lat": -4.6,
     "location_note": "Оглядова координата Gale; не поточна позиція марсохода."},
]


def main():
    out = ROOT/"data/processed/atlas/media"
    out.mkdir(parents=True, exist_ok=True)
    for item in ITEMS:
        path = out/f"{item['id']}.jpg"
        if not path.exists():
            r = requests.get(item["image"], timeout=(20, 90))
            r.raise_for_status()
            if len(r.content) > 15_000_000:
                raise ValueError("Image too large")
            image = Image.open(io.BytesIO(r.content)).convert("RGB")
            image.thumbnail((1200, 900))
            image.save(path, quality=90)
        item["url"] = f"/api/atlas/media/{item['id']}"
        item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"Prepared {path.name}")
    (out.parent/"missions.json").write_text(json.dumps(ITEMS, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
