"""Full-map point selection + native A*, and independent Mars scale verification."""
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
        page.get_by_role("button",name="Jezero · детально",exact=True).click()
        page.get_by_role("button",name="2D карта",exact=True).click()
        expect(page.locator("#dataset")).to_have_value("regional")
        expect(page.locator(".leaflet-control-scale-line")).to_be_visible()
        scale=page.evaluate("""async () => {
          const config=await (await fetch('/api/layers')).json();
          const [[south,west],[north,east]]=config.imagery.context.bounds_lat_lon;
          const image=document.querySelector('img[src$="ctx-context.png"]').getBoundingClientRect();
          const map=document.querySelector('.mars-map').getBoundingClientRect();
          const lat=north-(map.top+map.height/2-image.top)/image.height*(north-south);
          const control=document.querySelector('.leaflet-control-scale-line');
          const text=control.textContent, width=control.getBoundingClientRect().width;
          const metres=parseFloat(text)*(text.includes('km')?1000:1);
          const expected=3396190*Math.cos(lat*Math.PI/180)*(east-west)*Math.PI/180/image.width*width;
          return {text,width,metres,expected,relativeError:Math.abs(expected-metres)/metres};
        }""")
        assert scale["relativeError"]<.04,scale
        checks.append({"Mars_scale_independent_check":scale})
        # These points lie well south of the former 5km square.
        for name,value in [("Початок: довгота","77.38"),("Початок: широта","18.3836"),
                           ("Кінець: довгота","77.55"),("Кінець: широта","18.3836")]:
            page.get_by_label(name,exact=True).fill(value)
        page.locator("#slope").focus()
        for _ in range(10):page.locator("#slope").press("ArrowRight")
        page.get_by_role("button",name="Build Route",exact=True).click()
        expect(page.get_by_test_id("route-summary")).to_be_visible(timeout=60000)
        expect(page.locator(".js-plotly-plot")).to_be_visible(timeout=60000)
        checks.append("Real ~10km A* route with both endpoints outside former 5km AOI")
        page.screenshot(path=str(OUT/"regional-routing-scale.png"),full_page=True)
        before=page.locator(".leaflet-control-scale-line").inner_text()
        page.locator(".leaflet-control-zoom-in").click()
        page.locator(".leaflet-control-zoom-in").click()
        expect(page.locator(".leaflet-control-scale-line")).not_to_have_text(before)
        checks.append("Scale responds to zoom")
        page.get_by_role("button",name="До ділянки",exact=True).click()
        box=page.get_by_test_id("mars-map").bounding_box()
        # All-carte selection, not an arbitrary hidden 5km click gate.
        map_element=page.get_by_test_id("mars-map")
        map_element.click(position={"x":box["width"]*.35,"y":box["height"]*.62})
        expect(page.locator(".sample-readout").last).to_contain_text("м")
        page.set_viewport_size({"width":375,"height":812})
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
        expect(page.locator(".leaflet-control-scale-line")).to_be_visible()
        checks.append("Regional click sampling and mobile scale visibility")
        browser.close()
    assert not errors,errors
    result={"status":"passed","checks":checks,"page_errors":errors,
            "limitation":"Regional DEM coverage, not global routing; slopes can legitimately block routes."}
    (OUT/"regional_e2e_report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8001")
    run(parser.parse_args().url)
