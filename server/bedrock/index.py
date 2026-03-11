"""
FastAPI backend for LearnLLM with Bedrock chat integration.

This server provides chat endpoints with session management, RAG, and guardrails.
"""

import json
import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Import chat module components
from chat.handler import chat_handler, get_session_history_handler
from chat.models import ChatRequest, ChatHistoryRequest

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="LearnLLM Bedrock API",
    description="Chat API with session management, RAG, and guardrails",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get configuration from environment
PORT = int(os.getenv("PORT", "8000"))
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")
CHAT_SESSIONS_TABLE_NAME = os.getenv("CHAT_SESSIONS_TABLE_NAME", "ChatSessions")
KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID", "")
GUARDRAIL_ID = os.getenv("GUARDRAIL_ID", "")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "LearnLLM Bedrock API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/api/health",
            "chat": "/api/chat",
            "history": "/api/chat/history"
        }
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "LearnLLM Bedrock API",
        "region": AWS_REGION,
        "model": MODEL_ID,
        "table": CHAT_SESSIONS_TABLE_NAME,
        "knowledge_base": KNOWLEDGE_BASE_ID if KNOWLEDGE_BASE_ID else "not configured",
        "guardrails": "enabled" if GUARDRAIL_ID else "disabled"
    }


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint with session management and RAG.
    
    Request body:
    {
        "session_id": "session_xxx" or null,  // null creates new session
        "message": "Your question here"
    }
    
    Response:
    {
        "session_id": "session_xxx",
        "messages": [
            {
                "message_id": "message_xxx",
                "message_type": "HUMAN" or "BOT",
                "message": "Message content",
                "timestamp": 1234567890,
                "intent": "CHAT" or "QUERY",
                "sources": [...] or null
            }
        ]
    }
    """
    try:
        # Convert Pydantic model to event format expected by handler
        event = {
            "body": request.model_dump_json()
        }
        
        # Call the chat handler
        response = chat_handler(event)
        
        # Parse the response body
        response_data = json.loads(response.body)
        
        # Return appropriate status code
        if response.status_code == 200:
            return JSONResponse(content=response_data, status_code=200)
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=response_data
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)}
        )


@app.post("/api/chat/history")
async def chat_history(request: ChatHistoryRequest):
    """
    Get chat session history.
    
    Request body:
    {
        "session_id": "session_xxx"
    }
    
    Response:
    {
        "session_id": "session_xxx",
        "messages": [...]
    }
    """
    try:
        # Convert Pydantic model to event format expected by handler
        event = {
            "body": request.model_dump_json()
        }
        
        # Call the history handler
        response = get_session_history_handler(event)
        
        # Parse the response body
        response_data = json.loads(response.body)
        
        # Return appropriate status code
        if response.status_code == 200:
            return JSONResponse(content=response_data, status_code=200)
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=response_data
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in history endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "message": str(e)}
        )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "path": str(request.url)
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    logger.info("=" * 60)
    logger.info("Starting LearnLLM Bedrock API Server")
    logger.info("=" * 60)
    logger.info(f"Port: {PORT}")
    logger.info(f"AWS Region: {AWS_REGION}")
    logger.info(f"Model: {MODEL_ID}")
    logger.info(f"DynamoDB Table: {CHAT_SESSIONS_TABLE_NAME}")
    logger.info(f"Knowledge Base: {KNOWLEDGE_BASE_ID if KNOWLEDGE_BASE_ID else 'Not configured'}")
    logger.info(f"Guardrails: {'Enabled' if GUARDRAIL_ID else 'Disabled'}")
    logger.info("=" * 60)
    
    # Check if repository is implemented
    try:
        from chat.repository import MessageRepository
        repo = MessageRepository(CHAT_SESSIONS_TABLE_NAME)
        # Try to call the methods to see if they're implemented
        try:
            repo.save_message("test", "test", "HUMAN", "test")
        except NotImplementedError:
            logger.warning("⚠️  WARNING: repository.py methods not implemented yet!")
            logger.warning("   You need to implement save_message() and get_messages()")
            logger.warning("   See chat/repository.py for details")
    except Exception as e:
        logger.warning(f"Could not check repository implementation: {e}")
    
    logger.info("")
    logger.info("API Documentation: http://localhost:{}/docs".format(PORT))
    logger.info("")
    
    uvicorn.run(
        "index:app",
        host="0.0.0.0",
        port=PORT,
        reload=True,
        log_level="info"
    )
