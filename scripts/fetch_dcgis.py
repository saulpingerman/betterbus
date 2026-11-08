"""Download DC Open Data bus layers (Metrobus stops and routes, pre- and post-redesign, and bus
priority infrastructure) as GeoJSON in WGS84.

Each entry in LAYERS is an ArcGIS REST layer listed on opendata.dc.gov. For each the script saves
under data/raw/dcgis/:
  <name>.geojson      every feature, all attributes (outSR=4326)
  <name>.layer.json   the REST layer metadata (field list, description, edit dates)
  <name>.item.json    the ArcGIS Online item record behind the DC Open Data page (title,
                      modified date, license, description)

Layers:
  metro_bus_stops            Metro Bus Stops (current, Better Bus era), DCGIS MapServer layer 53
  metro_bus_routes           Metro Bus Routes (current), DCGIS MapServer layer 59
  metro_bus_stops_2023_2025  Metro Bus Stops 2023 - 2025 (archive, retired June 2025)
  metro_bus_routes_2023_2025 Metro Bus Routes 2023 - 2025 (archive, retired 2025-06-29)
  bus_priority_projects      DDOT Bus Priority Projects hub layer (bus_priority_hub_projects)
  bus_lanes                  DDOT existing bus lanes (item snippet: as of Dec 30, 2025)
  transit_signal_priority    DDOT existing transit signal priority locations (Nov 2023)
  priority_corridor_network  WMATA Metrobus Priority Corridor Network, DCGIS layer 153

Usage (from the repository root):
    uv run python scripts/fetch_dcgis.py            # skip layers already saved
    uv run python scripts/fetch_dcgis.py --refresh  # download all again
"""

import argparse
import json

from betterbus.config import RAW
from betterbus.download import arcgis_layer, get_json, record

DCGIS = "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Transportation_Rail_Bus_WebMercator/MapServer"
AGOL = "https://services.arcgis.com/neT9SoYxizqTHZPH/arcgis/rest/services"
LAYERS = {  # name: (REST layer URL, ArcGIS Online item id of the DC Open Data entry)
    "metro_bus_stops": (f"{DCGIS}/53", "e85b5321a5a84ff9af56fd614dab81b3"),
    "metro_bus_routes": (f"{DCGIS}/59", "35738eb6405f4bb0bfdceddb21ac3122"),
    "metro_bus_stops_2023_2025": (
        f"{AGOL}/Metro_Bus_Stops_2023_to_2025/FeatureServer/0",
        "136b8f87668048858b092ff0e1045b46",
    ),
    "metro_bus_routes_2023_2025": (
        f"{AGOL}/Metro_Bus_Lines_2023_to_2025/FeatureServer/0",
        "c2250022d6624a5c8bcfddc3d8292e47",
    ),
    "bus_priority_projects": (
        f"{AGOL}/bus_priority_hub_projects/FeatureServer/85",
        "45bd51349736419498239f5f7505e70e",
    ),
    "bus_lanes": (f"{AGOL}/Bus_Lanes/FeatureServer/0", "d6fda75b60964b36b3363f3a5858d6d5"),
    "transit_signal_priority": (
        f"{AGOL}/Existing_TSP_Nov2023/FeatureServer/0",
        "a05696130c5c4b928619b411f8406838",
    ),
    "priority_corridor_network": (f"{DCGIS}/153", "a95079dd98274e6ea6565364e050d130"),
}
OUT = RAW / "dcgis"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (url, item) in LAYERS.items():
        dest = OUT / f"{name}.geojson"
        if args.refresh:
            dest.unlink(missing_ok=True)
        item_url = f"https://www.arcgis.com/sharing/rest/content/items/{item}"
        item_path = OUT / f"{name}.item.json"
        item_path.write_text(json.dumps(get_json(item_url, params={"f": "json"}), indent=1))
        record(item_path, f"{item_url}?f=json")
        n, meta = arcgis_layer(url, dest)
        print(f"{name}: {n} features, {len(meta.get('fields', []))} fields")


if __name__ == "__main__":
    main()
