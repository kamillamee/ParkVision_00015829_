"""Chatbot API for parking assistance."""
import os
import re
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field
from backend.config import CHAT_ENABLED, OPENAI_API_KEY, CHAT_RATE_LIMIT
from backend.limiter import limiter

router = APIRouter(prefix="/api/chat", tags=["chat"])

SYSTEM_CONTEXT = """You are a helpful assistant for the Smart Vision System. You only answer questions about:
- Parking availability and how to check slot status
- How to register, login, add a car, make a reservation
- Pricing and payment (mention it is processed securely)
- General FAQ about Smart Vision

Keep answers short and friendly. If the user asks something off-topic, say you can only help with Smart Vision questions.
Do not give personal or financial advice. Do not make up specific prices or slot numbers."""

FAQ_FALLBACK = {
    "availability": "You can see live parking availability on the home page or in your dashboard. Green slots are available, red are occupied.",
    "reserve": "To reserve: log in, add a car in My Cars, then go to Dashboard or Reservations and choose a slot and time.",
    "register": "Click Sign Up on the top right. You need a phone number and password. After registering you can add cars and make reservations.",
    "login": "Use the Login link and enter your phone number and password.",
    "add car": "After logging in, go to My Cars and click Add Car. Enter plate number; brand and model are optional.",
    "price": "Pricing is shown when you make a reservation. Payment is processed securely after you confirm the booking.",
    "payment": "After creating a reservation you will be asked to confirm payment. The system uses secure payment processing.",
    "help": "I can help with: checking availability, how to register/login, adding a car, making a reservation, and general parking questions. What do you need?",
}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User message")


class ChatResponse(BaseModel):
    reply: str
    source: str = "faq"  # "faq" or "ai"


def _sanitize_message(text: str) -> str:
    """Keep only safe characters for FAQ matching."""
    return re.sub(r"[^\w\s?.,!]", "", text.lower()).strip()


def _faq_reply(user_message: str) -> str:
    """Return a reply from FAQ if a keyword matches."""
    msg = _sanitize_message(user_message)
    for keyword, reply in FAQ_FALLBACK.items():
        if keyword in msg:
            return reply
    return "I can help with parking availability, reservations, adding a car, and account questions. Try asking e.g. 'How do I reserve a slot?' or 'How do I add a car?'"


async def _openai_reply(user_message: str) -> str | None:
    """Call OpenAI API if key is set. Returns None on failure."""
    if not OPENAI_API_KEY:
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": SYSTEM_CONTEXT},
                        {"role": "user", "content": user_message},
                    ],
                    "max_tokens": 300,
                },
            )
            if r.status_code != 200:
                return None
            data = r.json()
            choice = data.get("choices", [{}])[0]
            return (choice.get("message") or {}).get("content", "").strip() or None
    except Exception:
        return None


@router.post("/", response_model=ChatResponse)
@limiter.limit(CHAT_RATE_LIMIT)
async def chat_post(request: Request, body: ChatRequest):
    """Send a message to the parking assistant. Rate limited."""
    if not CHAT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is temporarily disabled.",
        )
    user_message = (body.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required.")

    reply_ai = await _openai_reply(user_message)
    if reply_ai:
        return ChatResponse(reply=reply_ai, source="ai")
    return ChatResponse(reply=_faq_reply(user_message), source="faq")
