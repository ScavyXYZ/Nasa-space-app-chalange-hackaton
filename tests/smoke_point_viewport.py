"""A/B/stops inspect the selected point without issuing a camera-focus command."""
import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

from playwright.sync_api import sync_playwright,expect

OUT=Path(__file__).resolve().parents[1]/"artifacts/zoom"


def state(host,globe):
    keys=["data-view-lon","data-view-lat","data-camera-zoom" if globe else "data-zoom"]
    return tuple(float(host.get_attribute(k)) for k in keys)


def pick_without_moving(page,host,globe,field,x=.47,y=.46):
    before=state(host,globe)
    box=host.bounding_box()
    with page.expect_response(lambda r:"/api/atlas/inspect?" in r.url,timeout=30000) as inspection:
        host.click(position={"x":box["width"]*x,"y":box["height"]*y})
    inspection.value.json()
    coords=parse_qs(urlsplit(inspection.value.url).query)
    for label,key in [("довгота","lon"),("широта","lat")]:
        element=page.get_by_label(field+": "+label,exact=True)
        expect(element).not_to_have_value("")
        assert abs(float(element.input_value())-float(coords[key][0]))<1e-6
    # Include effects/data-response commits, not only the synchronous click.
    page.wait_for_timeout(150)
    after=state(host,globe)
    assert all(abs(a-b)<1e-9 for a,b in zip(before,after)),(before,after)


def run(url):
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(url)
        globe=page.get_by_test_id("mars-globe")
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]',timeout=60000)
        for _ in range(22):
            page.get_by_role("button",name="Наблизити планету",exact=True).click()
        assert state(globe,True)[2]>10
        pick_without_moving(page,globe,True,"Початок")
        pick_without_moving(page,globe,True,"Кінець",.57,.52)
        page.get_by_role("button",name="Додати зупинку",exact=True).click()
        pick_without_moving(page,globe,True,"Зупинка 1",.4,.54)

        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_timeout(200)
        pick_without_moving(page,globe,True,"Кінець",.54,.4)
        page.set_viewport_size({"width":1440,"height":1100})
        page.get_by_role("button",name="2D атлас",exact=True).click()
        page.get_by_role("button",name="Наблизити Jezero",exact=True).click()
        atlas=page.get_by_test_id("atlas-map")
        for z in range(11,14):
            page.get_by_role("button",name="Zoom in",exact=True).click()
            expect(atlas).to_have_attribute("data-zoom",str(z))
        page.locator(".mc-endpoint > button").nth(0).click()
        pick_without_moving(page,atlas,False,"Початок")
        pick_without_moving(page,atlas,False,"Кінець",.58,.52)
        page.get_by_role("button",name="Додати зупинку",exact=True).click()
        pick_without_moving(page,atlas,False,"Зупинка 2",.4,.54)

        # Explicit navigation must still work; only ordinary placement is inert.
        page.get_by_label("Пошук місць на Марсі").fill("Gale")
        page.locator(".mc-place").click()
        page.wait_for_function("""()=>{
          const d=document.querySelector('[data-testid="atlas-map"]').dataset;
          return Math.abs(Number(d.viewLon)-137.4)<1e-6&&Math.abs(Number(d.viewLat)+4.6)<1e-6
        }""")
        assert state(atlas,False)[2]<13
        assert not errors,errors
        report={"status":"passed","checks":["Globe A/B/stops preserve zoom and camera direction",
                "Mobile globe placement preserves view","2D A/B/stops preserve zoom 13 and map centre",
                "Selection still inspects the newly picked coordinates","Place search still navigates explicitly"],
                "page_errors":errors}
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/"point-viewport-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
