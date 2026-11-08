"""Decompose the Metrobus ridership change and simulate alternative allocations of the same hours.

Usage (from the repository root):
    uv run scripts/decompose_and_simulate.py [--out-decomp NAME] [--out-alt NAME]

Windows: August 2024 to May 2025 (before) and August 2025 to May 2026 (after), ten months each,
WMATA portal boardings. Family trips changes come from service_v1 (median weekday, May 2025 old
members, October 2025 new members).

Decomposition (ledger: decomposition_v1). Each family's log trips change D splits into D_tr, the
trips of old member routes whose every crosswalk successor is run by another operator, and D_w,
WMATA's own reallocation. With elasticity b and base_f = after_f x exp(-b D), the change in total
boardings equals: transfers sum base_f (exp(b D_tr) - 1), plus WMATA reallocation
sum base_f exp(b D_tr) (exp(b D_w) - 1), plus a common component sum base_f - before_f, plus the
change on routes in no family. b is drawn 1,000 times from N(0.698, 0.083).

Scenarios (ledger: alternatives_v1), each holding weekday scheduled hours fixed:
S1 speed held: each family's trips scale by its scheduled speed before over after.
S2 frequency where it pays: 5% of network weekday hours move from the families with the fewest
predicted riders per added hour to those with the most, using elasticity 0.849 for families with
pre-launch midday headways above 20.7 minutes and 0.385 otherwise (mechanisms_v1); donors lose
at most 30% and recipients gain at most 50% of their hours. S3: S1 then S2.
"""

import argparse
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from betterbus.config import DATA, RAW, REPO
from betterbus.families import stop_events
from betterbus.panel import family_service_detail, route_boardings

BEFORE = ("2024-08-01", "2025-05-01")
AFTER = ("2025-08-01", "2026-05-01")
B_MEAN, B_SE = 0.698, 0.083
B_LOW, B_LOW_SE, B_HIGH, B_HIGH_SE = 0.849, 0.0946, 0.385, 0.1314
HEADWAY_CUT = 20.714
TRANSFERRED = ["B21", "B22", "B24", "C11", "C12", "C13", "C14", "F12", "F13", "Q6", "W14"]
RNG = np.random.default_rng(0)


def windows():
    rb = route_boardings()
    mem = pd.read_csv(DATA / "processed" / "families_v1" / "membership.csv")
    rb = rb.merge(mem, on=["side", "route"], how="left")
    out = {}
    for name, (a, b) in {"before": BEFORE, "after": AFTER}.items():
        w = rb[(rb.month >= a) & (rb.month <= b)]
        out[name] = w.groupby("family").boardings.sum()
        out[f"{name}_total"] = w.boardings.sum()
        out[f"{name}_unmatched"] = w[w.family.isna()].boardings.sum()
        out[f"{name}_transferred_routes"] = w[
            (w.side == "old") & w.route.isin(TRANSFERRED)
        ].boardings.sum()
    return out


def family_table():
    sd = family_service_detail().set_index("family")
    mem = pd.read_csv(DATA / "processed" / "families_v1" / "membership.csv")
    rd = pd.read_parquet(DATA / "processed" / "service_v1" / "route_day.parquet")
    may = rd[(rd.date.dt.strftime("%Y-%m") == "2025-05") & (rd.day_type == "weekday")]
    may = may.groupby("route").trips.median()
    old = mem[mem.side == "old"].assign(trips=lambda d: d.route.map(may))
    sd["trips_transferred"] = old[old.route.isin(TRANSFERRED)].groupby("family").trips.sum()
    sd["trips_transferred"] = sd.trips_transferred.fillna(0)
    return sd


def eea_share():
    """Share of each family's October 2025 weekday stop events inside 2022 Equity Emphasis Areas."""
    ev = stop_events(
        RAW / "gtfs" / "mdb-1846" / "mdb-1846-202510160132.zip", pd.Timestamp("2025-10-22").date()
    )
    import zipfile

    with zipfile.ZipFile(RAW / "gtfs" / "mdb-1846" / "mdb-1846-202510160132.zip") as z:
        st = pd.read_csv(z.open("stops.txt"), dtype={"stop_id": str})
    pts = gpd.GeoDataFrame(
        st, geometry=gpd.points_from_xy(st.stop_lon, st.stop_lat), crs="EPSG:4326"
    )
    eea = gpd.read_file(RAW / "mwcog_eea" / "eea2022_layer0.geojson").to_crs("EPSG:4326")
    inside = set(gpd.sjoin(pts, eea[["geometry"]], predicate="within").stop_id)
    mem = pd.read_csv(DATA / "processed" / "families_v1" / "membership.csv")
    ev = ev.merge(mem[mem.side == "new"], on="route")
    ev["in_eea"] = ev.stop_id.isin(inside)
    g = ev.groupby("family")
    return (g.apply(lambda d: d.n[d.in_eea].sum(), include_groups=False) / g.n.sum()).rename(
        "eea_share"
    )


def decompose(w, ft, draws=1000):
    fams = ft.index.intersection(w["before"].index)
    before = w["before"].reindex(fams).fillna(0)
    after = w["after"].reindex(fams).fillna(0)
    ok = ft.reindex(fams).D_trips.notna()
    T_pre, T_post = ft.trips_pre.reindex(fams), ft.trips_post.reindex(fams)
    T_tr = ft.trips_transferred.reindex(fams).clip(upper=T_pre - 1e-9)
    D = np.log(T_post / T_pre)
    D_tr = np.log((T_pre - T_tr) / T_pre)
    D_w = D - D_tr
    total = w["before_total"]
    res = []
    for b in RNG.normal(B_MEAN, B_SE, draws):
        base = after[ok] * np.exp(-b * D[ok])
        tr = (base * (np.exp(b * D_tr[ok]) - 1)).sum()
        wm = (base * np.exp(b * D_tr[ok]) * (np.exp(b * D_w[ok]) - 1)).sum()
        common = base.sum() - before[ok].sum()
        other = (after[~ok].sum() - before[~ok].sum()) + (
            w["after_unmatched"] - w["before_unmatched"]
        )
        res.append([tr, wm, common, other])
    res = np.array(res) / total * 100
    observed = (w["after_total"] / w["before_total"] - 1) * 100

    def summ(x):
        return {
            "mean": round(float(x.mean()), 2),
            "p05": round(float(np.percentile(x, 5)), 2),
            "p95": round(float(np.percentile(x, 95)), 2),
        }

    return {
        "windows": {"before": BEFORE, "after": AFTER},
        "boardings_before": round(float(w["before_total"])),
        "boardings_after": round(float(w["after_total"])),
        "observed_change_pct": round(float(observed), 2),
        "transferred_routes_boardings_before": round(float(w["before_transferred_routes"])),
        "components_pct_of_before": {
            "routes_handed_to_other_operators": summ(res[:, 0]),
            "wmata_trip_reallocation": summ(res[:, 1]),
            "common_to_all_families": summ(res[:, 2]),
            "families_without_trip_measure_and_unmatched_routes": summ(res[:, 3]),
        },
        "check_sum_mean_pct": round(float(res.mean(axis=0).sum()), 2),
    }


def scenarios(w, ft, eea, draws=1000):
    df = ft.join(w["after"].rename("after"), how="inner").join(eea)
    df = df.dropna(subset=["D_trips", "speed_pre", "speed_post", "revenue_hours_post", "after"])
    df = df[df.after > 0].copy()
    low = df.midday_headway_pre > HEADWAY_CUT
    H = df.revenue_hours_post
    out = {"families": int(len(df)), "weekday_hours": round(float(H.sum()), 1)}
    s1_dlogT = np.log(df.speed_pre / df.speed_post)

    def s2_hours(b_low, b_high):
        b_f = np.where(low, b_low, b_high)
        m = b_f * df.after / H  # predicted riders per added hour, per unit hours change
        order = m.sort_values().index
        budget = 0.05 * H.sum()
        cut = pd.Series(0.0, index=df.index)
        for f in order:
            take = min(0.30 * H[f], budget - cut.sum())
            if take <= 0:
                break
            cut[f] = take
        recip = m.sort_values(ascending=False).index
        add = pd.Series(0.0, index=df.index)
        room = budget
        for f in recip:
            if cut[f] > 0:
                continue
            give = min(0.50 * H[f], room)
            add[f] = give
            room -= give
            if room <= 0:
                break
        return (H - cut + add) / H, cut, add

    results = {"S1": [], "S2": [], "S3": []}
    for _ in range(draws):
        b = RNG.normal(B_MEAN, B_SE)
        bl, bh = RNG.normal(B_LOW, B_LOW_SE), RNG.normal(B_HIGH, B_HIGH_SE)
        b_f = np.where(low, bl, bh)
        s1 = (df.after * (np.exp(b * s1_dlogT) - 1)).sum()
        ratio, _, _ = s2_hours(bl, bh)
        s2 = (df.after * (ratio**b_f - 1)).sum()
        s3 = (df.after * (np.exp(b * s1_dlogT) * ratio**b_f - 1)).sum()
        for k, v in zip(("S1", "S2", "S3"), (s1, s2, s3), strict=True):
            results[k].append(v / df.after.sum() * 100)
    for k, v in results.items():
        v = np.array(v)
        out[k] = {
            "riders_change_pct": round(float(v.mean()), 2),
            "p05": round(float(np.percentile(v, 5)), 2),
            "p95": round(float(np.percentile(v, 95)), 2),
        }
    ratio, cut, add = s2_hours(B_LOW, B_HIGH)
    out["S1_trips_change_pct"] = round(
        float((np.exp(s1_dlogT) * df.trips_post).sum() / df.trips_post.sum() * 100 - 100), 2
    )
    out["S2_donors"] = int((cut > 0).sum())
    out["S2_recipients"] = int((add > 0).sum())
    out["S2_eea_share_donors"] = round(
        float(np.average(df.eea_share[cut > 0].fillna(0), weights=cut[cut > 0])), 3
    )
    out["S2_eea_share_recipients"] = round(
        float(np.average(df.eea_share[add > 0].fillna(0), weights=add[add > 0])), 3
    )
    out["S2_low_frequency_share_of_added_hours"] = round(float(add[low].sum() / add.sum()), 3)
    out["S2_low_frequency_share_of_cut_hours"] = round(float(cut[low].sum() / cut.sum()), 3)
    plan = df.assign(hours_change=add - cut, hours_ratio=ratio)[
        ["hours_change", "hours_ratio", "midday_headway_pre", "eea_share", "after"]
    ]
    return out, plan[plan.hours_change != 0]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out-decomp", default="decomposition_v1")
    p.add_argument("--out-alt", default="alternatives_v1")
    args = p.parse_args(argv)
    w = windows()
    ft = family_table()
    dec = decompose(w, ft)
    eea = eea_share()
    alt, plan = scenarios(w, ft, eea)
    for name, obj in ((args.out_decomp, dec), (args.out_alt, alt)):
        d = REPO / "results" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "summary.json").write_text(json.dumps(obj, indent=1) + "\n")
    plan.round(4).to_csv(REPO / "results" / args.out_alt / "s2_reallocation.csv")
    print(json.dumps(dec, indent=1))
    print(json.dumps(alt, indent=1))


if __name__ == "__main__":
    main()
