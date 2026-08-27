from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


@router.post("")
def save_message(body: ChatMessage, db: Session = Depends(get_db)):
    return chat_service.save_message(db, body.role, body.content)


@router.get("/history")
def chat_history(limit: int = 50, db: Session = Depends(get_db)):
    return chat_service.get_history(db, limit)
