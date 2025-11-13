import pandas as pd
from math import floor, inf
from pathlib import Path

PREFS_PATH = Path(__file__).resolve().parents[1] / "prefs" / "preferences.csv"

def load_prefs():
    prefs = pd.read_csv(PREFS_PATH)
    prefs.columns = prefs.columns.str.strip()
    for c in ("traveler_type","preferred_category","weight"):
        if c not in prefs.columns:
            raise ValueError(f"Missing column '{c}' in preferences.csv")
    prefs["traveler_type"] = prefs["traveler_type"].astype("string").str.strip()
    prefs["preferred_category"] = prefs["preferred_category"].astype("string").str.strip()
    prefs["weight"] = pd.to_numeric(prefs["weight"], errors="coerce").fillna(0).astype(int)
    prefs["cat_norm"] = prefs["preferred_category"].str.lower().str.replace(" ", "_")
    return prefs

PREFS = load_prefs()

def proportional_quotas(weights, n_total):
    total_w = sum(w for _, w in weights)
    if total_w == 0 or n_total <= 0:
        return {c: 0 for c, _ in weights}
    raw = {c: (n_total * w) / total_w for c, w in weights}
    base = {c: floor(v) for c, v in raw.items()}
    rem = n_total - sum(base.values())
    if rem > 0:
        frac = sorted(((raw[c] - base[c], c) for c, _ in weights), reverse=True)
        for i in range(rem):
            base[frac[i % len(frac)][1]] += 1
    return base

def build_weighted_sequence(traveler_type: str, days: int):
    tprefs = PREFS.loc[PREFS["traveler_type"].str.lower() == traveler_type.lower()].copy()
    if tprefs.empty:
        return []

    cat_weights = (
        tprefs.groupby(["cat_norm"], as_index=False)["weight"]
             .max()
             .sort_values(["weight","cat_norm"], ascending=[False,True])
    )
    weights = list(zip(cat_weights["cat_norm"], cat_weights["weight"]))
    weight_map = dict(weights)

    n_keep = max(int(days) * 3 - 1, 0)  # 3 slots/day minus 1 buffer
    if n_keep == 0:
        return []

    quotas = proportional_quotas(weights, n_keep)
    quotas = {c: q for c, q in quotas.items() if q > 0}

    result, last = [], None
    while len(result) < n_keep and quotas:
        cand = sorted(quotas.items(), key=lambda kv: (-kv[1], -weight_map.get(kv, -inf), kv))
        placed = False
        for cat, q in cand:
            if cat != last and q > 0:
                result.append(cat)
                quotas[cat] = q - 1
                if quotas[cat] <= 0: del quotas[cat]
                last = cat
                placed = True
                break
        if not placed:
            cat, q = max(quotas.items(), key=lambda kv: (kv[1], weight_map.get(kv, -inf)))
            result.append(cat)
            quotas[cat] = q - 1
            if quotas[cat] <= 0: del quotas[cat]
            last = cat
    return result[:n_keep]

def sequence_to_days(seq, days):
    per = []
    i = 0
    for _ in range(days):
        per.append(seq[i:i+3])
        i += 3
    return per
