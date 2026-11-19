"""Download a real road network from OpenStreetMap around a point. Run this on YOUR
computer (it needs internet access to the Overpass API), then use the file with run_real.py.

    python3 fetch_osm.py --lat 33.7490 --lon -84.3880 --radius 2500 --out data/atlanta.osm.gz

Finds the lat/lon of any place on openstreetmap.org (right-click the map -> "Show address").
Radius is in meters; 2000-3000 m gives a few thousand road segments, which is plenty.
Alternative with no script: openstreetmap.org -> Export -> manually select an area -> Download.

Map data (c) OpenStreetMap contributors, ODbL. Be polite to the public server: one request.
"""
import argparse
import gzip
import urllib.parse
import urllib.request

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius", type=int, default=2500, help="meters")
    ap.add_argument("--out", default="data/area.osm.gz")
    a = ap.parse_args()

    around = f"(around:{a.radius},{a.lat},{a.lon})"
    query = f"""[out:xml][timeout:120];
(
  way["highway"]{around};
  node["amenity"~"^(cafe|fuel|fast_food)$"]{around};
);
(._;>;);
out;"""
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "detour-research/0.1"})
            with urllib.request.urlopen(req, timeout=180) as r:
                body = r.read()
            with gzip.open(a.out, "wb") as f:
                f.write(body)
            print(f"saved {a.out} ({len(body) / 1e6:.1f} MB uncompressed) from {url}")
            return
        except Exception as e:  # try the next mirror
            last = e
            print(f"{url} failed: {e}")
    raise SystemExit(f"all endpoints failed: {last}")


if __name__ == "__main__":
    main()
