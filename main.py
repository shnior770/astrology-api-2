import os
import ephem
import traceback
import math
from datetime import datetime, date, timedelta
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from astral import LocationInfo
from astral.sun import sun
import pytz

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware to allow requests from the dashboard frontend
origins = [
    "https://base44.app",
    "http://localhost:5173",  # Assuming local development is on port 5173
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for request and response data validation
class ChartRequest(BaseModel):
    city: str
    latitude: float
    longitude: float
    datetime: datetime


class Planet(BaseModel):
    name: str
    degree: float
    sign: str
    is_retrograde: bool
    is_in_sign: bool


class ChartData(BaseModel):
    sun: Planet
    moon: Planet
    mercury: Planet
    venus: Planet
    mars: Planet
    jupiter: Planet
    saturn: Planet
    uranus: Planet
    neptune: Planet
    pluto: Planet
    moon_phase: str
    day_length: str
    sunrise_time: str
    sunset_time: str

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


# Mappings for the constellation search endpoint
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

# ----------------- API Endpoints -----------------

@app.get("/")
async def root():
    return {"message": "Welcome to the Astrology API!"}


@app.post("/api/get-chart", response_model=ChartData)
async def get_chart(request_data: ChartRequest):
    """
    Calculates and returns astrological chart data based on user input.
    """
    print("Request received for get_chart endpoint.")
    print(f"Incoming data: {request_data.model_dump_json()}")

    try:
        # Create an observer object with the provided location data
        observer = ephem.Observer()
        observer.lat = str(request_data.latitude)
        observer.lon = str(request_data.longitude)

        # Fix for ephem date format issue
        date_str = request_data.datetime.strftime('%Y/%m/%d %H:%M:%S')
        observer.date = date_str

        # Calculate planet positions and other data
        chart_data = {
            "sun": {"name": "Sun", "is_retrograde": False},
            "moon": {"name": "Moon", "is_retrograde": False},
            "mercury": {"name": "Mercury", "is_retrograde": False},
            "venus": {"name": "Venus", "is_retrograde": False},
            "mars": {"name": "Mars", "is_retrograde": False},
            "jupiter": {"name": "Jupiter", "is_retrograde": False},
            "saturn": {"name": "Saturn", "is_retrograde": False},
            "uranus": {"name": "Uranus", "is_retrograde": False},
            "neptune": {"name": "Neptune", "is_retrograde": False},
            "pluto": {"name": "Pluto", "is_retrograde": False},
        }

        # Ephem objects for calculation
        planets = {
            "sun": ephem.Sun(),
            "moon": ephem.Moon(),
            "mercury": ephem.Mercury(),
            "venus": ephem.Venus(),
            "mars": ephem.Mars(),
            "jupiter": ephem.Jupiter(),
            "saturn": ephem.Saturn(),
            "uranus": ephem.Uranus(),
            "neptune": ephem.Neptune(),
            "pluto": ephem.Pluto(),
        }

        # Calculate position for each planet and check for retrograde
        signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

        for name, planet_obj in planets.items():
            planet_obj.compute(observer)
            degree = ephem.degrees(planet_obj.ra).znorm
            sign_index = int(degree / (ephem.pi / 6))
            chart_data[name]["degree"] = round(degree * 180 / ephem.pi, 2)
            chart_data[name]["sign"] = signs[sign_index]

            # Check for retrograde motion
            if name in ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]:
                # The logic for retrograde check in ephem is complex. A simple check of current RA vs previous RA is not reliable
                # and can lead to false positives. For this simple implementation, we'll assume planets are not retrograde unless
                # a more advanced algorithm is implemented.
                # A proper implementation would require computing the planet's position a day before and a day after
                # and comparing the RA values.
                # To avoid errors, we are currently not setting the is_retrograde flag.
                pass


            # Check if planet is in its own sign
            # This logic needs to be expanded with more rules for rulership
            chart_data[name]["is_in_sign"] = False # placeholder

        # The ephem.Moon() object in the 'planets' dictionary has already been computed
        # so we can use it to get the phase without a RuntimeError.
        moon_phase_value = planets['moon'].phase
        chart_data["moon_phase"] = "New Moon" if 0 <= moon_phase_value < 15 else "Full Moon" if 15 <= moon_phase_value <= 25 else "Gibbous"

        # Calculate day length and sunrise/sunset times
        city = LocationInfo(request_data.city, "Israel", "Asia/Jerusalem", request_data.latitude, request_data.longitude)
        s = sun(city.observer, date=request_data.datetime.date(), tzinfo=pytz.timezone(city.timezone))

        sunrise_time = s['sunrise'].strftime('%H:%M:%S')
        sunset_time = s['sunset'].strftime('%H:%M:%S')
        day_length_seconds = (s['sunset'] - s['sunrise']).seconds
        
        # --- FIX: Changed datetime.timedelta to timedelta as it's already imported ---
        day_length = str(timedelta(seconds=day_length_seconds))

        chart_data["day_length"] = day_length
        chart_data["sunrise_time"] = sunrise_time
        chart_data["sunset_time"] = sunset_time

        return ChartData(**chart_data)

    except Exception as e:
        # Catch any exception and log it with a full traceback
        error_message = f"An unexpected error occurred in get_chart: {e}\n{traceback.format_exc()}"
        print(error_message)
        # Raise an HTTPException to return a 500 status code to the client
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_message)


@app.post("/api/constellation-search", response_model=ConstellationSearchOutput)
async def constellation_search(input_data: ConstellationSearchInput):
    planet_name_lower = input_data.star_name.lower()
    sign_name_lower = input_data.sign_name.lower()

    PlanetClass = PLANET_MAPPING.get(planet_name_lower)
    if PlanetClass is None:
        raise HTTPException(status_code=400, detail=f"Invalid star name: {input_data.star_name}")

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
        planet = PlanetClass()
        planet.compute(current_dt)
        longitude = math.degrees(planet.ra)
        current_sign_id = int(longitude / 30)

        if current_sign_id == target_sign_index and last_sign_id != target_sign_index:
            position_details = CelestialBodyPosition(
                name=input_data.star_name.title(),
                longitude=round(longitude, 4),
                sign=input_data.sign_name.title(),
                degree_in_sign=round(longitude % 30, 4),
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
