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

# Setup logging (only if not already configured)
Path(LOG_DIR).mkdir(exist_ok=True)

# Get logger
logger = logging.getLogger(__name__)

# Only configure if no handlers exist
if not logger.handlers:
    log_file = Path(LOG_DIR) / f"chat-{datetime.now().strftime('%Y-%m-%d')}.log"
    
    # Create handlers
    file_handler = logging.FileHandler(log_file)
    console_handler = logging.StreamHandler()
    
    # Set format
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers
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
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - restricted to allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Pydantic models with validation
class Message(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=4000)

class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., min_length=1, max_length=50)

# System prompt
SYSTEM_PROMPT = """You are LearnLLM, a helpful AI assistant.

Be concise, clear, and friendly. Help users learn and understand concepts."""


async def stream_ollama_chat(messages: List[Message]):
    """
    Stream response from Ollama /api/chat endpoint (handles conversation history natively)
    
    Args:
        messages: List of conversation messages
        
    Yields:
        Response chunks from Ollama
    """
    # Convert to Ollama format
    ollama_messages = [{"role": msg.role, "content": msg.content} for msg in messages]
    
    # Add system prompt if not present
    if not ollama_messages or ollama_messages[0]["role"] != "system":
        ollama_messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    
    # Granular timeout settings
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            'POST',
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL_NAME,
                "messages": ollama_messages,
                "stream": True,
                "options": {
                    "temperature": 0.1
                }
            }
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if 'message' in data and 'content' in data['message']:
                            yield data['message']['content']
                    except json.JSONDecodeError:
                        continue


async def stream_response(messages: List[Message], request_id: str):
    """Stream chat response in SSE format"""
    try:
        # Log metadata only (no PII)
        logger.info(f"[{request_id}] Request - messages: {len(messages)}, last_role: {messages[-1].role}")
        
        start_time = datetime.now()
        chunk_count = 0
        
        # Stream from Ollama using /api/chat (handles conversation history)
        async for chunk in stream_ollama_chat(messages):
            if chunk:
                chunk_count += 1
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"[{request_id}] Complete - duration: {duration:.2f}s, chunks: {chunk_count}")
        
        yield "data: [DONE]\n\n"
        
    except httpx.TimeoutException as e:
        logger.error(f"[{request_id}] Timeout: {e}")
        yield f"data: {json.dumps({'error': 'Request timeout'})}\n\n"
    except httpx.HTTPStatusError as e:
        logger.error(f"[{request_id}] HTTP error: {e.response.status_code}")
        yield f"data: {json.dumps({'error': f'Ollama error: {e.response.status_code}'})}\n\n"
    except Exception as e:
        logger.error(f"[{request_id}] Error: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"


@app.get("/health/live")
async def liveness():
    """Liveness probe - is the process running?"""
    return {'status': 'ok'}


@app.get("/health/ready")
async def readiness():
    """Readiness probe - is Ollama reachable?"""
    try:
        timeout = httpx.Timeout(connect=2.0, read=3.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            return {'status': 'ready', 'ollama': 'connected'}
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
            status = "connected"
    except Exception as e:
        status = f"error: {str(e)}"
    
    return {
        'status': 'ok',
        'service': 'LearnLLM (Pure FastAPI + Ollama)',
        'model': MODEL_NAME,
        'ollama_url': OLLAMA_URL,
        'ollama_status': status
    }


@app.post("/api/chat")
@limiter.limit(RATE_LIMIT)
async def chat(request: ChatRequest, req: Request):
    """Chat endpoint with streaming and rate limiting"""
    request_id = str(uuid.uuid4())
    
    return StreamingResponse(
        stream_response(request.messages, request_id),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'X-Request-ID': request_id
        }
    )


@app.get("/api/model-info")
async def model_info():
    """Model information"""
    return {
        'model_name': MODEL_NAME,
        'ollama_url': OLLAMA_URL,
        'framework': 'Pure FastAPI + Ollama HTTP',
        'provider': 'Local',
        'cost': 'Free',
        'dependencies': ['fastapi', 'httpx']
    }


@app.get("/api/models")
@limiter.limit("5/minute")
async def list_models(req: Request):
    """List available Ollama models"""
    try:
        timeout = httpx.Timeout(connect=2.0, read=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
            return {
                'models': [m['name'] for m in data.get('models', [])]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    import uvicorn
    
    logger.info("=" * 60)
    logger.info("LearnLLM - Pure FastAPI + Ollama (Production)")
    logger.info("=" * 60)
    logger.info(f"Model: {MODEL_NAME}")
    logger.info(f"Ollama: {OLLAMA_URL}")
    logger.info(f"Port: {PORT}")
    logger.info(f"Rate limit: {RATE_LIMIT}")
    logger.info(f"Allowed origins: {ALLOWED_ORIGINS}")
    logger.info("=" * 60)
    
    uvicorn.run(app, host='0.0.0.0', port=PORT)
