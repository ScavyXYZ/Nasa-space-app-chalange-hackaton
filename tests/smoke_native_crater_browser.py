"""Small known crater: MOLA alone accepts crossing; the rim guard must detour."""
import argparse
import base64
import io
import json
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urljoin

from PIL import Image
from playwright.sync_api import sync_playwright,expect
from smoke_point_viewport import state

OUT=Path(__file__).resolve().parents[1]/"artifacts/global/rim-guard"


def run(url):
    # Initial shared point frames the region; editing A must not move the view.
    plan={"start":{"lon":-96.806,"lat":24.044},"end":{"lon":-96.776,"lat":24.044},
          "stops":[],"weight":5,"grade":15,"resolution":"auto"}
    encoded=base64.b64encode(json.dumps(plan).encode()).decode()
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(url+"/#mission="+encoded)
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]',timeout=60000)
        page.get_by_label("Початок: довгота",exact=True).fill("-96.836")
        page.get_by_label("Початок: широта",exact=True).fill("24.044")
        page.get_by_role("button",name="2D атлас",exact=True).click()
        atlas=page.get_by_test_id("atlas-map")
        page.wait_for_function("Number(document.querySelector('[data-testid=\"atlas-map\"]').dataset.zoom)>=2")
        before=state(atlas,False)
        with page.expect_response(lambda r:r.url.endswith("/api/expedition"),timeout=120000) as response:
            page.get_by_role("button",name="Побудувати маршрут",exact=True).click()
        result=response.value.json()
        assert result["status"]=="ok",result
        assert result["terrain_validation"]["entire_route"]
        assert result["terrain_validation"]["catalogue_rim_guard"]
        assert result["terrain_validation"]["model"]=="mola128-rim-guard-v1"
        assert result["metrics"]["max_surface_slope_deg"]<=15
        assert result["metrics"]["distance_m"]>result["metrics"]["direct_distance_m"]*1.15
        expect(page.get_by_test_id("global-route-summary")).to_be_visible()
        assert before==state(atlas,False)
        # This explicit focus action is allowed to navigate. Building is not.
        page.get_by_role("button",name="Показати схили 463 м та контури",exact=True).click()
        expect(atlas).to_have_attribute("data-zoom","9")
        for z in range(10,14):
            page.get_by_role("button",name="Zoom in",exact=True).click()
            expect(atlas).to_have_attribute("data-zoom",str(z))
        # Keyboard panning avoids momentum-dependent mouse-drag framing.
        atlas.focus()
        for _ in range(4):
            atlas.press("ArrowRight")
            page.wait_for_timeout(350)
        page.wait_for_function("""()=>{
            const d=document.querySelector('[data-testid="atlas-map"]').dataset;
            return Math.abs(Number(d.viewLon)+96.806)<.006
        }""")
        for _ in range(2):
            atlas.press("ArrowDown")
            page.wait_for_timeout(350)
        page.wait_for_function("""Array.from(document.querySelectorAll('.atlas-map img')).some(i=>
            i.src.includes('/api/hazards/native-slopes?')&&i.complete&&i.naturalWidth>0)""",timeout=30000)
        overlay=page.locator('img[src*="/api/hazards/native-slopes?"]')
        source=overlay.get_attribute("src")
        mask=Image.open(io.BytesIO(page.request.get(urljoin(url,source)).body())).convert("RGBA")
        bounds={k:float(v[0]) for k,v in parse_qs(urlsplit(source).query).items()
                if k in ("west","south","east","north")}
        def blocked(lon,lat):
            x=int((lon-bounds["west"])*128);y=int((bounds["north"]-lat)*128)
            assert 0<=x<mask.width and 0<=y<mask.height,(lon,lat,bounds)
            return mask.getpixel((x,y))[3]>0
        coords=result["route"]["geometry"]["coordinates"]
        assert all(not blocked(*point) for point in coords)
        a,b=(-96.836,24.044),(-96.776,24.044)
        crossed=sum(blocked(a[0]+(b[0]-a[0])*i/200,a[1]+(b[1]-a[1])*i/200) for i in range(201))
        assert crossed>0,crossed
        with page.expect_download() as download:
            page.get_by_role("button",name="Експорт GeoJSON",exact=True).click()
        exported=json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        assert exported["geometry"]==result["route"]["geometry"]
        assert exported["properties"]["terrain_validation"]["catalogue_rim_guard"]
        assert exported["properties"]["hazard_policy"]["mode"]=="unresolved_catalogue_rim_guard"
        OUT.mkdir(parents=True,exist_ok=True)
        page.locator(".atlas-map-shell").screenshot(path=str(OUT/"small-crater-detour.png"))
        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
        expect(page.locator(".atlas-rim-legend")).to_be_visible()

        # Actual crater-floor routing remains possible, not a blanket ban.
        for label,value in [("Початок: довгота","137.4"),("Початок: широта","-4.6"),
                            ("Кінець: довгота","137.45"),("Кінець: широта","-4.6")]:
            page.get_by_label(label,exact=True).fill(value)
        floor_view=state(atlas,False)
        with page.expect_response(lambda r:r.url.endswith("/api/expedition"),timeout=120000) as response:
            page.get_by_role("button",name="Побудувати маршрут",exact=True).click()
        floor=response.value.json()
        assert floor["status"]=="ok",floor
        expect(page.get_by_test_id("global-route-summary")).to_be_visible()
        assert floor_view==state(atlas,False),("floor",floor_view,state(atlas,False))

        # An unproven floor-to-outside exit must remove the preceding success,
        # including export/report actions, without moving this map.
        page.get_by_label("Кінець: довгота",exact=True).fill("138.4")
        page.get_by_label("Кінець: широта",exact=True).fill("-4.2")
        with page.expect_response(lambda r:r.url.endswith("/api/expedition"),timeout=120000) as response:
            page.get_by_role("button",name="Побудувати маршрут",exact=True).click()
        rejected=response.value.json()
        assert rejected["status"]=="no_route",rejected
        assert rejected["reason"]=="crater_exit_needs_finer_dem",rejected
        assert "route" not in rejected
        expect(page.get_by_test_id("global-route-summary")).to_have_count(0)
        expect(page.get_by_role("button",name="Експорт GeoJSON",exact=True)).to_have_count(0)
        expect(page.get_by_role("button",name="Звіт / PDF",exact=True)).to_have_count(0)
        expect(page.get_by_role("alert")).to_contain_text("по різні боки каталожного борту")
        assert floor_view==state(atlas,False),("rejected exit",floor_view,state(atlas,False))
        assert not errors,errors
        report={"status":"passed","distance_m":result["metrics"]["distance_m"],
                "direct_distance_m":result["metrics"]["direct_distance_m"],
                "straight_guarded_samples":crossed,"route_guarded_cells":0,
                "native_route_cells":len(coords),"max_surface_slope_deg":result["metrics"]["max_surface_slope_deg"],
                "mobile_no_overflow":True,
                "exported_guard_provenance":True,"real_crater_floor_route":True,
                "unverified_exit_rejected_without_stale_route_or_export":True,
                "page_errors":errors}
        (OUT/"small-crater-browser-report.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
