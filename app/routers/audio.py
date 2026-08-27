from fastapi import APIRouter

from app.services import audio_service

router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("/status")
def status():
    return audio_service.status()


@router.post("/start")
def start():
    return audio_service.start()


@router.post("/stop")
def stop():
    return audio_service.stop()


@router.post("/clear")
def clear():
    return audio_service.clear()
