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

## 2026-11-08T02:49Z | families/crosswalk | result
- WMATA's own crosswalk located: "Find Your Route in the 2025 Network", pages 1 to 4 of the 2025 Route Profiles PDF (Nov 2024, approval stage). Extracted to data/raw/route_profiles/crosswalk_2025_network.csv: 432 links from 185 Metrobus and 24 TheBus routes to 152 network routes.
- Agreement with families_v1 (built only from shared stops): WMATA's first-listed successor is in the same family for 75.1% of the 185 Metrobus routes; at least one listed successor is in the same family for 89.2%. Most first-choice disagreements are routes whose listed successor is not a WMATA route or old routes split across several new routes.
- 28 successor names in the crosswalk are absent from WMATA's launched GTFS (P52 to P57, P5X, P64, P65, P71, P76 to P78, P83 to P88, P95, P11, P22, P23, P43, P44, C22, D12, F64, M10): routes operated by other agencies (mostly TheBus) or not launched.
- Old Metrobus routes whose every listed successor is outside WMATA: B21, B22, B24, C11, C12, C13, C14, F12, F13, Q6, W14 (11 routes). They ran 366 of 13,574 classified weekday trips in May 2025 (2.7%) and 2.1% of scheduled revenue hours. 17 more routes have some non-WMATA successors (1,228 weekday trips, 9.0%). WMATA attributes about a quarter of the year-over-year bus decline to these realignments; route ridership is needed to test that.

## 2026-11-08T02:51Z | data/ridership | result
- WMATA Ridership Data Portal is an anonymous Tableau Server (exttabanalytics.wmata.com); scripts/fetch_wmata_ridership.py pulls the dashboards' full data in pieces under the 10,000-row reply cap.
- Metrobus: data/raw/wmata_ridership/bus_route_month.csv, route x month x day type (Weekday, Saturday, Sunday, Monthly Total), 2018-07 to 2026-09, 56,911 rows, 367 route codes. APC boardings plus paid boardings. Route sums match WMATA's daily systemwide bus totals within 0.0001% in all 93 months 2019-01 to 2026-09. Network field switches from "Former Routes" (through 2025-06) to "Current Metro Bus Routes" (from 2025-07); 11 codes are reused for different routes (A12, C11, C13, C21, C25, C26, C27, C29, D32, D34, P12), so the key is (Network, Route). Seven duplicated keys (2025-06 A12, C11, C13, C21, C26; 2023-03 route 33 Monthly Total at 170,479 and 25,277) and two 2026-07 rows with Route "None" are kept as published.
- Metrorail: station x date entries and exits (tap, non-tap estimate) 2019-01-01 to 2026-10-31; station x month x day type x 5 time periods (holidays excluded).
- Terms: no data license stated; data labelled preliminary; wmata.com Terms of Use restrict redistribution of site content. Raw ridership files stay out of the repository; only code and derived results are published.
- Cleanup owed: src/betterbus/download.py and src/betterbus/manifest.py duplicate each other; merge them.

## 2026-11-08T02:52Z | event_study_v1 | prereg
- Question: did route families that gained scheduled weekday trips in the redesign gain riders relative to families that lost trips, and were they already diverging before launch?
- Data: WMATA portal Metrobus APC monthly boardings (Monthly Total) summed to families_v1; months 2023-01 to 2026-09. Treatment D_f = log(median weekday scheduled trips, new members, 2025-10) minus log(same, old members, 2025-05), from service_v1.
- Primary specification: log(boardings_ft) = family FE + month FE + sum over months k (k != 2025-05) of beta_k * D_f * 1[t = k]; OLS, standard errors clustered by family; unweighted. Sample: families with both old and new members and positive boardings in every month used (C11's family excluded by construction).
- Summary estimand: pooled version, beta * D_f * 1[t >= 2025-07], months 2025-06 dropped (transition), same fixed effects. beta is the within-family elasticity of boardings with respect to weekday trips induced by the redesign.
- Pre-trend test: joint F-test that all beta_k for k in 2023-01 to 2025-04 are zero; also report the mean pre-period beta_k.
- Secondary (reported regardless of result): (a) weighted by family 2024 boardings; (b) D_f from revenue hours instead of trips; (c) excluding families with containment < 0.6; (d) excluding families with |D_f| > 1; (e) Poisson PPML on boardings levels.
- Benchmarks for interpretation: Berrebi, Joshi and Watkins (2021) within-segment frequency elasticity (inelastic, below 1) is the relevant comparison, not their 0.66 to 0.78 cross-sectional figure.
- Reading rule: the pooled beta is called a ridership response to redesign-induced service change only if the pre-trend test does not reject at the 5% level and the pre-period beta_k show no drift; otherwise it is reported as descriptive. Status: screen-free, of record once run as specified.

## 2026-11-08T02:53Z | event_study_v1 | decision
- Deviation (logged before running): the registered pre-trend test is a cluster-robust Wald test of 28 restrictions with 100 clusters, which is known to over-reject when restrictions are many relative to clusters. Added, without dropping the registered test: (1) a permutation version of the same statistic, permuting D across families (2,000 draws), and (2) a test of a linear pre-period trend in D x time. Also added an exploratory check for mechanical reassignment of riders between families: two-sided containment (inflow share = share of a family's post-launch stop events at stops its pre-launch routes served), with the pooled estimate re-run on families with inflow and containment both >= 0.7. These additions are exploratory, not of record.

## 2026-11-08T03:02Z | event_study_v1 | result
- Run: results/event_study_v1 (scripts/estimate_event_study.py), 100 families balanced over 2023-01 to 2026-09 (44 months after dropping none; 2025-06 dropped in pooled only). Treatment SD 0.40 log points.
- Primary pooled: beta 0.698 (SE 0.083, 95% CI 0.535 to 0.860). Secondary: weighted by 2024 boardings 0.613 (0.095); treatment from revenue hours 0.887 (0.082); containment >= 0.6, 0.695 (0.111, 74 families); |D| <= 1, 0.644 (0.079, 99 families). Poisson PPML not run (no two-way FE PPML implementation in the environment yet).
- Event coefficients: every pre-period coefficient 2023-01 to 2025-04 has |t| < 1.6, mean -0.015; 2025-06 -0.021 (SE 0.023). Post-launch coefficients jump to 0.59 in 2025-07 and stay between 0.63 and 0.73 through 2026-09, with no build-up.
- Registered pre-trend test: cluster-robust Wald 160.2 on 28 df, p = 1.7e-20 (rejects).
- Added tests (see decision entry): permutation p of the same Wald statistic 0.163 (2,000 permutations of D across families; median permuted statistic 103.6); linear pre-trend in D x time 0.0046 per year (SE 0.016, p 0.77); permutation p of the pooled beta < 0.0005.
- Exploratory, mechanical reassignment: inflow share (post-launch stop events at stops the family served before) quantiles 0.56 / 0.72 / 0.90 at 10th / 25th / 50th percentiles. Pooled beta on families with containment and inflow both >= 0.6: 0.486 (0.087, 67 families); >= 0.7: 0.798 (0.115, 48); >= 0.8: 0.780 (0.206, 37). corr(D, inflow) = -0.25.
- Reading: by the registered rule the pooled beta is descriptive, because the registered Wald test rejects; the permutation and linear-trend tests indicate the rejection is the test's over-rejection, not drift. Families that gained weekday trips gained boardings, with an elasticity between about 0.5 and 0.8 after excluding families with heavy rider reassignment. The step at launch with no build-up is consistent with part of the estimate being reassignment of riders between families; a stop or area panel is needed to separate it. The estimate is well above within-segment frequency elasticities reported elsewhere, which is a further reason for caution.

## 2026-11-08T03:02Z | access_v1 | result
- Runs: data/processed/access_v1/{pre,post} (scripts/build_access.py): r5py 1.1.7, OSM snapshot 2026-11-06 held fixed, WMATA bus and rail GTFS only. Pre: 2025-05-14 (bus mdb-1846-202505020000, rail mdb-1847-202505140012); post: 2025-10-22 (bus mdb-1846-202510160132, rail mdb-1847-202510220038). Departures 07:00 to 09:00 each minute, median travel time, transit plus walk, cap 60 minutes. 3,018 Compact origin block groups (population-weighted block points) to 4,132 block groups in the Compact and buffer counties; LODES 2024 jobs.
- Population-weighted mean jobs reachable (summarize_access.py, ACS 2020-2024 weights, 4,720,798 people): 60 min 250,473 to 254,756 (+4,283, +1.71%); 45 min +2.58%; 30 min about +2%. Gini of 60-minute access 0.6778 to 0.6813.
- By group, 60 min: white non-Hispanic +2.63%; Black non-Hispanic +1.10%; Hispanic -0.21%; Asian non-Hispanic +2.95%; below poverty +0.42%; zero-vehicle households +2.04%; adults with a disability +1.83%; residents of 2022 Equity Emphasis Area tracts -0.07%, with 38.2% of them in block groups whose access fell (24.6% of everyone). Prince George's -5.44% (41.5% with a decline); Arlington +3.62%; Alexandria +6.10%; DC +1.65%; Montgomery +2.93%.
- Limitation that changes the reading: the network is WMATA-only, so Prince George's routes handed to TheBus, and all other local operators, are missing; the Prince George's, Hispanic and EEA declines are overstated until the regional bundle is run. WMATA's "+20,000 jobs within an hour" is not reproduced (+4,283 for the average resident here); WMATA's method is undisclosed.
