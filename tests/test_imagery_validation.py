import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient
from algorithms.imagery_validation import valid_tile
from backend.main import create_app


def png():
    stream=io.BytesIO()
    Image.new("RGB",(256,256),(70,120,180)).save(stream,format="PNG")
    return stream.getvalue()


class TileValidationTests(unittest.TestCase):
    def test_complete_image_required_not_just_png_header(self):
        content=png()
        self.assertTrue(valid_tile(content,256))
        for length in [0,40,len(content)//2,len(content)-16]:
            self.assertFalse(valid_tile(content[:length],256))
        self.assertFalse(valid_tile(content,512))
        self.assertFalse(valid_tile(b"<html>Gateway error</html>",256))

    def test_known_repeated_image_rejected_despite_different_png_encodings(self):
        image=Image.new("RGB",(256,256),(70,120,180))
        a=io.BytesIO();b=io.BytesIO()
        image.save(a,format="PNG",compress_level=1)
        image.save(b,format="PNG",compress_level=9)
        self.assertNotEqual(a.getvalue(),b.getvalue())
        fingerprint=hashlib.sha256(image.tobytes()).hexdigest()
        with patch("algorithms.imagery_validation.BAD_CTX_PIXEL_HASHES",{fingerprint}):
            for data in [a.getvalue(),b.getvalue()]:
                self.assertFalse(valid_tile(data,256,"ctx-global"))
                self.assertTrue(valid_tile(data,256,"viking-hd"))

    def test_corrupt_disk_cache_is_replaced_from_valid_upstream(self):
        base=Path(os.environ.get("LOCALAPPDATA",tempfile.gettempdir()))/"Temp/opencode"
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root=Path(directory)
            folder=root/"data/processed/atlas";folder.mkdir(parents=True)
            url="https://trek.nasa.gov/tiles/Mars/test/0/0/0.png"
            (folder/"tiles.json").write_text(json.dumps([{
                "id":"mola","matrices":["0"],"template":url,
                "format":"image/png","style":"default","matrix_set":"default"}]))
            cache=root/"Temp/opencode/mars-explorer-tiles";cache.mkdir(parents=True)
            target=cache/(hashlib.sha256(url.encode()).hexdigest()+".tile")
            target.write_bytes(png()[:80])
            response=io.BytesIO(png())
            response.headers={"content-type":"image/png"}
            response.geturl=lambda:url
            with patch.dict(os.environ,{"LOCALAPPDATA":str(root)}):
                with patch("backend.main.urlopen",return_value=response) as upstream:
                    with TestClient(create_app(root)) as client:
                        result=client.get("/api/atlas/tiles/mola/0/0/0")
                        self.assertEqual(result.status_code,200)
                        self.assertTrue(valid_tile(result.content,256))
                        client.get("/api/atlas/tiles/mola/0/0/0")
                        self.assertEqual(upstream.call_count,1)
            self.assertEqual(target.read_bytes(),png())

    def test_display_fallback_crops_its_parent_not_a_neighbour(self):
        base=Path(os.environ.get("LOCALAPPDATA",tempfile.gettempdir()))/"Temp/opencode"
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root=Path(directory);folder=root/"data/processed/atlas";folder.mkdir(parents=True)
            (folder/"tiles.json").write_text(json.dumps([{
                "id":"mola","matrices":["0","1"],
                "template":"https://trek.nasa.gov/tiles/Mars/test/{TileMatrix}/{TileRow}/{TileCol}.png",
                "format":"image/png","style":"default","matrix_set":"default"}]))
            parent=Image.new("RGB",(256,256),"red")
            parent.paste((0,0,200),(0,128,128,256))
            stream=io.BytesIO();parent.save(stream,format="PNG")
            def upstream(url,timeout):
                data=b"truncated" if "/1/" in url else stream.getvalue()
                response=io.BytesIO(data);response.headers={"content-type":"image/png"};response.geturl=lambda:url
                return response
            with patch.dict(os.environ,{"LOCALAPPDATA":str(root)}),patch("backend.main.urlopen",side_effect=upstream):
                with TestClient(create_app(root)) as client:
                    response=client.get("/api/atlas/tiles/mola/1/1/2?fallback=true")
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.headers["X-Imagery-Source-LOD"],"0")
                    image=Image.open(io.BytesIO(response.content))
                    self.assertEqual(image.getpixel((128,128))[:3],(0,0,200))


if __name__=="__main__":
    unittest.main()
