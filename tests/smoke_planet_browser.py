"""Continuous 3D: local overview, automatic close-up photos and retained relief."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from smoke_point_viewport import state

OUT = Path(__file__).resolve().parents[1]/"artifacts/planet"


def run(url):
    OUT.mkdir(parents=True, exist_ok=True)
    errors, remote, surface_requests = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width":1440, "height":1100}, reduced_motion="reduce")
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error"
                and "THREE.WebGLProgram" in m.text else None)
        page.on("request", lambda r: remote.append(r.url) if "/api/atlas/tiles/" in r.url else None)
        page.on("request", lambda r: surface_requests.append(r.url) if "/api/global/surface?" in r.url else None)
        page.goto(url)
        globe = page.get_by_test_id("mars-globe")
        expect(globe).to_have_attribute("data-surface-source", "mola128", timeout=60000)
        expect(globe).to_have_attribute("data-surface-loading", "false", timeout=30000)
        page.wait_for_function("""()=>{
          const d=document.querySelector('[data-testid="mars-globe"]').dataset;
          return Number(d.detailReady)>0&&d.detailSource.includes('локальна')
        }""", timeout=30000)
        original_vertices = int(globe.get_attribute("data-surface-vertices"))
        assert not remote, remote
        expect(page.get_by_role("button",name="Автознімки HD",exact=True)).to_have_attribute("aria-pressed","true")
        page.locator(".globe-shell").screenshot(path=str(OUT/"planet-overview.png"))
        # A real volcano, not a one-crater geometry fixture.
        page.get_by_label("Пошук місць на Марсі").fill("Olympus")
        page.locator(".mc-place").click()
        page.get_by_role("button", name="Топографія", exact=True).click()
        page.get_by_label("Підсилення глобального рельєфу").select_option("10")
        for _ in range(6):
            page.get_by_role("button", name="Наблизити планету", exact=True).click()
        page.wait_for_function("""()=>{
          const d=document.querySelector('[data-testid="mars-globe"]').dataset;
          return Number(d.surfaceLevel)>=2&&d.surfaceLoading==='false'
        }""", timeout=60000)
        page.locator(".globe-shell").screenshot(path=str(OUT/"olympus-massif.png"))
        for _ in range(6):
            page.get_by_role("button", name="Наблизити планету", exact=True).click()
        page.wait_for_function("""()=>{
          const d=document.querySelector('[data-testid="mars-globe"]').dataset;
          return Number(d.surfaceLevel)>=4&&d.surfaceLoading==='false'
        }""", timeout=60000)
        before = state(globe, True)
        page.locator(".globe-shell").screenshot(path=str(OUT/"olympus-3d.png"))
        page.get_by_role("button", name="Ракурс 3D", exact=True).click()
        assert state(globe, True) == before
        page.get_by_role("button", name="Ракурс 3D", exact=True).click()
        assert state(globe, True) == before
        for _ in range(12):
            page.get_by_role("button", name="Наблизити планету", exact=True).click()
        expect(globe).to_have_attribute("data-surface-level", "8", timeout=60000)
        expect(globe).to_have_attribute("data-surface-loading", "false", timeout=30000)
        vertices = int(globe.get_attribute("data-surface-vertices"))
        assert original_vertices < vertices < 220000
        before = state(globe, True)
        box = globe.bounding_box()
        globe.click(position={"x":box["width"]*.5, "y":box["height"]*.5})
        expect(page.get_by_label("Кінець: довгота", exact=True)).not_to_have_value("")
        assert state(globe, True) == before
        # A failed numeric update must keep the last complete native geometry.
        page.route("**/api/global/surface?**", lambda r:r.fulfill(status=503,
                   json={"detail":{"message":"Controlled unavailable numerical detail"}}))
        # A new uncached centre, not a zoom-out that legitimately reuses a
        # previously cached whole-planet mesh before encountering the failure.
        page.get_by_role("button", name="Обернути Марс праворуч", exact=True).click()
        expect(globe).to_have_attribute("data-surface-offline", "true", timeout=30000)
        expect(globe).to_have_attribute("data-surface-source", "mola128")
        assert int(globe.get_attribute("data-surface-vertices")) == vertices
        page.unroute("**/api/global/surface?**")
        for width, height in [(375,812), (812,375), (768,1024)]:
            page.set_viewport_size({"width":width, "height":height})
            page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
            expect(page.get_by_role("button", name="Ракурс 3D", exact=True)).to_be_visible()
            if width == 375:
                page.locator(".globe-shell").screenshot(path=str(OUT/"planet-mobile.png"))
        # Satellite mode automatically displays optical photos at this zoom.
        # The auto-imagery button was never clicked.
        page.get_by_role("button", name="Супутник", exact=True).click()
        expect(globe).to_have_attribute("data-texture-source","ctx-global",timeout=120000)
        page.locator(".globe-shell").screenshot(path=str(OUT/"olympus-photo.png"))
        assert remote
        assert not errors, errors
        report = {"status":"passed", "initial_vertices":original_vertices, "native_detail_vertices":vertices,
                  "max_mesh_vertices":220000, "surface_requests":len(surface_requests),
                  "far_overview_remote_imagery_requests":0, "connected_native_lod":True,
                  "oblique_keeps_navigation_camera":True, "picking_preserves_zoom":True,
                  "numeric_failure_retains_mesh":True, "automatic_close_up_photography":True,
                  "mobile_tablet_landscape_no_overflow":True, "page_errors":errors}
        (OUT/"planet-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        browser.close()


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8004")
    run(parser.parse_args().url)
