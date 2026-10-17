# school-job-scraper

Scans three Utah school district job boards once a day and emails a summary of
**full-time elementary school teacher** openings, with a link to each posting.

| District | Board | How it is read |
| --- | --- | --- |
| Weber | https://wsd.schoolspring.com | `api.schoolspring.com` JSON API |
| Davis | https://dsdjobs.net/announcements | `dsdjobs.net/Jobs/GetList` JSON API |
| Ogden | https://ogdensd.schoolspring.com | `api.schoolspring.com` JSON API |

All three sites are JavaScript single-page apps, so there is no server-rendered
HTML to scrape — the pages are ~4KB shells. Each one is instead read through the
same unauthenticated JSON API its own front end uses, which is both far more
reliable than HTML parsing and immune to cosmetic redesigns.

## Quick start

```bash
make install          # installs dependencies and enables the commit hooks
make dry-run          # scan all three boards and print the summary, no email
```

To send real email, copy `.env.example` to `.env` and fill it in:

```bash
cp .env.example .env
$EDITOR .env
make run
```

Gmail needs an [App Password](https://myaccount.google.com/apppasswords), not
your account password, and the account must have 2-Step Verification enabled.

## What counts as qualifying

A posting must be **full-time**, a **teacher**, and **elementary**, with
elementary status positively evidenced — either the word "elementary"/
"primary"/"intermediate", or a grade band of 1st–6th. A bare "Science Teacher"
with no grade band is dropped rather than guessed at.

Rejected outright: part-time, aides and paraprofessionals, assistants,
substitutes, special education and student services, speech/psych, counselors,
coaches, administration, maintenance and nutrition, and anything at a junior
high, high school, adult-education or online program.

Four boundary cases are **configuration**, not hardcoded rules, because the
right answer only really becomes clear once you have watched a few real
postings go by. Defaults are in `.env.example`:

| Setting | Default | Covers |
| --- | --- | --- |
| `INCLUDE_TEMPORARY` | `true` | full-time roles with a fixed end date |
| `INCLUDE_KINDERGARTEN` | `false` | kindergarten |
| `INCLUDE_PRESCHOOL` | `false` | preschool / pre-K |
| `INCLUDE_IMMERSION` | `false` | dual-language immersion (DLI) |
| `INCLUDE_SPECIALISTS` | `false` | music, art, PE, library |
| `INCLUDE_INTERNAL` | `true` | employee-only postings, labelled in the email |

Flip one and re-run `make dry-run` to see the effect immediately. With the
defaults above, a live run on 2026-10-16 scanned 202 postings and matched none;
turning on kindergarten and immersion matched two.

Every run reports **all** currently-open qualifying postings, so the same job
appears each day until it closes. There is no state file to manage. If the
repetition becomes annoying, the thing to add is a seen-IDs store and a
`--new-only` flag.

By default nothing is sent on a day with no matches. Set `SEND_WHEN_EMPTY=true`
(or pass `--send-when-empty`) if you would rather get a daily "nothing today"
note as proof the job ran.

## Scheduling

The script is a single idempotent command, so plain cron is enough. To run at
6:30am daily:

```cron
30 6 * * * cd /home/adam-bushman/AllProjects/school-job-scraper && /usr/bin/python3 -m school_job_scraper.main >> /var/tmp/school-job-scraper.log 2>&1
```

Cron runs with a minimal environment, so either keep using the `.env` file (it
is read relative to the working directory, hence the `cd`) or set the variables
in the crontab itself. A non-zero exit status means the email could not be sent.

## Development

```bash
make test     # pytest
make lint     # black --check and mypy --strict
make check    # both
make format   # rewrite with black
```

`make install` points `core.hooksPath` at `.githooks`, so black, mypy and the
full test suite run on every commit and a failure blocks it. Use
`git commit --no-verify` to bypass deliberately. A `.pre-commit-config.yaml` is
included for anyone who prefers the pre-commit framework instead.

### Layout

```
src/school_job_scraper/
  models.py      JobPosting, District, the JsonFetcher protocol
  config.py      settings and filter toggles, read from the environment
  filters.py     the qualification rules
  pipeline.py    the two-stage scan
  render.py      email subject, text body, HTML body
  http.py        headers, timeouts, retries
  sources/       one adapter per board
  notify/        SMTP and console delivery
tests/
  fixtures/      real API payloads captured 2026-10-16
```

### Notes for whoever maintains this

Things that cost time to work out, worth not rediscovering:

- SchoolSpring's `domainName` parameter needs the **full host**
  (`wsd.schoolspring.com`). The short form (`wsd`) returns an empty list rather
  than an error, which looks exactly like "no jobs today".
- Its `jobtype` and `gradelevel` filters work, but only against metadata the
  districts populate inconsistently — just one of Weber's 129 live postings set
  a grade level. Trusting them server-side would silently drop postings, so the
  whole board is fetched and filtered locally.
- Davis's endpoint is at the site root (`/Jobs/GetList`). The `/api/` prefix
  redirects to an error page. It caps `pageSize` at 50 regardless of what is
  requested, so pagination is required — the live board had 57 postings.
- Davis publishes no full-time/part-time field at all; part-time there shows up
  only as text in the title. Its `category` field (`LICENSED EDUCATOR` /
  `CLASSIFIED` / `SUBSTITUTE`) is the strongest signal on that board.
- Ogden tags every posting `[LIC####]` (licensed) or `[ESP####]` (support
  professional), which is nearly free precision.
- Weber marks "open until filled" roles with a close date of 2050-01-01. That
  sentinel is discarded rather than shown as a deadline.
- Filtering runs twice on purpose: the listing payload carries only title,
  school and date, which rejects ~120 of Weber's 129 postings with no extra
  request. Only survivors get a detail lookup, whose `jobTypeName` is
  authoritative and can still overturn the first pass.
