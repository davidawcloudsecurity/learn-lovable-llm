"""
LearnLLM Backend - Strands Framework with Conversation Memory

This is the STATEFUL version of the chat server. Unlike app.py (which forgets
everything after each request), this version REMEMBERS previous messages in a
conversation using two mechanisms:

  1. SlidingWindowConversationManager — keeps the last N messages in RAM so the
     LLM can see recent context (like short-term memory)
  2. FileSessionManager — saves the full conversation to a JSON file on disk
     so it survives server restarts (like long-term memory)

Architecture:
  UI --POST {messages, session_id}--> Flask (/api/chat)
                                        |
                                        v
                                  agent_cache[session_id]  ← reuses the SAME agent for a session
                                        |
                                        v
                                  Strands Agent (has memory of past messages)
                                        |
                                        v
                                  AWS Bedrock LLM (sees system prompt + recent history + new message)
                                        |
  UI <---SSE stream--- Flask <--- response text

Key difference from app.py:
  - app.py: ONE global agent, no memory, every request is independent
  - app_with_memory.py: ONE agent PER SESSION, each remembers its conversation history
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Generator, Dict

from flask import Flask, request, Response, jsonify, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from botocore.config import Config as BotocoreConfig

from strands import Agent
from strands.models import BedrockModel
# SlidingWindowConversationManager: keeps only the last N messages in the agent's
# context window. Without this, the conversation would grow forever and eventually
# exceed the LLM's token limit (or get very expensive).
from strands.agent.conversation_manager import SlidingWindowConversationManager
# FileSessionManager: saves/loads conversation state to/from JSON files on disk.
# This means if the server restarts, conversations are NOT lost.
from strands.session.file_session_manager import FileSessionManager

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
load_dotenv()

PORT = int(os.getenv('PORT'))
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', '')
MODEL_ID = os.getenv('MODEL_ID', '')
LOG_LEVEL = os.getenv('LOG_LEVEL', '')
LOG_DIR = os.getenv('LOG_DIR', '')
SESSION_DIR = os.getenv('SESSION_DIR', '')        # Where conversation JSON files are stored on disk
CONVERSATION_WINDOW = int(os.getenv('CONVERSATION_WINDOW'))  # How many recent messages the LLM sees


# ---------------------------------------------------------------------------
# LOGGING & DIRECTORIES
# ---------------------------------------------------------------------------
Path(LOG_DIR).mkdir(exist_ok=True)
Path(SESSION_DIR).mkdir(exist_ok=True)  # Create session storage folder if it doesn't exist

log_file = Path(LOG_DIR) / f"chat-{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FLASK APP
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# AGENT CACHE — this is the core of the memory system
# ---------------------------------------------------------------------------
# A dictionary mapping session_id -> Agent instance.
# Each session gets its OWN agent with its OWN conversation history.
# Example: {"session-1234": Agent(...), "session-5678": Agent(...)}
#
# ⚠️ WARNING: This lives in RAM. If the server restarts, the cache is empty.
# The FileSessionManager handles persistence to disk, but the agents themselves
# need to be recreated (they'll reload history from the JSON files).
agent_cache: Dict[str, Agent] = {}


# ---------------------------------------------------------------------------
# BEDROCK MODEL — same as app.py, just the LLM connection config
# ---------------------------------------------------------------------------
def create_bedrock_model():
    """Create and configure Bedrock model (identical to app.py)"""
    boto_config = BotocoreConfig(
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=5,
        read_timeout=60,
        region_name=AWS_REGION
    )
    
    model_kwargs = {
        'model_id': MODEL_ID,
        'boto_client_config': boto_config,
        'temperature': 0.1,
        'max_tokens': 2000
    }
    
    guardrail_id = os.getenv('GUARDRAIL_ID')
    if guardrail_id:
        model_kwargs['guardrail_id'] = guardrail_id
        model_kwargs['guardrail_version'] = os.getenv('GUARDRAIL_VERSION', 'DRAFT')
    
    return BedrockModel(**model_kwargs)


# ---------------------------------------------------------------------------
# AGENT CREATION — this is where memory gets wired in
# ---------------------------------------------------------------------------
def create_agent(session_id: str = None, use_memory: bool = True):
    """
    Create a Strands Agent, optionally with conversation memory.
    
    Without memory (use_memory=False):
      - Behaves exactly like app.py — each call is independent
      - Used when no session_id is provided (anonymous/one-off chat)
    
    With memory (use_memory=True):
      - SlidingWindowConversationManager: keeps last CONVERSATION_WINDOW messages
        in the agent's context. Older messages get dropped so we don't exceed
        the LLM's token limit. Example: if window=20, the LLM sees the last
        20 messages (10 user + 10 assistant turns).
      - FileSessionManager: saves the conversation to disk as a JSON file at
        SESSION_DIR/{session_id}.json. This means conversations survive restarts.
    """
    model = create_bedrock_model()
    
    # System prompt now mentions "remember context" since this agent CAN do that
    system_prompt = """You are LearnLLM, a helpful and knowledgeable AI assistant.

Your purpose is to help users learn and understand concepts clearly.

Guidelines:
- Be concise and clear in your explanations
- Use examples when helpful
- Break down complex topics into simple parts
- Remember context from earlier in the conversation
- Admit when you don't know something
- Be friendly and encouraging

Always prioritize accuracy and helpfulness."""
    
    agent_kwargs = {
        'model': model,
        'system_prompt': system_prompt
    }
    
    if use_memory:
        # Sliding window: only keep the last N messages in the LLM's context.
        # Without this, a long conversation would eventually hit the token limit
        # and either error out or get very expensive.
        agent_kwargs['conversation_manager'] = SlidingWindowConversationManager(
            window_size=CONVERSATION_WINDOW
        )
        
        # File persistence: save conversation to disk so it survives server restarts.
        # Each session gets its own JSON file: SESSION_DIR/session-1234.json
        if session_id:
            agent_kwargs['session_manager'] = FileSessionManager(
                session_id=session_id,
                storage_dir=SESSION_DIR
            )
            logger.info(f"Agent created with persistent session: {session_id}")
    
    agent = Agent(**agent_kwargs)
    return agent


# ---------------------------------------------------------------------------
# AGENT CACHE LOOKUP — reuse agents so memory persists across requests
# ---------------------------------------------------------------------------
def get_or_create_agent(session_id: str = None) -> Agent:
    """
    Look up an existing agent for this session, or create a new one.
    
    This is critical for memory to work:
      - If we created a NEW agent every request, it would have no memory
        (even with FileSessionManager, the sliding window would be empty)
      - By REUSING the same agent instance, the SlidingWindowConversationManager
        already has the recent messages loaded in RAM
    
    Flow:
      session_id=None  → create a throwaway agent with no memory
      session_id="abc" → check cache → found? reuse it : create new & cache it
    """
    if not session_id:
        # No session = anonymous chat, no memory, no persistence
        return create_agent(use_memory=False)
    
    if session_id not in agent_cache:
        # First request for this session — create agent and cache it
        agent_cache[session_id] = create_agent(session_id=session_id, use_memory=True)
        logger.info(f"Created new agent for session: {session_id}")
    
    # Return the cached agent (which remembers previous messages)
    return agent_cache[session_id]


# ---------------------------------------------------------------------------
# STREAMING — same fake-streaming approach as app.py
# ---------------------------------------------------------------------------
def stream_agent_response(messages: list, request_id: str, session_id: str = None) -> Generator:
    """
    Call the LLM and stream the response back as SSE chunks.
    
    Same as app.py EXCEPT:
      - The agent is session-aware (get_or_create_agent looks up the cached agent)
      - The agent already knows the conversation history from previous requests
      - So even though we only send messages[-1], the agent's internal memory
        provides the context of earlier messages
    
    This means the UI could send JUST the latest message and the agent would
    still understand the conversation context. The full messages array from the
    UI is redundant here — only the last entry is used (same as app.py).
    """
    try:
        # Get the session-aware agent (with memory) or a throwaway one
        agent = get_or_create_agent(session_id)
        
        # Still only uses the LAST message, same as app.py.
        # But now the agent's internal memory provides the conversation context.
        user_message = messages[-1]['content'] if messages else ""
        
        logger.info(f"[{request_id}] Processing query: {user_message[:100]}...")
        if session_id:
            logger.info(f"[{request_id}] Session: {session_id}")
        
        start_time = datetime.now()
        full_response = ""
        chunk_count = 0
        
        # Call the agent — it sees: system_prompt + recent history (from memory) + this new message
        response = agent(user_message)
        
        # Extract text from Strands response (same as app.py)
        if hasattr(response, 'message'):
            content = response.message.get('content', [])
            if content and isinstance(content, list):
                response_text = content[0].get('text', '')
            else:
                response_text = str(content)
        else:
            response_text = str(response)
        
        # Fake-stream in 10-char chunks (same as app.py)
        chunk_size = 10
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i:i + chunk_size]
            full_response += chunk
            chunk_count += 1
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        
        duration = (datetime.now() - start_time).total_seconds()
        metadata = {
            'duration': f"{duration:.2f}s",
            'chunk_count': chunk_count,
            'response_length': len(full_response),
            'session_id': session_id
        }
        logger.info(f"[{request_id}] Response complete: {json.dumps(metadata)}")
        
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"[{request_id}] Error: {str(e)}", exc_info=True)
        error_data = json.dumps({'error': str(e)})
        yield f"data: {error_data}\n\n"


# ===========================================================================
# API ENDPOINTS
# ===========================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    GET /api/health
    Same as app.py but also reports memory-related features.
    """
    return jsonify({
        'status': 'ok',
        'service': 'LearnLLM API (Strands + Bedrock + Memory)',
        'model': MODEL_ID,
        'region': AWS_REGION,
        'features': {
            'conversation_memory': True,
            'session_persistence': True,
            'window_size': CONVERSATION_WINDOW  # How many messages the LLM can "see"
        }
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    POST /api/chat — THE MAIN ENDPOINT (now with optional session support)
    
    What the UI sends:
    {
        "messages": [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is..."},
            {"role": "user", "content": "How about JavaScript?"}
        ],
        "session_id": "session-1234567890"   ← OPTIONAL, new field vs app.py
    }
    
    If session_id is provided:
      - The server reuses the same agent (with memory of past messages)
      - The agent already knows the conversation context
      - Only messages[-1] is sent to the LLM, but it sees history from memory
    
    If session_id is omitted:
      - Behaves exactly like app.py — stateless, no memory
    
    Response: SSE stream (same format as app.py)
    """
    request_id = str(int(datetime.now().timestamp() * 1000))
    
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        session_id = data.get('session_id')  # NEW: optional session ID for memory
        
        if not messages:
            return jsonify({'error': 'Messages array is required'}), 400
        
        logger.info(f"[{request_id}] Chat request - {len(messages)} messages")
        
        return Response(
            stream_with_context(stream_agent_response(messages, request_id, session_id)),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
        
    except Exception as e:
        logger.error(f"[{request_id}] Error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to process chat request',
            'details': str(e)
        }), 500


# ---------------------------------------------------------------------------
# SESSION MANAGEMENT ENDPOINTS — these don't exist in app.py
# ---------------------------------------------------------------------------

@app.route('/api/session/new', methods=['POST'])
def new_session():
    """
    POST /api/session/new
    Creates a new session ID. The UI calls this when the user clicks "New Chat".
    
    Returns: {"session_id": "session-1711234567890", "created_at": "..."}
    
    Note: This just generates an ID — the actual agent is created lazily
    on the first /api/chat request that uses this session_id.
    """
    session_id = f"session-{int(datetime.now().timestamp() * 1000)}"
    return jsonify({
        'session_id': session_id,
        'created_at': datetime.now().isoformat()
    })


@app.route('/api/session/<session_id>', methods=['DELETE'])
def delete_session(session_id: str):
    """
    DELETE /api/session/{session_id}
    Deletes a session — removes the agent from cache AND deletes the JSON file from disk.
    After this, the conversation is gone forever.
    """
    try:
        # Remove from in-memory cache (frees RAM)
        if session_id in agent_cache:
            del agent_cache[session_id]
        
        # Delete the JSON file from disk (removes persistent history)
        session_file = Path(SESSION_DIR) / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
            logger.info(f"Deleted session: {session_id}")
        
        return jsonify({
            'status': 'deleted',
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Error deleting session: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """
    GET /api/sessions
    Lists all saved sessions by scanning the SESSION_DIR for JSON files.
    The UI could use this to show a sidebar of past conversations.
    """
    try:
        session_files = list(Path(SESSION_DIR).glob('*.json'))
        sessions = []
        
        for file in session_files:
            sessions.append({
                'session_id': file.stem,                    # filename without .json
                'created_at': datetime.fromtimestamp(file.stat().st_ctime).isoformat(),
                'modified_at': datetime.fromtimestamp(file.stat().st_mtime).isoformat()
            })
        
        return jsonify({
            'sessions': sessions,
            'count': len(sessions)
        })
        
    except Exception as e:
        logger.error(f"Error listing sessions: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# UTILITY ENDPOINTS — same as app.py
# ---------------------------------------------------------------------------

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """
    GET /api/logs?lines=50
    Debug endpoint — returns recent log lines from today's log file.
    """
    try:
        lines = int(request.args.get('lines', 50))
        log_file = Path(LOG_DIR) / f"chat-{datetime.now().strftime('%Y-%m-%d')}.log"
        
        if not log_file.exists():
            return jsonify({'logs': [], 'message': 'No logs for today'})
        
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:]
        
        return jsonify({
            'logs': recent_lines,
            'count': len(recent_lines)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/model-info', methods=['GET'])
def model_info():
    """
    GET /api/model-info
    Returns model config + memory-specific info like window size and active session count.
    """
    return jsonify({
        'model_id': MODEL_ID,
        'region': AWS_REGION,
        'framework': 'Strands',
        'provider': 'AWS Bedrock',
        'features': {
            'conversation_memory': True,
            'session_persistence': True,
            'window_size': CONVERSATION_WINDOW,
            'guardrails_enabled': bool(os.getenv('GUARDRAIL_ID'))
        },
        'active_sessions': len(agent_cache)  # How many agents are currently in RAM
    })


# ===========================================================================
# SERVER STARTUP
# ===========================================================================
if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("LearnLLM Backend - Strands Framework with Memory")
    logger.info("=" * 80)
    logger.info(f"Model: {MODEL_ID}")
    logger.info(f"Region: {AWS_REGION}")
    logger.info(f"Port: {PORT}")
    logger.info(f"Conversation window: {CONVERSATION_WINDOW} messages")
    logger.info(f"Session directory: {SESSION_DIR}")
    logger.info("=" * 80)
    
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=(os.getenv('FLASK_ENV') == 'development')
    )
