# Ledger

Append-only record of results, decisions and corrections. Newest entries are at the bottom.
Correct an entry by appending a new one that names the timestamp it corrects; never edit old text.
Headers are written with the clock:
`printf '\n## %s | %s | %s\n' "$(date -u +%Y-%m-%dT%H:%MZ)" "<study>" "<prereg|result|decision|correction of <timestamp>>" >> records/ledger.md`

## 2026-11-08T02:10Z | repo | decision
- Decision (PI): the GitHub repository holds code, data-access scripts, results and this ledger. The research proposal and literature notes stay in the git-ignored `notes/` folder; `records/HANDOFF.md` is git-ignored and local (guide option b).
- Decision (PI): the GTFS-Realtime archive is stored on the local disk only for now, with no cloud backup. Disk had 226 GB free (94% used) at this time; the archive is estimated at 130 to 260 GB per year compressed (zstd level 19, 4.9:1 on a Saturday 21:05 EST sample of all six WMATA feeds).

## 2026-11-08T02:10Z | data/gtfs-static | result
- Mobility Database feed mdb-1846 (WMATA bus): 20 datasets, schedules in force from 2024-07-09 to 2027-03-27, all 20 SHA-256 verified. Includes the last pre-launch schedule (2024-12-15 to 2025-06-28) and the launch schedule (from 2025-06-29). Downloaded by `scripts/fetch_mdb_gtfs.py`.
- Transitland lists 71 WMATA bus feed versions with continuous service-date coverage from 2019-12-23 to 2027-03-27, but its API returns 401 for every download on a free key. The feed's license record (developer.wmata.com/license) leaves redistribution unspecified.
- Mobility Database tfs-75 (migrated TransitFeeds archive of the same WMATA URL): 2,083 datasets, downloaded 2013-10-25 to 2020; nothing after 2020. mdb-1124 is not WMATA (a Thai operator), contrary to an earlier note.
- Consequence: schedules for 2023-01 to 2024-07 are not yet in hand. The event-study specification needs only the May 2025 and October 2025 schedules (in hand); the monthly service panel starts 2024-07 unless the earlier versions are obtained from Transitland or WMATA.

## 2026-11-08T02:10Z | data/gtfs-realtime | result
- All six WMATA GTFS-Realtime feeds answer with an api_key header (bus and rail vehicle positions, trip updates and alerts at api.wmata.com/gtfs/*.pb). Sample at 2026-11-08T02:05Z: 627 bus vehicle positions on 99 routes (457 with trip_id, median position age 5 s), 1,787 bus trip updates, 84 rail vehicles. Occupancy is NO_DATA_AVAILABLE.
- Default tier limits, stated by the WMATA portal: 10 calls/s and 50,000 calls/day. A Tier 4 request (150 calls/s, 10,000,000/day) is pending approval.

## 2026-11-08T02:27Z | data/ntd | result
- Source: NTD Complete Monthly Ridership (with Adjustments and Estimates), dataset 8bui-9xvu updated 2026-11-03, data through 2026-09; WMATA is NTD ID 30030 (confirmed). File sha256 d23b776d450c00707de133a4b1c7cd6ef907e521a5ae07374587121114cfd001.
- Metrobus (mode MB), FY2025 to FY2026 (Jul to Jun): unlinked trips 124.2M to 116.3M (-6.4%); vehicle revenue hours +11.1%; vehicle revenue miles +3.4%. June to May window: -6.3%, +9.9%, +3.1%. The reported "about 13% more service" is mostly added hours, not added miles.
- Metrorail (mode HR), same windows: unlinked trips +6.3% (Jul to Jun) and +8.3% (Jun to May), not the +13% in WMATA's FY26 Q3 report; the measures likely differ (entries vs unlinked trips). Not yet reconciled.
- Data quality: WMATA's monthly bus VRM/VRH ratio is constant within multi-month blocks (9.93 mph Jan to May 2024, 9.80 Feb to May 2025, about 9.2 Jul 2025 to May 2026), then 8.53 (2026-06), 10.24 (2026-07), 11.04 (2026-09). Monthly VRH and VRM look allocated from a fixed ratio, with a method change in mid-2026. Do not use NTD monthly VRH/VRM for WMATA as a treatment or speed measure; use GTFS-derived scheduled service. The step from 9.77 (2025-06) to 9.26 mph (2025-07) coincides with the redesign launch.
- From 2026-07, Metrobus unlinked trips are up 1.8% to 3.0% year over year while reported VRH is down 8% to 9%; open question whether service or reporting changed.

## 2026-11-08T02:32Z | service/system | result
- Run: data/processed/service_v1 (scripts/build_service_panel.py; run_meta.json holds the commit and input hashes). 20 Mobility Database versions of WMATA bus GTFS, 2024-06-18 to 2026-11-08, every date assigned the version in force (latest published version with service that day). 118,939 route-days, 315 route codes (186 pre-launch, 125 at launch).
- Validation against NTD: scheduled revenue miles from GTFS shapes are 0.99 to 1.04 times NTD VRM in most months; scheduled in-trip hours are about 0.82 of NTD VRH (NTD includes layover and recovery).
- Aug 1 to Jun 28, before vs after launch (332 days each): scheduled trips 4,206,082 to 4,096,145 (-2.6%); scheduled revenue hours 2,990,986 to 3,192,123 (+6.7%); revenue miles 35.57M to 37.15M (+4.4%); scheduled speed 11.89 to 11.64 mph. NTD over the same months: UPT -6.4%, VRH +11.1%, VRM +3.4%.
- Median weekday: May 2025 13,881 trips, 10,009 revenue hours; Oct 2025 13,344 trips (-3.9%), 10,504 hours (+4.9%); May 2026 13,425 trips, 10,624 hours.
- Interpretation (to be tested at route level): the redesign scheduled fewer, longer and slower trips; the "13% more service" is mostly added time (in-trip run time plus layover and recovery), not more trips. Frequency-based treatment measures (trips, headways) and time-based ones (revenue hours) move in opposite directions, so the choice of treatment measure matters.
- Fix before this run: an earlier build assigned four dates (2025-07-26, 2025-10-16, 2025-10-17, 2026-03-14) to versions whose calendars had no service those days; version coverage is now the set of dates with any active service.

## 2026-11-08T02:39Z | families | result
- Run: data/processed/families_v1 (scripts/build_route_families.py). Reference networks: last pre-launch version mdb-1846-202505020000 on 2025-05-14 and launch-period version mdb-1846-202507250117 on 2025-07-16.
- Stop IDs are stable across the redesign: 7,028 stop_ids appear in both the May 2025 and October 2025 feeds (75.9% of the 9,256 pre-launch stops); 95.5% of those are within 20 m of their earlier location. 2,228 stop_ids disappear and 473 are new.
- 105 families from 185 old and 125 new routes, linked by mutual best match on shared weekday stop events. Largest family has 8 routes (old C12, D12, NH1, NH2, P12; new P90, P93, P94). Old route C11 shares no stop with any new route (flag: discontinued or transferred).
- Containment (share of a family's pre-launch stop events still served in-family after launch): median 0.80, quartiles 0.60 and 0.92, 10th percentile 0.50. Lowest: F098 (old F14, new P63) 0.28; F029 (old 74, new C55) 0.32; F020 (old W2, W3, new C29) 0.33. Median share of pre-launch stop events at stops removed from the network: 0.11.
- Next: compare with WMATA's published crosswalk if one is found; test merging low-containment families; report estimates with and without families below a containment cutoff.

## 2026-11-08T02:40Z | data/geography | result
- LODES 8, 2024 latest (also 2019, 2022, 2023): WAC and RAC S000 for JT00, JT04 (all federal) and JT05 (federal primary), dc/md/va; OD main and aux JT00 for 2024. All 81 files match published checksums. 2024 workplace jobs: DC 672,632; MD 2,648,251; VA 3,957,886. DC JT04 federal jobs only 107,963 in 164 blocks (OPM coverage omits some agencies): federal exposure measures need a caveat or a second source.
- ACS 5-year 2020-2024 (newest the API serves), 16 counties: 4,132 block groups, 1,520 tracts. C21007 (disability, civilians 18+) is published at block group and sums exactly to tracts; B18101 is tract-only. B19013 is not computable for 232 block groups.
- TIGER 2020 and 2024 block groups and tracts (GEOIDs identical in DC/MD/VA), 2020 blocks, 253,330 block internal points.
- MWCOG Equity Emphasis Areas: 2022 vintage 364 EEA tracts (of 1,330), 2018 vintage 351; no open-data license stated, disclaimer only; no coverage of Howard or Anne Arundel.
- DC Open Data (CC BY 4.0): Better Bus stops 8,335 and routes 395; 2023-2025 archive stops 10,044 and routes 662 (all updated 2026-11-06). DDOT bus priority project, bus lane, signal priority and priority corridor layers (no license stated).
- OSM: Geofabrik DC, MD, VA builds with data to 2026-11-06T21:21:21Z, clipped to the study region plus buffer counties (298 MB, complete ways). This snapshot is held fixed for every accessibility network. The clip box extends into WV and PA, which are not in the source files (affects Loudoun and Frederick edges only).
