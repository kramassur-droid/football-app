"""Client for The Odds API (the-odds-api.com).

Free tier: 500 requests/month. Get a key at https://the-odds-api.com/
Set env var ODDS_API_KEY before starting the backend.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import requests

BASE_URL = "https://api.the-odds-api.com/v4"

# Map Odds-API team names -> football-data.co.uk team names.
# These two sources disagree on spelling for some teams; patch the common ones.
# Extend as you spot more mismatches in logs.
TEAM_ALIASES = {
    # Premier League
    'Manchester United': 'Man United', 'Manchester City': 'Man City',
    'Tottenham Hotspur': 'Tottenham', 'Newcastle United': 'Newcastle',
    'Wolverhampton Wanderers': 'Wolves', 'Brighton and Hove Albion': 'Brighton',
    'West Ham United': 'West Ham', 'Nottingham Forest': "Nott'm Forest",
    'Leicester City': 'Leicester', 'Leeds United': 'Leeds',
    # La Liga
    'Atletico Madrid': 'Ath Madrid', 'Athletic Bilbao': 'Ath Bilbao',
    'Real Sociedad': 'Sociedad', 'Real Betis': 'Betis',
    'Rayo Vallecano': 'Vallecano', 'Real Valladolid': 'Valladolid',
    # Serie A
    'Internazionale': 'Inter', 'AC Milan': 'Milan',
    'Hellas Verona': 'Verona',
    # Bundesliga
    'Bayern Munich': 'Bayern Munich', 'Borussia Dortmund': 'Dortmund',
    'Bayer Leverkusen': 'Leverkusen', 'Eintracht Frankfurt': 'Ein Frankfurt',
    'Borussia Monchengladbach': "M'gladbach", 'VfB Stuttgart': 'Stuttgart',
    'VfL Wolfsburg': 'Wolfsburg', '1. FC Heidenheim': 'Heidenheim',
    '1. FC Union Berlin': 'Union Berlin',
    # Ligue 1
    'Paris Saint Germain': 'Paris SG', 'Olympique Marseille': 'Marseille',
    'Olympique Lyonnais': 'Lyon',
}


def _norm(name: str) -> str:
    return TEAM_ALIASES.get(name, name)


class OddsClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ODDS_API_KEY')

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def fixtures_with_odds(self, sport_key: str,
                           regions: str = 'uk,eu',
                           markets: str = 'h2h') -> List[Dict]:
        """Upcoming fixtures for a league with best decimal odds.

        Returns list of {home, away, commence_time, odds: {home, draw, away}}.
        """
        if not self.api_key:
            return []
        url = f"{BASE_URL}/sports/{sport_key}/odds"
        params = {
            'apiKey': self.api_key,
            'regions': regions,
            'markets': markets,
            'oddsFormat': 'decimal',
            'dateFormat': 'iso',
        }
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 404:
                return []
            r.raise_for_status()
        except Exception as e:
            print(f"Odds API error for {sport_key}: {e}")
            return []

        out = []
        for event in r.json():
            home = _norm(event['home_team'])
            away = _norm(event['away_team'])

            # Aggregate best odds across bookmakers
            best = {'home': None, 'draw': None, 'away': None}
            for bk in event.get('bookmakers', []):
                for market in bk.get('markets', []):
                    if market['key'] != 'h2h':
                        continue
                    for outcome in market['outcomes']:
                        name = outcome['name']; price = outcome['price']
                        key = None
                        if name == event['home_team']:
                            key = 'home'
                        elif name == event['away_team']:
                            key = 'away'
                        elif name == 'Draw':
                            key = 'draw'
                        if key and (best[key] is None or price > best[key]):
                            best[key] = price

            out.append({
                'home': home,
                'away': away,
                'home_raw': event['home_team'],
                'away_raw': event['away_team'],
                'commence_time': event['commence_time'],
                'odds': best,
            })
        return out
