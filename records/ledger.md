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
