from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.services import gmail_service

router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.post("/summarize")
def summarize(db: Session = Depends(get_db)):
    return gmail_service.summarize_today(db)


@router.get("/summaries")
def summaries(db: Session = Depends(get_db)):
    return gmail_service.get_summaries(db)
