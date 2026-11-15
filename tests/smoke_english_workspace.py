"""Current compact English UI: no relief, onboarding, promos or disclaimer copy."""
import argparse
import base64
import json
from pathlib import Path
import re

from playwright.sync_api import sync_playwright, expect

OUT=Path(__file__).resolve().parents[1]/"artifacts/workspace"
CYRILLIC=re.compile(r"[\u0400-\u04ff]")
REMOVED=(".mc-missions,.mc-discover,.mc-jezero,.mc-demo,.mc-traversability,"
         ".mc-data-note,.research-warning,.map-hint,.atlas-snap-note,"
         ".atlas-rim-legend,.globe-destination,[data-testid=terrain-3d]")


def clean_ui(page):
    text=page.locator("body").inner_text()
    assert not CYRILLIC.search(text),text
    attrs=page.locator("[aria-label],[title],[placeholder]").evaluate_all(
        "es=>es.flatMap(e=>['aria-label','title','placeholder'].map(a=>e.getAttribute(a)||'')).join('\\n')")
    assert not CYRILLIC.search(attrs),attrs
    assert page.locator(REMOVED).count()==0
    assert not re.search(r"not (?:confirmed|verified)|traversability|getting started|"
                         r"Tharsis|demo points|3D (?:terrain|view)|exaggeration|safety assessment",
                         text,re.IGNORECASE),text


def view(host,globe=True):
    return tuple(float(host.get_attribute(k)) for k in
                 ["data-view-lon","data-view-lat","data-camera-zoom" if globe else "data-zoom"])


def same_view(before,host,globe=True):
    after=view(host,globe)
    assert all(abs(a-b)<1e-9 for a,b in zip(before,after)),(before,after)


def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    errors=[];relief_requests=[];mode="real"
    plan={"start":{"lon":-97.150761,"lat":24.024217},
          "end":{"lon":-97.095,"lat":24.009},"stops":[],"weight":5,"grade":15,"resolution":"auto"}
    encoded=base64.b64encode(json.dumps(plan).encode()).decode()
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.on("request",lambda r:relief_requests.append(r.url)
                if "/api/global/surface?" in r.url or "/api/mesh" in r.url else None)
        page.on("console",lambda m:errors.append(m.text) if m.type=="error"
                and "THREE.WebGLProgram" in m.text else None)

        def respond(request):
            if mode=="no_route":
                request.fulfill(json={"status":"no_route","expanded_cells":0,
                    "message":"Прохідність не підтверджена. Числова MOLA."})
            elif mode=="error":
                request.fulfill(status=503,json={"detail":{"code":"terrain_data_unavailable",
                    "message":"Числова MOLA недоступна."}})
            else:
                request.continue_()

        page.route("**/api/expedition",respond)
        page.goto(url+"/#mission="+encoded)
        assert page.locator("html").get_attribute("lang")=="en"
        globe=page.get_by_test_id("mars-globe")
        expect(globe).to_have_attribute("data-ready","true",timeout=60000)
        expect(globe).to_have_attribute("data-surface-mode","imagery")
        expect(page.get_by_label("Start: longitude",exact=True)).to_have_value("-97.150761")
        expect(page.get_by_role("button",name="Build route",exact=True)).to_be_enabled()
        clean_ui(page)
        page.screenshot(path=str(OUT/"english-desktop.png"),full_page=True)

        for _ in range(14):
            page.get_by_role("button",name="Zoom in on Mars",exact=True).click()
        expect(globe).to_have_attribute("data-texture-source","ctx-global",timeout=120000)
        before=view(globe)
        with page.expect_response(lambda r:r.url.endswith("/api/expedition"),timeout=120000) as response:
            page.get_by_role("button",name="Build route",exact=True).click()
        result=response.value.json()
        assert result["status"]=="ok",result
        expect(page.get_by_test_id("global-route-summary")).to_be_visible()
        same_view(before,globe)
        clean_ui(page)
        with page.expect_download() as download:
            page.get_by_role("button",name="Export GeoJSON",exact=True).click()
        exported=json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        assert exported["geometry"]==result["route"]["geometry"]
        assert exported["properties"]["metrics"]==result["metrics"]
        assert not CYRILLIC.search(json.dumps(exported,ensure_ascii=False))
        assert "traversability" not in exported["properties"]

        with page.expect_download() as download:
            page.get_by_role("button",name="Report / PDF",exact=True).click()
        report_path=OUT/"english-route-report.html"
        download.value.save_as(str(report_path))
        report=report_path.read_text(encoding="utf-8")
        assert 'lang="en"' in report
        assert not CYRILLIC.search(report)
        assert not re.search(r"unverified|not confirmed|traversability|safety assessment",report,re.IGNORECASE)
        report_page=browser.new_page()
        report_page.goto(report_path.as_uri())
        expect(report_page.get_by_role("heading",name="Route report",exact=True)).to_be_visible()
        report_page.pdf(path=str(OUT/"english-route-report.pdf"),format="A4")
        report_page.close()
        before=view(globe)
        page.get_by_role("button",name="Compare strategies",exact=True).click()
        expect(page.locator(".mc-comparison")).to_be_visible(timeout=120000)
        same_view(before,globe)
        page.get_by_role("button",name="Share / QR",exact=True).click()
        expect(page.get_by_label("Route link",exact=True)).to_be_visible()
        expect(page.get_by_alt_text("Route QR code")).to_be_visible()
        clean_ui(page)

        mode="no_route"
        page.get_by_role("button",name="Build route",exact=True).click()
        expect(page.get_by_role("alert")).to_have_text("No route meets the selected constraints.")
        expect(page.get_by_test_id("global-route-summary")).to_have_count(0)
        expect(page.get_by_role("button",name="Export GeoJSON",exact=True)).to_have_count(0)
        same_view(before,globe);clean_ui(page)
        mode="error"
        page.get_by_role("button",name="Build route",exact=True).click()
        expect(page.get_by_role("alert")).to_have_text("Terrain data unavailable.")
        same_view(before,globe);clean_ui(page)
        mode="real"

        page.get_by_role("button",name="2D atlas",exact=True).click()
        atlas=page.get_by_test_id("atlas-map")
        expect(atlas).to_be_visible()
        page.get_by_role("button",name="Jezero",exact=True).click()
        expect(atlas).to_have_attribute("data-zoom","10")
        before=view(atlas,False)
        box=atlas.bounding_box()
        with page.expect_response(lambda r:"/api/atlas/inspect?" in r.url):
            atlas.click(position={"x":box["width"]*.5,"y":box["height"]*.5})
        same_view(before,atlas,False);clean_ui(page)
        for width,height in [(375,812),(768,1024),(812,375),(1920,1080)]:
            page.set_viewport_size({"width":width,"height":height})
            page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
            clean_ui(page)
            if width==375:
                page.screenshot(path=str(OUT/"english-mobile.png"),full_page=True)

        page.set_viewport_size({"width":1440,"height":1100})
        page.get_by_role("button",name="Jezero map",exact=True).click()
        expect(page.get_by_test_id("mars-map")).to_be_visible(timeout=60000)
        clean_ui(page)
        for label,value in [("Start: longitude","77.450812"),("Start: latitude","18.444801"),
                            ("End: longitude","77.470379"),("End: latitude","18.426243")]:
            page.get_by_label(label,exact=True).fill(value)
        with page.expect_response(lambda r:r.url.endswith("/api/route"),timeout=60000) as response:
            page.get_by_role("button",name="Build route",exact=True).click()
        local=response.value.json()
        assert local["status"]=="ok",local
        expect(page.get_by_test_id("route-summary")).to_be_visible()
        expect(page.get_by_test_id("elevation-chart")).to_be_visible()
        expect(page.locator('[data-testid="elevation-chart"] .main-svg').first).to_be_visible(timeout=60000)
        clean_ui(page)
        page.screenshot(path=str(OUT/"english-jezero.png"),full_page=True)
        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
        clean_ui(page)
        page.get_by_role("button",name="Planet",exact=True).click()
        expect(page.get_by_test_id("mars-globe")).to_have_attribute("data-ready","true",timeout=60000)
        clean_ui(page)
        assert not relief_requests,relief_requests
        assert not errors,errors
        output={"status":"passed","language":"en","removed_promos_and_hints":True,
                "removed_disclaimer_copy_in_ui_and_report":True,"relief_requests":0,
                "automatic_ctx_imagery_retained":True,"real_global_and_local_routes":True,
                "geojson_geometry_and_metrics_unchanged":True,"report_and_pdf":True,
                "camera_retained_on_results_comparison_and_failures":True,
                "responsive_widths":[375,768,812,1440,1920],"page_errors":errors}
        (OUT/"english-workspace-report.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
        print(json.dumps(output,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
