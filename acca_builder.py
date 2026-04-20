"""Accumulator (acca) builder.

Given upcoming fixtures + their model predictions + bookmaker odds,
proposes three accas:

  1. SAFE    — only high-probability picks (model_prob >= 0.65).
               Minimises bust risk. Short leg count (3-4).
  2. VALUE   — only positive-edge picks (edge >= 3%).
               Best expected-value chain. Longer (4-5 legs).
  3. MAX_ODDS_SAFE — the highest combined-odds acca where every leg
                     is still "safe" (model_prob >= 0.60) AND the
                     combined probability stays >= 0.30.
"""
from __future__ import annotations

from typing import Dict, List, Optional


def _extract_markets(fixture: Dict) -> List[Dict]:
    """Turn a fixture+prediction+odds bundle into a flat list of available markets.

    Each market is one possible 'leg' in an acca:
      - Home win / Draw / Away win (1X2)
      - Over 2.5 / Under 2.5 goals
      - BTTS yes / no
    """
    if 'prediction' not in fixture:
        return []

    p = fixture['prediction']
    odds = fixture.get('odds') or {}
    home = fixture['home']
    away = fixture['away']
    fixture_id = f"{home}|{away}"
    commence = fixture.get('commence_time')

    markets = []

    def add(key: str, desc: str, prob_pct: float, odds_val: Optional[float]):
        if odds_val is None or odds_val <= 1.0:
            return
        prob = prob_pct / 100
        edge = (prob * odds_val - 1) * 100
        markets.append({
            'fixture_id': fixture_id,
            'match': f"{home} v {away}",
            'commence_time': commence,
            'market_key': key,
            'description': desc,
            'model_prob': round(prob_pct, 1),
            'odds': round(odds_val, 2),
            'edge_pct': round(edge, 1),
        })

    # 1X2 — we have odds for these directly
    add('home',  f"{home} to win",            p['win_probs']['home'],  odds.get('home'))
    add('draw',  "Draw",                       p['win_probs']['draw'],  odds.get('draw'))
    add('away',  f"{away} to win",            p['win_probs']['away'],  odds.get('away'))

    # O/U 2.5 and BTTS — h2h odds endpoint doesn't include these,
    # so we derive fair odds from model probability with a 5% margin
    # (approximates what a bookmaker would offer).
    def fair_odds(prob_pct: float, margin: float = 0.05) -> Optional[float]:
        if prob_pct <= 0:
            return None
        return round(1 / ((prob_pct / 100) * (1 + margin)), 2)

    add('over_2_5',  "Over 2.5 goals",  p['goals']['over_2_5'],  fair_odds(p['goals']['over_2_5']))
    add('under_2_5', "Under 2.5 goals", p['goals']['under_2_5'], fair_odds(p['goals']['under_2_5']))
    add('btts_yes',  "Both teams score",     p['btts']['yes'], fair_odds(p['btts']['yes']))
    add('btts_no',   "Clean sheet either side", p['btts']['no'],  fair_odds(p['btts']['no']))

    return markets


def _build_acca(picks: List[Dict]) -> Dict:
    """Compile a list of picks into an acca summary."""
    if not picks:
        return {'legs': [], 'combined_odds': 0, 'combined_prob_pct': 0,
                'edge_pct': 0, 'return_on_10': 0}

    combined_odds = 1.0
    combined_prob = 1.0
    for p in picks:
        combined_odds *= p['odds']
        combined_prob *= p['model_prob'] / 100

    edge = (combined_prob * combined_odds - 1) * 100

    return {
        'legs': picks,
        'combined_odds': round(combined_odds, 2),
        'combined_prob_pct': round(combined_prob * 100, 2),
        'edge_pct': round(edge, 1),
        'return_on_10': round(10 * combined_odds, 2),
    }


def propose_accas(fixtures: List[Dict], max_legs: int = 5, target_legs: Optional[int] = None) -> Dict:
    """Main entry point. Build three proposed accas from a list of fixtures.

    Args:
        fixtures: list of fixture+prediction+odds bundles
        max_legs: upper bound on legs per acca (default 5)
        target_legs: if set, try to build exactly this many legs per acca.
                     Safe acca will relax its threshold downward if not enough
                     picks qualify at 65%.
    """
    all_markets = []
    for f in fixtures:
        all_markets.extend(_extract_markets(f))

    # If target_legs specified, that overrides max_legs as the upper bound.
    cap = target_legs if target_legs else max_legs

    # --- SAFE ACCA ---
    # Only the highest-probability pick per fixture. Start at 65% threshold
    # and relax if we can't fill target_legs.
    thresholds = [65, 60, 55, 50] if target_legs else [65]
    safe_legs: List[Dict] = []
    for threshold in thresholds:
        by_fixture: Dict[str, Dict] = {}
        for m in all_markets:
            if m['model_prob'] < threshold:
                continue
            cur = by_fixture.get(m['fixture_id'])
            if cur is None or m['model_prob'] > cur['model_prob']:
                by_fixture[m['fixture_id']] = m
        candidates = sorted(by_fixture.values(), key=lambda x: -x['model_prob'])
        safe_legs = candidates[:cap]
        if len(safe_legs) >= cap:
            break  # filled at this threshold

    # --- VALUE ACCA ---
    # Top positive-edge picks, one per fixture, relax edge threshold if needed.
    edge_thresholds = [3.0, 1.0, 0.0] if target_legs else [3.0]
    value_legs: List[Dict] = []
    for edge_thr in edge_thresholds:
        by_fixture_val: Dict[str, Dict] = {}
        for m in all_markets:
            if m['edge_pct'] < edge_thr:
                continue
            cur = by_fixture_val.get(m['fixture_id'])
            if cur is None or m['edge_pct'] > cur['edge_pct']:
                by_fixture_val[m['fixture_id']] = m
        candidates = sorted(by_fixture_val.values(), key=lambda x: -x['edge_pct'])
        value_legs = candidates[:cap]
        if len(value_legs) >= cap:
            break

    # --- MAX-ODDS SAFE ACCA ---
    # Greedy: take picks in order of highest odds where model_prob >= 0.60.
    # Stop either at the cap or when adding another leg would push combined prob below 25%.
    safe_pool: Dict[str, Dict] = {}
    for m in all_markets:
        if m['model_prob'] < 60:
            continue
        cur = safe_pool.get(m['fixture_id'])
        if cur is None or m['odds'] > cur['odds']:
            safe_pool[m['fixture_id']] = m
    pool_sorted = sorted(safe_pool.values(), key=lambda x: -x['odds'])
    max_legs_picks: List[Dict] = []
    running_prob = 1.0
    floor = 0.25 if target_legs else 0.30
    for m in pool_sorted:
        next_prob = running_prob * (m['model_prob'] / 100)
        if next_prob < floor and not target_legs:
            if len(max_legs_picks) >= 3:
                break
        max_legs_picks.append(m)
        running_prob = next_prob
        if len(max_legs_picks) >= cap:
            break

    return {
        'safe':          _build_acca(safe_legs),
        'value':         _build_acca(value_legs),
        'max_odds_safe': _build_acca(max_legs_picks),
    }
