"""Route families: groups of pre-redesign and post-redesign routes that serve the same stops.

WMATA kept stop IDs across the June 2025 redesign (about 95% of shared IDs stay within 20 m), so
old and new routes can be linked through the stops they serve. For a reference weekday in each
network, each route's stop events (trips calling at each stop) are counted. For an old route r
and a new route s, share_old(r, s) is the fraction of r's stop events at stops that s also
serves; share_new(r, s) is the same fraction from s's side. Each old route is linked to its
best-matching new route, and each new route to its best-matching old route; families are the
connected components of those links. Old routes that share no stop with any new route form
their own family and are flagged (candidates for discontinued or transferred service).

containment(f) is the share of the family's pre-launch stop events at stops that are still
served after launch by routes in the same family; a low value means the family's riders were
moved to routes in other families.
"""

import zipfile
from collections import defaultdict

import pandas as pd

from betterbus.service import Feed


def stop_events(feed_path, day):
    """Weekday stop events: route, stop_id, n (trips calling there on `day`)."""
    feed = Feed(feed_path)
    services = feed.services_on(day)
    with zipfile.ZipFile(feed_path) as z:
        st = pd.read_csv(z.open("stop_times.txt"), dtype=str, usecols=["trip_id", "stop_id"])
    trips = feed.trips[feed.trips.service_id.isin(services)][["trip_id", "route"]]
    events = st.merge(trips, on="trip_id").groupby(["route", "stop_id"]).size()
    return events.rename("n").reset_index()


def pair_shares(pre, post):
    """Overlap of every (old route, new route) pair sharing at least one stop."""
    tot_o = pre.groupby("route").n.sum()
    tot_n = post.groupby("route").n.sum()
    j = pre.merge(post, on="stop_id", suffixes=("_old", "_new"))
    pair = (
        j.groupby(["route_old", "route_new"])
        .agg(
            events_old=("n_old", "sum"),
            events_new=("n_new", "sum"),
            shared_stops=("stop_id", "size"),
        )
        .reset_index()
    )
    pair["share_old"] = pair.events_old / pair.route_old.map(tot_o)
    pair["share_new"] = pair.events_new / pair.route_new.map(tot_n)
    return pair


def build_families(pre, post):
    """Return (membership, pairs): membership has family, side ('old'/'new'), route, flags."""
    pair = pair_shares(pre, post)
    best_old = pair.loc[pair.groupby("route_old").share_old.idxmax()]
    best_new = pair.loc[pair.groupby("route_new").share_new.idxmax()]
    pair["best_for_old"] = pair.index.isin(best_old.index)
    pair["best_for_new"] = pair.index.isin(best_new.index)

    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    old_routes, new_routes = sorted(pre.route.unique()), sorted(post.route.unique())
    for r in old_routes:
        find(("old", r))
    for r in new_routes:
        find(("new", r))
    for x in pd.concat([best_old, best_new]).itertuples():
        parent[find(("old", x.route_old))] = find(("new", x.route_new))

    groups = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)
    # stable family ids: sorted by the family's largest new route name, then old routes
    ordered = sorted(groups.values(), key=lambda g: sorted(f"{s}:{r}" for s, r in g))
    rows = []
    for i, members in enumerate(ordered, start=1):
        for side, route in sorted(members):
            rows.append({"family": f"F{i:03d}", "side": side, "route": route})
    mem = pd.DataFrame(rows)

    fam_of = {(x.side, x.route): x.family for x in mem.itertuples()}
    pre_f = pre.assign(family=[fam_of[("old", r)] for r in pre.route])
    post_f = post.assign(family=[fam_of[("new", r)] for r in post.route])
    served_after = set(zip(post_f.family, post_f.stop_id, strict=True))
    pairs_pre = zip(pre_f.family, pre_f.stop_id, strict=True)
    pre_f["kept"] = [(f, s) in served_after for f, s in pairs_pre]
    still_any = set(post.stop_id)
    pre_f["stop_survives"] = pre_f.stop_id.isin(still_any)
    fam = pre_f.groupby("family").agg(
        events_old=("n", "sum"),
        events_kept_in_family=("n", lambda s: s[pre_f.loc[s.index, "kept"]].sum()),
        events_at_removed_stops=("n", lambda s: s[~pre_f.loc[s.index, "stop_survives"]].sum()),
    )
    fam["containment"] = fam.events_kept_in_family / fam.events_old
    fam["share_events_at_removed_stops"] = fam.events_at_removed_stops / fam.events_old
    sizes = mem.groupby(["family", "side"]).size().unstack(fill_value=0)
    sizes = sizes.rename(columns={"old": "n_old_routes", "new": "n_new_routes"})
    fam = fam.join(sizes, how="right")
    fam["no_new_route"] = fam.n_new_routes.fillna(0) == 0
    return mem, pair, fam.reset_index()
