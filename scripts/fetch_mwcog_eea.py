"""Download MWCOG/TPB Equity Emphasis Areas (EEAs), 2022 and 2018 vintages, as GeoJSON.

EEAs are census tracts in the TPB planning area with above-average concentrations of low-income,
Black, Hispanic or Latino, or Asian residents. Two vintages are served from the Regional
Transportation Data Clearinghouse ArcGIS server (gis.mwcog.org):

  2022 vintage (2016-2020 ACS, updated July 2022): TPB/EEA_RTDC/MapServer
      layer 0: EEA tracts only;  layer 1: all TPB tracts with inputs and EEA flags
  2018 vintage (2012-2016 ACS, superseded):        CLRP/EEA_RTDC/MapServer
      layer 0: EEA tracts only;  layer 1: all tracts with inputs and EEA flags

Each layer is saved as data/raw/mwcog_eea/eea<year>_layer<n>.geojson (WGS84) with its REST
metadata in a matching .layer.json, plus the ArcGIS Online item records (description, license
text) in item_<id>.json.

Usage (from the repository root):
    uv run python scripts/fetch_mwcog_eea.py
"""

import json

from betterbus.config import RAW
from betterbus.download import arcgis_layer, get_json, record

SERVER = "https://gis.mwcog.org/wa/rest/services"
VINTAGES = {
    2022: ("TPB/EEA_RTDC/MapServer", "9facba0938e94a32a7da6b9ea1927a47"),
    2018: ("CLRP/EEA_RTDC/MapServer", "f20c49e98d6d495897eb519a005719bd"),
}
OUT = RAW / "mwcog_eea"


def main():
    for year, (service, item) in VINTAGES.items():
        url = f"https://www.arcgis.com/sharing/rest/content/items/{item}"
        dest = OUT / f"item_{item}.json"
        OUT.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(get_json(url, params={"f": "json"}), indent=1))
        record(dest, f"{url}?f=json")
        for layer in (0, 1):
            n, meta = arcgis_layer(
                f"{SERVER}/{service}/{layer}", OUT / f"eea{year}_layer{layer}.geojson"
            )
            print(f"{year} layer {layer} ({meta['name']}): {n} features")


if __name__ == "__main__":
    main()
