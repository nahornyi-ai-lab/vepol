# Health in the morning brief

Start the day knowing how you slept. Point the morning brief at a small
health file, and it opens with a short 🫀 Body section: last night's sleep,
how recovered you are, what you did yesterday, and one suggestion for today:
train, take it easy, or go to bed earlier. The suggestion also lands in the
brief's day plan.

Any source works. Vepol does not read your watch, ring or phone itself. Your
own sync (a script, an export, an automation) writes one JSON file per
morning, and the brief takes it from there. Garmin is the worked example
below, because its numbers map field by field: Body Battery at wake,
overnight HRV (heart rate variability) against your baseline, training
status.

## What you get

When today's data is in, the Body section shows:

- last night's sleep: duration and sleep score;
- HRV against your own baseline range, or your HRV status;
- resting heart rate, plus energy at wake (Body Battery) or readiness when
  your source has them;
- yesterday's steps and workouts, and anything far from your 7-day average;
- one suggestion for the day, grounded in those numbers.

When the data is late, stale or missing, you get one honest line instead
("No sleep and health data for today") with the reason in plain words, and
no numbers. The brief never passes old numbers off as today's. It reports
facts and suggestions, never medical conclusions.

If you use the morning audio digest, the Body section goes into it too: the
digest takes the whole finished brief.

## Turn it on

1. Have your sync write `<folder>/morning/<YYYY-MM-DD>.json` each morning, in
   the format below. For example: `~/health/morning/2026-10-09.json`.
2. Point the brief at that folder with one line in
   `~/knowledge/personal/.secrets`:

   ```text
   KB_HEALTH_METRICS=~/health
   ```

3. Check what the brief will see:

   ```bash
   KB_BRIEF_PROMPT_ONLY=1 kb-brief | grep -A2 '8. Health'
   ```

   This prints the brief's instructions and stops, so nothing is written or
   sent. The last line shown is JSON: `available` is `true` with your
   numbers, or `false` with a `reason`.

The next brief includes the Body section: the scheduled one, which runs once
you answered yes to "Install scheduled tasks?", or one you start by hand with
`kb-brief`.

## Worked example: Garmin

Garmin Connect already computes most of what the brief reads. A sync that
runs after your watch uploads the night fills the file like this:

| Garmin Connect | Field in the file |
|---|---|
| Sleep start, end and duration | `last_night.start`, `last_night.end`, `last_night.duration_min` |
| Deep and REM sleep | `last_night.deep_min`, `last_night.rem_min` |
| Sleep score | `last_night.score` |
| Overnight HRV and its baseline range | `recovery.hrv_night_ms`, `recovery.hrv_baseline_low_ms`, `recovery.hrv_baseline_high_ms` |
| HRV status (balanced, unbalanced, low) | `recovery.hrv_status` |
| Resting heart rate | `recovery.rhr` |
| Body Battery at wake | `recovery.bb_wake` |
| Training readiness | `recovery.readiness` |
| Yesterday's steps, intensity minutes, average stress and activities | `yesterday.steps`, `yesterday.intensity_min`, `yesterday.stress_avg`, `yesterday.activities` |
| Training status and VO2 max | `fitness.training_status`, `fitness.vo2max` |
| Weight from a connected scale | `body.weight_kg`, `body.measured_at` |

Two fields come from your sync, not from Garmin:

- `vs_7d` holds the differences from your 7-day average, computed from the
  files your sync has already written.
- `freshness.sleep_ready` turns `true` only once last night's sleep has
  synced. The night reaches Garmin Connect only after your watch syncs in
  the morning, so the brief can also wait for it (see
  [Waiting for a late sync](#waiting-for-a-late-sync)).

Other sources work the same way. With an Apple Health export or another
tracker, fill the fields you have and leave out the rest.

## Settings

Set them in the environment, or as `NAME=value` lines in
`~/knowledge/personal/.secrets` (the same file the brief reads its other
settings from). A leading `~/` is expanded to your home folder.

| Setting | Value | When unset |
|---|---|---|
| `KB_HEALTH_METRICS` | Folder that holds `morning/<YYYY-MM-DD>.json` | No health input, no 🫀 section, no mention of health |
| `KB_BRIEF_HEALTH_READY_FILE` | JSON file your sync writes once the morning data is final: `{"morning_wait": {"date": "<YYYY-MM-DD>", "done": true}}` | No waiting |
| `KB_BRIEF_HEALTH_WAIT_UNTIL` | Latest time to wait: `HH:MM`, or `HH:MM/HH:MM` for weekdays/weekends (e.g. `09:10/10:10`) | No waiting |

### Waiting for a late sync

Waiting happens only on the scheduled brief, and only when both the ready
file and the deadline are set. The brief checks the ready file every 30
seconds and goes out as soon as today's mark is done. At the deadline it
stops waiting and goes out with whatever the health file says; one line in
`~/knowledge/logs/brief.log` records that the mark was missing. Manual runs
never wait. A deadline that is not `HH:MM` or `HH:MM/HH:MM` is logged and
ignored.

Each scheduled run has a time cap: the `timeout:` of the `daily` process in
`~/knowledge/personal/processes.yaml`, 1800 seconds when unset. The brief
keeps about 14 minutes of that cap for writing and sending, so one run waits
at most about 15 minutes. If the deadline is still ahead then, the run stops
before writing the brief, logs `health wait paused`, and the scheduler starts
it again on its next tick (every 15 minutes). The wait carries on until the
mark or the deadline, with no change needed. Between runs nobody watches the
ready file, though, so the brief can go out up to about 15 minutes after your
sync finishes.

To send the brief within 30 seconds of the mark, give the `daily` process a
longer cap. Add one line to its block:

```yaml
- id: daily
  enabled: true
  when: after:mail-morning
  run: kb-brief
  outputs: [telegram, file]
  timeout: 7200
```

`7200` seconds is the most `processes.yaml` allows. One run can then wait
about 105 minutes, which covers a 09:10 deadline for a brief that starts
around 07:30.

## File format: `health-morning/v1`

`<KB_HEALTH_METRICS>/morning/<YYYY-MM-DD>.json`, one per day. Every block is
optional except `date` and `freshness`. Inside each block, null values and
empty lists or objects are dropped before the brief sees them.

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
`sleep_ready` is true. Otherwise the 🫀 section is the single "No sleep and
health data for today" line with a short reason in plain words. The check in
step 3 shows the reason code: `no_snapshot_for_today` (no file for today, or
its `date` is not today), the freshness status, `night_not_uploaded`
(`sleep_ready` is not true), or `reader_failed` (the file could not be read).

## Where the numbers go

- The file stays on your Mac. The brief passes today's numbers to the AI
  agent that writes it (Codex, or Claude when Codex is not available), along
  with the brief's other inputs.
- The finished brief, Body section included, goes to your own Telegram bot
  and is saved in `~/knowledge/briefs/<date>.md`.
- The morning audio digest uses the same brief. On the local Qwen route it
  is narrated on your Mac and sent to your Telegram as an MP3. On the
  NotebookLM route it is uploaded to Google NotebookLM, which makes the Audio
  Overview.

## What it does not do yet

The brief suggests; it does not change your plan's intensity or your calendar
on its own. A day plan that eases off by itself after a run of bad nights is
the direction, not a shipped feature.
