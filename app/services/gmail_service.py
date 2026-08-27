from datetime import date
from io import StringIO
import sys
from sqlalchemy.orm import Session
from app.db import GmailSummary
from app.services.gmail import get_gmail_service, get_emails_today, summarize_emails, get_llm_client


def summarize_today(db: Session) -> dict:
    existing = db.query(GmailSummary).filter(GmailSummary.date == date.today()).first()
    if existing:
        return {"message": "Ya existe un resumen para hoy", "summary": existing.summary}

    service = get_gmail_service()
    emails = get_emails_today(service)
    if not emails:
        return {"message": "No hay correos hoy"}

    llm = get_llm_client()
    buf = StringIO()
    sys.stdout = buf
    summarize_emails(emails, llm)
    sys.stdout = sys.__stdout__
    output = buf.getvalue()
    summary_text = output.split("===\n", 1)[-1].strip() if "===" in output else output.strip()

    record = GmailSummary(date=date.today(), summary=summary_text, email_count=len(emails))
    db.add(record)
    db.commit()

    return {"date": str(date.today()), "email_count": len(emails), "summary": summary_text}


def get_summaries(db: Session) -> list:
    rows = db.query(GmailSummary).order_by(GmailSummary.date.desc()).limit(30).all()
    return [{"id": r.id, "date": str(r.date), "email_count": r.email_count, "summary": r.summary} for r in rows]
