"""Keep camera/map state on success, failure and strategy comparison."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

from smoke_point_viewport import state


def run(url):
    mode="ok";calls=0;errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))

        def respond(route):
            nonlocal calls
            calls+=1
            payload=route.request.post_data_json
            checks=[{"id":"a","bounds":[-99.15625,22.03125,-95.15625,26.03125],
                     "spacing_m":463,"max_grade_deg":15,"source":"fixture",
                     "overlay_url":"/api/hazards/mola128/a/slopes?max_grade_deg=15",
                     "interpolated_fraction":0}]
            if mode!="ok":
                result={"status":"no_route","message":"Тестова непрохідна ділянка",
                        "terrain_checks":checks,"expanded_cells":1}
            else:
                a=payload["start"];b=payload["end"]
                result={"status":"ok","dataset":"mola","approximate":True,"elapsed_ms":1,"expanded_cells":2,
                        "terrain_checks":checks,
                        "route":{"type":"Feature","geometry":{"type":"LineString",
                                 "coordinates":[[a["lon"],a["lat"]],[b["lon"],b["lat"]]]},
                                 "properties":{"slope_weight":payload["slope_weight"]}},
                        "metrics":{"distance_m":1000,"direct_distance_m":1000,"ascent_m":0,"descent_m":0,
                                   "min_elevation_m":0,"max_elevation_m":0,"max_grade_deg":0,
                                   "cells":2,"interpolated_cells":0,"snap_offsets_m":[0,0]},
                        "profile":[{"distance_m":0,"elevation_m":0,"interpolated":False},
                                   {"distance_m":1000,"elevation_m":0,"interpolated":False}]}
            route.fulfill(json=result)

        # Isolate viewport behaviour from routing time/data. Real route behaviour
        # is separately covered by smoke_mission_browser.py and backend tests.
        page.route("**/api/expedition",respond)
        page.goto(url)
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]',timeout=60000)
        for label,value in [("Початок: довгота","-133.8"),("Початок: широта","18.65"),
                            ("Кінець: довгота","-112.5"),("Кінець: широта","-7.5")]:
            page.get_by_label(label,exact=True).fill(value)
        for _ in range(20):
            page.get_by_role("button",name="Наблизити планету",exact=True).click()

        for globe in [True,False]:
            if not globe:
                page.get_by_role("button",name="2D атлас",exact=True).click()
                page.get_by_role("button",name="Наблизити Jezero",exact=True).click()
                for z in range(11,14):
                    page.get_by_role("button",name="Zoom in",exact=True).click()
                    expect(page.get_by_test_id("atlas-map")).to_have_attribute("data-zoom",str(z))
            host=page.get_by_test_id("mars-globe" if globe else "atlas-map")
            for kind,compare in [("ok",False),("no_route",False),("ok",True)]:
                mode=kind;before=state(host,globe);previous_calls=calls
                name="Порівняти дві стратегії" if compare else "Побудувати маршрут"
                with page.expect_response(lambda r:r.url.endswith("/api/expedition")):
                    page.get_by_role("button",name=name,exact=True).click()
                expect(page.get_by_role("button",name="Побудувати маршрут",exact=True)).to_be_enabled()
                if kind=="ok":
                    expect(page.get_by_test_id("global-route-summary")).to_be_visible()
                else:
                    expect(page.get_by_role("alert")).to_contain_text("Тестова непрохідна ділянка")
                page.wait_for_timeout(150)
                assert host.is_visible()
                after=state(host,globe)
                assert all(abs(a-b)<1e-9 for a,b in zip(before,after)),(globe,kind,before,after)
                assert calls-previous_calls==(2 if compare else 1)
        assert not errors,errors
        output=Path(__file__).resolve().parents[1]/"artifacts/zoom"
        output.mkdir(parents=True,exist_ok=True)
        report={"status":"passed","checks":["Globe retains zoom/direction on route success, terrain failure and comparison",
                "2D retains zoom 13/centre on route success, terrain failure and comparison",
                "Failed terrain check does not switch globe to 2D"],"page_errors":errors}
        (output/"route-viewport-report.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
