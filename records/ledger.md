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

## 2026-11-08T03:16Z | mechanisms_v1 | prereg
- Question: which part of the redesign's service change moved ridership: the number of trips, scheduled speed, or route length? Prompted by the hypothesis that elongated routes lost riders.
- Family-level treatments, May 2025 (old members) to October 2025 (new members), median weekday values from service_v1: D_trips = change in log trips; D_speed = change in log scheduled speed (revenue miles over in-trip revenue hours); D_length = change in log miles per trip; D_removed = share of the family's pre-launch weekday stop events at stops that no longer exist (families_v1). By construction change in log hours = D_trips + D_length - D_speed.
- Specification: same panel, fixed effects, clustering and sample as event_study_v1 pooled: log boardings on post x D_trips + post x D_speed + post x D_length (joint), then adding post x D_removed. Heterogeneity: post x D_trips interacted with the family's pre-launch median weekday midday headway above vs below the median family (diminishing-returns test).
- Reading rule: a coefficient is reported as an effect only if its 95% interval excludes zero; signs and magnitudes reported regardless. Speed and length are measured from schedules, so D_speed captures scheduled (padded or real) speed, not observed speed.

## 2026-11-08T03:16Z | decomposition_v1 | prereg
- Question: how much of the year-over-year Metrobus decline (WMATA portal boardings, Aug to Jun windows before and after launch) is accounted for by (a) routes handed to other operators, (b) the change in scheduled trips on WMATA routes, and (c) a change common to all route families?
- Method: (a) pre-period boardings of the 11 old routes whose every crosswalk successor is outside WMATA, as an upper bound on riders who left WMATA's count by transfer, plus the same for the 17 partially transferred routes reported separately; (b) counterfactual post-period boardings with each family's D_trips set to zero, using the pooled beta from event_study_v1 (and the 0.5 to 0.8 range from the reassignment check), summed over families; (c) the remainder, which also contains anything the model omits. Uncertainty: 1,000 draws of beta from its estimated sampling distribution.
- (c) is not split further causally; federal employment, weather and rail substitution are reported only as descriptive magnitudes beside it.

## 2026-11-08T03:16Z | alternatives_v1 | prereg
- Question: with the same weekday scheduled hours as the launched network, what ridership and job access would alternative allocations deliver?
- Scenarios on the October 2025 network: S1 speed held: schedules at each family's pre-launch scheduled speed, with the freed hours spent on additional trips on the same routes (trips scale by the speed ratio); S2 frequency where it pays: move a fixed share of trips (5% of network trips) from the families with the fewest boardings per trip to those with the most, holding total hours; S3 both. Ridership predicted with the pooled trips elasticity (and the heterogeneity estimate if its interval excludes zero); job access computed with r5py on GTFS modified accordingly (stop times compressed for S1; trips duplicated at evenly spaced offsets for added frequency), same OSM, dates and settings as access_v1.
- These are model predictions under the estimated elasticity, not observed outcomes; reported with the elasticity's uncertainty and labeled as scenarios.

## 2026-11-08T03:17Z | mechanisms_v1 | result
- Run: results/mechanisms_v1/summary.json (scripts/estimate_mechanisms.py), 100 families, 2023-01 to 2026-09 excluding 2025-06. Treatment SDs across families: D_trips 0.34, D_speed 0.08, D_length 0.28; pairwise correlations 0.15 (trips, speed), -0.28 (trips, length), 0.07 (speed, length).
- Joint: D_trips 0.938 (95% CI 0.804 to 1.073); D_speed -1.204 (-1.650 to -0.758); D_length 0.754 (0.530 to 0.978). Adding D_removed: -0.248 (-0.643 to 0.148), other terms nearly unchanged. Trips-only on the same sample: 0.698.
- Headway split (90 families with a pre-launch midday headway; median 20.7 min): trips elasticity 0.849 (0.664 to 1.035) for families with headways above the median, 0.385 (0.127 to 0.643) for those at or below it.
- Reading: the diminishing-returns pattern is reported as a result. The speed and length coefficients pass the interval rule but are not read as behavioral responses: families whose routes were extended into denser territory gained both stops (riders counted) and slower scheduled streets, so D_speed and D_length measure where routes go. The elongation hypothesis is neither supported nor refuted by the family design; a place-level panel that holds geography fixed is needed (area_panel_v1).
## 2026-11-08T03:17Z | area_panel_v1 | prereg
- Question: holding place fixed, do areas that received more scheduled bus visits gain boardings, and do areas that lost stops lose boardings?
- Unit: H3 resolution-8 cells (about 0.7 km2) containing at least one Metrobus stop in May 2025 or October 2025. Boardings: each route's monthly APC boardings apportioned to its stops in proportion to a static demand weight (residents plus jobs within 400 m of the stop, 2020 census blocks and LODES 2024), using the route's stop list in the GTFS version in force that month; weights do not depend on frequency, so a route's added trips do not mechanically shift boardings toward a cell. Cell boardings are summed over routes.
- Treatment: D_visits = change in log weekday scheduled stop visits (trips calling at stops in the cell), October 2025 vs May 2025; D_stops = change in log number of served stops in the cell.
- Specification: log cell boardings on cell and month fixed effects plus post x D_visits and post x D_stops, standard errors clustered by cell; event-study version with D_visits x month dummies (reference 2025-05); 2025-06 dropped in the pooled model. Sample: cells with positive apportioned boardings in every month 2024-08 to 2026-09 (route stop lists come from service_v1 versions, which start 2024-07). Reading rule as in mechanisms_v1.
- Limitation stated in advance: apportionment assumes boardings per unit of demand weight are equal across a route's stops; the cell estimate measures how route-level ridership responses distribute over places, not stop-level counts.

## 2026-11-08T03:20Z | area_panel_v1 | result
- Run: data/processed/area_v1 (scripts/build_area_panel.py), results/area_panel_v1 (scripts/estimate_area_panel.py). 1,233 H3 cells, 26 months (2024-08 to 2026-09); route boardings matched to GTFS routes at least 99.9% in every month. 1,028 cells balanced with finite treatments; treatment SD 0.39.
- Pooled: D_visits 1.020 (0.948 to 1.092); with D_stops: 1.016 and 0.008 (-0.100 to 0.116). Split by pre-launch visits: 1.088 below median (291 weekday visits), 0.960 above. Event study: pre-period mean -0.011 but maximum |t| 5.61.
- 169 cells lost all scheduled Metrobus service; they held 1.45% of apportioned boardings Aug 2024 to Jun 2025.
- Verdict: uninformative design. A cell receives a share of every route serving it, so adding routes through a cell raises its apportioned boardings mechanically; an elasticity near 1 and failed pre-trends are the signature. The design cannot be repaired without stop-level boardings (requested from WMATA). Not used for inference; the coverage-loss count is used descriptively.
## 2026-11-08T03:20Z | event_study_v1 | result (exploratory)
- Stable-alignment check, not pre-registered: families whose post-launch routes serve nearly the same stops as their pre-launch routes (containment and inflow both >= 0.9), so the redesign changed frequency on an unchanged alignment. Pooled trips elasticity 0.709 (0.524 to 0.895), 22 families; one old route to one new route 0.760 (0.555 to 0.966), 21 families. Joint speed and length terms not distinguishable from zero in these families (speed -0.69, length -0.45, intervals include zero). At >= 0.85: 0.789 (0.328 to 1.250), 32 families.
- Reading: frequency, holding the route alignment fixed, carries an elasticity near 0.7, matching the full-sample pooled estimate (0.698). This is the estimate carried into the decomposition and the scenarios, with the range 0.5 to 0.8 from the reassignment checks.

## 2026-11-08T03:21Z | decomposition_v1 | result
- Run: results/decomposition_v1/summary.json (scripts/decompose_and_simulate.py). Windows Aug 2024 to May 2025 vs Aug 2025 to May 2026 (ten months each, portal boardings): 103,336,659 to 95,758,106, -7.33%.
- Components (percent of before-window boardings; mean and 5th to 95th percentile over 1,000 draws of the elasticity, N(0.698, 0.083)): routes handed to other operators -1.67 (-1.99 to -1.36); WMATA's reallocation of trips across families -1.21 (-1.92 to -0.62); common to all families -4.40 (-5.30 to -3.38); families without a trip measure and unmatched routes -0.05. Components sum to the observed change.
- The 11 fully transferred routes carried 1,421,678 boardings in the before window (1.38% of the total). The transfer component (1.67 points) is 23% of the decline; WMATA's Metro Bus Action Plan attributes about a quarter of the year-over-year loss to route realignments with Maryland providers, an independent agreement.
- The common component is not split causally; it contains the 2025 federal job losses, weather (January 2026: 11 days at or below 20 F, 7.0 in of snow at DCA), rail substitution, missed trips and anything the trips measure omits, including any effect of slower or less reliable service.
## 2026-11-08T03:21Z | alternatives_v1 | result
- Run: results/alternatives_v1/summary.json and s2_reallocation.csv. 104 families, 10,504 weekday scheduled hours (October 2025), ten-month after-window boardings as the base. 1,000 draws of the elasticities.
- S1 speed held (trips scale by pre over post scheduled speed, hours fixed): trips +1.63%; riders +1.05% (0.83 to 1.28).
- S2 frequency where it pays (5% of weekday hours, 525 hours, moved from the 25 families with the fewest predicted riders per added hour to 13 families with the most; elasticity 0.849 above and 0.385 at or below a 20.7-minute pre-launch midday headway): riders +2.86% (2.06 to 3.89). 85.6% of added hours go to low-frequency families; 2.7% of cut hours come from them. Equity Emphasis Area share of stop events: recipients 0.449, donors 0.330 (hours-weighted).
- S3 (S1 then S2): riders +4.03% (3.13 to 5.12).
- Reading: model predictions under the estimated elasticities, holding hours fixed. S3 exceeds the -1.21 points attributed to WMATA's own reallocation. S2 moves service from the most frequent routes to infrequent ones, the opposite of a frequent-network concentration, because the estimated response to added trips is about twice as large on infrequent routes. Job-access effects of S1 and S2 not yet computed.

## 2026-11-08T03:44Z | alternatives_v1 | correction of S2 and S3 in the alternatives_v1 result entry
- Error: families with no pre-launch midday service (peak-only routes, no headway value) were classed as frequent and could give up hours in S2. They now sit out S2 (neither give nor receive). Results moved to results/alternatives_v2; alternatives_v1 is superseded for S2 and S3 (S1 unchanged).
- Corrected: S2 riders +2.80% (2.00 to 3.84); S3 +3.96% (3.07 to 5.07). 17 donor and 13 recipient families; Equity Emphasis Area share of stop events, donors 0.355, recipients 0.449; 85.6% of added hours go to low-frequency families, 7.2% of cut hours come from them. Decomposition_v1 rerun identically.
- Scenario access runs on alternatives_v1 S2 and S3 feeds are superseded; the feeds are rebuilt as scenario_feeds_v2.

## 2026-11-08T04:00Z | mechanisms_v1 | decision
- Exploratory robustness of the headway split before relying on it for S2 (logged before running): (1) continuous interaction post x D_trips x log(pre-launch midday headway, centered at the median); (2) the binary split on families with containment and inflow both >= 0.7; (3) the binary split on families with containment and inflow both >= 0.9.

## 2026-11-08T04:00Z | mechanisms_v1 | result (exploratory)
- Continuous interaction (90 families): D_trips 0.648 (0.506 to 0.790) at the median headway; D_trips x log(headway / median) 0.367 (0.114 to 0.620).
- Binary split on families with containment and inflow >= 0.7 (40 families, 16 low-frequency): low-frequency 0.594 (0.230 to 0.958), high-frequency 0.688 (0.393 to 0.982). At >= 0.9 (17 families, 9 low-frequency): 0.647 (0.404 to 0.890) and 1.073 (-0.168 to 2.314).
- Reading: the larger response on infrequent routes does not survive restriction to families with little rider reassignment between families, so it may partly reflect infrequent families absorbing stops. S2 as specified rests on that heterogeneity; it is kept and reported beside a homogeneous-elasticity version (S2h, S3h: single elasticity 0.698 for all families), whose gains come only from moving hours toward families with more boardings per scheduled hour.

## 2026-11-08T04:01Z | alternatives_v1 | result (S2h, S3h added; supersedes alternatives_v2 for reporting)
- Run: results/alternatives_v3 (same code and draws as v2 plus S2h and S3h). S1 +1.05% (0.83 to 1.28); S2 +2.80% (2.00 to 3.84); S3 +3.96% (3.07 to 5.07); S2h +3.47% (2.65 to 4.38); S3h +4.46% (3.45 to 5.58).
- S2h moves hours from 24 donor families to 7 recipients, none of them low-frequency; Equity Emphasis Area share of stop events 0.390 (donors) and 0.374 (recipients). S2 sends 85.6% of added hours to low-frequency families (EEA share 0.355 to 0.449).
- Reading: holding scheduled speed and reallocating 5% of hours by predicted riders per hour gains 4.0% to 4.5% under either elasticity assumption, against the -1.21 points attributed to the launched reallocation. The direction of the reallocation depends on whether the response to added trips falls with baseline frequency, which the clean-family subsamples do not settle (mechanisms_v1 exploratory entry).

## 2026-11-08T04:15Z | federal_v1 | prereg
- Question: did route families more exposed to federal employment lose more riders in 2025 and 2026, which would help describe the component common to all families?
- Exposure per family (from its pre-launch routes' stops, May 2025): workplace federal share = LODES 2022 WAC JT04 jobs over JT00 jobs within 400 m of the family's stops (2022, before the 2025 shock); residence federal share = RAC JT04 over JT00 within 400 m. Standardized across families.
- Specification: log family boardings on family and month fixed effects, D_trips x post (as in event_study_v1) and each standardized exposure x month dummies (reference 2024-12), clustered by family; summaries are the mean coefficient over 2025-01 to 2025-06 (return to office and early cuts, before the redesign) and over 2025-07 to 2026-09.
- Reading rule: an exposure effect is reported if the period-mean coefficient's 95% interval excludes zero. Not causal for the federal shock; descriptive of where the common decline concentrated.

## 2026-11-08T04:16Z | federal_v1 | result
- Run: results/federal_v1 (scripts/estimate_federal_exposure.py), 100 families. Raw exposure means (SD): workplace federal share 0.070 (0.092); residence federal share 0.070 (0.019). D_trips x post 0.709 in this model.
- Per SD of workplace federal share: mean monthly coefficient -0.008 (-0.019 to 0.003) in 2025-01 to 2025-06 and -0.029 (-0.081 to 0.024) in 2025-07 to 2026-09. Per SD of residence share: 0.008 (-0.004 to 0.020) and -0.017 (-0.077 to 0.042).
- Reading: no differential decline by federal exposure across families; the common component is regionwide in this design. LODES JT04 omits some federal agencies (DC JT04 total 107,963 in 2024), so measurement error biases these toward zero.

## 2026-11-08T04:21Z | access_v1 | correction
- r5py caches built networks under a key derived from input file names. Runs labelled S2b and S3b (corrected S2 and S3 feeds, saved as S2.zip and S3.zip in scenario_feeds_v2) reused the cached networks of the superseded alternatives_v1 feeds (network load 5 s instead of about 95 s) and produced identical numbers; both outputs were deleted. Every scenario feed now has a distinct file name (S2b, S3b, S2h, S3h, hard links in the v2 and v3 stores) and the runs are repeated. Earlier runs (pre, post, S1, superseded S2 and S3) built their networks fresh and stand.
- Regional runs failed because R5 rejects TheBus's pre-launch feed (mdb-477-202504300021) for empty optional tables; removing those tables did not help because the cleaned copy keeps the original file name and the cache. Regional runs now use --allow-gtfs-errors (R5 skips invalid entities; warnings only concern empty fare, frequency and transfer tables), recorded in each run_meta.json.
