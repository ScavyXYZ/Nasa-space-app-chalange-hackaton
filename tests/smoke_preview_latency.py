"""A slow native source must not delay the overview; next LOD is warmed idle."""
import argparse
import asyncio
import io
import json
from pathlib import Path
import subprocess
from time import perf_counter
from urllib.parse import urlsplit

from PIL import Image
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/zoom"


async def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    subprocess.run(["node","frontend/node_modules/esbuild/bin/esbuild","tests/atlas_fixture.ts",
                    "--bundle","--format=iife",'--define:import.meta.env={"VITE_API_BASE_URL":""}',
                    "--outfile=artifacts/zoom/preview-fixture.js"],cwd=ROOT,check=True,capture_output=True)
    hold=asyncio.Event()
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={"width":800,"height":600})
        await page.route("**/atlas-fixture",lambda r:r.fulfill(body="<html><body></body></html>",content_type="text/html"))
        async def tile(route):
            z,y,x=map(int,urlsplit(route.request.url).path.split("/")[-3:])
            if z>=9:await hold.wait()
            else:await asyncio.sleep(.01)
            image=Image.new("RGB",(256,256),(80+z*5,80,160))
            stream=io.BytesIO();image.save(stream,format="PNG")
            try:await route.fulfill(body=stream.getvalue(),content_type="image/png")
            except Exception:pass
        await page.route("**/api/atlas/tiles/**",tile)
        await page.goto(url+"/atlas-fixture")
        await page.add_script_tag(content=(OUT/"preview-fixture.js").read_text())
        began=perf_counter()
        await page.evaluate("atlasFixture.view(150.624967,9.070396,6)")
        await page.wait_for_function("atlasFixture.status()?.preview&&atlasFixture.status()?.ready===0",timeout=1500)
        latency=perf_counter()-began
        samples=await page.evaluate("atlasFixture.samples()")
        assert any(max(s["rgb"])-min(s["rgb"])>30 for s in samples),samples[:3]
        hold.set()
        await page.wait_for_function("atlasFixture.status()?.ready===atlasFixture.status()?.total",timeout=15000)
        await page.wait_for_function("""performance.getEntriesByType('resource')
            .filter(r=>r.name.includes('/ctx-global/10/')&&r.responseEnd>0).length>=9""",timeout=15000)
        hold.clear()
        await page.evaluate("atlasFixture.view(150.624967,9.070396,12)")
        await page.wait_for_function("atlasFixture.status()?.zoom===10&&atlasFixture.status()?.ready>=4",timeout=1500)
        cached=await page.evaluate("atlasFixture.status().ready")
        hold.set()
        report={"status":"passed","preview_seconds_with_native_blocked":round(latency,3),
                "cached_next_lod_tiles_visible_before_network":cached,
                "scope":"Controlled zero native bandwidth; validates scheduling/cache, not an internet speed guarantee."}
        (OUT/"preview-latency-report.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
        await browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    asyncio.run(run(parser.parse_args().url))
