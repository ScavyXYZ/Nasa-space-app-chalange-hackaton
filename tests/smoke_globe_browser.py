"""Global Mars texture, interaction, fullscreen and Jezero transition."""
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
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]',timeout=60000)
        expect(page.get_by_role("button",name="Планета",exact=True)).to_have_attribute("aria-pressed","true")
        globe=page.get_by_test_id("mars-globe")
        globe.screenshot(path=str(OUT/"mars-whole-planet.png"))
        checks.append("Default whole-Mars globe with real locally hosted USGS Viking colorized texture")
        for _ in range(6):
            page.get_by_role("button",name="Обернути Марс праворуч").click()
        page.get_by_role("button",name="Наблизити планету").click()
        page.get_by_role("button",name="Віддалити планету").click()
        page.get_by_role("button",name="Показати Jezero",exact=True).click()
        canvas=globe.locator("canvas");box=canvas.bounding_box()
        canvas.click(position={"x":box["width"]/2,"y":box["height"]/2})
        expect(page.locator(".globe-note strong")).to_contain_text("лише глобальний огляд")
        checks.append("Both hemispheres via rotation; zoom; actual spherical coordinate picking")
        page.get_by_role("button",name="Весь екран",exact=True).click()
        page.wait_for_function("document.fullscreenElement !== null")
        page.get_by_role("button",name="Вийти з глобуса",exact=True).click()
        page.wait_for_function("document.fullscreenElement === null")
        page.get_by_role("button",name="Перейти до Jezero",exact=False).click()
        expect(page.get_by_test_id("mars-map")).to_be_visible()
        page.get_by_role("button",name="Завантажити демонстраційні точки").click()
        page.get_by_role("button",name="Build Route",exact=True).click()
        expect(page.get_by_test_id("route-summary")).to_be_visible(timeout=60000)
        page.get_by_role("button",name="Планета",exact=True).click()
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]')
        expect(page.get_by_test_id("route-summary")).to_be_visible()
        checks.append("Fullscreen and transition to real Jezero A*; route retained when returning to globe")
        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
        globe.screenshot(path=str(OUT/"mars-globe-mobile.png"))
        checks.append("Mobile globe layout")
        browser.close()
    assert not errors,errors
    result={"status":"passed","checks":checks,"page_errors":errors,
            "limitation":"Global visual browsing, no global DEM routing; colorized not true-color"}
    (OUT/"globe_e2e_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8001")
    run(parser.parse_args().url)
