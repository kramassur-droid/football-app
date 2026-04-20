# Footy Predict

A personal football prediction app — Poisson/Dixon-Coles model, live bookmaker odds, value bet detection, installable on your phone as a PWA.

Covers 16 leagues: Premier League, Championship, La Liga (1 & 2), Bundesliga (1 & 2), Serie A & B, Ligue 1 & 2, Eredivisie, Belgian Pro League, Primeira Liga, Super Lig, Greek Super League, Scottish Premiership.

---

## What you need before starting

1. **The Odds API key** — free tier, 500 requests/month. Sign up at https://the-odds-api.com/ and copy your key.
2. **GitHub account** — to host the code (free).
3. **Railway account** — to deploy (free tier, no credit card). Sign up at https://railway.app with your GitHub.

Total cost: £0.

---

## Deploy to Railway (recommended, ~15 min)

### Step 1 — Push to GitHub

```bash
cd football-app
git init
git add .
git commit -m "Initial"
```

Create a new empty repo on GitHub (e.g., `football-app`), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/football-app.git
git branch -M main
git push -u origin main
```

### Step 2 — Deploy on Railway

1. Go to railway.app → **New Project** → **Deploy from GitHub repo** → select `football-app`.
2. Railway detects Python automatically and starts building.
3. Once built, click the service → **Variables** → **New Variable**:
   - Name: `ODDS_API_KEY`
   - Value: *your key from the-odds-api.com*
4. Click the service → **Settings** → **Networking** → **Generate Domain**.
   You'll get a URL like `football-app-production.up.railway.app`.
5. First boot runs `train.py` which downloads ~3 seasons of history per league and trains models. Takes 3–5 minutes. Watch the **Deploy Logs**.

### Step 3 — Install on your Samsung

1. Open the Railway URL in Chrome on your phone.
2. Tap the **⋮** menu → **Add to Home screen**.
3. Icon appears on your home screen. Tap it — opens fullscreen like a real app.

Done. You have a football predictor installed on your phone, backed by a 24/7 cloud server.

---

## Run locally (for testing or laptop-only use)

```bash
pip install -r requirements.txt
export ODDS_API_KEY=your_key_here   # Windows: set ODDS_API_KEY=...
python train.py                     # One-time, ~5 min
uvicorn main:app --reload           # Server at http://localhost:8000
```

Open `http://localhost:8000` in a browser. To reach it from your phone on the same Wi-Fi:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Then from your phone visit `http://<your-laptop-ip>:8000`. The phone will only work while your laptop is on and on the same network.

---

## Keeping predictions fresh

Models improve as more recent matches are added. Retrain weekly:

**On Railway:** Redeploy the service (Settings → Redeploy). `train.py` runs on every deploy.

**Locally:** Run `python train.py` once a week.

For full automation on Railway, you can use a cron plugin or add a scheduler — but a manual redeploy every Monday takes 10 seconds and is simpler.

---

## How it works

### The model
Dixon-Coles (1997) extension of Poisson:
- Each team has an **attack** parameter (how many goals it scores) and **defense** parameter (how many it concedes).
- Expected home goals: `exp(attack_home + defense_away + home_advantage)`.
- Dixon-Coles correction adjusts low-scoring outcomes (0-0, 1-0, 0-1, 1-1) which are correlated in reality.
- Fitted by maximum likelihood on ~3 seasons of historical match results.

Realistic accuracy on 1X2 outcomes: **52–58%**. Bookmakers typically hit ~55%. Anyone claiming 80%+ is cherry-picking.

### Value bets
For every match, the app:
1. Fetches best available bookmaker decimal odds across UK/EU books.
2. Converts odds to implied probability (`1/odds`).
3. Compares to model probability.
4. Flags any outcome where `model_prob × odds > 1.03` as value (+3% edge).

A positive edge means you'd expect to profit over many bets at those odds — **over many bets**. Any individual bet is still a coin flip with variance. This is an analytical tool, not a money printer.

### Data sources
- **Historical results**: football-data.co.uk (free CSVs, ~20 leagues back to 1993).
- **Live fixtures & odds**: The Odds API (free tier 500 req/month — that's ~16 requests per league per month if you refresh once daily, fine for 16 leagues at a weekly refresh).

---

## Customising

### Adding a league
1. Find its football-data.co.uk code and its-odds-api.com `sport_key`.
2. Add an entry to the `LEAGUES` dict in `data_loader.py`.
3. Redeploy — `train.py` picks it up automatically.

### Fixing team name mismatches
If you see "⚠️ Unknown team" warnings, The Odds API and football-data.co.uk spell that team's name differently. Add an entry to `TEAM_ALIASES` in `odds_client.py`:

```python
'Real Madrid CF': 'Real Madrid',
```

Left side is what The Odds API returns; right side is what football-data.co.uk uses.

### Tuning value bet threshold
In `predictor.py`, `value_bets()` defaults to `min_edge=3.0` (3%). Raise to 5–8% for stricter filtering, lower to catch more candidates.

---

## Troubleshooting

**"No trained models"** — `train.py` didn't run or failed. Check Railway logs for network errors fetching football-data.co.uk.

**"ODDS_API_KEY not configured"** — Environment variable wasn't set. Add it in Railway → Variables and redeploy.

**"Unknown team(s)"** — Name mismatch between odds feed and historical data. Add to `TEAM_ALIASES`.

**Odds API returns empty** — Either the league has no imminent fixtures, or you've hit the free-tier monthly quota (500 requests). Check response headers `x-requests-remaining` in Railway logs.

**Predictions look off early season** — Fewer matches to learn from; accuracy improves after ~8–10 games. Consider training on previous 2 seasons plus current (already the default).

---

## Scope & limits

This is a personal tool, not a product. Things it deliberately doesn't do:

- Real-time in-play predictions (would need live minute-by-minute feeds).
- Player-level analysis (would need FBref/Understat scraping + much more data).
- xG-based features (available via FBref but needs a scraper — easy next step).
- Injury/lineup adjustments (API-Football has this; swap it in if you want).
- Tracking your own betting results (add a Postgres table and a UI; fun weekend project).

If you want any of these, the model file is the only thing to change — the frontend and API stay the same.

---

## Disclaimer

Football is high-variance. A good model beats coin-flip but loses often. Never bet money you can't afford to lose. Value bets are an *expected-value* edge over *many* bets, not a guarantee on any single one. Gambling is addictive — if it stops being fun, stop.
