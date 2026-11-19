# Data sources

Map data (c) OpenStreetMap contributors, licensed under the Open Database License (ODbL)
https://www.openstreetmap.org/copyright

| Folder | What | Where it came from |
|---|---|---|
| `west_oakland/` | tiny extract used only as a loader test fixture | `tests/input_data/West-Oakland.osm.bz2` in github.com/gboeing/osmnx |
| `helsinki/` | Helsinki city-centre extract, converted from PBF to OSM XML with `tools/pbf_to_osm.py` | `Helsinki.osm.pbf` bundled in the `pyrosm` Python package |
| `san_francisco/` | central San Francisco snapshot (JOSM export; the file's metadata suggests an old snapshot, around 2010-2011), bz2-compressed | `sfsubset.osm` in github.com/apparentlymart/sf-ped-map |

The San Francisco snapshot is OLD (date inferred from its metadata): road names, one-ways and shops have changed since. Use
`fetch_osm.py` (or an export from openstreetmap.org) to run the benchmark on current data.
