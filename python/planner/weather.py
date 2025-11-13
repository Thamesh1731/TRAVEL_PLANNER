import os
import requests
from collections import defaultdict
from datetime import datetime, timezone

OWM_KEY = os.getenv("OPENWEATHER_API_KEY")

def daily_forecast(lat: float, lng: float, days: int):
    """
    Aggregates OpenWeather 5-day/3-hour forecast into daily summaries.
    """
    if not OWM_KEY:
        raise RuntimeError("OPENWEATHER_API_KEY not set")
    url = "https://api.openweathermap.org/data/2.5/forecast"
    r = requests.get(url, params={"lat": lat, "lon": lng, "appid": OWM_KEY, "units": "metric"}, timeout=25)
    r.raise_for_status()
    data = r.json()

    buckets = defaultdict(lambda: {"temps": [], "pop": [], "weather": []})
    for it in data.get("list", []):
        dt = datetime.fromtimestamp(it["dt"], tz=timezone.utc).date()
        main = it.get("main", {})
        buckets[dt]["temps"].append(main.get("temp"))
        buckets[dt]["pop"].append(it.get("pop", 0))
        w = it.get("weather", [])
        if w:
            buckets[dt]["weather"].append(w[0].get("main"))

    out = []
    for d in sorted(buckets.keys())[:days]:
        rec = buckets[d]
        temps = [t for t in rec["temps"] if t is not None]
        pops  = [p for p in rec["pop"] if p is not None]
        avg_temp = round(sum(temps)/len(temps), 1) if temps else None
        avg_pop  = round(sum(pops)/len(pops), 2) if pops else None
        cond = max(set(rec["weather"]), key=rec["weather"].count) if rec["weather"] else None
        out.append({"date": d.isoformat(), "avg_temp_c": avg_temp, "avg_pop": avg_pop, "condition": cond})
    return out

INDOOR_CATS = {"museums","cafes","shopping_malls","markets","temples","theaters","cultural_centers","aquariums","science_centers","libraries","art_galleries"}

def prefer_indoor_if_rain(categories, forecast):
    """
    Simple reorder: if high rain probability, move indoor-first categories to earlier slots in the day.
    """
    if not forecast or forecast.get("avg_pop") is None:
        return categories
    rainy = forecast["avg_pop"] >= 0.5
    if not rainy:
        return categories
    indoors = [c for c in categories if c in INDOOR_CATS]
    outdoors = [c for c in categories if c not in INDOOR_CATS]
    # morning/afternoon/evening: indoor first if rainy
    mixed = (indoors + outdoors)[:3]
    return mixed + categories[3:]
