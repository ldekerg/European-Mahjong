# European Mahjong Association — Ranking App

A web application that reimplements the [EMA (European Mahjong Association)](http://mahjong-europe.org) player ranking system, built from data scraped from the official EMA website. The goal is to provide a richer, more interactive interface than the original EMA pages, with historical tracking, player statistics, and a Hall of Fame.

## Features

- **Live ranking** — weekly MCR and RCR rankings with position delta, active tournament count, and podium icons
- **Player pages** — full tournament history, ranking evolution chart (Chart.js), career stats, score max/best rank highlights
- **Tournament pages** — results, participants, coefficient, filterable list (active / all / special)
- **Hall of Fame** — medals table, weeks-at-the-top streaks (all-time and current), OEMC/WMC/OERC/WRC championship results
- **Player list** — searchable and sortable by name, country, MCR/RCR tournament count
- **Interactive map** — Leaflet.js map of tournament locations by country

## Ranking Algorithm

The EMA ranking score is computed as `0.5 × Part A + 0.5 × Part B` over the **104 active weeks** prior to the ranking date (excluding the COVID freeze period).

- **Part A** — top 5 tournaments + ceil(80% of the rest), weighted average by `ranking` points, tiebreak: lower `poids` wins
- **Part B** — top 4 tournaments, weighted average by `ranking` points, tiebreak: higher `poids` wins

A tournament becomes active the Monday of the week after it ends and stays active for 104 non-freeze weeks.

- **COVID freeze** — the 2020-03-02 → 2022-03-28 freeze period is correctly excluded from the 104-week ranking window and treated as continuity in streak calculations

The algorithm was reverse-engineered and calibrated against known EMA reference scores (see [`docs/freeze_covid_calibration.md`](docs/freeze_covid_calibration.md)).

## Project Structure

```
.
├── database.py              # SQLAlchemy engine + session
├── models.py                # ORM models (Joueur, Tournoi, Resultat, ClassementHistorique, …)
├── ranking.py               # Core ranking algorithm + COVID freeze constants
├── start.sh                 # Start the dev server (uvicorn)
│
├── app/
│   ├── main.py              # FastAPI app, route registration
│   ├── templates_config.py  # Jinja2 environment + custom filters
│   ├── static/
│   │   └── style.css        # CSS variables, dark mode, responsive layout
│   ├── routes/
│   │   ├── joueurs.py       # /joueurs/ — player list + detail + aperçu AJAX
│   │   ├── tournois.py      # /tournois/ — tournament list + detail
│   │   └── hallfame.py      # /hallfame/ — Hall of Fame (medals, streaks, championships)
│   └── templates/
│       ├── base.html        # Base layout, navbar, dark mode toggle
│       ├── accueil.html     # Weekly ranking page with week picker
│       ├── hallfame.html    # Hall of Fame
│       ├── joueurs/         # Player list, detail, aperçu panel
│       └── tournois/        # Tournament list, detail
│
├── scripts/
│   ├── import_ema.py        # Scrape tournament data from mahjong-europe.org
│   ├── import_all.sh        # Full import pipeline (MCR + RCR)
│   ├── calcul_historique.py # Compute weekly rankings for all historical weeks
│   ├── geocode.py           # Geocode tournament cities via Nominatim (OSM)
│   ├── detect_nationalite.py# Detect player nationality changes
│   └── migrate.py           # DB schema migrations
│
└── docs/
    └── freeze_covid_calibration.md   # Calibration notes for the COVID freeze period
```

## Tech Stack

| Layer | Library |
|-------|---------|
| Web framework | FastAPI 0.136 + Starlette |
| Templating | Jinja2 3.1 |
| ORM | SQLAlchemy 2.0 |
| Database | SQLite |
| Server | Uvicorn |
| Scraping | requests + BeautifulSoup4 |
| Charts | Chart.js (CDN) |
| Map | Leaflet.js (CDN) |

## Getting Started

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install fastapi starlette uvicorn sqlalchemy jinja2 requests beautifulsoup4 aiofiles
```

### 2. Import tournament data

```bash
cd scripts
./import_all.sh            # scrape all MCR + RCR tournaments from mahjong-europe.org
python3 geocode.py         # geocode tournament cities (requires internet)
```

### 3. Compute historical rankings

```bash
python3 scripts/calcul_historique.py   # fills classement_historique table (takes a few minutes)
```

### 4. Run the app

```bash
./start.sh
# → http://localhost:8000
```

## Data Source

All tournament and player data is scraped from [mahjong-europe.org](http://mahjong-europe.org). This project is not affiliated with the EMA.
