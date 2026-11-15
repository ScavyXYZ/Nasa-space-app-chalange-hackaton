"""Planner interaction regressions; delayed responses are deliberate UI fixtures."""
import argparse
from playwright.sync_api import sync_playwright, expect


def run(url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url, wait_until="load")
        page.get_by_role("button", name="Jezero · детально", exact=True).click()
        expect(page.locator(".science-card")).to_have_count(4)
        page.get_by_role("button", name="Показати всі 12 областей", exact=True).click()
        expect(page.locator(".science-card")).to_have_count(12)
        page.get_by_role("button", name="Згорнути каталог", exact=True).click()
        expect(page.locator(".science-card")).to_have_count(4)
        expect(page.locator("#weight")).not_to_be_visible()
        page.get_by_text("Додаткові параметри", exact=True).click()
        expect(page.locator("#weight")).to_be_visible()
        page.get_by_text("Додаткові параметри", exact=True).click()
        page.get_by_role("button", name="Завантажити демонстраційні точки").click()
        expect(page.get_by_test_id("mars-map")).to_be_visible()
        a = page.get_by_label("Початок: довгота", exact=True)
        b = page.get_by_label("Кінець: довгота", exact=True)
        original_a, original_b = a.input_value(), b.input_value()
        page.get_by_role("button", name="Поміняти A ↔ B", exact=True).click()
        expect(a).to_have_value(original_b)
        expect(b).to_have_value(original_a)

        page.get_by_role("button", name="Очистити план", exact=True).click()
        pending = []
        page.route("**/api/elevation?**", lambda route: pending.append(route))
        terrain = page.get_by_test_id("mars-map")
        box = terrain.bounding_box()
        terrain.click(position={"x": box["width"] / 2, "y": box["height"] / 2})
        expect(page.locator(".map-interaction")).to_contain_text("Перевіряємо")
        page.get_by_role("button", name="B · Кінець", exact=True).click()
        expect(page.locator(".map-interaction")).not_to_contain_text("Перевіряємо")
        assert pending, "Measurement request was not intercepted"
        pending.pop().fulfill(json={"valid": True, "elevation_m": -2500, "slope_deg": 2})
        # A server round trip lets the queued stale response settle without sleeping.
        page.request.get(f"{url}/api/health")
        expect(a).to_have_value("")
        expect(b).to_have_value("")
        expect(page.get_by_role("button", name="B · Кінець", exact=True)).to_have_attribute("aria-pressed", "true")
        page.unroute("**/api/elevation?**")

        page.get_by_role("button", name="Завантажити демонстраційні точки").click()
        pending_routes = []
        page.route("**/api/route", lambda route: pending_routes.append(route))
        page.get_by_role("button", name="Build Route", exact=True).click()
        page.get_by_role("button", name="Карта на всю ширину", exact=True).click()
        page.get_by_role("button", name="Скасувати очікування", exact=True).click()
        expect(page.locator(".map-search-status")).to_have_count(0)
        expect(page.get_by_test_id("route-summary")).to_have_count(0)
        for route in pending_routes:
            route.fulfill(json={"status": "no_route"})
        page.unroute("**/api/route")
        page.route("**/api/route", lambda route: route.fulfill(json={"status": "outside_grid"}))
        page.get_by_role("button", name="Показати планування", exact=True).click()
        expect(page.get_by_role("button", name="Build Route", exact=True)).to_be_enabled()
        page.get_by_role("button", name="Build Route", exact=True).click()
        expect(page.locator(".map-interaction")).to_contain_text("поза вибраною сіткою")
        page.get_by_role("button", name="Карта на всю ширину", exact=True).click()
        expect(page.locator(".map-interaction").get_by_role("alert")).to_be_visible()
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
        expect(page.get_by_role("button", name="A · Початок", exact=True)).to_be_visible()
        assert not errors, errors
        browser.close()
    print("Passed: progressive disclosure, swap A/B, demo transition, stale measurement, cancel wait, map-only errors, mobile")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    run(parser.parse_args().url)
