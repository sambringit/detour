"""Convert an OpenStreetMap .pbf extract to .osm XML (so detour.osm can read it).

    python3 tools/pbf_to_osm.py INPUT.osm.pbf OUTPUT.osm.bz2

Requires `pip install osmium`. Keeps all nodes and only highway ways."""
import sys

import osmium


def main(src: str, dst: str) -> None:
    writer = osmium.SimpleWriter(dst)
    n = w = 0
    try:
        for obj in osmium.FileProcessor(src):
            if obj.is_node():
                writer.add_node(obj)
                n += 1
            elif obj.is_way() and "highway" in obj.tags:
                writer.add_way(obj)
                w += 1
    finally:
        writer.close()
    print(f"wrote {dst}: {n} nodes, {w} highway ways")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
