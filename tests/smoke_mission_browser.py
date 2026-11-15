"""Real global MOLA routing, comparison, export, persistence, relief and layouts."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parents[1] / "artifacts/global"


def run(url):
    OUT.mkdir(parents=True, exist_ok=True)
    errors, checks = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url, wait_until="load")
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]', timeout=60000)
        expect(page.locator(".mc-system")).to_contain_text("ДАНІ ГОТОВІ", timeout=30000)
        page.screenshot(path=str(OUT/"mission-desktop.png"), full_page=True)
        page.get_by_role("button", name="Топографія", exact=True).click()
        page.get_by_label("Підсилення глобального рельєфу").select_option("10")
        expect(page.locator(".globe-note")).to_contain_text("×10")
        expect(page.locator(".globe-title")).to_contain_text("TOPOGRAPHY")
        checks.append("Real MOLA data, topographic texture and explicit x10 relief")
        page.get_by_role("button", name="Експедиція через Tharsis", exact=False).click()
        page.get_by_role("button", name="Порівняти дві стратегії", exact=True).click()
        expect(page.get_by_test_id("global-route-summary")).to_be_visible(timeout=120000)
        expect(page.locator(".mc-comparison")).to_be_visible(timeout=120000)
        expect(page.get_by_label("Точка профілю висот")).to_be_visible()
        page.get_by_label("Точка профілю висот").focus()
        page.get_by_label("Точка профілю висот").press("End")
        page.locator(".mc-comparison button").nth(1).click()
        page.get_by_role("button", name="Jezero · детально", exact=True).click()
        expect(page.get_by_test_id("mars-map")).to_be_visible(timeout=30000)
        page.get_by_role("button", name="Планета", exact=True).click()
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]', timeout=60000)
        expect(page.get_by_test_id("global-route-summary")).to_be_visible()
        expect(page.locator(".mc-comparison")).to_be_visible()
        page.screenshot(path=str(OUT/"global-route.png"), full_page=True)
        checks.append("Real coarse-to-fine routes, strategy comparison, selectable result, keyboard elevation profile; global session retained after Jezero")
        with page.expect_download() as download:
            page.get_by_role("button", name="Експорт GeoJSON", exact=True).click()
        download.value.save_as(str(OUT/"global-route.geojson"))
        exported = json.loads((OUT/"global-route.geojson").read_text())
        assert exported["geometry"]["type"] == "LineString"
        assert exported["properties"]["approximate"]
        assert "Mars" in exported["properties"]["coordinate_system"]
        page.get_by_role("button", name="Зберегти", exact=True).click()
        expect(page.locator(".mc-planner .mc-feedback")).to_contain_text("збережено")
        original = page.get_by_label("Початок: довгота", exact=True).input_value()
        page.get_by_role("button", name="Очистити", exact=True).click()
        expect(page.get_by_test_id("global-route-summary")).to_have_count(0)
        page.get_by_role("button", name="Відновити план", exact=True).click()
        expect(page.get_by_label("Початок: довгота", exact=True)).to_have_value(original)
        checks.append("Scientific GeoJSON export; explicit save/restore with stale result invalidation")
        page.get_by_label("Пошук місць на Марсі").fill("Hellas")
        expect(page.locator(".mc-place")).to_have_count(1)
        page.locator(".mc-place").click()
        expect(page.get_by_label("Кінець: довгота", exact=True)).to_have_value("70.000000")
        expect(page.locator(".mc-telemetry")).to_contain_text("MOLA128")
        expect(page.locator(".mc-telemetry")).to_contain_text("463 м / клітинка")
        expect(page.locator(".mc-telemetry")).to_contain_text("офіційна інтерполяція")
        page.get_by_label("Пошук місць на Марсі").fill("")
        checks.append("Place search, endpoint selection, camera focus and real elevation sampling")
        # A deliberately late response must not replace a changed plan.
        pending = []
        page.route("**/api/expedition", lambda route: pending.append(route))
        page.get_by_role("button", name="Побудувати маршрут", exact=True).click()
        expect(page.get_by_role("button", name="Скасувати очікування", exact=True)).to_be_visible()
        page.get_by_label("Кінець: довгота", exact=True).fill("71")
        for request in pending:
            request.fulfill(json={"status": "no_route", "expanded_cells": 0})
        page.unroute("**/api/expedition")
        expect(page.get_by_test_id("global-route-summary")).to_have_count(0)
        expect(page.locator(".mc-planner .mc-feedback")).not_to_contain_text("шляху немає")
        checks.append("Late response ignored after coordinate edit")
        for width, height in [(375, 812), (812, 375), (768, 1024)]:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
            expect(page.get_by_role("button", name="Побудувати маршрут", exact=True)).to_be_enabled()
            if width == 375:
                page.screenshot(path=str(OUT/"mission-mobile.png"), full_page=True)
        checks.append("375px mobile, landscape and tablet without horizontal overflow; reduced motion")
        assert not errors, errors
        browser.close()
    report = {"status": "passed", "checks": checks, "page_errors": errors}
    (OUT/"mission_e2e_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    run(parser.parse_args().url)
