# backend/app/schemas/chatbot_schema.py

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = "user"  # "user" or "assistant"
    content: str


class ChatbotAskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Financial query for the Virtual CFO")
    history: Optional[List[ChatMessage]] = Field(default_factory=list)


class ChatbotAskResponse(BaseModel):
    answer: str
    tools_executed: List[str] = Field(default_factory=list)
    status: str = "completed"
    source: str = "gemini_function_calling"
    warnings: Optional[List[str]] = None


class SuggestedQuestionsResponse(BaseModel):
    categories: Dict[str, List[str]]
