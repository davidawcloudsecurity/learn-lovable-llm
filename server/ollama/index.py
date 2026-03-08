"""
LearnLLM Backend - Pure FastAPI + Ollama
Direct HTTP calls to Ollama API - no LangChain needed!
Production-ready with proper error handling, rate limiting, and security
"""

import os
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables
load_dotenv()

# Configuration
PORT = int(os.getenv('PORT', 8000))
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
MODEL_NAME = os.getenv('OLLAMA_MODEL', 'smollm:1.7b')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.getenv('LOG_DIR', 'logs')
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:5173').split(',')
RATE_LIMIT = os.getenv('RATE_LIMIT', '10/minute')

# Setup logging
Path(LOG_DIR).mkdir(exist_ok=True)
logger = logging.getLogger(__name__)

if not logger.handlers:
    log_file = Path(LOG_DIR) / f"chat-{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(log_file)
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(getattr(logging, LOG_LEVEL))

# Initialize FastAPI
app = FastAPI(
    title="LearnLLM API (Ollama)",
    description="Pure FastAPI chatbot with direct Ollama HTTP calls",
    version="1.0.0"
)

# Rate limiting
# IMPORTANT: slowapi requires the FastAPI Request object to be named
# exactly `request` in every endpoint function. It scans by name, not type.
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Pydantic models
class Message(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=4000)

class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., min_length=1, max_length=50)

# System prompt
SYSTEM_PROMPT = """You are LearnLLM, a helpful AI assistant.
Be concise, clear, and friendly. Help users learn and understand concepts."""


async def stream_ollama_chat(messages: List[Message]):
    """Stream response from Ollama /api/chat (handles conversation history natively)"""

    # Convert to Ollama format
    ollama_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

    # Prepend system prompt if not already present
    if not ollama_messages or ollama_messages[0]["role"] != "system":
        ollama_messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    # read=None means no per-chunk timeout, which is correct for streaming
    timeout = httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL_NAME,
                "messages": ollama_messages,
                "stream": True,
                "options": {"temperature": 0.1}
            }
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
                        if data.get("done"):
                            return
                    except json.JSONDecodeError:
                        continue


async def stream_response(messages: List[Message], request_id: str):
    """Wrap Ollama stream into SSE format"""
    try:
        logger.info(f"[{request_id}] Request - messages: {len(messages)}, last_role: {messages[-1].role}")
        start_time = datetime.now()
        chunk_count = 0

        async for chunk in stream_ollama_chat(messages):
            if chunk:
                chunk_count += 1
                yield f"data: {json.dumps({'text': chunk})}\n\n"

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"[{request_id}] Complete - duration: {duration:.2f}s, chunks: {chunk_count}")
        yield "data: [DONE]\n\n"

    except httpx.TimeoutException:
        logger.error(f"[{request_id}] Timeout connecting to Ollama")
        yield f"data: {json.dumps({'error': 'Request timeout'})}\n\n"
    except httpx.HTTPStatusError as e:
        logger.error(f"[{request_id}] Ollama HTTP error: {e.response.status_code}")
        yield f"data: {json.dumps({'error': f'Ollama error: {e.response.status_code}'})}\n\n"
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {type(e).__name__}")
        yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"


# ---------------------------------------------------------------------------
# Routes
# Note: every rate-limited endpoint must have `request: Request` as a
# parameter - slowapi looks for this exact name to extract the client IP.
# ---------------------------------------------------------------------------

@app.get("/health/live")
async def liveness():
    """Liveness probe - is the process running?"""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness():
    """Readiness probe - is Ollama reachable?"""
    try:
        timeout = httpx.Timeout(connect=2.0, read=3.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            return {"status": "ready", "ollama": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama not ready: {str(e)}")


@app.get("/api/health")
async def health():
    """Combined health check (legacy)"""
    try:
        timeout = httpx.Timeout(connect=2.0, read=3.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            ollama_status = "connected"
    except Exception as e:
        ollama_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "service": "LearnLLM (Pure FastAPI + Ollama)",
        "model": MODEL_NAME,
        "ollama_status": ollama_status   # ollama_url removed (internal detail)
    }


@app.post("/api/chat")
@limiter.limit(RATE_LIMIT)
async def chat(chat_request: ChatRequest, request: Request):
    #                                     ^^^^^^^^^^^^^^^^
    # `request: Request` must be named exactly `request` for slowapi.
    # The body parameter is renamed to `chat_request` to avoid the clash.
    """Chat endpoint with streaming and rate limiting"""
    request_id = str(uuid.uuid4())

    return StreamingResponse(
        stream_response(chat_request.messages, request_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id
        }
    )


@app.get("/api/model-info")
async def model_info():
    """Model information (no internal URLs exposed)"""
    return {
        "model_name": MODEL_NAME,
        "framework": "Pure FastAPI + Ollama HTTP",
        "provider": "Local",
        "cost": "Free",
    }


@app.get("/api/models")
@limiter.limit("5/minute")
async def list_models(request: Request):
    #                  ^^^^^^^^^^^^^^^^
    # Same rule: must be named `request` for slowapi to work.
    """List available Ollama models"""
    try:
        timeout = httpx.Timeout(connect=2.0, read=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
            return {"models": [m["name"] for m in data.get("models", [])]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 60)
    logger.info("LearnLLM - Pure FastAPI + Ollama (Production)")
    logger.info("=" * 60)
    logger.info(f"Model:         {MODEL_NAME}")
    logger.info(f"Ollama:        {OLLAMA_URL}")
    logger.info(f"Port:          {PORT}")
    logger.info(f"Rate limit:    {RATE_LIMIT}")
    logger.info(f"CORS origins:  {ALLOWED_ORIGINS}")
    logger.info("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=PORT)
