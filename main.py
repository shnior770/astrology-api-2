# main.py
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
import ephem
import math
import json # ייבוא חדש של מודול json

# ייבוא חדש לפתרון בעיית CORS ולתמיכה ב-Firestore
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin # ייבוא חדש של מודול firebase_admin

# ----------------- Firestore Initialization -----------------
# השתמש בפרטי הקונפיגורציה המסופקים על ידי המערכת.
db = None
try:
    if '__firebase_config' in globals():
        firebase_config = json.loads(__firebase_config)
        cred = credentials.Certificate(firebase_config)
        if not firebase_admin._apps:
            initialize_app(cred)
        db = firestore.client()
    else:
        print("Firebase config not found.")
except (json.JSONDecodeError, ValueError) as e:
    print(f"Failed to initialize Firebase with provided config: {e}")

# ----------------- App Definition -----------------
app = FastAPI(
    title="Astrology API",
    description="API for historical astrological calculations with Firestore support.",
    version="0.3.1",
)

# ----------------- CORS Middleware Configuration -----------------
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Helper Mappings -----------------
PLANET_MAPPING = {
    "sun": ephem.Sun, "moon": ephem.Moon, "mercury": ephem.Mercury,
    "venus": ephem.Venus, "mars": ephem.Mars, "jupiter": ephem.Jupiter,
    "saturn": ephem.Saturn, "uranus": ephem.Uranus, "neptune": ephem.Neptune,
    "pluto": ephem.Pluto,
}

# ----------------- Pydantic Schemas (Data Models) -----------------
class CelestialBodyPosition(BaseModel):
    name: str
    longitude: float
    sign: str
    degree_in_sign: float
    is_retrograde: bool

class ConstellationSearchResult(BaseModel):
    date: date
    description: str
    celestial_bodies: List[CelestialBodyPosition]

class ConstellationSearchOutput(BaseModel):
    status: str = "success"
    results: List[ConstellationSearchResult]

class SaveSearchInput(BaseModel):
    user_id: str = Field(..., description="The user ID to associate the search with.")
    search_data: ConstellationSearchOutput = Field(..., description="The search results to save.")
    search_query: Dict[str, Any] = Field(..., description="The original query that generated the search.")

class SavedSearch(BaseModel):
    id: str
    user_id: str
    search_query: Dict[str, Any]
    search_data: ConstellationSearchOutput
    saved_at: datetime

# ----------------- API Endpoints -----------------

@app.post("/api/constellation-search", response_model=ConstellationSearchOutput)
async def constellation_search(
    star_name: str,
    sign_name: str,
    start_year: int,
    end_year: int,
    limit: int = 10,
):
    """
    Finds dates when a celestial body enters a specific zodiac sign.
    """
    planet_name_lower = star_name.lower()
    sign_name_lower = sign_name.lower()

    PlanetClass = PLANET_MAPPING.get(planet_name_lower)
    if PlanetClass is None:
        raise HTTPException(status_code=400, detail=f"Invalid star name: {star_name}")

    signs = [
        "aries", "taurus", "gemini", "cancer", "leo", "virgo",
        "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"
    ]
    if sign_name_lower not in signs:
        raise HTTPException(status_code=400, detail=f"Invalid sign name: {sign_name}")
    
    target_sign_index = signs.index(sign_name_lower)
    
    results_found = []
    current_dt = datetime(start_year, 1, 1)
    end_dt = datetime(end_year + 1, 1, 1)

    last_sign_id = -1
    last_longitude = -1.0

    while current_dt < end_dt:
        planet = PlanetClass()
        planet.compute(current_dt)
        longitude = math.degrees(planet.ra)
        current_sign_id = int(longitude / 30)

        if current_sign_id == target_sign_index and last_sign_id != target_sign_index:
            position_details = CelestialBodyPosition(
                name=star_name.title(),
                longitude=round(longitude, 4),
                sign=sign_name.title(),
                degree_in_sign=round(longitude % 30, 4),
                is_retrograde=(longitude < last_longitude)
            )
            found_item = ConstellationSearchResult(
                date=current_dt.date(),
                description=f"{star_name.title()} entered {sign_name.title()}",
                celestial_bodies=[position_details]
            )
            results_found.append(found_item)
            if len(results_found) >= limit:
                break
        
        last_sign_id = current_sign_id
        last_longitude = longitude
        current_dt += timedelta(days=1)

    return ConstellationSearchOutput(results=results_found)

@app.post("/api/save-search")
async def save_search(input_data: SaveSearchInput):
    """
    Saves a search result to Firestore.
    """
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized.")

    app_id = "default-app-id" # Fallback if __app_id is not defined
    try:
        if '__app_id' in globals():
            app_id = __app_id
    except NameError:
        pass

    try:
        # Save to Firestore
        collection_path = f"artifacts/{app_id}/users/{input_data.user_id}/saved_searches"
        doc_ref = db.collection(collection_path).document()
        
        # Convert Pydantic models to dictionaries for Firestore
        data_to_save = {
            "user_id": input_data.user_id,
            "search_query": input_data.search_query,
            "search_data": input_data.search_data.dict(),
            "saved_at": firestore.SERVER_TIMESTAMP
        }
        
        doc_ref.set(data_to_save)
        
        return {"status": "success", "message": "Search saved successfully", "search_id": doc_ref.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save search: {str(e)}")

@app.get("/")
async def read_root():
    """
    A simple health check endpoint.
    """
    return {"message": "Astrology API is running"}
