"""Rendered design checks: flat atlas, readable controls, contrast and focus."""
import argparse
import json
from pathlib import Path
import re

from playwright.sync_api import sync_playwright, expect

OUT=Path(__file__).resolve().parents[1]/"artifacts/workspace"
SIZES=[(375,812),(768,1024),(812,375),(1440,1000),(1920,1080)]


def luminance(rgb):
    values=[v/255 for v in rgb]
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
    return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))


def contrast(foreground,background):
    def rgb(value):
        numbers=[float(n) for n in re.findall(r"[\d.]+",value)]
        channels=numbers[:3]
        if value.startswith("color(srgb"):
            channels=[v*255 for v in channels]
        if len(numbers)>3:
            # A bright underlying image is the conservative case for dark overlays.
            alpha=numbers[3]
            channels=[v*alpha+255*(1-alpha) for v in channels]
        return channels
    light,dark=sorted([luminance(rgb(foreground)),luminance(rgb(background))],reverse=True)
    return (light+.05)/(dark+.05)


def check_controls(page,selector):
    controls=page.locator(selector).evaluate_all("""elements=>elements
      .filter(e=>e.getClientRects().length&&!e.disabled)
      .map(e=>{
        const s=getComputedStyle(e),r=e.getBoundingClientRect();
        let node=e,bg='';
        while(node){
          const c=getComputedStyle(node).backgroundColor;
          if(c!=='rgba(0, 0, 0, 0)'&&c!=='transparent'){bg=c;break}
          node=node.parentElement;
        }
        return {name:e.getAttribute('aria-label')||e.textContent.trim()||e.id,
          height:r.height,width:r.width,font:parseFloat(s.fontSize),
          color:s.color,background:bg};
      })""")
    for control in controls:
        assert control["height"]>=43.9,control
        assert control["font"]>=12,control
        assert contrast(control["color"],control["background"])>=4.5,control
    return len(controls)


def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    errors=[];checked=0
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1000},reduced_motion="reduce")
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(url)
        expect(page.get_by_test_id("mars-globe")).to_have_attribute("data-ready","true",timeout=60000)
        expect(page.get_by_role("heading",name="Mars atlas",exact=True)).to_be_visible()
        assert page.locator(".mc-planet-facts,.mc-kicker,.mc-intro em,.mc-brand-symbol").count()==0
        expect(page.get_by_role("button",name="Restore plan",exact=True)).to_be_enabled()
        for width,height in SIZES:
            page.set_viewport_size({"width":width,"height":height})
            page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
            assert page.locator(".mc-observatory").bounding_box()["y"]<200
            design=page.locator(".mc-planner").evaluate("""e=>({
              scheme:getComputedStyle(e).colorScheme,
              bg:getComputedStyle(e.parentElement).backgroundColor,
              title:parseFloat(getComputedStyle(document.querySelector('h1')).fontSize),
              endpointShadow:getComputedStyle(document.querySelector('.mc-endpoint')).boxShadow
            })""")
            assert design["scheme"]=="dark",design
            assert design["bg"]=="rgb(32, 35, 38)",design
            assert design["title"]==18,design
            assert design["endpointShadow"]=="none",design
            checked+=check_controls(page,".mc-header button,.mc-planner button,"
                ".mc-planner input,.mc-planner select,.mc-planner summary,.globe-controls button")
            if width in (375,1440):
                page.evaluate("scrollTo(0,0)")
                page.screenshot(path=str(OUT/f"workstation-globe-{width}.png"),full_page=True)
        # Keyboard focus stays visible above the fixed mobile navigation.
        page.set_viewport_size({"width":375,"height":812})
        page.locator(".mc-save button").last.focus()
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Tab")
        focus=page.evaluate("""()=>{
          const e=document.activeElement,r=e.getBoundingClientRect();
          const nav=document.querySelector('.mc-mobile-nav').getBoundingClientRect();
          return {tag:e.tagName,bottom:r.bottom,top:r.top,navTop:nav.top};
        }""")
        assert focus["tag"]=="BUTTON" and focus["top"]>=0 and focus["bottom"]<=focus["navTop"],focus
        page.get_by_role("button",name="2D atlas",exact=True).click()
        expect(page.get_by_test_id("atlas-map")).to_be_visible()
        page.evaluate("scrollTo(0,0)")
        page.screenshot(path=str(OUT/"workstation-atlas-375.png"),full_page=True)
        page.get_by_role("button",name="Jezero map",exact=True).click()
        expect(page.get_by_test_id("mars-map")).to_be_visible(timeout=60000)
        for width,height in SIZES:
            page.set_viewport_size({"width":width,"height":height})
            page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
            assert page.locator(".app .intro h1").evaluate("e=>getComputedStyle(e).fontSize")=="18px"
            assert page.locator(".app .intro em,.app .step").count()==0
            checked+=check_controls(page,".app-header button,.app-header nav a,"
                ".planner button,.planner input,.planner select,.planner summary,.map-view-controls button")
            if width in (375,1440):
                page.evaluate("scrollTo(0,0)")
                page.screenshot(path=str(OUT/f"workstation-jezero-{width}.png"),full_page=True)
        # Expand/collapse keeps the same Leaflet instance and endpoint state.
        host=page.get_by_test_id("mars-map")
        instance=host.element_handle()
        page.get_by_label("Start: longitude",exact=True).fill("77.45")
        page.get_by_label("Start: latitude",exact=True).fill("18.44")
        before=page.get_by_label("Start: longitude",exact=True).input_value()
        page.get_by_role("button",name="Expand map",exact=True).click()
        expect(page.locator("#planner-panel")).to_be_hidden()
        page.get_by_role("button",name="Show planner",exact=True).click()
        expect(page.locator("#planner-panel")).to_be_visible()
        assert host.evaluate("(e,original)=>e===original",instance)
        after=page.get_by_label("Start: longitude",exact=True).input_value()
        assert before==after,(before,after)
        assert not errors,errors
        report={"status":"passed","responsive_sizes":SIZES,"flat_dark_planner":True,
                "compact_title_and_map_first":True,"control_checks":checked,
                "control_text_contrast_minimum":4.5,"control_height_minimum":44,
                "mobile_keyboard_focus_visible":True,"local_map_instance_and_endpoints_retained":True,
                "page_errors":errors}
        (OUT/"workstation-design-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
