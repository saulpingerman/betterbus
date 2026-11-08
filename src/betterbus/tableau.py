"""Read data from a public Tableau Server view the way the browser viewer does.

WMATA's ridership dashboards are embedded from a Tableau Server (exttabanalytics.wmata.com, version
2025.1) that allows anonymous viewing. A view's "Download > Data > Full Data" button returns the
underlying rows of a worksheet with the dashboard's current filters applied. This module opens the
same viewer session the embedded dashboard opens and calls the same server commands:

1. GET  /views/<workbook>/<view>?:embed=y            (sets the load-balancer cookies)
2. POST /vizql/w/<workbook>/v/<view>/startSession/viewing   (returns the session config as JSON)
3. POST <vizql_root>/bootstrapSession/sessions/<id>  (returns the dashboard layout and filters)
4. POST <vizql_root>/sessions/<id>/commands/tabdoc/<command>  (filters and data requests)

The server returns at most 10,000 rows per data request (the `topN` field of the reply), so callers
must split a download with filters until every piece is below that cap; `TableauView.underlying`
raises if a reply is truncated.
"""

import json
import re
import time

import requests

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) betterbus-research-download"


class TableauError(RuntimeError):
    pass


def _parse_length_prefixed(text):
    """Split a bootstrap reply of the form `<len>;<json><len>;<json>...` into parsed objects."""
    parts, i = [], 0
    while i < len(text):
        m = re.match(r"(\d+);", text[i:])
        if not m:
            raise TableauError(f"unexpected bootstrap reply at offset {i}: {text[i : i + 80]!r}")
        start = i + len(m.group(0))
        end = start + int(m.group(1))
        parts.append(json.loads(text[start:end]))
        i = end
    return parts


class TableauView:
    """One anonymous viewer session on one dashboard of a published workbook."""

    def __init__(self, host, workbook, view, delay=0.4, timeout=300):
        self.host = host.rstrip("/")
        self.workbook = workbook
        self.view = view
        self.delay = delay
        self.timeout = timeout
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        self._open()

    # session setup

    def _post(self, url, **kw):
        time.sleep(self.delay)
        r = self.http.post(url, timeout=self.timeout, **kw)
        return r

    def _open(self):
        wb, view = self.workbook, self.view
        embed = f"{self.host}/views/{wb}/{view}?:embed=y&:showVizHome=no"
        self.http.get(embed, timeout=self.timeout).raise_for_status()
        r = self._post(
            f"{self.host}/vizql/w/{wb}/v/{view}/startSession/viewing",
            headers={
                "Accept": "application/json",
                "Tableau-Viz-Location": embed,
                "Tableau-Viz-Path": f"/w/{wb}/v/{view}",
            },
        )
        r.raise_for_status()
        self.config = r.json()
        self.session_id = self.config["sessionid"]
        self.root = self.host + self.config["vizql_root"]
        port = '{"w":1600,"h":1200}'
        form = {
            "worksheetPortSize": port,
            "dashboardPortSize": port,
            "clientDimension": port,
            "renderMapsClientSide": "true",
            "isBrowserRendering": "true",
            "browserRenderingThreshold": "100",
            "formatDataValueLocally": "false",
            "clientNum": "",
            "navType": "Reload",
            "navSrc": "Top",
            "devicePixelRatio": "1",
            "clientRenderPixelLimit": "25000000",
            "allowAutogenWorksheetPhoneLayouts": "true",
            "sheet_id": self.config["sheetId"],
            "showParams": self.config["showParams"],
            "stickySessionKey": self.config["stickySessionKey"],
            "filterTileSize": "200",
            "locale": "en_US",
            "language": "en",
            "verboseMode": "false",
            ":session_feature_flags": "{}",
            "keychain_version": "1",
        }
        r = self._post(f"{self.root}/bootstrapSession/sessions/{self.session_id}", data=form)
        r.raise_for_status()
        first = _parse_length_prefixed(r.text)[0]
        self.dashboard = first["sheetName"]
        zones = first["worldUpdate"]["applicationPresModel"]["workbookPresModel"][
            "dashboardPresModel"
        ]["zones"]
        self.worksheets = sorted({z["worksheet"] for z in zones.values() if z.get("worksheet")})
        self.quick_filters = {}
        for z in zones.values():
            q = z.get("presModelHolder", {}).get("quickFilterDisplay")
            if not q:
                continue
            qf = q["quickFilter"]
            caption = q.get("quickFilterTitle", {}).get("caption")
            self.quick_filters[caption] = {
                "worksheet": z.get("worksheet"),
                "fn": qf.get("fn"),
                "type": qf.get("quickFilterType"),
                "selection": qf.get("selectionSummary"),
                "range": {k: qf.get(k) for k in ("valueMin", "valueMax", "rangeMin", "rangeMax")},
            }

    # commands

    def command(self, name, worksheet, **fields):
        vis = json.dumps({"worksheet": worksheet, "dashboard": self.dashboard})
        fields.setdefault("visualIdPresModel", vis)
        url = f"{self.root}/sessions/{self.session_id}/commands/tabdoc/{name}"
        r = self._post(url, data=fields, headers={"Accept": "application/json"})
        if r.status_code != 200:
            raise TableauError(f"{name} failed with HTTP {r.status_code}: {r.text[:400]}")
        return r.json()

    def _filter_fn(self, caption):
        qf = self.quick_filters[caption]
        return qf["worksheet"], qf["fn"]

    def filter_all(self, caption):
        ws, fn = self._filter_fn(caption)
        self.command(
            "categorical-filter",
            ws,
            globalFieldName=fn,
            membershipTarget="filter",
            filterUpdateType="filter-all",
        )

    def filter_values(self, caption, values):
        """Keep only `values` (display labels, e.g. "July 2018") in a categorical quick filter."""
        ws, fn = self._filter_fn(caption)
        self.command(
            "categorical-filter",
            ws,
            globalFieldName=fn,
            membershipTarget="filter",
            filterUpdateType="filter-replace",
            filterValues=json.dumps(list(values)),
        )

    def filter_range(self, caption, lo, hi, field=None):
        """Set a quantitative (date) quick filter to the inclusive range [lo, hi] (YYYY-MM-DD)."""
        ws = self.quick_filters[caption]["worksheet"]
        fn = field or self.quick_filters[caption]["fn"]
        if fn is None:
            raise TableauError(f"quick filter {caption!r} has no field name; pass field=")
        self.command(
            "range-filter",
            ws,
            globalFieldName=fn,
            rangeMin=lo,
            rangeMax=hi,
            included="include-range",
        )

    def _table(self, reply):
        try:
            d = reply["vqlCmdResponse"]["cmdResultList"][0]["commandReturn"]["dataTablePresModel"]
        except (KeyError, IndexError) as e:
            raise TableauError(f"no data table in reply: {json.dumps(reply)[:400]}") from e
        meta = {c["uniqueName"]: c for c in d["showDataTableColumnPresModels"]}
        table = json.loads(d["showDataTable"])["table"]
        columns = [
            {
                "field": u,
                "caption": meta[u]["fieldCaption"] if u in meta else u,
                "type": meta[u]["dataType"] if u in meta else None,
            }
            for u in table["schema"]
        ]
        return columns, table["tuples"], d.get("topN")

    def underlying(self, worksheet):
        """The "Full Data" rows of `worksheet` under the current filters: (columns, rows).

        Values are the server's unformatted strings; SQL NULL is the string "null".
        Raises TableauError if the reply hit the server's row cap.
        """
        reply = self.command(
            "api-get-worksheet-underlying-logical-table-data",
            worksheet,
            versionName="1.0",
            showDataTableId="single-table-id-sentinel",
            maxRows="0",
            ignoreAliases="false",
            ignoreSelection="true",
            includeAllColumns="true",
        )
        columns, rows, top_n = self._table(reply)
        if top_n and len(rows) >= int(top_n):
            raise TableauError(f"{worksheet}: reply truncated at {top_n} rows; narrow the filters")
        return columns, rows

    def summary(self, worksheet):
        """The "Summary" rows of `worksheet` (the aggregated marks) under the current filters."""
        reply = self.command(
            "api-get-worksheet-summary-logical-table-data",
            worksheet,
            versionName="1.0",
            maxRows="0",
            ignoreAliases="false",
            ignoreSelection="true",
        )
        columns, rows, top_n = self._table(reply)
        if top_n and len(rows) >= int(top_n):
            raise TableauError(f"{worksheet}: summary truncated at {top_n} rows")
        return columns, rows
