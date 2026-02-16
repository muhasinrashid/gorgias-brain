from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from backend.database import get_db
from backend.models import AuditLog
from backend.dependencies import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

class FeedbackRequest(BaseModel):
    org_id: int
    ticket_id: str
    suggestion_id: str = None # Optional correlation ID
    helpful: bool # True for Thumbs Up, False for Thumbs Down
    feedback_text: str = None

@router.post("/log")
def log_audit_event(feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """
    Logs feedback and other audit events.
    """
    try:
        action = "feedback_positive" if feedback.helpful else "feedback_negative"
        
        log_entry = AuditLog(
            org_id=feedback.org_id,
            action=action,
            details={
                "ticket_id": feedback.ticket_id,
                "suggestion_id": feedback.suggestion_id,
                "feedback_text": feedback.feedback_text
            }
        )
        
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        
        return {"status": "recieved", "id": log_entry.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
