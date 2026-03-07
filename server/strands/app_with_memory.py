"""
LearnLLM Backend - Strands Framework with Conversation Memory
Advanced version with session management and memory
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
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.session.file_session_manager import FileSessionManager

# Load environment variables
load_dotenv()

# Configuration
PORT = int(os.getenv('PORT', 8000))
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
MODEL_ID = os.getenv('BEDROCK_MODEL_ID', 'amazon.nova-pro-v1:0')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.getenv('LOG_DIR', 'logs')
SESSION_DIR = os.getenv('SESSION_DIR', 'sessions')
CONVERSATION_WINDOW = int(os.getenv('CONVERSATION_WINDOW', 10))

# Setup directories
Path(LOG_DIR).mkdir(exist_ok=True)
Path(SESSION_DIR).mkdir(exist_ok=True)

# Setup logging
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

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Agent cache (session_id -> agent)
agent_cache: Dict[str, Agent] = {}


def create_bedrock_model():
    """Create and configure Bedrock model"""
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
    
    # Add guardrails if configured
    guardrail_id = os.getenv('GUARDRAIL_ID')
    if guardrail_id:
        model_kwargs['guardrail_id'] = guardrail_id
        model_kwargs['guardrail_version'] = os.getenv('GUARDRAIL_VERSION', 'DRAFT')
    
    return BedrockModel(**model_kwargs)


def create_agent(session_id: str = None, use_memory: bool = True):
    """
    Create Strands agent with optional memory
    
    Args:
        session_id: Unique session identifier for persistent memory
        use_memory: Whether to enable conversation memory
    """
    model = create_bedrock_model()
    
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
        # Add sliding window conversation manager
        agent_kwargs['conversation_manager'] = SlidingWindowConversationManager(
            window_size=CONVERSATION_WINDOW
        )
        
        # Add session persistence if session_id provided
        if session_id:
            agent_kwargs['session_manager'] = FileSessionManager(
                session_id=session_id,
                storage_dir=SESSION_DIR
            )
            logger.info(f"Agent created with persistent session: {session_id}")
    
    agent = Agent(**agent_kwargs)
    return agent


def get_or_create_agent(session_id: str = None) -> Agent:
    """Get existing agent from cache or create new one"""
    if not session_id:
        # No session, create temporary agent
        return create_agent(use_memory=False)
    
    if session_id not in agent_cache:
        agent_cache[session_id] = create_agent(session_id=session_id, use_memory=True)
        logger.info(f"Created new agent for session: {session_id}")
    
    return agent_cache[session_id]


def stream_agent_response(messages: list, request_id: str, session_id: str = None) -> Generator:
    """
    Stream agent response using Server-Sent Events (SSE)
    
    Args:
        messages: List of conversation messages
        request_id: Unique request identifier
        session_id: Optional session ID for memory
        
    Yields:
        SSE formatted data chunks
    """
    try:
        # Get or create agent
        agent = get_or_create_agent(session_id)
        
        # Get the last user message
        user_message = messages[-1]['content'] if messages else ""
        
        logger.info(f"[{request_id}] Processing query: {user_message[:100]}...")
        if session_id:
            logger.info(f"[{request_id}] Session: {session_id}")
        
        start_time = datetime.now()
        full_response = ""
        chunk_count = 0
        
        # Call agent
        response = agent(user_message)
        
        # Extract response text
        if hasattr(response, 'message'):
            content = response.message.get('content', [])
            if content and isinstance(content, list):
                response_text = content[0].get('text', '')
            else:
                response_text = str(content)
        else:
            response_text = str(response)
        
        # Stream response in chunks
        chunk_size = 10
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i:i + chunk_size]
            full_response += chunk
            chunk_count += 1
            
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        
        # Log completion
        metadata = {
            'duration': f"{duration:.2f}s",
            'chunk_count': chunk_count,
            'response_length': len(full_response),
            'session_id': session_id
        }
        logger.info(f"[{request_id}] Response complete: {json.dumps(metadata)}")
        
        # Send completion signal
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"[{request_id}] Error: {str(e)}", exc_info=True)
        error_data = json.dumps({'error': str(e)})
        yield f"data: {error_data}\n\n"


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'service': 'LearnLLM API (Strands + Bedrock + Memory)',
        'model': MODEL_ID,
        'region': AWS_REGION,
        'features': {
            'conversation_memory': True,
            'session_persistence': True,
            'window_size': CONVERSATION_WINDOW
        }
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Chat endpoint with streaming and memory support
    
    Request body:
    {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ],
        "session_id": "optional-session-id"  // For persistent memory
    }
    """
    request_id = str(int(datetime.now().timestamp() * 1000))
    
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        session_id = data.get('session_id')  # Optional
        
        if not messages:
            return jsonify({'error': 'Messages array is required'}), 400
        
        logger.info(f"[{request_id}] Chat request - {len(messages)} messages")
        
        # Stream response
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


@app.route('/api/session/new', methods=['POST'])
def new_session():
    """Create a new session"""
    session_id = f"session-{int(datetime.now().timestamp() * 1000)}"
    return jsonify({
        'session_id': session_id,
        'created_at': datetime.now().isoformat()
    })


@app.route('/api/session/<session_id>', methods=['DELETE'])
def delete_session(session_id: str):
    """Delete a session and its history"""
    try:
        # Remove from cache
        if session_id in agent_cache:
            del agent_cache[session_id]
        
        # Delete session file
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
    """List all active sessions"""
    try:
        session_files = list(Path(SESSION_DIR).glob('*.json'))
        sessions = []
        
        for file in session_files:
            sessions.append({
                'session_id': file.stem,
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


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get recent logs"""
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
    """Get model and configuration information"""
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
        'active_sessions': len(agent_cache)
    })


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
