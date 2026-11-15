"""Download official discovery metadata and only geology vectors from the USGS ZIP.

HTTP ranges avoid downloading the ~790 MB archive and its raster basemaps.
This stages source data only; it does not replace the application's runtime DEM.
"""
import hashlib
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/atlas"
MAX_BYTES = 120_000_000


class RemoteZip(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos, self.used = url, 0, 0
        with requests.get(url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"},
                          timeout=(20, 90), stream=True) as response:
            if response.status_code != 206:
                raise ValueError("Server does not support ranges; refusing full archive download")
            self.size = int(response.headers["Content-Range"].split("/")[-1])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        if self.pos < 0:
            raise ValueError("Negative file position")
        return self.pos

    def read(self, size=-1):
        size = min(self.size-self.pos, size if size >= 0 else self.size)
        if size <= 0:
            return b""
        if self.used+size > MAX_BYTES:
            raise ValueError("Download budget exceeded")
        with requests.get(self.url, headers={"Range": f"bytes={self.pos}-{self.pos+size-1}",
                                            "Accept-Encoding": "identity"},
                          timeout=(20, 120), stream=True) as response:
            if response.status_code != 206:
                raise ValueError("Range request ignored")
            content = response.raw.read(size+1)
            if len(content) != size:
                raise ValueError("Unexpected range length")
        self.pos += size
        self.used += size
        return content


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []

    def download(url, name):
        path = OUT/name
        if not path.exists():
            with requests.get(url, timeout=(20, 90), stream=True) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_content(65536):
                    content.extend(chunk)
                    if len(content) > 10_000_000:
                        raise ValueError("Metadata download too large")
            path.write_bytes(content)
        content = path.read_bytes()
        manifest.append({"url": url, "path": path.relative_to(ROOT).as_posix(),
                         "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        return content

    base = "https://pubs.usgs.gov/sim/3292/downloads/"
    download(base+"sim3292_readme.txt", "sim3292_readme.txt")
    download(base+"sim3292_metadata.xml", "sim3292_metadata.xml")
    download(base+"sim3292_metadata.txt", "sim3292_metadata.txt")
    config = json.loads(download("https://trek.nasa.gov/tiles/apidoc/config/config.json", "trek_config.json"))["mars"]
    projection = config["projections"]["equirectangular"]
    catalog_url = config["service_endpoints"]["listVisibleLayersUrl"].replace("PROJECTIONTYPE", "eq").replace("PROJECTION", projection)
    catalog = json.loads(download(catalog_url, "mars_trek_layers.json"))
    docs = catalog.get("response", {}).get("docs", [])
    print(f"Mars Trek catalog: {len(docs)} layers")
    # Persist a small readable shortlist, not invented tile endpoints.
    shortlist = [{"title": d.get("title"), "product": d.get("productLabel"),
                  "uuid": d.get("item_UUID"), "services": d.get("services"),
                  "bounding": d.get("bounding")}
                 for d in docs if any(word in str(d.get("title", "")).lower()
                                     for word in ["mola", "themis", "ctx", "geolog", "hirise", "hrsc"])]
    (OUT/"trek_shortlist.json").write_text(json.dumps(shortlist, indent=2), encoding="utf-8")
    services = []
    selected_products = {
        "Mars_MGS_MOLA_ClrShade_merge_global_463m",
        "THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018",
        "THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018",
        "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw",
    }
    for layer in shortlist:
        if layer["product"] not in selected_products:
            continue
        product = layer["product"]
        response = json.loads(download(config["service_endpoints"]["getLayerServiceUrl"]+layer["uuid"],
                                       f"{product}_service.json"))
        for service in response.get("response", {}).get("docs", []):
            endpoint = service.get("endPoint", "")
            if not endpoint:
                continue
            if urlparse(endpoint).hostname != "trek.nasa.gov":
                raise ValueError("Unexpected tile service host")
            url = endpoint.rstrip("/")+"/1.0.0/WMTSCapabilities.xml"
            content = download(url, f"{product}_capabilities.xml")
            tree = ET.fromstring(content)
            ns = {"w": "http://www.opengis.net/wmts/1.0", "o": "http://www.opengis.net/ows/1.1"}
            layers = tree.findall(".//w:Layer", ns)
            resources = [r.attrib for layer_xml in layers for r in layer_xml.findall("w:ResourceURL", ns)]
            services.append({**layer, "endpoint": endpoint, "capabilities_url": url, "resources": resources,
                             "note": "Rendered imagery tiles; not numeric DEM measurements."})
            print(f"Verified WMTS capabilities: {product}")
    (OUT/"verified_tile_services.json").write_text(json.dumps(services, indent=2), encoding="utf-8")
    archive_url = base+"sim3292_database.zip"
    remote = RemoteZip(archive_url)
    with zipfile.ZipFile(remote) as archive:
        entries = archive.infolist()
        selected = [entry for entry in entries
                    if "shapefiles" in entry.filename.lower()
                    and "global_geology" in entry.filename.lower()
                    and Path(entry.filename).suffix.lower() in {".shp", ".shx", ".dbf", ".prj", ".cpg", ".xml", ".sbn", ".sbx"}]
        (OUT/"sim3292_archive_index.json").write_text(json.dumps(
            [{"name": e.filename, "bytes": e.file_size, "compressed_bytes": e.compress_size}
             for e in entries], indent=2), encoding="utf-8")
        if not selected:
            raise ValueError("No expected global geology shapefile found; inspect saved archive index")
        if sum(e.file_size for e in selected) > MAX_BYTES:
            raise ValueError("Selected vectors exceed extraction budget")
        folder = OUT/"geology"
        folder.mkdir(exist_ok=True)
        for entry in selected:
            path = folder/Path(entry.filename).name
            if path.exists() and path.stat().st_size == entry.file_size:
                content = path.read_bytes()
                import zlib
                if zlib.crc32(content) != entry.CRC:
                    raise ValueError(f"Existing source CRC mismatch: {path.name}")
            else:
                content = archive.read(entry)  # zipfile verifies CRC.
                path.write_bytes(content)
            manifest.append({"url": archive_url, "archive_member": entry.filename,
                             "path": path.relative_to(ROOT).as_posix(), "bytes": len(content),
                             "sha256": hashlib.sha256(content).hexdigest()})
            print(f"Geology: {path.name} ({len(content):,} bytes)")
    report = {"source_files": manifest, "trek_layers": len(docs), "verified_tile_services": len(services),
              "archive_size_bytes": remote.size, "archive_bytes_downloaded": remote.used,
              "status": "staged_source_data_not_runtime_integrated"}
    (OUT/"acquisition_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"USGS archive: downloaded {remote.used:,} of {remote.size:,} bytes")


if __name__ == "__main__":
    main()
