"""Orbit design: screenshots, contrast, disclosure, keyboard and responsive QA."""
import argparse
import json
from pathlib import Path
import re

from playwright.sync_api import sync_playwright,expect

OUT=Path(__file__).resolve().parents[1]/"artifacts/design"


def luminance(color):
    values=[float(n)/255 for n in re.findall(r"[\d.]+",color)[:3]]
    assert len(values)==3,color
    channels=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
    return sum(a*b for a,b in zip(channels,[.2126,.7152,.0722]))


def contrast(page,selector):
    colors=page.locator(selector).first.evaluate("""e=>{
      const s=getComputedStyle(e);
      const c=document.createElement('canvas').getContext('2d');
      function rgb(value){
        c.fillStyle=value;c.fillRect(0,0,1,1);
        return 'rgb('+Array.from(c.getImageData(0,0,1,1).data).slice(0,3).join(',')+')'
      }
      let bg=s.backgroundColor,parent=e;
      while((bg==='rgba(0, 0, 0, 0)'||bg==='transparent')&&parent.parentElement){
        parent=parent.parentElement;bg=getComputedStyle(parent).backgroundColor;
      }
      return {fg:rgb(s.color),bg:rgb(bg)}
    }""")
    a,b=sorted([luminance(colors["fg"]),luminance(colors["bg"])])
    ratio=(b+.05)/(a+.05)
    assert ratio>=4.5,(selector,colors,ratio)
    return round(ratio,2)


def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    errors=[];contrasts={}
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100},reduced_motion="reduce")
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(url)
        page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]',timeout=60000)
        expect(page.get_by_role("heading",level=1)).to_contain_text("Наступний горизонт")
        page.keyboard.press("Tab")
        expect(page.locator(".mc-skip")).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator("#mission-plan")).to_be_in_viewport()
        details=page.locator(".mc-data-note")
        assert not details.get_attribute("open")
        details.locator("summary").click()
        expect(details.locator("p")).to_be_visible()
        expect(details.locator("p")).to_contain_text("нерозрізнені каталожні борти")
        details.locator("summary").click()
        for label,value in [("Початок: довгота","-97.150761"),("Початок: широта","24.024217"),
                            ("Кінець: довгота","-97.095"),("Кінець: широта","24.009")]:
            page.get_by_label(label,exact=True).fill(value)
        expect(page.get_by_role("button",name="Побудувати маршрут",exact=True)).to_be_enabled()
        for selector in [".mc-planner>.mc-subtle",".mc-coordinate-fields input",
                         ".mc-planner>.mc-primary",".mc-intro p",".mc-secondary",".mc-system"]:
            contrasts[selector]=contrast(page,selector)
        page.evaluate("document.activeElement?.blur()")
        page.evaluate("scrollTo(0,0)")
        for width,height in [(1440,1100),(1920,1080),(1024,768),(768,1024),(375,812),(812,375)]:
            page.set_viewport_size({"width":width,"height":height})
            page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
            if width in (1440,375,768):
                page.screenshot(path=str(OUT/f"mission-{width}.png"),full_page=True)
                if width==1440:page.screenshot(path=str(OUT/"mission-desktop-first-fold.png"))
            if width==375:
                page.evaluate("scrollTo(0,0)")
                page.screenshot(path=str(OUT/"mission-mobile-first-fold.png"))
                expect(page.get_by_role("navigation",name="Швидка навігація атласом")).to_be_visible()
                assert page.locator(".mc-spinner").count()==0
                page.get_by_role("navigation",name="Швидка навігація атласом").get_by_role("button",name="План",exact=True).click()
                expect(page.locator("#mission-plan")).to_be_in_viewport()
        page.set_viewport_size({"width":1440,"height":1100})
        page.locator(".mc-missions").screenshot(path=str(OUT/"mission-stories.png"))
        page.locator(".mc-discover").screenshot(path=str(OUT/"mission-locations.png"))
        with page.expect_response(lambda r:r.url.endswith("/api/expedition"),timeout=120000):
            page.get_by_role("button",name="Побудувати маршрут",exact=True).click()
        expect(page.get_by_test_id("global-route-summary")).to_be_visible()
        expect(page.get_by_test_id("traversability-notice")).to_be_visible()
        page.locator(".mc-results").scroll_into_view_if_needed()
        page.locator(".mc-results").screenshot(path=str(OUT/"mission-results.png"))
        page.get_by_role("button",name="Jezero · детально",exact=True).click()
        expect(page.get_by_test_id("mars-map")).to_be_visible(timeout=60000)
        page.evaluate("scrollTo(0,0)")
        page.screenshot(path=str(OUT/"jezero-desktop.png"))
        for width,height in [(375,812),(812,375)]:
            page.set_viewport_size({"width":width,"height":height})
            page.wait_for_function("document.documentElement.scrollWidth<=innerWidth")
        page.screenshot(path=str(OUT/"jezero-landscape.png"))
        assert not errors,errors
        result={"status":"passed","viewports":[1440,1920,1024,768,375,812],
                "contrast_ratios":contrasts,"keyboard_skip_link":True,
                "scientific_disclosure":True,"real_route_and_results":True,
                "coordinated_jezero_theme":True,"reduced_motion":True,"page_errors":errors}
        (OUT/"design-report.json").write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
