"""Train a Poisson model for each supported league and save to disk.

Run this:
  1) Once at initial setup
  2) Weekly (e.g., every Monday) to keep models fresh with recent results

Creates models/<LEAGUE_CODE>.pkl files.
"""
from __future__ import annotations

from pathlib import Path

from data_loader import LEAGUES, download_league
from predictor import PoissonPredictor

MODELS_DIR = Path(__file__).parent / 'models'
CACHE_DIR = Path(__file__).parent / 'cache'


def train_all(n_seasons: int = 3):
    MODELS_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)

    results = []
    for code, info in LEAGUES.items():
        print(f"\n=== {info['name']} ({code}) ===")
        df = download_league(code, n_seasons=n_seasons, cache_dir=CACHE_DIR)
        if len(df) < 50:
            print(f"  skipped - only {len(df)} matches")
            continue

        print(f"  Training on {len(df)} matches across {df['HomeTeam'].nunique()} teams")
        model = PoissonPredictor(use_dixon_coles=True).fit(df, league=code)
        path = MODELS_DIR / f"{code}.pkl"
        model.save(str(path))
        print(f"  Saved {path.name}  |  home_adv={model.home_advantage:.3f}  rho={model.rho:.3f}")
        results.append((code, len(df)))

    print(f"\nTrained {len(results)} leagues.")


if __name__ == '__main__':
    train_all(n_seasons=3)
