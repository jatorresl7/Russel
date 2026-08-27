from sqlalchemy.orm import Session
from app.db import Conversation


def save_message(db: Session, role: str, content: str) -> dict:
    msg = Conversation(role=role, content=content)
    db.add(msg)
    db.commit()
    return {"id": msg.id}


def get_history(db: Session, limit: int = 50) -> list:
    msgs = db.query(Conversation).order_by(Conversation.created_at.desc()).limit(limit).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "created_at": str(m.created_at)} for m in reversed(msgs)]
