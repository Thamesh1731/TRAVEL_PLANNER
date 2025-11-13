import os
import time
import requests
from math import radians, sin, cos, sqrt, atan2

FOURSQUARE_KEY = os.getenv("FOURSQUARE_API_KEY")

CATEGORY_QUERY = {
    "romantic": ["scenic viewpoint", "sunset point", "romantic restaurant"],
    "scenic": ["viewpoint", "scenic view"],
    "quiet": ["botanical garden", "nature trail"],
    "parks": ["park"],
    "lakes": ["lake"],
    "viewpoints": ["viewpoint"],
    "gardens": ["botanical garden"],
    "sunset_points": ["sunset point"],
    "cafes": ["cafe"],
    "heritage_sites": ["heritage site", "historical landmark"],
    "beaches": ["beach"],
    "mountain_views": ["viewpoint", "mountain"],
    "waterfalls": ["waterfall"],
    "museums": ["museum"],
    "hiking": ["hiking trail"],
    "trekking": ["hiking trail"],
    "adventure": ["adventure park"],
    "temples": ["hindu temple", "temple"],
    "cultural": ["cultural center"],
    "family_restaurants": ["family restaurant"],
    "amusement_parks": ["amusement park"],
    "aquariums": ["aquarium"],
    "zoo": ["zoo"],
    "science_centers": ["science center"],
    "picnic_spots": ["picnic area"],
    "shopping_malls": ["shopping mall"],
    "sightseeing": ["tourist attraction"],
    "group_activities": ["escape room", "team building"],
    "shopping": ["market", "shopping mall"],
    "markets": ["market"],
    "cultural_centers": ["cultural center"],
    "theaters": ["theater"],
    "pilgrimage_sites": ["pilgrimage site"],
    "festivals": ["event venue"],
    "city_tours": ["city tour"]
}

def geocode_city(place: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": place, "format": "json", "limit": 1}
    headers = {"User-Agent": "TravelPlanner/1.0"}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])

def places_text_search(query: str, lat: float, lng: float, radius=15000, min_rating=3.5, max_results=12):
    if not FOURSQUARE_KEY:
        raise RuntimeError("FOURSQUARE_API_KEY not set")
    url = "https://api.foursquare.com/v3/places/search"
    headers = {"Authorization": FOURSQUARE_KEY, "Accept": "application/json"}
    params = {
        "query": query,
        "ll": f"{lat},{lng}",
        "radius": radius,
        "limit": max_results
    }
    r = requests.get(url, headers=headers, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    out = []
    for p in data.get("results", []):
        rating = p.get("rating", 0) / 2  # Foursquare rating out of 10, normalize to 5
        if rating >= min_rating:
            out.append({
                "name": p.get("name"),
                "rating": rating,
                "user_ratings_total": p.get("stats", {}).get("total_ratings", 0),
                "address": p.get("location", {}).get("formatted_address"),
                "place_id": p.get("fsq_id"),
                "lat": p["geocodes"]["main"]["latitude"],
                "lng": p["geocodes"]["main"]["longitude"],
                "price_level": None,
                "types": [c["name"] for c in p.get("categories", [])]
            })
    return out

def candidates_for_category(lat: float, lng: float, cat: str, max_results=8):
    queries = CATEGORY_QUERY.get(cat, [cat.replace("_"," ")])
    seen = {}
    for q in queries:
        for p in places_text_search(q, lat, lng, max_results=max_results):
            key = p["place_id"]
            if key not in seen:
                seen[key] = p | {"category": cat}
    return list(seen.values())

def haversine(a, b):
    R = 6371.0
    lat1, lon1 = a; lat2, lon2 = b
    dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
    x = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2*R*atan2(sqrt(x), sqrt(1 - x))

def nearest_route(start_latlng, points):
    route, unused = [], points[:]
    cur = start_latlng
    while unused:
        nxt = min(unused, key=lambda p: haversine(cur, (p["lat"], p["lng"])))
        route.append(nxt)
        cur = (nxt["lat"], nxt["lng"])
        unused.remove(nxt)
    return route
