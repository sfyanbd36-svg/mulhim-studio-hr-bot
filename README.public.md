# Mulhim Studio HR Bot

Telegram job board bot for Iraq (Arabic): seekers register a CV once (`/mycv`), get
matching job recommendations, and apply in one tap; companies post jobs with
`/company` + `/postjob`. Auto-forwards applications by email to the announcing
company and to the operator.

## Stack

- Python 3.12, `python-telegram-bot` v22 (long polling), SQLite via `storage.py`
- PDF CVs via `reportlab`; feeds via `match_feed.py`; outreach in `outreach/`
- Runs 24/7 on GitHub Actions (`.github/workflows/live.yml`): hourly scheduled
  chunks (~6h each) with a single concurrency group, so a run is always queued.

## Runtime data

No data lives in this repository. The runner restores `.env`, the SQLite
database, CV files, and outreach state from the private backup repository at
start, and pushes a fresh backup zip at the end of every chunk.

## Local development

```bash
pip install -r requirements
python -m pytest -q tests
python bot.py
```
