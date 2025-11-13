import os
from typing import Optional, Tuple, List, Dict, Any
from .preferences import build_weighted_sequence, sequence_to_days
from .places import geocode_city, candidates_for_category, nearest_route
from .weather import daily_forecast, prefer_indoor_if_rain

from groq import Groq

GROQ_KEY = os.getenv("GROQ_API_KEY")

def score_candidates(start_latlng: Tuple[float,float], items: List[Dict[str,Any]], k=1):
    # Score = 0.6*rating_norm + 0.4*(1 - distance_norm)
    if not items:
        return []
    from .places import haversine
    dists = [haversine(start_latlng, (x["lat"], x["lng"])) for x in items]
    ratings = [x.get("rating", 0) for x in items]
    dmin, dmax = min(dists), max(dists)
    rmin, rmax = min(ratings), max(ratings)
    scored = []
    for x, d, r in zip(items, dists, ratings):
        dn = 0 if dmax == dmin else (d - dmin) / (dmax - dmin)
        rn = 0 if rmax == rmin else (r - rmin) / (rmax - rmin)
        score = 0.6 * rn + 0.4 * (1 - dn)
        scored.append((score, x))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [x for _, x in scored[:k]]

def groq_refine(destination: str, latlng, traveler_type: str, days_data: List[Dict[str,Any]]):
    if not GROQ_KEY:
        return None
    client = Groq(api_key=GROQ_KEY)
    # Prepare a compact prompt
    payload = {
        "destination": destination,
        "latlng": {"lat": latlng, "lng": latlng[1]},
        "traveler_type": traveler_type,
        "days": days_data
    }
    system = "You are a concise travel planner. Produce helpful notes and backup alternatives."
    user = f"Refine this plan JSON and add one sentence notes per day and one nearby meal suggestion per slot.\nJSON:\n{payload}"
    chat = client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        temperature=0.2,
        max_tokens=800
    )
    return chat.choices.message.content

def generate_itinerary(traveler_type: str, destination: str, days: int, start_date: Optional[str] = None,
                       stay_latlng: Optional[Tuple[float,float]] = None, use_groq: bool = False):
    # Geocode if stay location not given
    latlng = stay_latlng or geocode_city(destination)
    if not latlng:
        raise ValueError("Could not geocode destination")

    # Build category sequence and split per day
    seq = build_weighted_sequence(traveler_type, days)
    per_day_categories = sequence_to_days(seq, days)

    # Weather summary per day
    forecasts = daily_forecast(latlng[0], latlng[1], days)

    plan = []
    for i, cats in enumerate(per_day_categories):
        cats = [c for c in cats if c]
        # Weather-aware tweak
        fcast = forecasts[i] if i < len(forecasts) else None
        cats = prefer_indoor_if_rain(cats, fcast)

        # Candidates and picks
        day_shortlists = []
        for c in cats:
            cand = candidates_for_category(latlng, latlng[1], c, max_results=10)
            picks = score_candidates(latlng, cand, k=3)  # shortlist
            if picks:
                day_shortlists.append({"category": c, "picks": picks})

        chosen = [sl["picks"] for sl in day_shortlists if sl["picks"]]
        route = nearest_route(latlng, chosen)

        slots = []
        for part, place in zip(["Morning","Afternoon","Evening"], route):
            slots.append({
                "part": part,
                "place": place,
            })

        plan.append({
            "date": forecasts[i]["date"] if i < len(forecasts) and "date" in forecasts[i] else None,
            "weather": fcast,
            "categories": cats,
            "slots": slots,
            "alternatives": [
                {"category": sl["category"], "alts": sl["picks"][1:3]}
                for sl in day_shortlists
            ]
        })

    groq_notes = None
    if use_groq:
        try:
            groq_notes = groq_refine(destination, latlng, traveler_type, plan)
        except Exception:
            groq_notes = None

    return {
        "destination": destination,
        "latlng": {"lat": latlng[0], "lng": latlng[1]},
        "traveler_type": traveler_type,
        "plan": plan,
        "llm_notes": groq_notes
    }
