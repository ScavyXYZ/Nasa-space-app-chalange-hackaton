"""Real imagery at both reported endpoints, not a generic demo location."""
import argparse
import base64
import json
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright

OUT=Path(__file__).resolve().parents[1]/"artifacts/zoom"


def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    errors=[]
    points=[{"lon":-97.150761,"lat":24.024217},{"lon":150.624967,"lat":9.070396}]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1100})
        page.on("pageerror",lambda e:errors.append(str(e)))
        reports=[]
        for i,point in enumerate(points):
            plan={"start":point,"end":points[1-i],"stops":[],"weight":5,"grade":15,"resolution":"auto"}
            encoded=quote(base64.b64encode(quote(json.dumps(plan),safe="").encode()).decode(),safe="")
            page.goto(url+"/#mission="+encoded)
            if i:page.reload()  # A hash-only navigation does not remount React.
            page.wait_for_selector('[data-testid="mars-globe"][data-ready="true"]')
            for _ in range(12):
                page.get_by_role("button",name="Наблизити планету",exact=True).click()
            page.wait_for_function("""()=>{
              const d=document.querySelector('[data-testid="mars-globe"]').dataset;
              return Number(d.detailZoom)>=8&&Number(d.detailTotal)>0
                &&Number(d.detailReady)+Number(d.detailFallback)===Number(d.detailTotal)
            }""",timeout=120000)
            page.locator(".globe-shell").screenshot(path=str(OUT/f"user-region-{i+1}.png"))
            reports.append({"point":point,"status":page.locator(".globe-detail-status").inner_text()})
        assert not errors,errors
        (OUT/"user-region-report.json").write_text(json.dumps({"cases":reports,"errors":errors},indent=2),encoding="utf-8")
        print(json.dumps(reports,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
