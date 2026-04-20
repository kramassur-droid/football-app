"""Poisson / Dixon-Coles football match predictor."""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson


class PoissonPredictor:
    """Dixon-Coles (1997) extension of the basic Poisson goals model."""

    def __init__(self, use_dixon_coles: bool = True):
        self.use_dixon_coles = use_dixon_coles
        self.team_params: Dict[str, Dict[str, float]] = {}
        self.home_advantage = 0.3
        self.rho = -0.1
        self.league: Optional[str] = None

    def fit(self, df: pd.DataFrame, league: Optional[str] = None, max_iter: int = 200):
        """Fit via MLE. df needs: HomeTeam, AwayTeam, FTHG, FTAG."""
        self.league = league
        teams = sorted(set(df['HomeTeam']).union(df['AwayTeam']))
        n = len(teams)
        idx = {t: i for i, t in enumerate(teams)}

        home_ids = df['HomeTeam'].map(idx).values
        away_ids = df['AwayTeam'].map(idx).values
        hg = df['FTHG'].values.astype(int)
        ag = df['FTAG'].values.astype(int)

        x0 = np.concatenate([np.zeros(n), np.zeros(n), [0.3], [-0.1]])

        def neg_log_lik(params):
            atk = params[:n]; dfn = params[n:2*n]
            ha = params[2*n]; rho = params[2*n + 1]
            lam_h = np.clip(np.exp(atk[home_ids] + dfn[away_ids] + ha), 0.01, 10)
            lam_a = np.clip(np.exp(atk[away_ids] + dfn[home_ids]), 0.01, 10)
            log_p = poisson.logpmf(hg, lam_h) + poisson.logpmf(ag, lam_a)
            if self.use_dixon_coles:
                adj = self._dc_adj_vec(hg, ag, lam_h, lam_a, rho)
                log_p = log_p + np.log(np.clip(adj, 1e-10, None))
            return -np.sum(log_p)

        constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x[:n])}]
        result = minimize(neg_log_lik, x0, constraints=constraints,
                          method='SLSQP', options={'maxiter': max_iter})
        p = result.x
        self.team_params = {t: {'attack': p[idx[t]], 'defense': p[n + idx[t]]}
                            for t in teams}
        self.home_advantage = p[2*n]
        self.rho = p[2*n + 1]
        return self

    @staticmethod
    def _dc_adj_vec(hg, ag, lam_h, lam_a, rho):
        adj = np.ones_like(lam_h)
        m00 = (hg == 0) & (ag == 0); m01 = (hg == 0) & (ag == 1)
        m10 = (hg == 1) & (ag == 0); m11 = (hg == 1) & (ag == 1)
        adj[m00] = 1 - lam_h[m00] * lam_a[m00] * rho
        adj[m01] = 1 + lam_h[m01] * rho
        adj[m10] = 1 + lam_a[m10] * rho
        adj[m11] = 1 - rho
        return adj

    def known_teams(self) -> List[str]:
        return sorted(self.team_params.keys())

    def predict_match(self, home: str, away: str, max_goals: int = 6) -> Dict:
        if home not in self.team_params or away not in self.team_params:
            missing = [t for t in (home, away) if t not in self.team_params]
            raise ValueError(f"Unknown team(s): {missing}")

        h = self.team_params[home]; a = self.team_params[away]
        lam_h = float(np.exp(h['attack'] + a['defense'] + self.home_advantage))
        lam_a = float(np.exp(a['attack'] + h['defense']))

        i = np.arange(max_goals + 1)
        p_h = poisson.pmf(i, lam_h); p_a = poisson.pmf(i, lam_a)
        m = np.outer(p_h, p_a)
        if self.use_dixon_coles:
            m[0, 0] *= 1 - lam_h * lam_a * self.rho
            m[0, 1] *= 1 + lam_h * self.rho
            m[1, 0] *= 1 + lam_a * self.rho
            m[1, 1] *= 1 - self.rho
        m /= m.sum()

        home_win = float(np.tril(m, -1).sum())
        draw = float(np.diag(m).sum())
        away_win = float(np.triu(m, 1).sum())
        goals_grid = np.add.outer(np.arange(max_goals+1), np.arange(max_goals+1))
        over_2_5 = float(m[goals_grid > 2].sum())
        under_2_5 = float(m[goals_grid <= 2].sum())
        btts_yes = float(m[1:, 1:].sum())

        flat = sorted(
            [(float(m[i, j]), f"{i}-{j}") for i in range(max_goals + 1)
             for j in range(max_goals + 1)],
            reverse=True
        )
        top = [{'score': s, 'pct': round(p * 100, 1)} for p, s in flat[:5]]

        return {
            'home': home, 'away': away,
            'expected_goals': {'home': round(lam_h, 2), 'away': round(lam_a, 2)},
            'win_probs': {
                'home': round(home_win * 100, 1),
                'draw': round(draw * 100, 1),
                'away': round(away_win * 100, 1),
            },
            'goals': {
                'over_2_5': round(over_2_5 * 100, 1),
                'under_2_5': round(under_2_5 * 100, 1),
            },
            'btts': {
                'yes': round(btts_yes * 100, 1),
                'no': round((1 - btts_yes) * 100, 1),
            },
            'top_scorelines': top,
        }

    def value_bets(self, home: str, away: str, odds: Dict[str, float],
                   min_edge: float = 3.0) -> Dict:
        """Compare model to decimal odds. odds keys: home, draw, away."""
        pred = self.predict_match(home, away)
        wp = pred['win_probs']
        model_p = {'home': wp['home']/100, 'draw': wp['draw']/100, 'away': wp['away']/100}
        out = {}
        for k in ('home', 'draw', 'away'):
            if k not in odds or odds[k] is None:
                continue
            edge = (model_p[k] * odds[k] - 1) * 100
            out[k] = {
                'odds': odds[k],
                'model_prob': round(model_p[k] * 100, 1),
                'implied_prob': round(100 / odds[k], 1),
                'edge_pct': round(edge, 1),
                'is_value': edge >= min_edge,
            }
        return out

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: str) -> 'PoissonPredictor':
        with open(path, 'rb') as f:
            return pickle.load(f)
