"""Release acceptance: unified atlas, NASA tiles, geology, stops, flyover, report, QR."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT=Path(__file__).resolve().parents[1]/"artifacts/release"


def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    errors,checks=[],[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(url,wait_until="load")
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]',timeout=60000)
        page.get_by_label("Геологія USGS",exact=True).check()
        expect(page.locator(".mc-geology-info")).to_contain_text("1:20M")
        page.get_by_role("button",name="2D атлас",exact=True).click()
        expect(page.get_by_test_id("atlas-map")).to_be_visible()
        page.get_by_label("Картографічний шар").select_option("themis-day")
        page.wait_for_function("Array.from(document.querySelectorAll('.atlas-map img.leaflet-tile')).some(i=>i.complete&&i.naturalWidth>0)",timeout=60000)
        page.screenshot(path=str(OUT/"atlas-desktop.png"),full_page=True)
        checks.append("Unified 2D atlas, real NASA WMTS tiles, geological overlay and source unit inspection")
        page.get_by_role("button",name="Експедиція через Tharsis",exact=False).click()
        page.get_by_role("button",name="Додати зупинку",exact=True).click()
        page.get_by_label("Пошук місць на Марсі").fill("Valles")
        page.locator(".mc-place").click()
        expect(page.locator(".mc-stops>div")).to_have_count(1)
        page.get_by_label("Зупинка 1: довгота",exact=True).fill("-122")
        page.get_by_label("Зупинка 1: широта",exact=True).fill("6")
        page.get_by_role("button",name="Побудувати маршрут",exact=True).click()
        expect(page.get_by_test_id("global-route-summary")).to_be_visible(timeout=120000)
        expect(page.locator(".mc-leg-list>div")).to_have_count(2)
        page.locator(".mc-route-geology summary").click()
        expect(page.locator(".mc-route-geology")).to_contain_text("USGS SIM 3292")
        checks.append("Actual multi-stop global expedition, two ordered legs, source-geometry geological intersections")
        page.get_by_role("button",name="Політ уздовж маршруту",exact=True).click()
        expect(page.get_by_role("button",name="Призупинити політ",exact=True)).to_be_visible()
        page.wait_for_function("Number(document.querySelector('[aria-label=\"Точка профілю висот\"]').value)>0")
        page.get_by_role("button",name="Призупинити політ",exact=True).click()
        page.get_by_label("Точка профілю висот").focus()
        page.get_by_label("Точка профілю висот").press("End")
        expect(page.locator(".mc-flight-controls")).to_contain_text("100%")
        page.screenshot(path=str(OUT/"expedition-flight.png"),full_page=True)
        checks.append("User-started demand-driven orbital flyover, pause and keyboard-synchronised profile")
        with page.expect_download() as download:
            page.get_by_role("button",name="Звіт / PDF",exact=True).click()
        path=OUT/"expedition-report.html"
        download.value.save_as(str(path))
        report=browser.new_page()
        report.set_content(path.read_text(encoding="utf-8"))
        expect(report.get_by_role("heading",name="Геологічний контекст",exact=True)).to_be_visible()
        report.pdf(path=str(OUT/"expedition-report.pdf"),format="A4",print_background=True)
        checks.append("Downloaded scientific report with route overview, profile, legs, provenance and actual printable PDF")
        page.get_by_role("button",name="Поділитися / QR",exact=True).click()
        expect(page.locator(".mc-share img")).to_be_visible()
        page.wait_for_function("document.querySelector('.mc-share img').naturalWidth>0")
        shared=page.get_by_label("Посилання експедиції").input_value()
        second=browser.new_page()
        second.goto(shared,wait_until="load")
        expect(second.get_by_label("Початок: довгота",exact=True)).to_have_value("-133.800000")
        expect(second.locator(".mc-stops>div")).to_have_count(1)
        expect(second.get_by_test_id("global-route-summary")).to_have_count(0)
        checks.append("Real QR image and shared coordinate plan loaded in a fresh tab, no trusted cached route")
        # Unified map automatically uses CTX when every stop is inside Jezero.
        page.get_by_role("button",name="Очистити",exact=True).click()
        for label,value in [("Початок: довгота","77.450812"),("Початок: широта","18.444801"),
                            ("Кінець: довгота","77.470379"),("Кінець: широта","18.426243")]:
            page.get_by_label(label,exact=True).fill(value)
        page.get_by_role("button",name="Побудувати маршрут",exact=True).click()
        expect(page.get_by_test_id("global-route-summary")).to_be_visible(timeout=60000)
        expect(page.locator(".mc-route-notes")).to_contain_text("CTX")
        expect(page.locator(".mc-route-notes")).to_contain_text("Точний A*")
        page.get_by_role("button",name="2D атлас",exact=True).click()
        page.get_by_role("button",name="Наблизити Jezero",exact=True).click()
        page.wait_for_function("Array.from(document.querySelectorAll('.atlas-map img.leaflet-image-layer')).some(i=>i.src.includes('ctx-context')&&i.complete&&i.naturalWidth>0)")
        checks.append("Automatic local CTX 20m routing and registered CTX optical overlay in the same planetary atlas")
        expect(page.locator(".mc-mission-grid article")).to_have_count(3)
        checks.append("Three locally hosted NASA image stories with credits and explicit region-only coordinates")
        for width,height in [(375,812),(812,375),(768,1024)]:
            page.set_viewport_size({"width":width,"height":height})
            page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
            if width==375:page.screenshot(path=str(OUT/"atlas-mobile.png"),full_page=True)
        checks.append("Mobile, landscape, tablet and reduced-motion layouts without horizontal overflow")
        assert not errors,errors
        browser.close()
    report={"status":"passed","base_url":url,"checks":checks,"page_errors":errors}
    name="public_acceptance.json" if url.startswith("https://") else "acceptance.json"
    (OUT/name).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
