"""Check actual GPU coverage and far-side occlusion, including extreme zoom."""
import argparse
import json
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/zoom"


def run(url):
    OUT.mkdir(parents=True,exist_ok=True)
    subprocess.run(["node","frontend/node_modules/esbuild/bin/esbuild","tests/globe_line_fixture.ts",
                    "--bundle","--format=iife","--outfile=artifacts/zoom/globe-line-fixture.js"],
                   cwd=ROOT,check=True,capture_output=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={"width":800,"height":600})
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.on("console",lambda m:errors.append(m.text) if m.type=="error" else None)
        page.route("**/line-fixture",lambda r:r.fulfill(body="<html><body></body></html>",content_type="text/html"))
        page.goto(url+"/line-fixture")
        page.add_script_tag(content=(OUT/"globe-line-fixture.js").read_text(encoding="utf-8"))
        reports=[]
        for lon,lat in [(-97.15,24.02),(179.999,10),(12,85)]:
            for zoom in [1,20,200,2000,8192]:
                report=page.evaluate("p=>lineFixture.view(...p)",[lon,lat,zoom])
                assert report["tested"]>25,report
                assert report["coverage"]>.98,report
                assert report["backPixels"]==0,report
                reports.append(report)
        page.screenshot(path=str(OUT/"globe-line-gpu.png"))
        assert not errors,errors
        result={"status":"passed","checks":reports,"page_errors":errors}
        (OUT/"globe-line-report.json").write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8003")
    run(parser.parse_args().url)
