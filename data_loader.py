"""Download & load historical match data from football-data.co.uk.

That site provides free CSVs of results back to 1993 for ~20 leagues.
We download recent seasons, concatenate, and use for training.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests

# League codes on football-data.co.uk and their Odds-API equivalents.
LEAGUES = {
    'E0':  {'name': 'Premier League',     'odds_key': 'soccer_epl'},
    'E1':  {'name': 'Championship',       'odds_key': 'soccer_efl_champ'},
    'SP1': {'name': 'La Liga',            'odds_key': 'soccer_spain_la_liga'},
    'SP2': {'name': 'La Liga 2',          'odds_key': 'soccer_spain_segunda_division'},
    'D1':  {'name': 'Bundesliga',         'odds_key': 'soccer_germany_bundesliga'},
    'D2':  {'name': 'Bundesliga 2',       'odds_key': 'soccer_germany_bundesliga2'},
    'I1':  {'name': 'Serie A',            'odds_key': 'soccer_italy_serie_a'},
    'I2':  {'name': 'Serie B',            'odds_key': 'soccer_italy_serie_b'},
    'F1':  {'name': 'Ligue 1',            'odds_key': 'soccer_france_ligue_one'},
    'F2':  {'name': 'Ligue 2',            'odds_key': 'soccer_france_ligue_two'},
    'N1':  {'name': 'Eredivisie',         'odds_key': 'soccer_netherlands_eredivisie'},
    'B1':  {'name': 'Belgian Pro League', 'odds_key': 'soccer_belgium_first_div'},
    'P1':  {'name': 'Primeira Liga',      'odds_key': 'soccer_portugal_primeira_liga'},
    'T1':  {'name': 'Super Lig',          'odds_key': 'soccer_turkey_super_league'},
    'G1':  {'name': 'Super League Greece','odds_key': 'soccer_greece_super_league'},
    'SC0': {'name': 'Scottish Premiership','odds_key': 'soccer_spl'},
}

BASE_URL = "https://www.football-data.co.uk/mmz4281"


def season_codes(n_seasons: int = 3) -> List[str]:
    """Returns season codes like '2324' for 2023-24. Latest N seasons."""
    import datetime as dt
    now = dt.date.today()
    start_year = now.year if now.month >= 8 else now.year - 1
    codes = []
    for y in range(start_year, start_year - n_seasons, -1):
        codes.append(f"{str(y)[2:]}{str(y+1)[2:]}")
    return codes


def download_league(league_code: str, n_seasons: int = 3,
                    cache_dir: Optional[Path] = None) -> pd.DataFrame:
    """Download historical data for one league."""
    cache_dir = Path(cache_dir) if cache_dir else None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)

    dfs = []
    for season in season_codes(n_seasons):
        url = f"{BASE_URL}/{season}/{league_code}.csv"
        cache_path = cache_dir / f"{league_code}_{season}.csv" if cache_dir else None

        if cache_path and cache_path.exists():
            df = pd.read_csv(cache_path, encoding='latin-1')
        else:
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                df = pd.read_csv(io.BytesIO(r.content), encoding='latin-1')
                if cache_path:
                    cache_path.write_bytes(r.content)
            except Exception as e:
                print(f"  Skipped {league_code} {season}: {e}")
                continue

        cols = ['HomeTeam', 'AwayTeam', 'FTHG', 'FTAG']
        if not all(c in df.columns for c in cols):
            continue
        df = df[cols].dropna()
        df['FTHG'] = df['FTHG'].astype(int)
        df['FTAG'] = df['FTAG'].astype(int)
        df['League'] = league_code
        dfs.append(df)

    if not dfs:
        return pd.DataFrame(columns=['HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'League'])
    return pd.concat(dfs, ignore_index=True)


def download_all(n_seasons: int = 3, cache_dir: Optional[Path] = None) -> pd.DataFrame:
    """Download all supported leagues."""
    frames = []
    for code in LEAGUES:
        print(f"Fetching {LEAGUES[code]['name']} ({code})...")
        df = download_league(code, n_seasons, cache_dir)
        if len(df):
            frames.append(df)
            print(f"  {len(df)} matches")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
