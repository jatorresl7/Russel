"""Jarvis solo-vision: monta unicamente /vision, sin tocar PostgreSQL.
Util mientras la DB del proyecto no levanta.

  python3 -m uvicorn vision_only:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI

from app.routers import vision, robot, audio, system

app = FastAPI(title="Jarvis Vision")
app.include_router(vision.router)
app.include_router(robot.router)
app.include_router(audio.router)
app.include_router(system.router)
