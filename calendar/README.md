# calendar

Posting calendars. The `schedule` workflow runs every hour (and on every push here) and hands each post that is due
within the next 30 hours to Buffer, scheduled for its exact time. Buffer then publishes it.

## A calendar file

`calendar/<name>.json`, times are local to `timezone`:

```json
{"timezone": "Europe/Berlin",
 "posts": [{"at": "2026-10-13T19:00", "account": "nocode.founders", "platform": "youtube",
            "job": "2026-10-11-founders", "clip": "01-zain"}]}
```

- `platform` is `youtube`, `tiktok` or `instagram`. `job` and `clip` name a rendered clip: caption, title and ad label
  come from `results/<job>/manifest.json`, the video from the `media` branch (`<job>/<clip>-<platform>.mp4`).
- Files starting with `_` are skipped (`_example.json` is an example; rename a file to `_...` to pause it).
- Make one with the planner instead of by hand: the same clip order on every platform, one clip per time a day,
  a platform can start later.

```
python -m clips.schedule plan --job 2026-10-11-founders --start 2026-10-13 --times 12:00,16:00,19:00 \
  --platforms youtube,tiktok,instagram --order 01-zain,02-klar,03-quicktables --account nocode.founders \
  --offset instagram=1 --out calendar/week-42.json
```

Running it again with another job extends the file. It refuses two posts at the same time and more than 3 a day.

## Check before it posts

```
python -m clips.schedule run --calendar 'calendar/*.json' --dry-run --repo <owner>/<repo> --now 2026-10-13T06:00:00Z
```

## Rules the scheduler keeps

- Every queued post is written to `results/_schedule/queued.json` (Buffer post id, `dueAt` in UTC). A post in that
  file is never sent to Buffer again, and one video file is never queued for two accounts.
- At most 3 posts a day per account and platform, at most 9 posts waiting per Buffer channel (the free plan stops
  at 10); the rest wait for a later run.
- A post is skipped and reported when its video does not answer, its job is not rendered, or its caption has no ad
  label. A problem with a post due within 3 hours turns the run red, so GitHub sends a mail.
- Posts whose time passed before they were queued are reported as missed, never posted late.

## Which Buffer channel

The channel of the right network whose name contains the handle without dots (`nocodefounders`). When that is not
unique, add `calendar/accounts.json`:

```json
{"nocode.founders": {"youtube": "<Buffer channel name or id>", "tiktok": "<name or id>"}}
```
