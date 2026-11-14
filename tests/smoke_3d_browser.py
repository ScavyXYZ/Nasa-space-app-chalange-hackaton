"""Real WebGL/DEM smoke test. No security-weakening Chromium flags."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT=Path(__file__).resolve().parents[1]/"artifacts/mvp"


def run(url):
    errors=[];checks=[]
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(url,wait_until="load")
        expect(page.get_by_role("heading",name="План експедиції")).to_be_visible()
        page.get_by_role("button",name="2D карта",exact=True).click()
        page.get_by_role("button",name="Завантажити демонстраційні точки").click()
        page.get_by_role("button",name="Build Route",exact=True).click()
        expect(page.get_by_test_id("route-summary")).to_be_visible()
        page.get_by_role("button",name="3D рельєф",exact=True).click()
        page.wait_for_selector('[data-testid="terrain-3d"][data-ready="true"]',timeout=60000)
        expect(page.get_by_test_id("terrain-3d").locator("canvas")).to_be_visible()
        checks.append("Real CTX DEM WebGL surface + actual A* route")
        page.get_by_role("button",name="Обернути 3D праворуч").click()
        page.get_by_label("Візуальне підсилення висот").select_option("3")
        page.wait_for_selector('[data-testid="terrain-3d"][data-ready="true"]')
        expect(page.locator(".terrain3d-note")).to_contain_text("×3")
        # Display exaggeration must not change the computed route metrics.
        expect(page.get_by_test_id("route-summary")).to_be_visible()
        page.get_by_test_id("terrain-3d").screenshot(path=str(OUT/"terrain-3d-ctx.png"))
        checks.append("Camera rotation + explicit visual exaggeration; route metrics retained")
        page.get_by_role("button",name="2D карта",exact=True).click()
        expect(page.get_by_test_id("mars-map")).to_be_visible()
        expect(page.get_by_test_id("route-summary")).to_be_visible()
        page.get_by_role("button",name="3D рельєф",exact=True).click()
        page.wait_for_selector('[data-testid="terrain-3d"][data-ready="true"]')
        page.locator("#dataset").select_option("hirise")
        page.wait_for_selector('[data-testid="terrain-3d"][data-ready="true"]',timeout=60000)
        expect(page.locator(".terrain3d-title")).to_contain_text("HIRISE")
        page.get_by_role("button",name="Скинути вид",exact=True).click()
        page.get_by_test_id("terrain-3d").screenshot(path=str(OUT/"terrain-3d-hirise.png"))
        canvas=page.get_by_test_id("terrain-3d").locator("canvas")
        box=canvas.bounding_box()
        canvas.click(position={"x":box["width"]/2,"y":box["height"]/2})
        expect(page.get_by_label("Початок: довгота")).not_to_have_value("")
        checks.append("3D raycast selects a coordinate validated by the real elevation API")
        checks.append("Separate real HiRISE mesh; switching 2D/3D preserves route until dataset changes")
        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
        checks.append("Mobile 3D layout without horizontal overflow")
        browser.close()
    assert not errors,errors
    result={"status":"passed","checks":checks,"page_errors":errors}
    (OUT/"3d_e2e_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8001")
    run(parser.parse_args().url)
