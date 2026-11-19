from pathlib import Path

import pytest

from detour.drive import simulate_drive
from detour.matching import TrackMatcher, match, reachable_edges
from detour.obs import Obs
from detour.osm import load_osm, parse_maxspeed, way_direction
from detour.world import GridWorld

MINI = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6">
 <node id="1" lat="0.000" lon="0.000"/>
 <node id="2" lat="0.000" lon="0.001"/>
 <node id="3" lat="0.000" lon="0.002"/>
 <node id="4" lat="0.001" lon="0.002"/>
 <node id="5" lat="0.001" lon="0.003"/>
 <node id="6" lat="-0.001" lon="0.000"/>
 <node id="7" lat="0.010" lon="0.010"/>
 <node id="8" lat="0.010" lon="0.011"/>
 <node id="9" lat="0.000" lon="0.003"><tag k="amenity" v="fuel"/></node>
 <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/>
   <tag k="highway" v="residential"/><tag k="maxspeed" v="25 mph"/></way>
 <way id="11"><nd ref="3"/><nd ref="4"/><nd ref="5"/><nd ref="3"/>
   <tag k="highway" v="residential"/><tag k="oneway" v="yes"/></way>
 <way id="12"><nd ref="1"/><nd ref="6"/><tag k="highway" v="footway"/></way>
 <way id="13"><nd ref="7"/><nd ref="8"/><tag k="highway" v="residential"/></way>
</osm>
"""


@pytest.fixture()
def mini(tmp_path):
    p = tmp_path / "mini.osm"
    p.write_text(MINI)
    return load_osm(p, poi_tag=("amenity", "fuel"), poi_name="Gas")


def test_parse_helpers():
    assert parse_maxspeed("40") == 40
    assert abs(parse_maxspeed("25 mph") - 40.2336) < 1e-3
    assert parse_maxspeed("walk") is None
    assert way_direction({"highway": "residential", "oneway": "-1"}) == "backward"
    assert way_direction({"highway": "motorway"}) == "forward"
    assert way_direction({"highway": "motorway", "oneway": "no"}) == "both"


def test_loader_filters_ways_and_islands(mini):
    net, _ = mini
    assert set(net.pos) == {1, 2, 3, 4, 5}  # footway node 6 and island 7-8 are gone


def test_one_way_edges_are_directed(mini):
    net, _ = mini
    assert net.has_edge(3, 4) and not net.has_edge(4, 3)
    assert net.has_edge(1, 2) and net.has_edge(2, 1)


def test_maxspeed_used(mini):
    net, _ = mini
    assert abs(net.speed(1, 2) - 25 * 1.609344 / 3.6) < 1e-6


def test_uturn_only_at_intersections_and_dead_ends(mini):
    net, _ = mini
    assert net.uturn_ok[1]          # dead end
    assert not net.uturn_ok[2]      # mid-street shape node
    assert net.uturn_ok[3]          # junction


def test_real_poi_snapped_to_nearest_road_node(mini):
    net, k = mini
    assert k == 1 and net.pois[0].node == 5 and net.pois[0].name == "Gas"


def test_no_reversal_mid_street_so_cost_includes_detour_to_junction(mini):
    net, _ = mini
    g = net.cost_to_go(1, uturn_penalty=20.0)
    t = lambda a, b: net.length(a, b) / net.speed(a, b)
    cost, has_uturn = g[(1, 2)]  # heading 1->2, target is node 1 right behind us
    assert has_uturn
    assert abs(cost - (t(2, 3) + 20.0 + t(3, 2) + t(2, 1))) < 1e-6  # must go on to junction 3


def test_strongly_connected_after_load(mini):
    net, _ = mini
    first = sorted(net.pos)[0]
    assert set(net.times_to(first)) == set(net.pos)


HELSINKI = Path(__file__).resolve().parent.parent / "data/helsinki/Helsinki.osm.bz2"


@pytest.mark.skipif(not HELSINKI.exists(), reason="sample extract not present")
def test_helsinki_sample_is_a_real_connected_network():
    net, k = load_osm(HELSINKI, poi_tag=("amenity", "cafe"), poi_name="Cafe")
    assert len(net.pos) > 1000 and k >= 50
    assert any(not net.has_edge(b, a) for a in net.out for b in net.out[a])  # has one-ways
    assert set(net.times_to(sorted(net.pos)[0])) == set(net.pos)
    # a simulated drive stays on real edges
    nodes = sorted(net.pos)
    ticks = simulate_drive(net, nodes[0], nodes[len(nodes) // 2])
    assert all(net.has_edge(*t.edge) for t in ticks)


def test_reachable_edges_and_track_matcher_on_grid():
    w = GridWorld(n=12)
    m = match(w, Obs(0, 410.0, 400.0, 90.0, 8.0))  # on row 2, heading east
    assert (m.a, m.b) == ((2, 2), (3, 2))
    reach = reachable_edges(w, m, horizon=300.0)
    assert ((3, 2), (4, 2)) in reach and ((3, 2), (2, 2)) not in reach  # ahead yes, reversal no
    ticks = simulate_drive(w, (1, 1), (10, 8))
    tm = TrackMatcher(w)
    hits = sum((r := tm.update(t)).a == t.edge[0] and r.b == t.edge[1] for t in ticks[::3])
    assert hits / len(ticks[::3]) > 0.95
