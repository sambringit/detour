#!/usr/bin/env bash
# Rebuild every number and chart in the README (about 5 minutes on 2 CPU cores).
set -euo pipefail
pip install -e ".[dev]" -q
pytest -q
python3 run_sim.py                    # fig0: the problem on a toy drive
python3 run_benchmark.py              # synthetic grid benchmark   -> results/benchmark.json
python3 run_sweeps.py                 # noise / density / penalty / hysteresis sweeps (~3 min)
python3 make_figures.py               # fig1-fig4
SF=data/san_francisco/sfsubset.osm.bz2
HEL=data/helsinki/Helsinki.osm.bz2
for ns in "3 5" "8 10" "15 20"; do set -- $ns
  python3 run_real.py --osm $HEL --pos-sigma $1 --head-sigma $2 --out results/real_p$1.json
done
python3 run_real.py --osm $SF --tag "name=~Starbucks" --name Starbucks --min-dist 1500 --configs all --drives 30 --out results/real_sf_starbucks_p8.json
python3 run_real.py --osm $SF --tag "name=~Starbucks" --name Starbucks --min-dist 1500 --configs all --drives 30 --pos-sigma 15 --head-sigma 20 --out results/real_sf_starbucks_p15.json
python3 run_real.py --osm $SF --tag "amenity=fuel" --name "Gas station" --min-dist 1500 --configs all --drives 30 --out results/real_sf_fuel_p8.json
python3 run_real.py --osm $SF --tag "amenity=cafe" --name Cafe --min-dist 1500 --configs sparse --drives 30 --out results/real_sf_cafe_p8.json
python3 analysis_road_class.py --osm $SF --tag "name=~Starbucks" --name Starbucks
python3 make_real_figures.py          # fig5, fig6
python3 make_summary_figure.py        # fig7
