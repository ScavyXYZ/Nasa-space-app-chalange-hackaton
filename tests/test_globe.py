import hashlib
import json
import unittest
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient
from backend.main import create_app

ROOT=Path(__file__).resolve().parents[1]


class GlobeTests(unittest.TestCase):
    def test_official_source_and_texture(self):
        metadata=json.loads((ROOT/"data/processed/globe/metadata.json").read_text())
        self.assertIn("astrogeology.usgs.gov",metadata["download_url"])
        self.assertIn("NOT true-color",metadata["color_note"])
        self.assertIn("Not a global DEM",metadata["geometry_note"])
        self.assertEqual(metadata["bounds_lon_lat_deg"],[-180,-90,180,90])
        with Image.open(ROOT/"data/processed/globe/mars_viking_colorized.jpg") as image:
            self.assertEqual(image.size,(4096,2048))
            self.assertEqual(image.mode,"RGB")
        raw=ROOT/metadata["raw_path"]
        if raw.is_file():  # Runtime deployments intentionally omit raw originals.
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(),metadata["raw_sha256"])

    def test_global_api_is_independent_of_routing_coverage(self):
        with TestClient(create_app()) as client:
            self.assertEqual(client.get("/api/globe").status_code,200)
            image=client.get("/api/assets/mars-global.jpg")
            self.assertEqual(image.status_code,200)
            self.assertEqual(image.headers["content-type"],"image/jpeg")
            self.assertGreater(len(image.content),100000)
            self.assertEqual(client.get("/api/elevation?lon=-100&lat=0").status_code,422)


if __name__=="__main__":
    unittest.main()
