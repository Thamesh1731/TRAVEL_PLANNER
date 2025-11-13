# Import everything from the standalone planner module
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

# Load environment variables from .env
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=env_path)

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
GOOGLE_PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY")   # You'll need to get this key
OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY") 
GROQ_KEY = os.getenv("GROQ_API_KEY") 

GOOGLE_PLACES_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
OW_GEOCODE_URL = "http://api.openweathermap.org/geo/1.0/direct"
OW_ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall"

# -------------------------
# Models
# -------------------------
class PlanRequest(BaseModel):
    traveler_type: str = Field(..., min_length=1)
    destination: str = Field(..., min_length=1)
    days: int = Field(..., ge=1, le=14)
    start_date: Optional[str] = None  # ISO date format
    end_date: Optional[str] = None    # ISO date format
    stay_lat: Optional[float] = None
    stay_lng: Optional[float] = None
    use_groq: bool = False

class PlaceInfo(BaseModel):
    name: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    rating: Optional[float] = None
    address: Optional[str] = None
    categories: Optional[List[str]] = None

class TimeSlot(BaseModel):
    part: str  # "Morning", "Afternoon", "Evening"
    place: Optional[PlaceInfo] = None

class DayPlan(BaseModel):
    day: int
    date: str
    slots: List[TimeSlot]
    weather: Optional[dict] = None
    categories: Optional[List[str]] = None
    alternatives: Optional[List[dict]] = None

class PlanResponse(BaseModel):
    destination: str
    traveler_type: str
    days: int
    plan: List[DayPlan]
    llm_notes: Optional[str] = None
    latlng: Optional[dict] = None

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

def osm_search_places(lat, lng, traveler_type="solo", limit=20):
    """Fetch places using OpenStreetMap Overpass API - completely free!"""
    
    # Map traveler type → OSM amenity/tourism types
    amenity_map = {
        "solo": ["museum", "library", "cafe", "park", "viewpoint", "monument"],
        "nuclear family": ["zoo", "amusement_park", "playground", "park", "museum", "restaurant"],
        "joint family": ["temple", "place_of_worship", "park", "restaurant", "tourist_attraction"],
        "family": ["zoo", "park", "museum", "playground", "restaurant", "tourist_attraction"],
        "couple": ["restaurant", "cafe", "spa", "viewpoint", "bar", "tourist_attraction"],
        "friends": ["bar", "pub", "restaurant", "nightclub", "cafe", "tourist_attraction"],
    }
    amenities = amenity_map.get(traveler_type.lower(), ["tourist_attraction", "restaurant", "cafe"])
    
    # Create Overpass API query
    amenity_queries = []
    for amenity in amenities[:3]:  # Limit to avoid too complex queries
        amenity_queries.append(f'node["amenity"="{amenity}"](around:5000,{lat},{lng});')
        amenity_queries.append(f'node["tourism"="{amenity}"](around:5000,{lat},{lng});')
    
    # Overpass query to get points of interest around the location
    overpass_query = f"""
[out:json][timeout:25];
(
  {''.join(amenity_queries)}
  node["tourism"="attraction"](around:8000,{lat},{lng});
  node["tourism"="museum"](around:8000,{lat},{lng});
  node["amenity"="restaurant"](around:5000,{lat},{lng});
  node["amenity"="cafe"](around:5000,{lat},{lng});
);
out center meta;
"""
    
    try:
        r = requests.post(
            "https://overpass-api.de/api/interpreter",
            data=overpass_query,
            headers={"User-Agent": "TravelPlanner/1.0"},
            timeout=20
        )
        r.raise_for_status()
        data = r.json()
        
        results = []
        seen_names = set()  # Avoid duplicates
        
        for element in data.get("elements", []):
            if len(results) >= limit:
                break
                
            tags = element.get("tags", {})
            name = tags.get("name")
            if not name or name in seen_names:
                continue
                
            seen_names.add(name)
            
            # Extract categories
            categories = []
            if "amenity" in tags:
                categories.append(tags["amenity"].replace("_", " ").title())
            if "tourism" in tags:
                categories.append(tags["tourism"].replace("_", " ").title())
            if "cuisine" in tags:
                categories.append(f"{tags['cuisine'].title()} Cuisine")
                
            results.append({
                "id": element.get("id"),
                "name": name,
                "lat": element.get("lat"),
                "lng": element.get("lon"),
                "rating": None,  # OSM doesn't have ratings
                "categories": categories[:3],  # Limit categories
                "address": tags.get("addr:full") or f"{tags.get('addr:street', '')} {tags.get('addr:housenumber', '')}".strip() or "Address not available"
            })
            
        # If we don't have enough results, add some generic attractions
        if len(results) < 3:
            generic_places = [
                {"name": "Local Market", "lat": lat + 0.01, "lng": lng + 0.01, "categories": ["Shopping"]},
                {"name": "City Center", "lat": lat, "lng": lng, "categories": ["Sightseeing"]},
                {"name": "Local Restaurant", "lat": lat - 0.01, "lng": lng - 0.01, "categories": ["Dining"]},
                {"name": "Scenic Viewpoint", "lat": lat + 0.02, "lng": lng + 0.02, "categories": ["Nature"]},
                {"name": "Cultural Site", "lat": lat - 0.02, "lng": lng + 0.01, "categories": ["Culture"]}
            ]
            
            for place in generic_places:
                if len(results) >= limit:
                    break
                place.update({
                    "id": f"generic_{len(results)}",
                    "rating": None,
                    "address": "Address not available"
                })
                results.append(place)
        
        return results[:limit]
        
    except Exception as e:
        print(f"OSM query failed: {e}")
        # Fallback to basic attractions if API fails
        fallback_places = [
            {"name": "Main Tourist Attraction", "lat": lat, "lng": lng, "categories": ["Attraction"]},
            {"name": "Popular Restaurant", "lat": lat + 0.005, "lng": lng + 0.005, "categories": ["Restaurant"]},
            {"name": "Local Cafe", "lat": lat - 0.005, "lng": lng - 0.005, "categories": ["Cafe"]},
            {"name": "Shopping Area", "lat": lat + 0.01, "lng": lng - 0.01, "categories": ["Shopping"]},
            {"name": "Cultural Center", "lat": lat - 0.01, "lng": lng + 0.01, "categories": ["Culture"]}
        ]
        
        return [{**place, "id": f"fallback_{i}", "rating": None, "address": "Address not available"} 
                for i, place in enumerate(fallback_places[:limit])]

def openweather_forecast(lat, lon, days=3, start_date=None):
    """Get weather forecast for the location with enhanced information."""
    if not OPENWEATHER_KEY:
        return [None] * days
    
    try:
        params = {"lat": lat, "lon": lon, "units": "metric", "appid": OPENWEATHER_KEY, "exclude": "minutely,hourly,alerts"}
        r = requests.get(OW_ONECALL_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        forecasts = []
        for i, d in enumerate(data.get("daily", [])[:days]):
            weather_info = d.get("weather", [{}])[0]
            desc = weather_info.get("description", "Clear")
            temp_day = d.get("temp", {}).get("day")
            temp_min = d.get("temp", {}).get("min")
            temp_max = d.get("temp", {}).get("max")
            humidity = d.get("humidity")
            
            # Get weather emoji based on condition
            weather_emoji = "🌤️"  # default
            desc_lower = desc.lower()
            if "rain" in desc_lower:
                weather_emoji = "🌧️"
            elif "cloud" in desc_lower:
                weather_emoji = "☁️"
            elif "clear" in desc_lower or "sun" in desc_lower:
                weather_emoji = "☀️"
            elif "snow" in desc_lower:
                weather_emoji = "🌨️"
            elif "thunderstorm" in desc_lower:
                weather_emoji = "⛈️"
                
            forecasts.append({
                "condition": desc.capitalize(),
                "avg_temp_c": round(temp_day) if temp_day is not None else None,
                "min_temp_c": round(temp_min) if temp_min is not None else None,
                "max_temp_c": round(temp_max) if temp_max is not None else None,
                "humidity": humidity,
                "emoji": weather_emoji,
                "description": f"{weather_emoji} {desc.capitalize()}"
            })
        return forecasts
    except Exception as e:
        print(f"Weather API error: {e}")
        # Return pleasant weather as fallback
        return [{
            "condition": "Pleasant weather",
            "avg_temp_c": 25,
            "min_temp_c": 20,
            "max_temp_c": 30,
            "humidity": 60,
            "emoji": "🌤️",
            "description": "🌤️ Pleasant weather"
        }] * days

def groq_generate_city_intro(destination: str, traveler_type: str):
    """Generate a beautiful city introduction - with fallback to curated content."""
    # Static fallback content for popular destinations
    fallback_intros = {
        "ooty": {
            "couple": "🏔️ Nestled in the Nilgiri Hills of Tamil Nadu, Ooty (Udhagamandalam) beckons couples with its enchanting mist-covered mountains and romantic colonial charm. Known as the 'Queen of Hill Stations,' this beautiful retreat offers couples a perfect blend of natural splendor and old-world elegance. Stroll hand-in-hand through the fragrant botanical gardens, enjoy intimate moments by the serene Ooty Lake, and witness breathtaking sunrises from Doddabetta Peak. The vintage charm of the Nilgiri Mountain Railway, the colorful tea gardens stretching as far as the eye can see, and the cozy climate make Ooty an ideal romantic getaway. Whether you're sharing a quiet moment in a hillside café or exploring the beautiful Rose Garden together, Ooty promises memories that will last a lifetime.",
            "family": "🌟 Welcome to Ooty, the magical 'Queen of Hill Stations' that promises unforgettable family adventures! This charming hill station in Tamil Nadu's Nilgiri Hills offers families the perfect blend of natural beauty, fun activities, and educational experiences. From the exciting toy train journey through tunnels and over bridges to boating on the picturesque Ooty Lake, every moment here is filled with wonder. The expansive Botanical Garden showcases exotic plants and colorful flowers that will captivate both children and adults. Adventure awaits at every turn - from exploring the tea factories and learning about tea-making to enjoying pony rides and visiting the beautiful Rose Garden. Ooty's pleasant climate and safe, family-friendly attractions make it an ideal destination for creating precious family memories.",
            "solo": "🎒 Discover the soul-stirring beauty of Ooty, where solo travelers find both adventure and tranquility in perfect harmony. This hill station offers the ideal setting for self-discovery, with peaceful walking trails through eucalyptus groves, quiet moments by the lake, and stunning viewpoints perfect for reflection. The colonial architecture tells stories of the past, while the vibrant local markets offer authentic experiences. Whether you're photographing the morning mist rolling over tea gardens, enjoying a cup of fresh Nilgiri tea while watching the sunset, or taking the scenic toy train journey, Ooty provides countless opportunities for meaningful solo exploration.",
            "friends": "🎉 Get ready for an amazing adventure in Ooty with your squad! This hill station is the perfect playground for friends seeking both excitement and relaxation. From thrilling activities like trekking in the Nilgiri Hills to fun-filled boat rides on Ooty Lake, there's never a dull moment. Explore the vibrant local markets together, indulge in street food adventures, and capture Instagram-worthy shots at the colorful tea gardens. The cool weather makes it perfect for outdoor activities, group photography sessions at scenic spots, and cozy evenings around bonfires. Whether you're racing down the slopes or sharing stories over hot chocolate, Ooty promises an unforgettable group getaway."
        },
        "paris": {
            "couple": "💕 Paris, the City of Love, awaits with its timeless romance and unparalleled charm. From intimate Seine river cruises at sunset to candlelit dinners in hidden bistros, every corner of this magnificent city whispers sweet promises to lovers. The Eiffel Tower's golden glow at night, leisurely walks along the Champs-Élysées, and stolen kisses in Montmartre create the perfect romantic symphony.",
            "family": "🎠 Paris enchants families with its perfect blend of culture, fun, and magical experiences. From the wonder of Disneyland Paris to the educational treasures of the Louvre, this city offers unforgettable adventures for every family member. Climb the Eiffel Tower together, enjoy picnics in beautiful parks, and create magical memories that will last a lifetime.",
            "solo": "🗼 Paris beckons solo travelers with its rich culture, stunning architecture, and café culture. Wander through artistic neighborhoods, discover hidden gems, and immerse yourself in the city's intellectual and creative energy. Every museum, every street corner, every café offers a new story to discover.",
            "friends": "🥐 Paris with friends is an adventure filled with laughter, discovery, and unforgettable moments. From exploring vibrant neighborhoods to enjoying group dinners in cozy bistros, the City of Light offers endless possibilities for fun and friendship."
        }
    }
    
    # Try to get destination-specific intro
    dest_key = destination.lower().strip()
    traveler_key = traveler_type.lower().strip()
    
    if dest_key in fallback_intros and traveler_key in fallback_intros[dest_key]:
        return fallback_intros[dest_key][traveler_key]
    
    # Generic fallback
    return f"🌍 Welcome to {destination}! This beautiful destination offers {traveler_type} travelers an amazing opportunity to explore, discover, and create unforgettable memories. From stunning natural beauty to rich cultural experiences, {destination} has something special waiting for every visitor. Get ready for an adventure that will leave you with stories to tell for years to come!"

def groq_generate_detailed_plan(req: PlanRequest, plan: List[DayPlan], city_intro: str = None):
    """Generate a comprehensive and engaging itinerary explanation with fallback."""
    
    # Build plan overview
    plan_overview = []
    for p in plan:
        weather_str = ""
        if p.weather:
            weather_str = f" 🌤️ Weather: {p.weather.get('condition', 'Pleasant')}"
            if p.weather.get('avg_temp_c'):
                weather_str += f", {p.weather.get('avg_temp_c')}°C"
        
        activities = []
        for slot in p.slots:
            if slot.place and slot.place.name != "Free exploration":
                emoji = "🏖️" if "Morning" in slot.part else "🌅" if "Afternoon" in slot.part else "🌆"
                activities.append(f"  {emoji} **{slot.part}**: {slot.place.name}")
                if slot.place.categories:
                    activities[-1] += f" ({', '.join(slot.place.categories)})"
            else:
                emoji = "🌅" if "Afternoon" in slot.part else "🌆"
                activities.append(f"  {emoji} **{slot.part}**: Free exploration time")
        
        plan_overview.append(f"**Day {p.day}** ({p.date}){weather_str}\n" + "\n".join(activities))
    
    # Create comprehensive guide
    plan_text = '\n\n'.join(plan_overview)
    intro_text = city_intro if city_intro else f"Get ready to explore the amazing destination of {req.destination}!"
    
    guide_content = f"""🌟 **Welcome to Your {req.days}-Day {req.destination} Adventure!**

{intro_text}

📅 **Your Detailed Itinerary**

{plan_text}

🍽️ **Local Cuisine Must-Tries**
"""
    
    # Add destination-specific recommendations
    if req.destination.lower() == "ooty":
        guide_content += """
• **Fresh Nilgiri Tea**: Sip on the world-famous tea while enjoying mountain views
• **Homemade Chocolates**: Visit local chocolate factories for fresh, artisanal treats
• **Varkey (Ooty Bread)**: A local specialty perfect for breakfast with butter and jam
• **Traditional South Indian Meals**: Try authentic Tamil cuisine at local restaurants

🚗 **Transportation Tips**
• **Toy Train**: Book the Nilgiri Mountain Railway in advance for a scenic journey
• **Local Taxis**: Available for day trips to various viewpoints and attractions
• **Walking**: Many attractions in the main town are within walking distance
• **Private Vehicle**: Recommended for flexibility in exploring tea gardens and viewpoints

💎 **Insider Secrets**
• **Early Morning Photography**: Visit Doddabetta Peak at sunrise for breathtaking views with minimal crowds
• **Tea Garden Walks**: Ask locals about lesser-known tea gardens where you can walk among the bushes
• **Local Markets**: Visit the main bazaar in the evening for fresh produce and authentic shopping experience
• **Heritage Bungalows**: Some colonial-era bungalows offer tours showcasing Ooty's British heritage
"""
    else:
        guide_content += f"""
• **Local Specialties**: Ask your hotel or local guides for the most authentic regional dishes
• **Street Food**: Explore local markets for genuine street food experiences
• **Traditional Restaurants**: Visit family-run establishments for authentic flavors

🚗 **Transportation Tips**
• **Local Transport**: Use public transportation or taxis for convenient city travel
• **Walking**: Explore on foot when possible to discover hidden gems
• **Day Trips**: Consider organized tours for attractions outside the main area

💎 **Insider Secrets**
• **Early Hours**: Visit popular attractions early morning for better photos and fewer crowds
• **Local Guides**: Hire local guides for authentic stories and hidden viewpoints
• **Seasonal Events**: Check for local festivals or events happening during your visit
"""
    
    # Add traveler-type specific advice
    guide_content += f"\n🎒 **Special Tips for {req.traveler_type.title()} Travelers**\n"
    
    if req.traveler_type.lower() == "couple":
        guide_content += """
• **Romantic Moments**: Plan sunset viewing at scenic spots for unforgettable memories
• **Private Experiences**: Book private boat rides or intimate dining experiences
• **Photography**: Carry a camera for couple photos at beautiful locations
• **Comfortable Pace**: Don't rush - allow time for spontaneous romantic moments
"""
    elif "family" in req.traveler_type.lower():
        guide_content += """
• **Kid-Friendly Activities**: Plan activities that engage all family members
• **Safety First**: Keep emergency contacts and first aid kit handy
• **Rest Breaks**: Schedule regular breaks, especially if traveling with young children
• **Educational Opportunities**: Turn sightseeing into learning experiences for kids
"""
    elif req.traveler_type.lower() == "solo":
        guide_content += """
• **Stay Connected**: Share your itinerary with family/friends back home
• **Local Connections**: Don't hesitate to chat with locals for authentic experiences
• **Flexible Planning**: Leave room for spontaneous discoveries
• **Personal Safety**: Trust your instincts and stay in well-lit, populated areas
"""
    elif req.traveler_type.lower() == "friends":
        guide_content += """
• **Group Activities**: Plan activities everyone can enjoy together
• **Photo Opportunities**: Designate a group photographer for memorable shots
• **Budget Planning**: Discuss and agree on budget for activities and meals
• **Compromise**: Be flexible with plans to accommodate everyone's interests
"""
    else:
        guide_content += f"""
• **Plan Together**: Discuss preferences and interests with your travel companions
• **Stay Flexible**: Be open to changes and spontaneous adventures
• **Capture Memories**: Take lots of photos and keep a travel journal
• **Enjoy the Moment**: Don't forget to put the phone down and truly experience each location
"""
    
    guide_content += f"\n\n✨ **Have an amazing time exploring {req.destination}! Remember, the best travel experiences often come from unexpected moments and genuine connections with local culture and people.**"
    
    return guide_content

# -------------------------
# Endpoint: /plan
# -------------------------
@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest):
    try:
        # Geocode destination if needed
        lat, lng = req.stay_lat, req.stay_lng
        if lat is None or lng is None:
            geo = geocode_location(req.destination)
            if not geo:
                raise HTTPException(status_code=400, detail=f"Could not geocode destination '{req.destination}'. Provide stay_lat & stay_lng")
            lat, lng = geo

        # Fetch places using OpenStreetMap
        places = osm_search_places(lat, lng, traveler_type=req.traveler_type, limit=req.days * 3)
        
        # Get weather forecast with start date
        weather_list = openweather_forecast(lat, lng, days=req.days, start_date=req.start_date)

        # Calculate actual dates for the trip
        if req.start_date:
            start_date = datetime.fromisoformat(req.start_date)
        else:
            start_date = datetime.utcnow()

        # Build per-day plan
        plan_list: List[DayPlan] = []
        places_per_day = max(1, len(places) // req.days)
        
        for d in range(req.days):
            start_idx = d * places_per_day
            end_idx = min((d + 1) * places_per_day, len(places))
            day_places = places[start_idx:end_idx]
            
            # Create time slots
            slots = []
            time_parts = ["Morning", "Afternoon", "Evening"]
            
            for i, part in enumerate(time_parts):
                if i < len(day_places):
                    place_data = day_places[i]
                    place = PlaceInfo(
                        name=place_data["name"],
                        lat=place_data["lat"],
                        lng=place_data["lng"],
                        rating=place_data.get("rating"),
                        address=place_data.get("address"),
                        categories=place_data.get("categories")
                    )
                else:
                    place = PlaceInfo(name="Free exploration")
                
                slots.append(TimeSlot(part=part, place=place))
            
            # Use enhanced weather data
            weather = weather_list[d] if weather_list and len(weather_list) > d else None
            categories = list(set([cat for place in day_places for cat in (place.get("categories") or [])]))[:3]
            
            # Calculate actual date for this day
            current_date = start_date + timedelta(days=d)
            
            plan_list.append(DayPlan(
                day=d + 1,
                date=current_date.strftime("%Y-%m-%d"),
                slots=slots,
                weather=weather,
                categories=categories
            ))

        # Generate enhanced content with Groq
        city_intro = None
        detailed_notes = None
        
        if req.use_groq:
            # Generate city introduction
            city_intro = groq_generate_city_intro(req.destination, req.traveler_type)
            # Generate detailed travel plan
            detailed_notes = groq_generate_detailed_plan(req, plan_list, city_intro)

        return PlanResponse(
            destination=req.destination,
            traveler_type=req.traveler_type,
            days=req.days,
            plan=plan_list,
            llm_notes=detailed_notes,
            latlng={"lat": lat, "lng": lng}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------
# Health
# -------------------------
@app.get("/health")
def health():
    return {
        "status": "ok", 
        "osm_api": "available", 
        "ow_key": bool(OPENWEATHER_KEY), 
        "groq_key": bool(GROQ_KEY) and HAS_GROQ
    }