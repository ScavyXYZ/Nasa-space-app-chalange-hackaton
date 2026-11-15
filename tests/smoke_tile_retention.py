"""Synthetic delayed tiles: verify rendered overlap, not merely request counts."""
import argparse
import asyncio
import io
import json
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parents[1] / "artifacts/zoom"


async def run(url):
    image = Image.new("RGB", (256, 256), (230, 0, 230))
    data = io.BytesIO()
    image.save(data, format="PNG")
    gray = io.BytesIO()
    Image.new("RGB", (256, 256), (90, 90, 90)).save(gray, format="PNG")
    target_zoom = None
    slow = False
    requests = 0
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width":1440,"height":1100})
        page.on("pageerror", lambda e: errors.append(str(e)))

        async def tile(route):
            nonlocal requests
            requests += 1
            if slow:
                # A few fast responses among slow ones reproduce partial atlases.
                await asyncio.sleep(.04 if requests % 6 == 0 else 1.5)
            try:
                level = int(urlsplit(route.request.url).path.split("/")[-3])
                await route.fulfill(body=data.getvalue() if level==target_zoom else gray.getvalue(),
                                    content_type="image/png")
            except Exception:
                pass  # An obsolete offscreen request can legitimately be cancelled.

        await page.route("**/api/atlas/tiles/**", tile)
        await page.goto(url)
        await page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]')
        for _ in range(19):
            await page.get_by_role("button", name="Zoom in on Mars", exact=True).click()
        await page.wait_for_timeout(250)
        target_zoom = int(await page.get_by_test_id("mars-globe").get_attribute("data-detail-zoom"))
        # Only the tested native LOD is magenta. A lower-resolution fallback
        # must not make the pixel-retention assertion pass accidentally.
        await page.reload()
        await page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]')
        for _ in range(19):
            await page.get_by_role("button", name="Zoom in on Mars", exact=True).click()
        await page.wait_for_timeout(250)
        await page.wait_for_function(r"""()=>{
          const g=document.querySelector('[data-testid="mars-globe"]');
           return Number(g.dataset.detailReady)>0&&g.dataset.detailReady===g.dataset.detailTotal
        }""")
        globe = page.get_by_test_id("mars-globe")
        box = await globe.bounding_box()
        x, y = box["x"] + box["width"]*.5, box["y"] + box["height"]*.5

        async def coverage():
            screenshot = await globe.screenshot()
            shot = Image.open(io.BytesIO(screenshot)).convert("RGB")
            # Exclude overlaid controls and text near the canvas edges.
            w, h = shot.size
            pixels = list(shot.crop((int(w*.1),int(h*.25),int(w*.9),int(h*.75))).getdata())
            return sum(r>80 and b>80 and g<min(r,b)*.4 for r,g,b in pixels)/len(pixels)

        initial = await coverage()
        assert initial > .85, initial
        slow = True
        fractions = []
        for _ in range(7):
            await page.mouse.move(x, y)
            await page.mouse.down()
            await page.mouse.move(x+95, y, steps=5)
            await page.mouse.up()
            await page.wait_for_timeout(180)
            fractions.append(await coverage())
        # Previously loaded overlap must survive successive partial replacements.
        assert min(fractions) > .65, fractions
        # Return to the loaded ground while requests are still delayed.
        for _ in range(7):
            await page.mouse.move(x+95, y)
            await page.mouse.down()
            await page.mouse.move(x, y, steps=5)
            await page.mouse.up()
            await page.wait_for_timeout(90)
        restored = await coverage()
        assert restored > .85, restored
        assert not errors, errors
        OUT.mkdir(parents=True, exist_ok=True)
        report = {"status":"passed", "native_zoom":target_zoom, "initial_coverage":initial,
                  "delayed_pan_coverage":fractions, "return_coverage":restored,
                  "requests":requests, "page_errors":errors}
        (OUT/"retention-report.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8003")
    asyncio.run(run(parser.parse_args().url))
