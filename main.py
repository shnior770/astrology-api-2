import os
import ephem
import traceback
import math
import json
from datetime import datetime, date, timedelta
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# Import Firestore libraries
try:
    from firebase_admin import credentials, firestore, initialize_app
    from firebase_admin.auth import get_user, verify_id_token
    from google.cloud.firestore import Client, DocumentReference
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("Firebase libraries not found. Firestore functionality will be disabled.")


# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware to allow requests from the dashboard frontend
origins = [
    "https://base44.app",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Firestore Initialization -----------------
db = None
app_id = None
if FIREBASE_AVAILABLE:
    firebase_config_json = os.environ.get('__firebase_config')
    app_id = os.environ.get('__app_id')
    
    if firebase_config_json and app_id:
        try:
            firebase_config = json.loads(firebase_config_json)
            cred = credentials.Certificate(firebase_config)
            initialize_app(cred)
            db = firestore.client()
            print("Firestore initialized successfully.")
        except Exception as e:
            print(f"Error initializing Firestore: {e}")
            db = None
    else:
        print("Required Firebase environment variables not found. Firestore functionality will be disabled.")
else:
    print("Firebase libraries were not imported. Firestore functionality is disabled.")


# ----------------- Pydantic Models for API Contract -----------------
class PlanetData(BaseModel):
    name: str
    longitude: float
    latitude: float
    sign: str
    degree: float
    house: int
    speed: float
    is_retrograde: bool

class HouseData(BaseModel):
    house: int
    longitude: float
    sign: str

class AspectData(BaseModel):
    planet1: str
    planet2: str
    aspect_type: str
    angle: float
    orb: float

class ChartOutput(BaseModel):
    planets: List[PlanetData]
    houses: List[HouseData]
    aspects: List[AspectData]

class ConstellationSearchInput(BaseModel):
    star_name: str = Field(..., description="The name of the celestial body (e.g., 'Mars').", examples=["Mars"])
    sign_name: str = Field(..., description="The name of the zodiac sign (e.g., 'Aries').", examples=["Aries"])
    start_year: int = Field(..., description="The start year for the search.", examples=[1924])
    end_year: int = Field(..., description="The end year for the search.", examples=[2024])
    limit: int = Field(20, ge=1, le=100, description="Maximum number of results to return.")

class ConstellationSearchOutput(BaseModel):
    date: date
    description: str

class SearchCriteria(BaseModel):
    planet: str
    sign: str

class SearchQuery(BaseModel):
    criteria: List[SearchCriteria]
    search_range: str
    search_date: datetime

class SearchDatum(BaseModel):
    date: date
    description: str

class SaveSearchInput(BaseModel):
    user_id: str
    search_query: SearchQuery
    search_data: List[SearchDatum]

class SaveSearchOutput(BaseModel):
    status: str = "success"
    message: str

class SavedSearch(BaseModel):
    search_query: SearchQuery
    search_data: List[SearchDatum]

# ----------------- Helper Functions -----------------
def is_valid_date_for_ephem(date_str: str) -> str:
    """
    Validates and formats a date string for ephem.
    Ephem expects a format like 'YYYY/MM/DD HH:MM:SS'.
    """
    try:
        dt_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt_obj.strftime('%Y/%m/%d %H:%M:%S')
    except (ValueError, TypeError):
        raise ValueError("Invalid date format. Expected ISO 8601 string.")

# ----------------- API Endpoints -----------------

@app.get("/")
async def root():
    return {"message": "Welcome to the Astrology API!"}

@app.post("/api/get-chart", response_model=ChartOutput)
async def get_chart(request_data: dict):
    """
    Calculates and returns astrological chart data based on user input.
    """
    try:
        # Validate and format the date string for ephem
        formatted_date = is_valid_date_for_ephem(request_data.get('datetime'))
        
        observer = ephem.Observer()
        observer.lat = str(request_data.get('latitude'))
        observer.lon = str(request_data.get('longitude'))
        observer.date = formatted_date

        # The fix for the `ValueError: 'ephem.Date' object has no attribute 'value'`
        # is here. We use `float(observer.date)` to get the Julian date.
        house_cusps = [0] * 13
        house_cusps[0] = ephem.degrees(observer.sidereal_time()).znorm
        house_cusps[1] = ephem.degrees(float(observer.date) + ephem.degrees(90)).znorm
        
        planets_data = []
        ephem_planets = {
            "Sun": ephem.Sun(), "Moon": ephem.Moon(), "Mercury": ephem.Mercury(),
            "Venus": ephem.Venus(), "Mars": ephem.Mars(), "Jupiter": ephem.Jupiter(),
            "Saturn": ephem.Saturn(), "Uranus": ephem.Uranus(), "Neptune": ephem.Neptune(),
            "Pluto": ephem.Pluto()
        }
        
        signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

        for name, planet_obj in ephem_planets.items():
            planet_obj.compute(observer)
            
            longitude = math.degrees(ephem.degrees(planet_obj.ra).znorm)
            latitude = math.degrees(ephem.degrees(planet_obj.dec).znorm)
            sign_index = int(longitude / 30)
            sign = signs[sign_index]
            degree = round(longitude % 30, 2)
            house = (int(longitude / 30) + 1)
            speed = 0.0
            is_retrograde = False

            planets_data.append(PlanetData(
                name=name,
                longitude=longitude,
                latitude=latitude,
                sign=sign,
                degree=degree,
                house=house,
                speed=speed,
                is_retrograde=is_retrograde
            ))

        houses_data = []
        aspects_data = []
        
        return ChartOutput(planets=planets_data, houses=houses_data, aspects=aspects_data)

    except Exception as e:
        error_message = f"An unexpected error occurred in get_chart: {e}"
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": error_message, "error_code": "INTERNAL_SERVER_ERROR"}
        )

@app.post("/api/constellation-search", response_model=List[ConstellationSearchOutput])
async def constellation_search(input_data: ConstellationSearchInput):
    """
    Search historical dates when a star was in a specific sign.
    """
    try:
        planet_name_lower = input_data.star_name.lower()
        sign_name_lower = input_data.sign_name.lower()

        ephem_planets_map = {
            "mars": ephem.Mars, "venus": ephem.Venus, "mercury": ephem.Mercury,
            "sun": ephem.Sun, "moon": ephem.Moon, "jupiter": ephem.Jupiter,
            "saturn": ephem.Saturn, "uranus": ephem.Uranus, "neptune": ephem.Neptune,
            "pluto": ephem.Pluto
        }

        PlanetClass = ephem_planets_map.get(planet_name_lower)
        if not PlanetClass:
            raise ValueError(f"Invalid planet name: {input_data.star_name}")
        
        signs = ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"]
        if sign_name_lower not in signs:
            raise ValueError("Invalid sign name")

        target_sign_index = signs.index(sign_name_lower)
        results = []
        current_date = datetime(input_data.start_year, 1, 1)
        end_date = datetime(input_data.end_year, 12, 31)

        while current_date <= end_date and len(results) < input_data.limit:
            planet = PlanetClass()
            planet.compute(current_date)
            longitude = math.degrees(ephem.degrees(planet.ra).znorm)
            current_sign_index = int(longitude / 30)

            if current_sign_index == target_sign_index:
                results.append(ConstellationSearchOutput(
                    date=current_date.date(),
                    description=f"מאדים בטלה - אירוע היסטורי"
                ))
            
            current_date += timedelta(days=1)
        
        return results
    except Exception as e:
        error_message = f"An error occurred during constellation search: {e}"
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": error_message, "error_code": "CONSTELLATION_SEARCH_ERROR"}
        )

@app.post("/api/save-search", response_model=SaveSearchOutput)
async def save_search(request_data: SaveSearchInput):
    """
    Saves a user's search query to Firestore.
    """
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database not available.")

    try:
        if not app_id:
            raise ValueError("App ID is not available.")
            
        user_id = request_data.user_id
        collection_path = f"/artifacts/{app_id}/users/{user_id}/saved_searches"
        
        search_data_dict = request_data.model_dump()
        
        doc_ref = db.collection(collection_path).document()
        doc_ref.set(search_data_dict)
        
        return SaveSearchOutput(message="Search saved successfully")
    except Exception as e:
        error_message = f"Failed to save search: {e}"
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": error_message, "error_code": "SAVE_SEARCH_ERROR"}
        )

@app.get("/api/get-saved-searches", response_model=List[SavedSearch])
async def get_saved_searches(user_id: str):
    """
    Retrieves a user's saved searches from Firestore.
    """
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database not available.")
    
    try:
        if not app_id:
            raise ValueError("App ID is not available.")
        
        collection_path = f"/artifacts/{app_id}/users/{user_id}/saved_searches"
        docs = db.collection(collection_path).stream()
        
        results = []
        for doc in docs:
            saved_search_data = doc.to_dict()
            results.append(SavedSearch(**saved_search_data))
        
        return results
    except Exception as e:
        error_message = f"Failed to get saved searches: {e}"
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": error_message, "error_code": "GET_SAVED_SEARCHES_ERROR"}
        )
