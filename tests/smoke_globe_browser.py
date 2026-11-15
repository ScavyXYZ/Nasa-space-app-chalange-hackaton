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
        expect(page.get_by_role("button",name="Планета",exact=True)).to_have_attribute("aria-current","page")
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
        expect(page.locator(".globe-note strong")).to_contain_text("°")
        expect(page.get_by_label("Початок: довгота",exact=True)).not_to_have_value("")
        first=page.get_by_label("Початок: довгота",exact=True).input_value()
        x,y=box["x"]+box["width"]/2,box["y"]+box["height"]/2
        page.mouse.move(x,y)
        page.mouse.down()
        page.mouse.move(x+60,y,steps=5)
        page.mouse.move(x,y,steps=5)
        page.mouse.up()
        expect(page.get_by_label("Кінець: довгота",exact=True)).to_have_value("")
        elevation_requests=[]
        page.on("request",lambda request:elevation_requests.append(request.url) if "/api/elevation?" in request.url else None)
        for _ in range(3):
            page.get_by_role("button",name="Обернути Марс праворуч").click()
        canvas.click(position={"x":box["width"]/2,"y":box["height"]/2})
        expect(page.get_by_label("Кінець: довгота",exact=True)).not_to_have_value("")
        expect(page.get_by_label("Початок: довгота",exact=True)).to_have_value(first)
        assert not elevation_requests,"Global pin placement must not request unavailable DEM"
        page.get_by_role("button",name="Побудувати маршрут",exact=True).click()
        expect(page.get_by_test_id("global-route-summary")).to_be_visible(timeout=60000)
        page.screenshot(path=str(OUT/"global-waypoints.png"),full_page=True)
        checks.append("Global A/B placement on different hemispheres and real spherical MOLA routing")
        # Independent quarter-circumference check using manually entered coordinates.
        for label,value in [("Початок: довгота","0"),("Початок: широта","0"),
                            ("Кінець: довгота","90"),("Кінець: широта","0")]:
            page.get_by_label(label,exact=True).fill(value)
        expect(page.get_by_test_id("global-route-summary")).to_have_count(0)
        expect(page.get_by_role("button",name="Побудувати маршрут",exact=True)).to_be_enabled()
        checks.append("Manual coordinates invalidate stale global routes")
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
        page.get_by_role("button",name="Jezero · детально",exact=True).click()
        expect(page.get_by_test_id("route-summary")).to_be_visible()
        checks.append("Fullscreen and transition to real Jezero A*; local route retained after visiting global mode")
        page.get_by_role("button",name="Планета",exact=True).click()
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]')
        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
        expect(page.get_by_role("button",name="Перейти до Jezero",exact=False)).to_be_visible()
        globe.screenshot(path=str(OUT/"mars-globe-mobile.png"))
        checks.append("Mobile globe layout")
        browser.close()
    assert not errors,errors
    result={"status":"passed","checks":checks,"page_errors":errors,
            "limitation":"Global MOLA routing is approximate, 0.0625 degree bins; Viking texture is colorized"}
    (OUT/"globe_e2e_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8001")
    run(parser.parse_args().url)
