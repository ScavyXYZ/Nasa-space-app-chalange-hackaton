"""Real optical LOD in globe and automatic source switching in 2D."""
import argparse
import json
import math
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT=Path(__file__).resolve().parents[1]/"artifacts/zoom"
DETAIL_DISPLAYED="""()=>{const d=document.querySelector('[data-testid="mars-globe"]').dataset;
    return Number(d.detailReady)+Number(d.detailFallback)>0}"""


def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.on("console",lambda m:errors.append(m.text) if m.type=="error" and "THREE.WebGLProgram" in m.text else None)
        page.goto(url)
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]',timeout=60000)
        # Close-up optical imagery is automatic, without a manual HD toggle.
        expect(page.get_by_role("button",name="Автознімки HD",exact=True)).to_have_attribute("aria-pressed","true")
        # Detail starts in the initial view, not only after the first zoom.
        page.wait_for_function(DETAIL_DISPLAYED,timeout=120000)
        for _ in range(6):
            page.get_by_role("button",name="Наблизити планету",exact=True).click()
        page.wait_for_function(DETAIL_DISPLAYED,timeout=120000)
        page.screenshot(path=str(OUT/"globe-detail.png"),full_page=True)
        first=int(page.get_by_test_id("mars-globe").get_attribute("data-detail-zoom"))
        for _ in range(3):
            page.get_by_role("button",name="Наблизити планету",exact=True).click()
        page.wait_for_function(f"Number(document.querySelector('[data-testid=\"mars-globe\"]').dataset.detailZoom)>{first}",timeout=60000)
        page.wait_for_function(DETAIL_DISPLAYED,timeout=120000)
        page.screenshot(path=str(OUT/"globe-close.png"),full_page=True)
        # At extreme perspective zoom, a small drag stays inside the viewport.
        for _ in range(30):
            page.get_by_role("button",name="Наблизити планету",exact=True).click()
        globe=page.get_by_test_id("mars-globe")
        zoom=float(globe.get_attribute("data-camera-zoom"))
        assert zoom>100
        before=(float(globe.get_attribute("data-view-lon")),float(globe.get_attribute("data-view-lat")))
        box=globe.bounding_box()
        x,y=box["x"]+box["width"]/2,box["y"]+box["height"]/2
        page.mouse.move(x,y)
        page.mouse.down()
        page.mouse.move(x+20,y+10,steps=5)
        page.mouse.up()
        page.wait_for_function("(lon)=>Number(document.querySelector('[data-testid=\"mars-globe\"]').dataset.viewLon)!==lon",arg=before[0])
        after=(float(globe.get_attribute("data-view-lon")),float(globe.get_attribute("data-view-lat")))
        angular_drag=math.hypot(((after[0]-before[0]+180)%360-180)*math.cos(math.radians(before[1])),after[1]-before[1])
        visible_degrees=2*.16*math.tan(math.radians(19))/zoom*180/math.pi
        assert 0<angular_drag<visible_degrees*.2,(angular_drag,visible_degrees)
        page.get_by_role("button",name="2D атлас",exact=True).click()
        expect(page.get_by_label("Картографічний шар")).to_have_value("auto")
        page.get_by_role("button",name="Наблизити Jezero",exact=True).click()
        expect(page.get_by_test_id("atlas-map")).to_have_attribute("data-source","ctx-jezero")
        for expected_zoom in range(11,14):
            page.get_by_role("button",name="Zoom in",exact=True).click()
            expect(page.get_by_test_id("atlas-map")).to_have_attribute("data-zoom",str(expected_zoom))
        expect(page.get_by_test_id("atlas-map")).to_have_attribute("data-source","hirise-jezero")
        page.wait_for_function("Array.from(document.querySelectorAll('.atlas-map img.leaflet-tile')).some(i=>i.src.includes('hirise-jezero')&&i.complete&&i.naturalWidth>0)",timeout=120000)
        page.wait_for_function("Array.from(document.querySelectorAll('.atlas-map img.leaflet-tile')).filter(i=>i.src.includes('hirise-jezero')).every(i=>i.complete)",timeout=120000)
        page.screenshot(path=str(OUT/"hirise-jezero.png"),full_page=True)
        # This is not a Jezero-only atlas: prove high zoom at Gale as well.
        page.get_by_label("Пошук місць на Марсі").fill("Gale")
        page.locator(".mc-place").click()
        expect(page.get_by_test_id("atlas-map")).to_have_attribute("data-source","ctx-global")
        current=int(page.get_by_test_id("atlas-map").get_attribute("data-zoom"))
        for expected_zoom in range(current+1,13):
            page.get_by_role("button",name="Zoom in",exact=True).click()
            expect(page.get_by_test_id("atlas-map")).to_have_attribute("data-zoom",str(expected_zoom))
        page.wait_for_function("Array.from(document.querySelectorAll('.atlas-map img.leaflet-tile')).some(i=>i.src.includes('ctx-global/12/')&&i.complete&&i.naturalWidth>0)",timeout=120000)
        page.screenshot(path=str(OUT/"gale-global-detail.png"),full_page=True)
        # Tiles must be above fallback imagery, not hidden by ImageOverlay's default pane.
        pane=page.evaluate("""()=>{const tile=document.querySelector('.atlas-map img.leaflet-tile');
          const fallback=document.querySelector('.atlas-map img.leaflet-image-layer');
          return tile.closest('.leaflet-tile-pane')===fallback.closest('.leaflet-tile-pane')}""")
        assert pane
        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
        assert not errors,errors
        report={"status":"passed","checks":["Initial view starts detail loading without a zoom gesture",
                "Extreme zoom drag stays within 20% of visible surface span",
                "Globe loads real detail tiles and increases LOD with zoom",
                "2D automatically switches CTX to HiRISE in Jezero","Real CTX tiles at zoom 12 in Gale, outside Jezero","Optical tiles render above fallback image",
                "Mobile no horizontal overflow"],"page_errors":errors}
        (OUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
