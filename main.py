from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime, timedelta

# ייבוא עבור Swiss Ephemeris
import swisseph as swe

# ----------------- App Definition -----------------
app = FastAPI(
    title="Astrology API",
    description="API for historical astrological calculations.",
    version="0.2.0", # עדכון גרסה
)

# ----------------- Helper Mappings -----------------
PLANET_MAPPING = {
    "sun": swe.SUN, "moon": swe.MOON, "mercury": swe.MERCURY, "venus": swe.VENUS,
    "mars": swe.MARS, "jupiter": swe.JUPITER, "saturn": swe.SATURN, "uranus": swe.URANUS,
    "neptune": swe.NEPTUNE, "pluto": swe.PLUTO,
}

SIGN_MAPPING = {
    "aries": 0, "taurus": 1, "gemini": 2, "cancer": 3, "leo": 4, "virgo": 5,
    "libra": 6, "scorpio": 7, "sagittarius": 8, "capricorn": 9, "aquarius": 10, "pisces": 11
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
    hebrew_name: Optional[str] = None
    longitude: float
    sign: str
    degree_in_sign: float
    is_retrograde: bool

class ConstellationSearchResult(BaseModel):
    date: date
    description: str
    celestial_bodies: List[CelestialBodyPosition] # נמלא את הרשימה הזו

class ConstellationSearchOutput(BaseModel):
    status: str = "success"
    results: List[ConstellationSearchResult]

# ----------------- API Endpoints -----------------

@app.post("/api/constellation-search", response_model=ConstellationSearchOutput)
async def constellation_search(input_data: ConstellationSearchInput):
    swe.set_ephe_path('')

    planet_name_lower = input_data.star_name.lower()
    sign_name_lower = input_data.sign_name.lower()

    planet_id = PLANET_MAPPING.get(planet_name_lower)
    if planet_id is None:
        raise HTTPException(status_code=400, detail=f"Invalid star name: {input_data.star_name}")

    sign_id = SIGN_MAPPING.get(sign_name_lower)
    if sign_id is None:
        raise HTTPException(status_code=400, detail=f"Invalid sign name: {input_data.sign_name}")

    results_found = []
    current_dt = datetime(input_data.start_year, 1, 1)
    end_dt = datetime(input_data.end_year + 1, 1, 1)

    last_sign_id = -1

    while current_dt < end_dt:
        jd_utc = swe.julday(current_dt.year, current_dt.month, current_dt.day, 0.0)

        # *** שינוי כאן: הוספנו דגל לחישוב מהירות (FLG_SPEED) ***
        # התוצאה תחזיר כעת גם את מהירות הכוכב, שמאפשרת לזהות נסיגה
        ret = swe.calc_ut(jd_utc, planet_id, swe.FLG_SWIEPH | swe.FLG_SPEED)
        
        longitude = ret[0][0]
        # *** שינוי כאן: קבלת מהירות הכוכב מהתוצאה ***
        speed = ret[0][3]

        current_sign_id = int(longitude / 30)
        
        if current_sign_id == sign_id and last_sign_id != sign_id:
            # *** שינוי כאן: יצירת אובייקט עם כל פרטי המיקום ***
            position_details = CelestialBodyPosition(
                name=input_data.star_name.title(),
                longitude=round(longitude, 4),
                sign=input_data.sign_name.title(),
                # חישוב המעלה בתוך המזל (0-30)
                degree_in_sign=round(longitude % 30, 4),
                # מהירות שלילית משמעותה נסיגה
                is_retrograde=(speed < 0)
            )

            found_item = ConstellationSearchResult(
                date=current_dt.date(),
                description=f"{input_data.star_name.title()} entered {input_data.sign_name.title()}",
                # *** שינוי כאן: הוספת האובייקט לרשימה ***
                celestial_bodies=[position_details]
            )
            results_found.append(found_item)

            if len(results_found) >= input_data.limit:
                break

        last_sign_id = current_sign_id
        current_dt += timedelta(days=1)

    return ConstellationSearchOutput(results=results_found)


@app.get("/")
async def read_root():
    """A simple health check endpoint."""
    return {"message": "Astrology API is running"}