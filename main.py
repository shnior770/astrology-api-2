# main.py
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
import ephem
import math
import json
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin

# ייבוא חדש לפתרון בעיית CORS
from fastapi.middleware.cors import CORSMiddleware

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
    version="0.6.0", # עדכון גרסה לתיקון שגיאה
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

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

def get_sign_details(longitude):
    """
    Calculates the zodiac sign and degree within the sign from a given longitude.
    """
    longitude = longitude % 360
    sign_index = int(longitude / 30)
    degree_in_sign = longitude % 30
    return ZODIAC_SIGNS[sign_index], degree_in_sign

# ----------------- Pydantic Schemas (Data Models) -----------------
class ConstellationSearchInput(BaseModel):
    star_name: str = Field(..., description="The name of the celestial body (e.g., 'Mars').", examples=["Mars"])
    sign_name: str = Field(..., description="The name of the zodiac sign (e.g., 'Aries').", examples=["Aries"])
    start_year: int = Field(..., description="The start year for the search.", examples=[1990])
    end_year: int = Field(..., description="The end year for the search.", examples=[2000])
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results to return.")

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

# מודלים חדשים לחישוב מפה אסטרולוגית מלאה
class ChartInput(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format.", examples=["2023-10-27"])
    time: str = Field(..., description="Time in HH:MM format.", examples=["14:30"])
    latitude: float = Field(..., description="Observer's latitude.", examples=[31.7683])
    longitude: float = Field(..., description="Observer's longitude.", examples=[35.2137])

class PlanetPosition(BaseModel):
    name: str
    longitude: float
    sign: str
    degree_in_sign: float
    is_retrograde: bool
    house: int

class HouseCusp(BaseModel):
    house_number: int
    longitude: float
    sign: str
    degree_in_sign: float

# מודל חדש לייצוג היבט אסטרולוגי
class Aspect(BaseModel):
    planet1: str
    planet2: str
    type: str # e.g., "Conjunction", "Trine", "Square"
    orb: float # The difference in degrees from the exact aspect
    angle: float

# עדכון מודל הפלט לכלול היבטים
class FullChartOutput(BaseModel):
    status: str = "success"
    date_time: str
    location: str
    planet_positions: List[PlanetPosition]
    house_cusps: List[HouseCusp]
    aspects: List[Aspect] # הוספה חדשה של רשימת ההיבטים

# ----------------- API Endpoints -----------------

@app.post("/api/constellation-search", response_model=ConstellationSearchOutput)
async def constellation_search(input_data: ConstellationSearchInput):
    """
    Finds dates when a celestial body enters a specific zodiac sign.
    """
    planet_name_lower = input_data.star_name.lower()
    sign_name_lower = input_data.sign_name.lower()

    PlanetClass = PLANET_MAPPING.get(planet_name_lower)
    if PlanetClass is None:
        raise HTTPException(status_code=400, detail=f"Invalid star name: {input_data.star_name}")

    signs = [s.lower() for s in ZODIAC_SIGNS]
    if sign_name_lower not in signs:
        raise HTTPException(status_code=400, detail=f"Invalid sign name: {input_data.sign_name}")
    
    target_sign_index = signs.index(sign_name_lower)
    
    results_found = []
    current_dt = datetime(input_data.start_year, 1, 1)
    end_dt = datetime(input_data.end_year + 1, 1, 1)

    last_sign_id = -1
    last_longitude = -1.0

    while current_dt < end_dt:
        planet = PlanetClass()
        planet.compute(current_dt)
        longitude = math.degrees(planet.ra)
        current_sign_id = int(longitude / 30)

        if current_sign_id == target_sign_index and last_sign_id != target_sign_index:
            sign_name, degree_in_sign = get_sign_details(longitude)
            position_details = CelestialBodyPosition(
                name=input_data.star_name.title(),
                longitude=round(longitude, 4),
                sign=sign_name,
                degree_in_sign=round(degree_in_sign, 4),
                is_retrograde=(longitude < last_longitude)
            )
            found_item = ConstellationSearchResult(
                date=current_dt.date(),
                description=f"{input_data.star_name.title()} entered {input_data.sign_name.title()}",
                celestial_bodies=[position_details]
            )
            results_found.append(found_item)
            if len(results_found) >= input_data.limit:
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

    app_id = "default-app-id"
    try:
        if '__app_id' in globals():
            app_id = __app_id
    except NameError:
        pass

    try:
        collection_path = f"artifacts/{app_id}/users/{input_data.user_id}/saved_searches"
        doc_ref = db.collection(collection_path).document()
        
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

def calculate_aspects(planet_positions: List[PlanetPosition]) -> List[Aspect]:
    """
    Calculates major aspects between all planet pairs.
    """
    aspects = []
    # הגדרת היבטים וטווח אורב (orb)
    major_aspects = {
        "Conjunction": {"angle": 0, "orb": 8},
        "Sextile": {"angle": 60, "orb": 6},
        "Square": {"angle": 90, "orb": 8},
        "Trine": {"angle": 120, "orb": 8},
        "Opposition": {"angle": 180, "orb": 8},
    }

    num_planets = len(planet_positions)
    for i in range(num_planets):
        for j in range(i + 1, num_planets):
            p1 = planet_positions[i]
            p2 = planet_positions[j]

            angle_diff = abs(p1.longitude - p2.longitude)
            angle_diff = min(angle_diff, 360 - angle_diff)

            for aspect_name, aspect_details in major_aspects.items():
                ideal_angle = aspect_details["angle"]
                orb = aspect_details["orb"]

                if abs(angle_diff - ideal_angle) <= orb:
                    aspects.append(Aspect(
                        planet1=p1.name,
                        planet2=p2.name,
                        type=aspect_name,
                        orb=round(abs(angle_diff - ideal_angle), 2),
                        angle=round(angle_diff, 2)
                    ))

    return aspects

@app.post("/api/get-chart", response_model=FullChartOutput)
async def get_chart(input_data: ChartInput):
    """
    Calculates and returns a full astrological chart with Equal House system.
    """
    try:
        # יצירת אובייקט Observer עם המיקום והזמן
        observer = ephem.Observer()
        observer.lat, observer.lon = str(input_data.latitude), str(input_data.longitude)
        observer.date = f"{input_data.date} {input_data.time}"

        # --- תיקון השגיאה כאן: חישוב המעלה (Ascendant) בצורה נכונה ---
        # קודם כל נחשב את זמן הכוכבים המקומי (Local Sidereal Time)
        lst_rad = observer.sidereal_time()
        
        # עכשיו נשתמש ב-LST כדי למצוא את המיקום על גלגל המזלות של המעלה
        # על ידי המרה של קואורדינטות משווניות לאקליפטיות
        equator_point = ephem.Equator(lst_rad, 0)
        ecliptic_point = ephem.Ecliptic(equator_point)
        ascendant = math.degrees(ecliptic_point.lon)
        # ----------------- סוף התיקון -----------------

        # חישוב 12 הבתים בשיטת הבתים השווים (Equal House)
        house_cusps = []
        for i in range(1, 13):
            cusp_longitude = (ascendant + (i-1) * 30) % 360
            sign, degree = get_sign_details(cusp_longitude)
            house_cusps.append(HouseCusp(
                house_number=i,
                longitude=round(cusp_longitude, 4),
                sign=sign,
                degree_in_sign=round(degree, 4)
            ))

        # חישוב מיקומי כוכבי הלכת
        planet_positions = []
        for name, PlanetClass in PLANET_MAPPING.items():
            planet = PlanetClass(observer)
            planet_lon = math.degrees(planet.ra)
            
            # חישוב האם הכוכב בנסיגה
            # השוואת קו האורך הנוכחי עם קו אורך של דקה לפני
            observer_prev = ephem.Observer()
            observer_prev.lat, observer_prev.lon = str(input_data.latitude), str(input_data.longitude)
            prev_datetime = datetime.fromisoformat(f"{input_data.date}T{input_data.time}") - timedelta(minutes=1)
            observer_prev.date = prev_datetime.strftime("%Y-%m-%d %H:%M")
            
            planet_prev = PlanetClass(observer_prev)
            is_retrograde = math.degrees(planet.ra) < math.degrees(planet_prev.ra)

            # מציאת הבית של הכוכב
            house_number = 1
            for i in range(11):
                # מציאת גבולות הבית
                start_lon = house_cusps[i].longitude
                end_lon = house_cusps[(i+1)%12].longitude
                
                # טיפול במקרה של מעבר בין 360 ל-0 מעלות
                if start_lon <= end_lon:
                    if start_lon <= planet_lon < end_lon:
                        house_number = i + 1
                        break
                else: # המעבר חוצה את נקודת ה-0
                    if planet_lon >= start_lon or planet_lon < end_lon:
                        house_number = i + 1
                        break
            else: # אם הכוכב בבית האחרון
                house_number = 12


            sign, degree = get_sign_details(planet_lon)
            planet_positions.append(PlanetPosition(
                name=name.title(),
                longitude=round(planet_lon, 4),
                sign=sign,
                degree_in_sign=round(degree, 4),
                is_retrograde=is_retrograde,
                house=house_number
            ))

        # חישוב ההיבטים
        aspects = calculate_aspects(planet_positions)

        return FullChartOutput(
            date_time=observer.date.strftime("%Y-%m-%d %H:%M"),
            location=f"Lat: {input_data.latitude}, Lon: {input_data.longitude}",
            planet_positions=planet_positions,
            house_cusps=house_cusps,
            aspects=aspects
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate chart: {str(e)}")

@app.get("/")
async def read_root():
    """
    A simple health check endpoint.
    """
    return {"message": "Astrology API is running"}
