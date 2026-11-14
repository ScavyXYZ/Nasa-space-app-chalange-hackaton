"""Real production-bundle E2E + a recorded LOCAL demo. Start API on :8001.

Only the explicit no_route UI branch is mocked; all successful routing uses
the real A* API/DEM. No external website is used or published by this script.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/mvp"


def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    checks=[]
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        context=browser.new_context(viewport={"width":1440,"height":1100},
            reduced_motion="reduce",record_video_dir=str(OUT/"video"),record_video_size={"width":1440,"height":1100})
        page=context.new_page()
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(url,wait_until="load")
        expect(page.get_by_role("heading",name="План експедиції")).to_be_visible(timeout=60000)
        page.get_by_role("button",name="2D карта",exact=True).click()
        # Legacy 5km workflow remains explicitly selectable; regional has its
        # own full-map routing/scale E2E test.
        page.locator("#dataset").select_option("ctx")
        context_image=page.locator('img.leaflet-image-layer[src$="ctx-context.png"]')
        expect(context_image).to_be_visible()
        page.wait_for_function("Array.from(document.querySelectorAll('img.leaflet-image-layer')).every(i=>i.complete && i.naturalWidth>0)")
        map_bounds=page.get_by_test_id("mars-map").bounding_box()
        detail=page.locator('img.leaflet-image-layer[src$="ctx-optical.png"]').bounding_box()
        assert detail["height"] >= .75*min(map_bounds["width"],map_bounds["height"])
        page.get_by_role("button",name="Карта на всю ширину").click()
        expect(page.locator("#planner-panel")).to_be_hidden()
        page.wait_for_function("document.querySelector('.mars-map').getBoundingClientRect().width > 1100")
        page.get_by_role("button",name="Огляд регіону",exact=True).click()
        page.get_by_role("button",name="На весь екран",exact=True).click()
        page.wait_for_function("document.fullscreenElement !== null")
        page.screenshot(path=str(OUT/"map-fullscreen.png"))
        page.get_by_role("button",name="Вийти з екрана",exact=True).click()
        page.wait_for_function("document.fullscreenElement === null")
        page.get_by_role("button",name="Показати планування").click()
        expect(page.locator("#planner-panel")).to_be_visible()
        page.get_by_role("button",name="До ділянки",exact=True).click()
        checks.append("Full-width map, native fullscreen, regional overview and planner restoration")
        map_bounds=page.get_by_test_id("mars-map").bounding_box()
        for _ in range(8):
            if page.locator(".leaflet-control-zoom-out").get_attribute("aria-disabled")=="true":
                break
            page.locator(".leaflet-control-zoom-out").click()
        regional=context_image.bounding_box()
        assert regional["width"] >= map_bounds["width"]*.95 and regional["height"] >= map_bounds["height"]*.95
        page.get_by_role("button",name="До ділянки").click()
        detail=page.locator('img.leaflet-image-layer[src$="ctx-optical.png"]').bounding_box()
        assert detail["height"] >= .75*min(map_bounds["width"],map_bounds["height"])
        checks.append("Regional real CTX context fills zoomed-out view; DEM fills default view; reset works")
        map_box=page.get_by_test_id("mars-map").bounding_box()
        page.get_by_test_id("mars-map").click(position={"x":map_box["width"]/2,"y":map_box["height"]/2})
        expect(page.get_by_label("Початок: довгота")).not_to_have_value("")
        page.get_by_test_id("mars-map").click(position={"x":map_box["width"]/2+30,"y":map_box["height"]/2+20})
        expect(page.get_by_label("Кінець: довгота")).not_to_have_value("")
        checks.append("Real map clicks select validated A and B coordinates")
        page.get_by_role("button",name="Завантажити демонстраційні точки").click()
        page.get_by_role("button",name="Build Route",exact=True).click()
        expect(page.get_by_test_id("route-summary")).to_be_visible(timeout=60000)
        expect(page.locator(".js-plotly-plot")).to_be_visible(timeout=60000)
        expect(page.locator(".distance-tag").first).to_be_visible()
        page.get_by_role("button",name="До маршруту",exact=True).click()
        page.get_by_role("button",name="До ділянки",exact=True).click()
        checks.append("Real CTX A* -> map -> metrics -> Plotly -> sourced nearby science")
        page.screenshot(path=str(OUT/"desktop.png"),full_page=True)
        with page.expect_download() as download:
            page.get_by_role("button",name="GeoJSON",exact=True).click()
        download.value.save_as(str(OUT/"demo-route.geojson"))
        exported=json.loads((OUT/"demo-route.geojson").read_text())
        assert exported["geometry"]["type"]=="LineString"
        assert "Mars" in exported["properties"]["coordinate_system"]
        checks.append("GeoJSON export of real route with Mars coordinate disclaimer")
        page.get_by_label("Геологія",exact=True).check()
        page.get_by_label("Ухили",exact=True).check()
        page.get_by_label("Висоти",exact=True).check()
        page.locator("#science").get_by_role("button",name="Показати на карті").first.click()
        page.get_by_label("Початок: довгота").fill("0")
        assert page.get_by_test_id("route-summary").count()==0
        page.get_by_role("button",name="Build Route",exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("поза вибраною сіткою")
        checks.append("Stale results cleared; real outside-grid error rendered")
        page.get_by_role("button",name="Завантажити демонстраційні точки").click()
        page.locator("#slope").focus()
        page.locator("#slope").press("Home")
        page.get_by_role("button",name="Build Route",exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("непрохідній клітинці")
        checks.append("Real blocked-endpoint error at zero slope threshold")
        page.get_by_role("button",name="Завантажити демонстраційні точки").click()
        page.route("**/api/route",lambda route:route.fulfill(json={"status":"no_route"}))
        page.get_by_role("button",name="Build Route",exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("шляху немає")
        page.unroute("**/api/route")
        checks.append("no_route UI branch (mocked; graph disconnection tested in routing unit tests)")
        page.locator("#dataset").select_option("hirise")
        for label,value in [
            ("Початок: довгота","77.4508"),("Початок: широта","18.4447"),
            ("Кінець: довгота","77.4513"),("Кінець: широта","18.4452")]:
            page.get_by_label(label,exact=True).fill(value)
        page.locator("#slope").focus();page.locator("#slope").press("End")
        page.get_by_role("button",name="Build Route",exact=True).click()
        expect(page.get_by_test_id("route-summary")).to_be_visible(timeout=60000)
        checks.append("Real HiRISE A* with explicit separate grid")
        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(OUT/"mobile.png"),full_page=True)
        page.set_viewport_size({"width":812,"height":375})
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
        checks.append("375px mobile and landscape; reduced motion")
        video=page.video
        context.close()
        video.save_as(str(OUT/"mars-explorer-local-demo.webm"))
        browser.close()
    assert not errors,errors
    result={"status":"passed","checks":checks,"page_errors":errors,
            "scope":"Local production build with real API. Public deployment not verified."}
    (OUT/"e2e_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:8001")
    run(parser.parse_args().url)
