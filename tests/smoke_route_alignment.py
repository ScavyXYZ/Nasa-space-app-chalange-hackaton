"""Real local DEM route: view retained, honest snapping links, unchanged export."""
import argparse
import base64
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from smoke_point_viewport import state

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/zoom"


def run(url):
    plan={"start":{"lon":-97.150761,"lat":24.024217},"end":{"lon":-97.095,"lat":24.009},
          "stops":[],"weight":5,"grade":15,"resolution":"auto"}
    encoded=base64.b64encode(json.dumps(plan).encode()).decode()
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.on("console",lambda m:errors.append(m.text) if m.type=="error" and "THREE.WebGLProgram" in m.text else None)
        page.goto(url+"/#mission="+encoded)
        globe=page.get_by_test_id("mars-globe")
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]',timeout=60000)
        for _ in range(23):
            page.get_by_role("button",name="Наблизити планету",exact=True).click()
        before=state(globe,True)
        with page.expect_response(lambda r:r.url.endswith("/api/expedition"),timeout=60000) as response:
            page.get_by_role("button",name="Побудувати маршрут",exact=True).click()
        result=response.value.json()
        assert result["status"]=="ok",result
        assert result["dataset"]=="mola128",result["dataset"]
        assert result["terrain_validation"]["entire_route"]
        expect(page.get_by_test_id("global-route-summary")).to_be_visible()
        expect(page.locator(".globe-note")).to_contain_text("не перевірений проїзд")
        assert before==state(globe,True)
        OUT.mkdir(parents=True,exist_ok=True)
        page.locator(".globe-shell").screenshot(path=str(OUT/"route-alignment-globe.png"))
        with page.expect_download() as download:
            page.get_by_role("button",name="Експорт GeoJSON",exact=True).click()
        exported=json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        assert exported["geometry"]==result["route"]["geometry"]
        assert exported["properties"]["metrics"]["distance_m"]==result["metrics"]["distance_m"]
        page.get_by_role("button",name="2D атлас",exact=True).click()
        page.get_by_role("button",name="Показати схили 463 м та контури",exact=True).click()
        atlas=page.get_by_test_id("atlas-map")
        for z in range(10,13):
            page.get_by_role("button",name="Zoom in",exact=True).click()
            expect(atlas).to_have_attribute("data-zoom",str(z))
        expect(page.locator(".atlas-snap-note")).to_be_visible()
        # Leaflet uses a canvas renderer: inspect the actual vector overlay,
        # not SVG path counts or the unrelated optical background.
        painted=page.locator(".leaflet-overlay-pane canvas").evaluate("""canvas=>{
          const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
          let grey=0,mint=0;
          for(let i=0;i<pixels.length;i+=4){
            if(pixels[i+3]<50)continue;
            if(Math.abs(pixels[i]-193)<5&&Math.abs(pixels[i+1]-200)<5&&Math.abs(pixels[i+2]-207)<5)grey++;
            if(Math.abs(pixels[i]-164)<5&&Math.abs(pixels[i+1]-240)<5&&Math.abs(pixels[i+2]-211)<5)mint++;
          }
          return {grey,mint}
        }""")
        assert painted["grey"]>10 and painted["mint"]>100,painted
        page.locator(".atlas-map-shell").screenshot(path=str(OUT/"route-alignment-atlas.png"))
        assert not errors,errors
        report={"status":"passed","distance_m":result["metrics"]["distance_m"],
                "snap_offsets_m":result["metrics"]["snap_offsets_m"],
                "checks":["Real MOLA128 path with visible unverified endpoint connectors",
                          "Building preserves high-zoom camera",
                          "GeoJSON geometry and distance unchanged; connectors excluded",
                          "2D connector and route pixels independently visible at zoom 12"],
                "page_errors":errors}
        (OUT/"route-alignment-report.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
