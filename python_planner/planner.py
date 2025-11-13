# planner.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
from math import ceil
import requests, os

# Optional: Groq import handled lazily
try:
    from groq import Groq
    HAS_GROQ = True
except Exception:
    HAS_GROQ = False

app = FastAPI(title="Travel Planner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Configuration: keys & urls
# -------------------------
# You can keep these hardcoded for testing or set them as environment variables.
SERVICE_KEY = "YOUR_KEY"
OPENWEATHER_KEY = "YOUR_KEY"
GROQ_KEY = "YOUR_KEY"

FSQ_SEARCH_URL = "https://places-api.foursquare.com/places/search"
OW_GEOCODE_URL = "http://api.openweathermap.org/geo/1.0/direct"
OW_ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall"

# -------------------------
# Models
# -------------------------
class PlanRequest(BaseModel):
    traveler_type: str = Field(..., alias="type")
    destination: str = Field(..., alias="location")
    days: int
    stay_lat: Optional[float] = None
    stay_lng: Optional[float] = None
    use_groq: Optional[bool] = False

    class Config:
        populate_by_name = True

class DayPlan(BaseModel):
    day: int
    date: str
    activities: List[str]
    weather: Optional[str] = None

class PlanResponse(BaseModel):
    destination: str
    traveler_type: str
    days: int
    plan: List[DayPlan]
    notes: Optional[str] = None

# -------------------------
# Helpers
# -------------------------
def geocode_location(place: str):
    """Try OpenWeather geocoding, fallback to Nominatim."""
    if OPENWEATHER_KEY:
        try:
            r = requests.get(OW_GEOCODE_URL, params={"q": place, "limit": 1, "appid": OPENWEATHER_KEY}, timeout=10)
            if r.status_code == 200:
                j = r.json()
                if j:
                    return j[0]["lat"], j[0]["lon"]
        except Exception:
            pass

    # Nominatim fallback
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                          params={"q": place, "format": "json", "limit": 1},
                          headers={"User-Agent": "TravelPlanner/1.0"},
                          timeout=10)
        if r.status_code == 200:
            j = r.json()
            if j:
                return float(j[0]["lat"]), float(j[0]["lon"])
    except Exception:
        pass

    return None

def fsq_search(lat, lng, traveler_type="solo", limit=20):
    """Fetch places from Foursquare API with traveler-type heuristics."""
    if not SERVICE_KEY:
        raise RuntimeError("SERVICE_KEY not set")

    # Map traveler type → query keywords instead of category IDs
    query_map = {
        "solo": "museum,park,landmark",
        "family": "zoo,amusement,park,museum",
        "couple": "scenic,romantic,restaurant,cafe",
        "friends": "nightlife,bar,club,restaurant",
    }
    query = query_map.get(traveler_type.lower(), "attractions")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {SERVICE_KEY}",
        "X-Places-Api-Version": "2023-12-01"
    }
    params = {"ll": f"{lat},{lng}", "limit": limit, "query": query}

    r = requests.get(FSQ_SEARCH_URL, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    results = []
    for p in data.get("results", [])[:limit]:
        loc = p.get("geocodes", {}).get("main", {})
        results.append({
            "id": p.get("fsq_id"),
            "name": p.get("name"),
            "lat": loc.get("latitude"),
            "lng": loc.get("longitude"),
            "categories": [c.get("name") for c in p.get("categories", [])],
        })
    return results


def openweather_forecast(lat, lon, days=3):
    if not OPENWEATHER_KEY:
        raise RuntimeError("OPENWEATHER_API_KEY not set")
    params = {"lat": lat, "lon": lon, "units": "metric", "appid": OPENWEATHER_KEY, "exclude": "minutely,hourly,alerts"}
    r = requests.get(OW_ONECALL_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    # return list of short descriptions for days
    forecasts = []
    for i, d in enumerate(data.get("daily", [])[:days]):
        desc = d.get("weather", [{}])[0].get("description", "Clear")
        temp = d.get("temp", {}).get("day")
        forecasts.append(f"{desc.capitalize()}" + (f", {temp}°C" if temp is not None else ""))
    return forecasts

def groq_generate_notes(req: PlanRequest, plan: List[DayPlan]):
    """Generate a friendly itinerary summary using Groq if available."""
    if not HAS_GROQ and not GROQ_KEY:
        return None
    api_key = GROQ_KEY if GROQ_KEY else None
    try:
        client = Groq(api_key=api_key) if HAS_GROQ else Groq(api_key=api_key)
    except Exception:
        # If import exists but initialization fails, just return None
        return None

    plan_text = "\n".join([f"Day {p.day} ({p.date}): {', '.join(p.activities)} (Weather: {p.weather})" for p in plan])
    prompt = f"""
You are a helpful travel assistant. Create a concise {req.days}-day itinerary summary for a {req.traveler_type} visiting {req.destination}.
Plans:
{plan_text}

Include:
- Short welcome intro
- Day-by-day highlights in narrative style
- Two practical travel tips (food, transport, or hidden gems)
"""
    try:
        completion = client.chat.completions.create(
            model="llama-3.2-90b-text-preview",
            messages=[{"role": "user", "content": prompt}],
        )
        # Groq SDK typically exposes text at .choices[0].message.content
        return completion.choices[0].message.content
    except Exception:
        return None

# -------------------------
# Endpoint: /plan
# -------------------------
@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest):
    if req.days <= 0:
        raise HTTPException(status_code=400, detail="days must be > 0")

    # Geocode destination if needed
    lat, lng = req.stay_lat, req.stay_lng
    if lat is None or lng is None:
        geo = geocode_location(req.destination)
        if not geo:
            raise HTTPException(status_code=400, detail=f"Could not geocode destination '{req.destination}'. Provide stay_lat & stay_lng")
        lat, lng = geo

    # Fetch places (names) from Foursquare
    try:
        places = fsq_search(lat, lng, traveler_type=req.traveler_type, limit=20)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Foursquare error: {e}")

    # Get weather (short descriptions) if available
    try:
        weather_list = openweather_forecast(lat, lng, days=req.days) if OPENWEATHER_KEY else [None]*req.days
    except Exception:
        weather_list = [None] * req.days

    # Build per-day plan (distribute places evenly)
    plan_list: List[DayPlan] = []
    chunk_size = ceil(len(places) / req.days) if places else 0
    for d in range(req.days):
        activities = places[d*chunk_size:(d+1)*chunk_size] if places else []
        if not activities:
            activities = ["Free exploration"]
        weather = weather_list[d] if weather_list and len(weather_list) > d else None
        plan_list.append(DayPlan(day=d+1, date=(datetime.utcnow() + timedelta(days=d)).strftime("%Y-%m-%d"), activities=activities, weather=weather))

    # Optional Groq summary
    notes = groq_generate_notes(req, plan_list) if req.use_groq else None

    # Return shape expected by frontend: destination / traveler_type / days / plan / notes
    return PlanResponse(destination=req.destination, traveler_type=req.traveler_type, days=req.days, plan=plan_list, notes=notes)

# -------------------------
# Health
# -------------------------
@app.get("/health")
def health():
    return {"status": "ok", "fsq_key": bool(SERVICE_KEY), "ow_key": bool(OPENWEATHER_KEY), "groq_key": bool(GROQ_KEY) or HAS_GROQ}
