"""Create a temporary, explicitly requested public demo with an official quick tunnel.

Windows only. Downloads a SHA-256-verified official cloudflared release to the
approved OpenCode temp folder; does not install a Windows service or open ports.
The tunnel is temporary; keep this process and the local backend running.
"""
import argparse
import hashlib
import json
import os
import queue
import re
import subprocess
import threading
from pathlib import Path

import qrcode
import requests

ROOT=Path(__file__).resolve().parents[1]
RELEASE="2026.11.0"
SHA256="d5c1d82031da6253dcdcff64c944cd0fe063016edeb2e4fd088075fc9bd52d0a"


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8003)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:
        parser.error("Port must be 1024..65535")
    requests.get(f"http://127.0.0.1:{args.port}/api/atlas",timeout=15).raise_for_status()
    folder=Path(os.environ["LOCALAPPDATA"])/"Temp/opencode"
    folder.mkdir(parents=True,exist_ok=True)
    binary=folder/f"cloudflared-{RELEASE}.exe"
    url=f"https://github.com/cloudflare/cloudflared/releases/download/{RELEASE}/cloudflared-windows-amd64.exe"
    if not binary.exists():
        with requests.get(url,stream=True,timeout=(20,120)) as response:
            response.raise_for_status()
            content=bytearray()
            for chunk in response.iter_content(1024*1024):
                content.extend(chunk)
                if len(content)>70_000_000:
                    raise ValueError("Binary exceeds download budget")
        if hashlib.sha256(content).hexdigest()!=SHA256:
            raise ValueError("Official binary checksum mismatch")
        binary.write_bytes(content)
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=SHA256:
        raise ValueError("Cached binary checksum mismatch")
    out=ROOT/"artifacts/release"
    out.mkdir(parents=True,exist_ok=True)
    process=subprocess.Popen([str(binary),"tunnel","--url",f"http://127.0.0.1:{args.port}",
                              "--protocol","http2","--no-autoupdate"],stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace")
    ready=queue.Queue()
    def capture():
        with (out/"tunnel.log").open("w",encoding="utf-8") as log:
            for line in process.stdout:
                log.write(line);log.flush()
                match=re.search(r"https://[a-z0-9-]+\.trycloudflare\.com",line)
                if match:
                    ready.put(match.group())
    threading.Thread(target=capture,daemon=True).start()
    try:
        public=ready.get(timeout=90)
        qrcode.make(public,box_size=12,border=4).save(out/"demo-qr.png")
        data={"url":public,"local_port":args.port,"tunnel_pid":process.pid,
              "temporary":True,"notice":"Keep backend, tunnel, computer and internet running. URL changes on restart.",
              "cloudflared_release":RELEASE,"binary_sha256":SHA256}
        (out/"public_demo.json").write_text(json.dumps(data,indent=2),encoding="utf-8")
        print(json.dumps(data,indent=2),flush=True)
        print("QR: artifacts/release/demo-qr.png",flush=True)
        process.wait()
    except (KeyboardInterrupt,queue.Empty):
        process.terminate()
        raise


if __name__=="__main__":
    main()
