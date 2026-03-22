# Google Play Review Crawler

Crawl Google Play Store reviews by app name, URL, or package ID. Built with Python + Streamlit.

## Features

- Input: Google Play URL, package ID, or app name
- Crawl up to 1000 reviews per language
- Support for 13 languages or "All languages" mode
- Store reviews in SQLite (local) or in-memory (cloud)
- Filter by star rating
- Export CSV / JSON

## Run locally

```bash
pip install -r requirements.txt
streamlit run src/app.py
```
