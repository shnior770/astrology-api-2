# השתמש ב-Image בסיסי של Python. בחר גרסה שתואמת למה ש-Render משתמש (Python 3.13.4 במקרה שלך)
FROM python:3.13.4-slim-bullseye

# הגדר משתני סביבה
ENV PYTHONUNBUFFERED 1

# הגדר את תיקיית העבודה בתוך הקונטיינר
WORKDIR /app

# התקן תלויות מערכת נחוצות עבור swisseph
# build-essential הוא לקומפילציה, libatlas-base-dev לספריות לינאריות (כמו numpy, שעשוי להיות תלות של swisseph)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libatlas-base-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# העתק את קובץ requirements.txt לתיקיית העבודה
COPY requirements.txt /app/

# התקן את התלויות של Python
RUN pip install --no-cache-dir -r requirements.txt

# העתק את שאר קבצי הפרויקט לתיקיית העבודה
COPY . /app/

# הגדר את פקודת ההפעלה של היישום
# Render ידרוס את זה עם ה-Start Command שאתה מגדיר בדשבורד, אבל טוב שיהיה כאן ברירת מחדל
CMD ["gunicorn", "main:app", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]