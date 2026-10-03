import os

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="TactiVision IA Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://tactivision-frontend.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_database_status() -> str:
    username = os.getenv("NEON_DB_USERNAME")
    password = os.getenv("NEON_DB_PASSWORD")
    database_url = os.getenv("NEON_DB_URL")

    if not username or not password or not database_url:
        return "DISCONNECTED"

    try:
        with psycopg2.connect(
            database_url,
            user=username,
            password=password
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status FROM system_status WHERE name = 'TactiVision'"
                )
                row = cursor.fetchone()

        if row and row[0] == "ACTIVE":
            return "CONNECTED"

        return "DISCONNECTED"

    except Exception:
        return "DISCONNECTED"

@app.get("/api/hello")
def get_hello():
    return {"message": "Hello from TactiVision IA backend"}

@app.get("/api/status")
def get_status():
    return {
        "backend": "OK",
        "database": get_database_status(),
    }
