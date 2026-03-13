"""
LearnLLM Backend - Strands Framework Version
Replaces Node.js/Ollama with Python/AWS Bedrock
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Generator

from flask import Flask, request, Response, jsonify, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from botocore.config import Config as BotocoreConfig

from strands import Agent
from strands.models import BedrockModel

# Load environment variables
load_dotenv()

# Configuration
PORT = int(os.getenv('PORT', 8000))
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
MODEL_ID = os.getenv('MODEL_ID', 'amazon.nova-pro-v1:0')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.getenv('LOG_DIR', 'logs')

# Setup logging
Path(LOG_DIR).mkdir(exist_ok=True)
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

# Initialize Bedrock Model
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
        logger.info(f"Using guardrail: {guardrail_id}")
    
    return BedrockModel(**model_kwargs)

# Initialize agent
def create_agent():
    """Create Strands agent with Bedrock model"""
    model = create_bedrock_model()
    
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

# Create global agent instance
agent = create_agent()


def log_request(request_id: str, messages: list):
    """Log incoming request"""
    logger.info(f"[{request_id}] Incoming chat request")
    logger.info(f"[{request_id}] Message count: {len(messages)}")
    logger.debug(f"[{request_id}] Messages: {json.dumps(messages, indent=2)}")


def log_response(request_id: str, full_response: str, metadata: dict):
    """Log complete response with metadata"""
    logger.info(f"[{request_id}] Response complete")
    logger.info(f"[{request_id}] Response length: {len(full_response)} chars")
    logger.debug(f"[{request_id}] Full response: {full_response}")
    logger.info(f"[{request_id}] Metadata: {json.dumps(metadata, indent=2)}")


def stream_agent_response(messages: list, request_id: str) -> Generator:
    """
    Stream agent response using Server-Sent Events (SSE)
    
    Args:
        messages: List of conversation messages
        request_id: Unique request identifier
        
    Yields:
        SSE formatted data chunks
    """
    try:
        # Convert messages to Strands format
        # Frontend sends: [{"role": "user", "content": "text"}]
        # Strands expects similar format
        
        # Get the last user message
        user_message = messages[-1]['content'] if messages else ""
        
        logger.info(f"[{request_id}] Processing query: {user_message[:100]}...")
        
        start_time = datetime.now()
        full_response = ""
        chunk_count = 0
        
        # Call agent (Strands handles streaming internally)
        response = agent(user_message)
        
        # Extract response text
        if hasattr(response, 'message'):
            # Strands response format
            content = response.message.get('content', [])
            if content and isinstance(content, list):
                response_text = content[0].get('text', '')
            else:
                response_text = str(content)
        else:
            response_text = str(response)
        
        # Stream response in chunks (simulate streaming for compatibility)
        chunk_size = 10  # characters per chunk
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i:i + chunk_size]
            full_response += chunk
            chunk_count += 1
            
            # Send SSE formatted data
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        
        # Log completion
        metadata = {
            'duration': f"{duration:.2f}s",
            'chunk_count': chunk_count,
            'response_length': len(full_response)
        }
        log_response(request_id, full_response, metadata)
        
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
        'service': 'LearnLLM API (Strands + Bedrock)',
        'model': MODEL_ID,
        'region': AWS_REGION
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Chat endpoint with streaming support
    
    Request body:
    {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ]
    }
    
    Response: Server-Sent Events (SSE) stream
    """
    request_id = str(int(datetime.now().timestamp() * 1000))
    
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        
        if not messages:
            return jsonify({'error': 'Messages array is required'}), 400
        
        # Log request
        log_request(request_id, messages)
        
        # Stream response
        return Response(
            stream_with_context(stream_agent_response(messages, request_id)),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
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
    Get recent logs
    
    Query params:
    - lines: Number of recent lines to return (default: 50)
    """
    try:
        lines = int(request.args.get('lines', 50))
        log_file = Path(LOG_DIR) / f"chat-{datetime.now().strftime('%Y-%m-%d')}.log"
        
        if not log_file.exists():
            return jsonify({
                'logs': [],
                'message': 'No logs for today'
            })
        
        # Read last N lines
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:]
        
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
    """Get information about the current model"""
    return jsonify({
        'model_id': MODEL_ID,
        'region': AWS_REGION,
        'framework': 'Strands',
        'provider': 'AWS Bedrock',
        'guardrails_enabled': bool(os.getenv('GUARDRAIL_ID'))
    })


if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("LearnLLM Backend - Strands Framework")
    logger.info("=" * 80)
    logger.info(f"Model: {MODEL_ID}")
    logger.info(f"Region: {AWS_REGION}")
    logger.info(f"Port: {PORT}")
    logger.info(f"Log directory: {LOG_DIR}")
    logger.info("=" * 80)
    
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=(os.getenv('FLASK_ENV') == 'development')
    )
