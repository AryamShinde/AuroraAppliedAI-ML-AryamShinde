"""
Minimal Question-Answering API (clean build)
- Exposes /health and /ask
- Uses public GET /messages data as context
- Answers via OpenAI (set OPENAI_API_KEY in environment)
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
import httpx
from openai import OpenAI

# Load env from project .env explicitly (works regardless of CWD)
_env_path = Path(__file__).with_name('.env')
load_dotenv(dotenv_path=_env_path)
print(f"[qa_app] Loaded .env from {_env_path} -> OPENAI_API_KEY present: {bool(os.getenv('OPENAI_API_KEY'))}")

app = FastAPI(title="Member QA (Clean)", version="0.1.0")

# Config with safe defaults
DEFAULT_MESSAGES_URL = "https://november7-730026606190.europe-west1.run.app/messages/"
MESSAGES_API_URL = os.getenv("MESSAGES_API_URL", DEFAULT_MESSAGES_URL)
if not MESSAGES_API_URL.endswith("/"):
    # Avoid 307 redirect from upstream API
    MESSAGES_API_URL = MESSAGES_API_URL + "/"

# OpenAI client (created lazily in handler to surface missing key clearly)

auth_error = (
    "OpenAI API key not configured. Set OPENAI_API_KEY in your environment or .env file."
)


class Question(BaseModel):
    question: str


class Answer(BaseModel):
    answer: str


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "Member QA (Clean)"}


@app.get("/")
async def root() -> dict:
    """Simple landing endpoint so base URL doesn't 404."""
    return {
        "service": "Member QA (Clean)",
        "message": "Welcome. Use POST /ask with {'question': '...'} or see /docs.",
        "endpoints": {"health": "/health", "ask": "/ask", "docs": "/docs"},
    }


async def fetch_messages_data() -> dict:
    """Fetch messages JSON from the public API and return the parsed JSON dict."""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(MESSAGES_API_URL)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Upstream messages API error: {e}")


def build_context(messages_json: dict) -> str:
    """Convert items array to a compact text context for the LLM."""
    items = messages_json.get("items", [])
    lines = ["Member messages:\n"]
    for it in items:
        user = it.get("user_name", "Unknown")
        msg = it.get("message", "")
        ts = it.get("timestamp", "")
        lines.append(f"- {user} (on {ts}): {msg}")
    context = "\n".join(lines)
    # Trim to keep prompt size reasonable
    return context[-6000:] if len(context) > 6000 else context


def ask_openai(question: str, context: str) -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail=auth_error)

    client = OpenAI(api_key=key)

    system = (
        "You answer questions about member data based ONLY on the provided messages. "
        "If the answer is not in the messages, reply: I don't have enough information to answer that question."
    )
    user = f"""Context:\n{context}\n\nQuestion: {question}\nProvide a concise answer."""

    try:
        res = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "300")),
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")


@app.post("/ask", response_model=Answer)
async def ask(payload: Question) -> Answer:
    q = (payload.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    data = await fetch_messages_data()
    context = build_context(data)
    answer = ask_openai(q, context)
    return Answer(answer=answer)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8100))
    uvicorn.run(app, host="0.0.0.0", port=port)
