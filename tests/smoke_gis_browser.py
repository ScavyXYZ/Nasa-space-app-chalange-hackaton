"""Optional live browser QA, separate from unittest. Requires Playwright Chromium.

Run server first, then python tests/smoke_gis_browser.py.
No fabricated terrain is used. Screenshots/report are written to processed/gis.
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/gis"


def run(url):
    errors=[]
    checks=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1000},reduced_motion="reduce")
        page.on("pageerror",lambda e: errors.append(str(e)))
        page.goto(url,wait_until="load")
        expect(page.locator("#status")).to_contain_text("Шари завантажено",timeout=60000)
        # Layer bounds and pixel placement share the same geographic display.
        result=page.evaluate("""() => {
          const point=L.latLng(18.4447,77.4508);
          const back=map.containerPointToLatLng(map.latLngToContainerPoint(point));
          return {errorDeg:Math.max(Math.abs(point.lat-back.lat),Math.abs(point.lng-back.lng)),
                  errorPixels:map.project(point).distanceTo(map.project(back)),
                  marsEastDistance:map.distance(point,L.latLng(18.4447,77.4517)),
                  images:Array.from(document.querySelectorAll('.leaflet-image-layer')).every(i=>i.complete && i.naturalWidth>0)};
        }""")
        assert result["errorPixels"] <= 0.71, result  # Leaflet rounds display points to pixels.
        assert 49 < result["marsEastDistance"] < 52, result
        assert result["images"],result
        checks.append({"map_coordinate_roundtrip_and_Mars_distance":result})
        for dataset in ["ctx","hirise"]:
            page.locator("#dataset").select_option(dataset)
            for lon,lat in [(77.4508,18.4447),(77.452,18.4452)]:
                page.locator("#lon").fill(str(lon))
                page.locator("#lat").fill(str(lat))
                page.get_by_role("button",name="Перевірити координати").click()
                expect(page.locator("#status")).to_contain_text(f"{dataset.upper()} [")
                # Wait for the async point action, not a fixed sleep.
                expected_count=1 if lon==77.4508 else 2
                expect(page.locator("#vertex-count")).to_have_text(f"Вершин: {expected_count}")
            page.get_by_role("button",name="Побудувати профіль").click()
            expect(page.locator("#status")).to_contain_text("Профіль розрахований",timeout=60000)
            expect(page.locator("#chart polyline")).to_be_visible()
            assert page.locator("#samples tr").count()>1
            checks.append({f"{dataset}_interactive_point_and_profile":"passed"})
            page.screenshot(path=str(OUT/f"gis_{dataset}_profile.png"),full_page=True)
            page.get_by_role("button",name="Очистити",exact=True).click()
        # Real geology and terrain image overlays can be enabled together.
        for title in ["CTX elevation","CTX slope","Геологічні одиниці","Наукові області"]:
            page.locator(".leaflet-control-layers label").filter(has_text=title).locator("input").check()
        expect(page.locator(".leaflet-overlay-pane path").first).to_be_visible()
        page.wait_for_function("Array.from(document.querySelectorAll('.leaflet-image-layer')).every(i=>i.complete && i.naturalWidth>0)")
        page.screenshot(path=str(OUT/"gis_desktop.png"),full_page=True)
        checks.append({"real_geology_science_terrain_overlays":"passed"})
        page.set_viewport_size({"width":375,"height":812})
        page.evaluate("map.invalidateSize()")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile horizontal overflow"
        page.screenshot(path=str(OUT/"gis_mobile.png"),full_page=True)
        checks.append({"mobile_375px_no_horizontal_overflow":"passed"})
        page.set_viewport_size({"width":812,"height":375})
        page.evaluate("map.invalidateSize()")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        checks.append({"landscape_no_horizontal_overflow":"passed"})
        browser.close()
    assert not errors, errors
    report={"status":"passed","checks":checks,"page_errors":errors,
            "note":"Automated display and interaction checks; not proof of metre-accurate geology registration."}
    (OUT/"browser_validation_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:8000/gis-check")
    args=parser.parse_args()
    run(args.url)
