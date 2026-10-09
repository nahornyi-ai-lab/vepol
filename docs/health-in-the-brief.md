# Health in the morning brief

The morning brief (`kb-brief`) can open with a short 🫀 Body section: last
night's sleep, recovery, yesterday's activity and one suggestion for the day.
It is off until you point the brief at your health data. Vepol does not collect
health data itself: any source (an Apple Health export, a sync from your
watch's vendor, your own script) can feed it by writing one small JSON file per
morning.

## Settings

Set them in the environment, or as `NAME=value` lines in
`~/knowledge/personal/.secrets` (the same file the brief reads its other
settings from). A leading `~/` is expanded to your home folder.

| Setting | Value | When unset |
|---|---|---|
| `KB_HEALTH_METRICS` | Folder that holds `morning/<YYYY-MM-DD>.json` | No health input, no 🫀 section, no mention of health |
| `KB_BRIEF_HEALTH_READY_FILE` | JSON file your sync writes once the morning data is final: `{"morning_wait": {"date": "<YYYY-MM-DD>", "done": true}}` | No waiting |
| `KB_BRIEF_HEALTH_WAIT_UNTIL` | Latest time to wait: `HH:MM`, or `HH:MM/HH:MM` for weekdays/weekends (e.g. `09:10/10:10`) | No waiting |

Waiting happens only on the scheduled brief, and only when both the ready file
and the deadline are set. The brief checks the ready file every 30 seconds and
goes out as soon as today's mark is done, or at the deadline without fresh
health data (one line in `logs/brief.log` says so). Manual runs never wait. A
deadline that is not `HH:MM` or `HH:MM/HH:MM` is logged and ignored.

## File format: `health-morning/v1`

`<KB_HEALTH_METRICS>/morning/<YYYY-MM-DD>.json`, one per day. Every block is
optional except `date` and `freshness`; empty values are dropped before the
brief sees them.

```json
{
  "schema": "health-morning/v1",
  "date": "2026-10-09",
  "built_at": "2026-10-09T06:55:00+02:00",
  "freshness": {"status": "fresh", "sleep_ready": true},
  "last_night": {"start": "23:40", "end": "07:05", "duration_min": 445,
                 "deep_min": 70, "rem_min": 95, "score": 82},
  "recovery": {"hrv_night_ms": 48, "hrv_baseline_low_ms": 42,
               "hrv_baseline_high_ms": 55, "hrv_status": "balanced",
               "rhr": 52, "bb_wake": 78, "readiness": 74},
  "yesterday": {"date": "2026-10-08", "steps": 9100, "intensity_min": 35,
                "activities": ["run 5 km"], "stress_avg": 28},
  "fitness": {"training_status": "productive", "vo2max": 49},
  "vs_7d": {"sleep_min": 20, "hrv_ms": 3, "rhr": -1, "history_days": 7},
  "body": {"weight_kg": 78.4, "measured_at": "2026-10-09T07:10:00+02:00"},
  "observations": ["Short plain-language notes your source wants the brief to see."]
}
```

- `freshness.status`: `fresh` when the data is current; otherwise any short
  code such as `stale`, `error` or `login_needed`.
- `freshness.sleep_ready`: `true` once last night's sleep is in the file.
- `bb_wake` is an energy-at-wake score (0–100) if your source has one.
- `vs_7d` holds differences from your 7-day average.

The brief uses the file only when `date` is today, `status` is `fresh` and
`sleep_ready` is true. Otherwise the 🫀 section is a single "no sleep and
health data for today" line with the reason: `no_snapshot_for_today`, the
freshness status, `night_not_uploaded`, or `reader_failed` (the file could not
be read). The brief reports facts and suggestions only, never medical
conclusions.
