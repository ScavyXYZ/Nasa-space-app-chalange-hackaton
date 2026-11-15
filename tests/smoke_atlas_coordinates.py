"""Compare real GPU samples against distinct z/y/x-coded tile imagery."""
import argparse
import asyncio
import io
import json
import math
import subprocess
from urllib.parse import urlsplit
from pathlib import Path
from PIL import Image,ImageDraw
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/zoom"


def color(z,y,x):
    # Hash all coordinates; a repeated tile or wrong row cannot pass.
    return (48+(x*37+y*71+z*13)%160,48+(x*97+y*29+z*43)%160,48+(x*11+y*53+z*83)%160)


async def run(url,real=False):
    OUT.mkdir(parents=True,exist_ok=True)
    subprocess.run(["node","frontend/node_modules/esbuild/bin/esbuild","tests/atlas_fixture.ts",
                    "--bundle","--format=iife",'--define:import.meta.env={"VITE_API_BASE_URL":""}',
                    "--outfile=artifacts/zoom/atlas-fixture.js"],
                   cwd=ROOT,check=True,capture_output=True)
    errors=[]
    attempts={}
    failures=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={"width":800,"height":600},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        async def record_failure(response):
            if "/api/atlas/tiles/" in response.url and response.status>=400:
                failures.append({"url":response.url,"status":response.status,"body":await response.text()})
        page.on("response",record_failure)
        await page.route("**/atlas-fixture",lambda r:r.fulfill(body="<html><body></body></html>",content_type="text/html"))
        async def tile(route):
            if real:
                await route.continue_()
                return
            z,y,x=map(int,urlsplit(route.request.url).path.split("/")[-3:])
            if z==9 and (x+y)%17==0:
                await route.fulfill(status=502,body="Permanently truncated source tile")
                return
            key=(z,y,x);attempts[key]=attempts.get(key,0)+1
            if (x+y)%13==0 and attempts[key]==1:
                await route.fulfill(status=503,body="Transient tile error")
                return
            image=Image.new("RGB",(256,256),color(z,y,x))
            # Off-centre orientation mark catches flipped UVs as well as tile IDs.
            ImageDraw.Draw(image).rectangle((20,35,75,95),fill=(250,250,250))
            stream=io.BytesIO();image.save(stream,format="PNG")
            await asyncio.sleep(.01+(x%3)*.02)
            await route.fulfill(body=stream.getvalue(),content_type="image/png")
        await page.route("**/api/atlas/tiles/**",tile)
        await page.goto(url+"/atlas-fixture")
        await page.add_script_tag(content=(OUT/"atlas-fixture.js").read_text(encoding="utf-8"))
        cases=[(150.624967,9.070396,3),(150.624967,9.070396,6),
               *[(150.624967+i*.18,9.070396,6) for i in range(1,13)],
               (150.624967,9.070396,6),(150.624967,9.070396,20),
               (150.624967,9.070396,3),(-97.150761,24.024217,6),
               (77.45,18.44,20),(179.98,10,20),(-179.98,10,20)]
        if real:cases=[(150.624967,9.070396,3),(-97.150761,24.024217,3)]
        reports=[]
        native={}
        for lon,lat,zoom in cases:
            await page.evaluate("p=>atlasFixture.view(...p)",[lon,lat,zoom])
            await page.wait_for_timeout(120)
            try:
                await page.wait_for_function(
                    "atlasFixture.status()?.ready===atlasFixture.status()?.total&&atlasFixture.status()?.total>0"
                    +"||atlasFixture.status()?.offline",timeout=60000 if real else 30000)
            except Exception:
                print("Incomplete atlas:",await page.evaluate("atlasFixture.status()"))
                raise
            status=await page.evaluate("atlasFixture.status()")
            samples=await page.evaluate("atlasFixture.samples()")
            z=status["zoom"];step=180/2**z
            checked=bad=0;examples=[]
            for sample in samples:
                tx=(sample["lon"]+180)/step;ty=(90-sample["lat"])/step
                px=(tx%1)*256;py=(ty%1)*256
                # Avoid anti-aliased tile borders and orientation-marker edges.
                if min(px,py,256-px,256-py)<5:continue
                if real:
                    key=None
                    for level in range(z,max(-1,z-4),-1):
                        scale=2**(z-level);parent_x=tx/scale;parent_y=ty/scale
                        candidate=(level,int(parent_y),int(parent_x))
                        if candidate not in native:
                            response=await page.request.get(url+f"/api/atlas/tiles/ctx-global/{level}/{candidate[1]}/{candidate[2]}")
                            native[candidate]=(Image.open(io.BytesIO(await response.body())).convert("RGBA").resize((256,256),Image.Resampling.BILINEAR)
                                               if response.ok else None)
                        if native[candidate] is not None:
                            key=candidate;px=(parent_x%1)*256;py=(parent_y%1)*256
                            break
                    if key is None:continue
                    pixel=native[key].getpixel((min(255,int(px)),min(255,int(py))))
                    if pixel[3]<250:continue  # Genuine source NoData is transparent.
                    expected=pixel[:3]
                else:
                    effective_z=z
                    if z==9 and (int(tx)+int(ty))%17==0:
                        effective_z=z-1
                        tx/=2;ty/=2;px=(tx%1)*256;py=(ty%1)*256
                    expected=(250,250,250) if 23<px<72 and 38<py<92 else color(effective_z,int(ty),int(tx))
                    if 15<px<80 and 30<py<100 and expected!=(250,250,250):continue
                checked+=1
                if max(abs(a-b) for a,b in zip(sample["rgb"],expected))>(25 if real else 12):
                    bad+=1
                    if len(examples)<3:examples.append({**sample,"expected":expected})
            reports.append({"view":[lon,lat,zoom],"lod":z,"checked":checked,"bad":bad,"examples":examples,
                            "ready":status["ready"],"fallback":status["fallback"],"total":status["total"]})
            await page.screenshot(path=str(OUT/f"{'real-' if real else ''}coordinate-{len(reports)}.png"))
        (OUT/("real-coordinate-report.json" if real else "coordinate-report.json")).write_text(json.dumps({"cases":reports,"errors":errors,"upstream_failures":failures},indent=2))
        print(json.dumps(reports,indent=2))
        assert not errors,errors
        assert all(r["checked"]>80 and r["bad"]/r["checked"]<(.1 if real else .03) for r in reports),reports
        await browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    parser.add_argument("--real",action="store_true")
    args=parser.parse_args()
    asyncio.run(run(args.url,args.real))
