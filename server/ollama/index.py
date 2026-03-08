"""
LearnLLM Backend - Pure FastAPI + Ollama
Direct HTTP calls to Ollama API - no LangChain needed!
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
PORT = int(os.getenv('PORT', 8000))
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
MODEL_NAME = os.getenv('OLLAMA_MODEL', 'smollm:1.7b')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.getenv('LOG_DIR', 'logs')

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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

# System prompt
SYSTEM_PROMPT = """You are LearnLLM, a helpful AI assistant.

Be concise, clear, and friendly. Help users learn and understand concepts."""


async def call_ollama(prompt: str) -> str:
    """
    Call Ollama API directly
    
    Args:
        prompt: The prompt to send
        
    Returns:
        Response text from Ollama
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1
                }
            }
        )
        response.raise_for_status()
        data = response.json()
        return data.get('response', '')


async def stream_ollama(prompt: str):
    """
    Stream response from Ollama API
    
    Args:
        prompt: The prompt to send
        
    Yields:
        Response chunks from Ollama
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            'POST',
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
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
                        if 'response' in data:
                            yield data['response']
                    except json.JSONDecodeError:
                        continue


async def stream_response(messages: List[Message], request_id: str):
    """Stream chat response in SSE format"""
    try:
        user_message = messages[-1].content if messages else ""
        logger.info(f"[{request_id}] Query: {user_message[:100]}...")
        
        start_time = datetime.now()
        
        # Build prompt
        prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_message}\nAssistant:"
        
        # Stream from Ollama
        async for chunk in stream_ollama(prompt):
            if chunk:
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"[{request_id}] Done in {duration:.2f}s")
        
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"[{request_id}] Error: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@app.get("/api/health")
async def health():
    """Health check"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
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
async def chat(request: ChatRequest):
    """Chat endpoint with streaming"""
    request_id = str(int(datetime.now().timestamp() * 1000))
    
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages required")
    
    return StreamingResponse(
        stream_response(request.messages, request_id),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
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
async def list_models():
    """List available Ollama models"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
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
    logger.info("LearnLLM - Pure FastAPI + Ollama")
    logger.info("=" * 60)
    logger.info(f"Model: {MODEL_NAME}")
    logger.info(f"Ollama: {OLLAMA_URL}")
    logger.info(f"Port: {PORT}")
    logger.info(f"Dependencies: FastAPI + httpx only!")
    logger.info("=" * 60)
    
    uvicorn.run(app, host='0.0.0.0', port=PORT)
