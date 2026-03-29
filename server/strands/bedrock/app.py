"""
LearnLLM Backend - Strands Framework Version

This is a STATELESS chat server. Each request is independent — the server does NOT
remember previous messages between requests. The UI is responsible for sending the
full conversation history each time, but this server only uses the LAST message.

Architecture:
  UI (React) --POST JSON--> Flask (/api/chat) --single string--> Strands Agent ---> AWS Bedrock LLM
                                                                                        |
  UI <---SSE stream of text chunks--- Flask <---full response string--- Strands Agent <--'

Key points:
  - The UI sends an array of messages, but only the LAST one is used (role is ignored)
  - The Strands Agent calls AWS Bedrock (Claude/Nova) with that single message
  - The response comes back all at once, then gets chopped into small chunks
    and sent to the UI as Server-Sent Events (SSE) to simulate streaming
  - No session management, no database, no memory between requests
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Generator

from flask import Flask, request, Response, jsonify, stream_with_context
from flask_cors import CORS          # Allows the React UI (different port) to call this API
from dotenv import load_dotenv       # Reads .env file for config like AWS_REGION, MODEL_ID
from botocore.config import BotocoreConfig  # AWS SDK connection settings

from strands import Agent            # Strands framework — wraps LLM into a callable agent
from strands.models import BedrockModel  # Connects Strands to AWS Bedrock as the LLM provider

# ---------------------------------------------------------------------------
# CONFIGURATION — all values come from .env file, with sensible defaults
# ---------------------------------------------------------------------------
load_dotenv()

PORT = int(os.getenv('PORT', 8000))              # Flask listens on this port
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', '') # Which AWS region to call Bedrock in
MODEL_ID = os.getenv('MODEL_ID', 'amazon.nova-pro-v1:0')  # Which LLM model to use
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.getenv('LOG_DIR', 'logs')

# ---------------------------------------------------------------------------
# LOGGING — writes to both a daily log file and the terminal
# ---------------------------------------------------------------------------
Path(LOG_DIR).mkdir(exist_ok=True)
log_file = Path(LOG_DIR) / f"chat-{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),   # Persists logs to disk
        logging.StreamHandler()          # Also prints to terminal
    ]
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FLASK APP — the web server that receives HTTP requests from the UI
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)  # Without this, the browser blocks requests from localhost:8080 (UI) to localhost:8000 (API)


# ---------------------------------------------------------------------------
# BEDROCK MODEL — the connection to AWS's hosted LLM
# ---------------------------------------------------------------------------
def create_bedrock_model():
    """
    Configure how we talk to AWS Bedrock (the LLM hosting service).
    This sets timeouts, retries, and which model to use.
    """
    # AWS SDK connection settings — how patient we are with network issues
    boto_config = BotocoreConfig(
        retries={"max_attempts": 3, "mode": "standard"},  # Retry up to 3 times on failure
        connect_timeout=5,    # Wait max 5 seconds to establish connection
        read_timeout=60,      # Wait max 60 seconds for the LLM to respond (LLMs can be slow)
        region_name=AWS_REGION
    )
    
    model_kwargs = {
        'model_id': MODEL_ID,
        'boto_client_config': boto_config,
        'temperature': 0.1,   # Low = more deterministic/focused responses. High = more creative/random
        'max_tokens': 2000    # Cap the response length (roughly ~1500 words max)
    }
    
    # Optional: AWS Bedrock Guardrails filter harmful/inappropriate content
    # Only enabled if GUARDRAIL_ID is set in .env
    guardrail_id = os.getenv('GUARDRAIL_ID')
    if guardrail_id:
        model_kwargs['guardrail_id'] = guardrail_id
        model_kwargs['guardrail_version'] = os.getenv('GUARDRAIL_VERSION', 'DRAFT')
        logger.info(f"Using guardrail: {guardrail_id}")
    
    return BedrockModel(**model_kwargs)


# ---------------------------------------------------------------------------
# STRANDS AGENT — the "brain" that processes user messages
# ---------------------------------------------------------------------------
def create_agent():
    """
    Create the Strands Agent. This wraps the Bedrock model with a system prompt
    that defines the agent's personality and behavior rules.
    
    The agent is STATELESS — it has no memory of previous conversations.
    Each call to agent("some message") is completely independent.
    """
    model = create_bedrock_model()
    
    # This system prompt is sent to the LLM with EVERY request, before the user's message.
    # It's like giving the LLM its job description each time.
    system_prompt = """You are LearnLLM, a helpful and knowledgeable AI assistant.

Your purpose is to help users learn and understand concepts clearly.

Guidelines:
- Be concise and clear in your explanations
- Use examples when helpful
- Break down complex topics into simple parts
- Admit when you don't know something
- Be friendly and encouraging

Always prioritize accuracy and helpfulness."""
    
    agent = Agent(
        model=model,
        system_prompt=system_prompt
    )
    
    logger.info(f"Agent created with model: {MODEL_ID}")
    return agent


# Create ONE agent instance when the server starts.
# This same instance handles ALL requests (it's stateless, so that's fine).
agent = create_agent()


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS — logging for debugging
# ---------------------------------------------------------------------------
def log_request(request_id: str, messages: list):
    """Log incoming request details for debugging"""
    logger.info(f"[{request_id}] Incoming chat request")
    logger.info(f"[{request_id}] Message count: {len(messages)}")
    logger.debug(f"[{request_id}] Messages: {json.dumps(messages, indent=2)}")


def log_response(request_id: str, full_response: str, metadata: dict):
    """Log the complete response after it's been fully generated"""
    logger.info(f"[{request_id}] Response complete")
    logger.info(f"[{request_id}] Response length: {len(full_response)} chars")
    logger.debug(f"[{request_id}] Full response: {full_response}")
    logger.info(f"[{request_id}] Metadata: {json.dumps(metadata, indent=2)}")


# ---------------------------------------------------------------------------
# STREAMING — the core logic that talks to the LLM and sends chunks to the UI
# ---------------------------------------------------------------------------
def stream_agent_response(messages: list, request_id: str) -> Generator:
    """
    This is where the actual LLM call happens.
    
    Flow:
      1. Extract the last message's content from the array (ignores role, ignores history)
      2. Send that single string to the Strands Agent → which calls AWS Bedrock
      3. Bedrock returns the FULL response at once (not truly streamed)
      4. We chop the response into 10-character chunks and yield them as SSE events
         to give the UI a "typing" effect
      5. Finally yield a [DONE] signal so the UI knows the response is complete
    
    SSE (Server-Sent Events) format:
      Each chunk looks like:  data: {"text": "Hello, ho"}\n\n
      End signal looks like:  data: [DONE]\n\n
    """
    try:
        # ⚠️ THIS IS THE KEY LINE — only the LAST message matters.
        # The 'role' field is never checked. If the array has 50 messages,
        # the first 49 are completely ignored.
        user_message = messages[-1]['content'] if messages else ""
        
        logger.info(f"[{request_id}] Processing query: {user_message[:100]}...")
        
        start_time = datetime.now()
        full_response = ""
        chunk_count = 0
        
        # ---- CALL THE LLM ----
        # agent() sends the message to Bedrock and WAITS for the complete response.
        # This is a blocking call — nothing streams here despite the function name.
        response = agent(user_message)
        
        # ---- EXTRACT THE TEXT FROM THE RESPONSE ----
        # Strands wraps the response in an object. We need to dig into it
        # to get the actual text string.
        if hasattr(response, 'message'):
            # Normal case: response.message is a dict like:
            # {'content': [{'text': 'Hello! How can I help?'}]}
            content = response.message.get('content', [])
            if content and isinstance(content, list):
                response_text = content[0].get('text', '')  # Get the text from first content block
            else:
                response_text = str(content)
        else:
            # Fallback: if the response format is unexpected, just stringify it
            response_text = str(response)
        
        # ---- SIMULATE STREAMING ----
        # The LLM already returned the full response above. Now we break it into
        # small 10-character chunks and send them one at a time to the UI.
        # This creates a "typing" animation effect in the chat interface.
        chunk_size = 10  # characters per chunk
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i:i + chunk_size]
            full_response += chunk
            chunk_count += 1
            
            # SSE format: "data: " + JSON + two newlines
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        
        # ---- LOG STATS ----
        duration = (datetime.now() - start_time).total_seconds()
        metadata = {
            'duration': f"{duration:.2f}s",
            'chunk_count': chunk_count,
            'response_length': len(full_response)
        }
        log_response(request_id, full_response, metadata)
        
        # ---- SIGNAL COMPLETION ----
        # The UI watches for this exact string to know the response is finished
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"[{request_id}] Error: {str(e)}", exc_info=True)
        # Send the error to the UI so it can display it
        error_data = json.dumps({'error': str(e)})
        yield f"data: {error_data}\n\n"


# ===========================================================================
# API ENDPOINTS — the URLs the UI calls
# ===========================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    GET /api/health
    Simple "is the server alive?" check. The UI or monitoring tools can ping this.
    Returns basic info about which model and region are configured.
    """
    return jsonify({
        'status': 'ok',
        'service': 'LearnLLM API (Strands + Bedrock)',
        'model': MODEL_ID,
        'region': AWS_REGION
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    POST /api/chat — THE MAIN ENDPOINT
    
    This is what the UI calls when the user sends a message.
    
    What the UI sends (request body):
    {
        "messages": [
            {"role": "user", "content": "What is Python?"},        ← ignored
            {"role": "assistant", "content": "Python is..."},      ← ignored
            {"role": "user", "content": "How about JavaScript?"}   ← THIS is the only one used
        ]
    }
    
    What the UI receives (SSE stream):
        data: {"text": "JavaScript"}
        data: {"text": " is a pro"}
        data: {"text": "gramming l"}
        ...
        data: [DONE]
    
    Note: The "role" field in each message is NEVER checked by this server.
    Only messages[-1]['content'] matters.
    """
    # Generate a unique ID for this request (used in log messages for tracing)
    request_id = str(int(datetime.now().timestamp() * 1000))
    
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        
        if not messages:
            return jsonify({'error': 'Messages array is required'}), 400
        
        log_request(request_id, messages)
        
        # Return an SSE stream (not a regular JSON response)
        # stream_with_context keeps the Flask request context alive during streaming
        return Response(
            stream_with_context(stream_agent_response(messages, request_id)),
            mimetype='text/event-stream',  # Tells the browser this is an SSE stream
            headers={
                'Cache-Control': 'no-cache',       # Don't cache streamed responses
                'X-Accel-Buffering': 'no'           # Tell nginx (if present) not to buffer
            }
        )
        
    except Exception as e:
        logger.error(f"[{request_id}] Error processing request: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to process chat request',
            'details': str(e)
        }), 500


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """
    GET /api/logs?lines=50
    Debug endpoint — returns recent log lines from today's log file.
    Useful for checking what happened without SSH-ing into the server.
    """
    try:
        lines = int(request.args.get('lines', 50))
        log_file = Path(LOG_DIR) / f"chat-{datetime.now().strftime('%Y-%m-%d')}.log"
        
        if not log_file.exists():
            return jsonify({
                'logs': [],
                'message': 'No logs for today'
            })
        
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:]  # Only return the last N lines
        
        return jsonify({
            'logs': recent_lines,
            'count': len(recent_lines),
            'file': str(log_file)
        })
        
    except Exception as e:
        logger.error(f"Error reading logs: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/model-info', methods=['GET'])
def model_info():
    """
    GET /api/model-info
    Returns metadata about the current model configuration.
    Useful for the UI to display "Powered by ___" or similar.
    """
    return jsonify({
        'model_id': MODEL_ID,
        'region': AWS_REGION,
        'framework': 'Strands',
        'provider': 'AWS Bedrock',
        'guardrails_enabled': bool(os.getenv('GUARDRAIL_ID'))
    })


# ===========================================================================
# SERVER STARTUP — only runs when you execute this file directly
# ===========================================================================
if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("LearnLLM Backend - Strands Framework")
    logger.info("=" * 80)
    logger.info(f"Model: {MODEL_ID}")
    logger.info(f"Region: {AWS_REGION}")
    logger.info(f"Port: {PORT}")
    logger.info(f"Log directory: {LOG_DIR}")
    logger.info("=" * 80)
    
    # host='0.0.0.0' means accept connections from any IP (not just localhost)
    # This is needed if the UI runs on a different machine or in a container
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=(os.getenv('FLASK_ENV') == 'development')  # Auto-reload on code changes in dev
    )
