"""User crater example must never look like a confirmed drivable route."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def run(url):
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100})
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(url)
        for name,value in [
            ("Початок: довгота","-97.150761"),("Початок: широта","24.024217"),
            ("Кінець: довгота","150.624967"),("Кінець: широта","9.070396")]:
            page.get_by_label(name,exact=True).fill(value)
        button=page.get_by_role("button",name="Побудувати маршрут",exact=True)
        expect(button).to_be_enabled(timeout=60000)
        with page.expect_response(lambda r:r.url.endswith("/api/expedition"),timeout=120000) as response:
            button.click()
        result=response.value.json()
        assert result["dataset"]=="mola128"
        assert result["traversability"]["status"]=="unverified"
        notice=page.get_by_test_id("traversability-notice")
        expect(notice).to_contain_text("СХИЛИ ТА БОРТИ: ЧИСЛОВА DEM 463 М")
        expect(notice).to_contain_text("Дно кратера дозволене")
        assert result["terrain_validation"]["entire_route"]
        assert result["hazard_policy"]["records"]>380000
        assert result["metrics"]["max_grade_deg"]<=15
        page.get_by_role("button",name="2D атлас",exact=True).click()
        page.get_by_role("button",name="Показати схили 463 м та контури",exact=True).click()
        expect(notice).to_be_visible()
        page.wait_for_function("Array.from(document.querySelectorAll('.atlas-map img')).some(i=>i.src.includes('/api/hazards/native-slopes?')&&i.complete&&i.naturalWidth>0)")
        page.wait_for_function("Array.from(document.querySelectorAll('.atlas-map img')).some(i=>i.src.includes('/ctx-global/6/')&&i.complete&&i.naturalWidth>0)",timeout=60000)
        output=Path(__file__).resolve().parents[1]/"artifacts/global"
        output.mkdir(parents=True,exist_ok=True)
        page.locator(".atlas-map-shell").screenshot(path=str(output/"crater-aware-start.png"))
        (output/"crater-aware-api.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        with page.expect_download() as download:
            page.get_by_role("button",name="Звіт / PDF",exact=True).click()
        html=Path(download.value.path()).read_text(encoding="utf-8")
        assert "ПРОХІДНІСТЬ НЕ ПІДТВЕРДЖЕНА" in html
        assert "Увесь шлях перевірений на числовій MOLA" in html
        with page.expect_download() as download:
            page.get_by_role("button",name="Експорт GeoJSON",exact=True).click()
        exported=Path(download.value.path()).read_text(encoding="utf-8")
        assert '"unverified"' in exported and '"native_terrain_entire_route": true' in exported
        assert not errors,errors
        print("Passed: exact user coordinates; full native DEM, persistent slope notice, report and GeoJSON provenance; no page errors.")
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
