import os
import ephem
import traceback
from datetime import datetime
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
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
                if planet_obj.ra < planets[name].ra:
                    chart_data[name]["is_retrograde"] = True
                
            # Check if planet is in its own sign
            # This logic needs to be expanded with more rules for rulership
            chart_data[name]["is_in_sign"] = False # placeholder

        # Calculate moon phase
        moon_phase = ephem.Moon().phase
        chart_data["moon_phase"] = "New Moon" if 0 <= moon_phase < 15 else "Full Moon" if 15 <= moon_phase <= 25 else "Gibbous"

        # Calculate day length and sunrise/sunset times
        city = LocationInfo(request_data.city, "Israel", "Asia/Jerusalem", request_data.latitude, request_data.longitude)
        s = sun(city.observer, date=request_data.datetime.date(), tzinfo=pytz.timezone(city.timezone))
        
        sunrise_time = s['sunrise'].strftime('%H:%M:%S')
        sunset_time = s['sunset'].strftime('%H:%M:%S')
        day_length_seconds = (s['sunset'] - s['sunrise']).seconds
        day_length = str(datetime.timedelta(seconds=day_length_seconds))
        
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

