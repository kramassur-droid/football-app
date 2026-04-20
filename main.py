"""FastAPI backend for the football predictor PWA.

Endpoints:
  GET /api/leagues                 -> list available leagues with trained models
  GET /api/fixtures?league=E0      -> upcoming fixtures with odds + predictions
  GET /api/predict/{league}/{home}/{away}  -> single match prediction
  GET /api/teams/{league}          -> list teams known to the model

Static files:
  /                                -> serves static/index.html (the PWA)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from predictor import PoissonPredictor
from data_loader import LEAGUES
from odds_client import OddsClient

BASE = Path(__file__).parent
MODELS_DIR = BASE / 'models'
STATIC_DIR = BASE / 'static'

app = FastAPI(title="Football Predictor API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

odds_client = OddsClient(os.getenv('ODDS_API_KEY'))

# Lazy-loaded model cache: {league_code: PoissonPredictor}
_model_cache: Dict[str, PoissonPredictor] = {}


def get_model(league: str) -> PoissonPredictor:
    if league in _model_cache:
        return _model_cache[league]
    path = MODELS_DIR / f"{league}.pkl"
    if not path.exists():
        raise HTTPException(404, f"No trained model for league '{league}'. Run train.py first.")
    m = PoissonPredictor.load(str(path))
    _model_cache[league] = m
    return m


@app.get("/api/leagues")
def leagues():
    """Leagues with a trained model available."""
    out = []
    for code, info in LEAGUES.items():
        if (MODELS_DIR / f"{code}.pkl").exists():
            out.append({'code': code, 'name': info['name'], 'odds_key': info['odds_key']})
    return {'leagues': out, 'odds_configured': odds_client.is_configured}


@app.get("/api/teams/{league}")
def teams(league: str):
    return {'league': league, 'teams': get_model(league).known_teams()}


@app.get("/api/predict/{league}/{home}/{away}")
def predict(league: str, home: str, away: str,
            odds_h: Optional[float] = None, odds_d: Optional[float] = None,
            odds_a: Optional[float] = None):
    model = get_model(league)
    try:
        pred = model.predict_match(home, away)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if odds_h and odds_d and odds_a:
        pred['value_bets'] = model.value_bets(home, away,
                                              {'home': odds_h, 'draw': odds_d, 'away': odds_a})
    return pred


@app.get("/api/fixtures")
def fixtures(league: str):
    """Upcoming fixtures in a league, each with prediction + value bet analysis."""
    if league not in LEAGUES:
        raise HTTPException(404, f"Unknown league '{league}'")
    if not odds_client.is_configured:
        raise HTTPException(503, "ODDS_API_KEY not configured on server")

    model = get_model(league)
    sport_key = LEAGUES[league]['odds_key']
    raw = odds_client.fixtures_with_odds(sport_key)

    out = []
    for fx in raw:
        item = {
            'home': fx['home'], 'away': fx['away'],
            'commence_time': fx['commence_time'],
            'odds': fx['odds'],
            'home_raw': fx['home_raw'], 'away_raw': fx['away_raw'],
        }
        try:
            pred = model.predict_match(fx['home'], fx['away'])
            item['prediction'] = pred
            if all(fx['odds'].get(k) for k in ('home', 'draw', 'away')):
                item['value_bets'] = model.value_bets(fx['home'], fx['away'], fx['odds'])
        except ValueError as e:
            item['error'] = str(e)  # Team not recognised
        out.append(item)

    # Sort by kickoff time
    out.sort(key=lambda x: x['commence_time'])
    return {'league': league, 'league_name': LEAGUES[league]['name'], 'fixtures': out}


# --- Static / PWA ---
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def root():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/manifest.json")
    def manifest():
        return FileResponse(STATIC_DIR / "manifest.json")

    @app.get("/sw.js")
    def service_worker():
        return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/api/health")
def health():
    return {'ok': True, 'models_loaded': len(_model_cache),
            'odds_configured': odds_client.is_configured}
