# backend/app/api/chatbot/routes.py

"""
PHASE 7: AI VIRTUAL CFO CHATBOT API ROUTES

Prefix: /api/v1/chatbot

Endpoints:
- POST /api/v1/chatbot/ask: Accepts query + history, executes tool calling with Gemini, returns answer
- GET  /api/v1/chatbot/suggested: Returns contextual starter questions for business owners
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.chatbot_schema import (
    ChatbotAskRequest,
    ChatbotAskResponse,
    SuggestedQuestionsResponse,
)
from app.services import chatbot_service

router = APIRouter(prefix="/chatbot", tags=["AI Virtual CFO Chatbot"])


@router.get("/suggested", response_model=SuggestedQuestionsResponse)
def get_suggested_questions():
    """Returns curated starter questions across major CFO domains."""
    return {
        "categories": {
            "Revenue & Sales": [
                "What is my total invoiced revenue to date?",
                "What is my average invoice size this month?",
                "How much sales revenue have we collected versus invoiced?",
            ],
            "GST & Tax Compliance": [
                "What is my current net GST liability?",
                "How much eligible Input Tax Credit (ITC) do I have?",
                "When is my next GSTR-3B return due?",
            ],
            "Cash Flow & Outstanding": [
                "Show me all overdue or unpaid customer invoices.",
                "Which customers owe the highest outstanding balance?",
                "What was my last incoming customer payment?",
            ],
            "Operations & Ledger": [
                "Give me a breakdown of all invoices by status.",
                "How many invoices are currently in draft state?",
            ],
        }
    }


@router.post("/ask", response_model=ChatbotAskResponse)
def ask_virtual_cfo(
    payload: ChatbotAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submits a prompt to the AI Virtual CFO.
    Orchestrates Gemini structured tool calling against the user's private data.
    """
    history_dicts = [h.model_dump() for h in (payload.history or [])]
    result = chatbot_service.ask_cfo_chatbot(
        db=db,
        user_id=current_user.id,
        query=payload.query,
        history=history_dicts,
    )
    return ChatbotAskResponse(**result)
