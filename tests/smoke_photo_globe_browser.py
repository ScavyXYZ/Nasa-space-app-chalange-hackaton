"""Automatic optical photos on the ordinary globe, without terrain relief."""
import argparse
import base64
import io
import json
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright, expect
from smoke_point_viewport import state

OUT=Path(__file__).resolve().parents[1]/"artifacts/planet"


def photo_fraction(globe):
    image=Image.open(io.BytesIO(globe.screenshot())).convert("RGB")
    w,h=image.size
    pixels=list(image.crop((int(w*.15),int(h*.25),int(w*.85),int(h*.8))).getdata())
    # Black background/empty tiles and saturated white do not count as photos.
    return sum(max(rgb)-min(rgb)<=4 and 20<sum(rgb)/3<235 for rgb in pixels)/len(pixels)


def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.on("console",lambda m:errors.append(m.text) if m.type=="error" and "THREE.WebGLProgram" in m.text else None)
        plan={"start":{"lon":137.4,"lat":-4.6},"end":{"lon":137.5,"lat":-4.5},
              "stops":[],"weight":5,"grade":15,"resolution":"auto"}
        encoded=base64.b64encode(json.dumps(plan).encode()).decode()
        page.goto(url+"/#mission="+encoded)
        globe=page.get_by_test_id("mars-globe")
        expect(globe).to_have_attribute("data-ready","true",timeout=60000)
        expect(globe).to_have_attribute("data-surface-mode","imagery")
        expect(globe).to_have_attribute("data-texture-source","viking-local",timeout=30000)
        auto=page.get_by_role("button",name="Auto HD",exact=True)
        expect(auto).to_have_attribute("aria-pressed","true")
        for _ in range(14):
            page.get_by_role("button",name="Zoom in on Mars",exact=True).click()
        expect(globe).to_have_attribute("data-texture-source","ctx-global",timeout=120000)
        page.wait_for_function("""()=>{
            const d=document.querySelector('[data-testid="mars-globe"]').dataset;
            return Number(d.detailReady)>0
        }""",timeout=120000)
        fraction=photo_fraction(globe)
        assert fraction>.75,("CTX must visibly replace brown Viking, not just be requested",fraction)
        before=state(globe,True)
        page.locator(".globe-shell").screenshot(path=str(OUT/"gale-photo-globe.png"))
        auto.click()
        expect(globe).to_have_attribute("data-texture-source","viking-local",timeout=60000)
        assert state(globe,True)==before
        auto.click()
        expect(globe).to_have_attribute("data-texture-source","ctx-global",timeout=60000)
        assert state(globe,True)==before
        expect(auto).to_have_attribute("aria-pressed","true")
        for _ in range(14):
            page.get_by_role("button",name="Zoom out from Mars",exact=True).click()
        expect(globe).to_have_attribute("data-texture-source","viking-local",timeout=60000)
        assert photo_fraction(globe)<.25,"Zoom-out must visibly restore Viking colors"
        # Back in close-up, disabling auto photos remains an explicit offline option.
        auto.click()
        expect(auto).to_have_attribute("aria-pressed","false")
        for _ in range(14):
            page.get_by_role("button",name="Zoom in on Mars",exact=True).click()
        expect(globe).to_have_attribute("data-texture-source","viking-local",timeout=30000)
        auto.click()
        page.get_by_role("button",name="Jezero",exact=True).click()
        for _ in range(27):
            page.get_by_role("button",name="Zoom in on Mars",exact=True).click()
        expect(globe).to_have_attribute("data-texture-source","hirise-jezero",timeout=120000)
        page.wait_for_function("""()=>{
            const d=document.querySelector('[data-testid="mars-globe"]').dataset;
            return d.detailSourceId==='hirise-jezero'&&Number(d.detailReady)>0
        }""",timeout=120000)
        page.locator(".globe-shell").screenshot(path=str(OUT/"jezero-hirise-globe.png"))
        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
        assert not errors,errors
        report={"status":"passed","automatic_ctx_on_globe":True,
                "gale_grayscale_photo_fraction":round(fraction,3),
                "automatic_controlled_hirise_on_jezero":True,
                "imagery_roundtrip_preserves_camera":True,
                "zoom_out_restores_viking":True,"explicit_offline_option":True,
                "page_errors":errors}
        (OUT/"photo-globe-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
