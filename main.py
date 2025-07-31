# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime, timedelta

# ייבוא עבור PyEphem
import ephem
import math

# ----------------- App Definition -----------------
app = FastAPI(
    title="Astrology API",
    description="API for historical astrological calculations.",
    version="0.2.1", # עדכון גרסה לשימוש ב-ephem
)

# ----------------- Helper Mappings -----------------
# מפת כוכבי לכת עבור ephem
PLANET_MAPPING = {
    "sun": ephem.Sun,
    "moon": ephem.Moon,
    "mercury": ephem.Mercury,
    "venus": ephem.Venus,
    "mars": ephem.Mars,
    "jupiter": ephem.Jupiter,
    "saturn": ephem.Saturn,
    "uranus": ephem.Uranus,
    "neptune": ephem.Neptune,
    "pluto": ephem.Pluto,
}

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

# ----------------- API Endpoints -----------------

@app.post("/api/constellation-search", response_model=ConstellationSearchOutput)
async def constellation_search(input_data: ConstellationSearchInput):
    planet_name_lower = input_data.star_name.lower()
    sign_name_lower = input_data.sign_name.lower()

    PlanetClass = PLANET_MAPPING.get(planet_name_lower)
    if PlanetClass is None:
        raise HTTPException(status_code=400, detail=f"Invalid star name: {input_data.star_name}")

    # הגדרת מזלות
    signs = [
        "aries", "taurus", "gemini", "cancer", "leo", "virgo",
        "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"
    ]
    if sign_name_lower not in signs:
        raise HTTPException(status_code=400, detail=f"Invalid sign name: {input_data.sign_name}")
    
    target_sign_index = signs.index(sign_name_lower)
    
    results_found = []
    current_dt = datetime(input_data.start_year, 1, 1)
    end_dt = datetime(input_data.end_year + 1, 1, 1)

    last_sign_id = -1
    last_longitude = -1.0

    while current_dt < end_dt:
        # יצירת אובייקט כוכב לכת
        planet = PlanetClass()
        
        # חישוב מיקום הכוכב לתאריך הנוכחי
        planet.compute(current_dt)

        # המרה ממעלות מעריכיות (Decimal degrees) ל-360 מעלות
        longitude = math.degrees(planet.ra)

        current_sign_id = int(longitude / 30)

        # בדיקה אם הכוכב נכנס למזל היעד
        # נבדוק גם אם המעבר הוא חיובי (לא נסיגה חוזרת לאותו מזל)
        if current_sign_id == target_sign_index and last_sign_id != target_sign_index:
            position_details = CelestialBodyPosition(
                name=input_data.star_name.title(),
                longitude=round(longitude, 4),
                sign=input_data.sign_name.title(),
                degree_in_sign=round(longitude % 30, 4),
                # חישוב נסיגה: מהירות הירח היא שלילית כשנמצא בנסיגה
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


@app.get("/")
async def read_root():
    """A simple health check endpoint."""
    return {"message": "Astrology API is running"}
