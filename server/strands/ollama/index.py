"""
LearnLLM Backend - Strands Framework with Ollama
Local LLM version using Ollama instead of AWS Bedrock
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

from langchain_community.llms import Ollama
from strands import Agent

# Load environment variables
load_dotenv()

# Configuration
PORT = int(os.getenv('PORT', 8000))
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
MODEL_NAME = os.getenv('OLLAMA_MODEL', 'smollm:1.7b')
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


# Custom Ollama Model Wrapper for Strands
class OllamaModelWrapper:
    """Wrapper to make Ollama compatible with Strands Agent"""
    
    def __init__(self, model_name: str, base_url: str):
        self.llm = Ollama(
            model=model_name,
            base_url=base_url,
            temperature=0.1
        )
        self.model_name = model_name
    
    def invoke(self, messages):
        """
        Invoke the model with messages
        
        Args:
            messages: List of message dicts or string
        
        Returns:
            Response in Strands-compatible format
        """
        # Convert messages to prompt
        if isinstance(messages, list):
            # Extract last user message
            user_message = messages[-1].get('content', '') if messages else ''
        else:
            user_message = str(messages)
        
        # Call Ollama
        response_text = self.llm.invoke(user_message)
        
        # Return in Strands-compatible format
        return {
            'message': {
                'content': [{'text': response_text}]
            }
        }


def create_ollama_model():
    """Create and configure Ollama model"""
    return OllamaModelWrapper(
        model_name=MODEL_NAME,
        base_url=OLLAMA_URL
    )


def create_agent():
    """Create Strands-style agent with Ollama model"""
    model = create_ollama_model()
    
    system_prompt = """You are LearnLLM, a helpful and knowledgeable AI assistant.

Your purpose is to help users learn and understand concepts clearly.

Guidelines:
- Be concise and clear in your explanations
- Use examples when helpful
- Break down complex topics into simple parts
- Admit when you don't know something
- Be friendly and encouraging

Always prioritize accuracy and helpfulness."""
    
    # Note: Strands Agent expects specific model interface
    # We use our wrapper to make Ollama compatible
    logger.info(f"Agent created with Ollama model: {MODEL_NAME}")
    
    return {
        'model': model,
        'system_prompt': system_prompt
    }


# Create global agent instance
agent_config = create_agent()


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
        # Get the last user message
        user_message = messages[-1]['content'] if messages else ""
        
        logger.info(f"[{request_id}] Processing query: {user_message[:100]}...")
        
        start_time = datetime.now()
        full_response = ""
        chunk_count = 0
        
        # Build prompt with system message
        full_prompt = f"{agent_config['system_prompt']}\n\nUser: {user_message}\nAssistant:"
        
        # Call Ollama model
        response = agent_config['model'].invoke([{'role': 'user', 'content': user_message}])
        
        # Extract response text
        if isinstance(response, dict) and 'message' in response:
            content = response['message'].get('content', [])
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
            'response_length': len(full_response),
            'model': MODEL_NAME
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
    # Test Ollama connection
    try:
        test_response = agent_config['model'].llm.invoke("test")
        ollama_status = "connected"
    except Exception as e:
        ollama_status = f"error: {str(e)}"
    
    return jsonify({
        'status': 'ok',
        'service': 'LearnLLM API (Strands + Ollama)',
        'model': MODEL_NAME,
        'ollama_url': OLLAMA_URL,
        'ollama_status': ollama_status
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
        'model_name': MODEL_NAME,
        'ollama_url': OLLAMA_URL,
        'framework': 'Strands + Ollama',
        'provider': 'Local (Ollama)',
        'cost': 'Free'
    })


if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("LearnLLM Backend - Strands Framework with Ollama")
    logger.info("=" * 80)
    logger.info(f"Model: {MODEL_NAME}")
    logger.info(f"Ollama URL: {OLLAMA_URL}")
    logger.info(f"Port: {PORT}")
    logger.info(f"Log directory: {LOG_DIR}")
    logger.info("=" * 80)
    
    # Test Ollama connection
    try:
        test_model = Ollama(model=MODEL_NAME, base_url=OLLAMA_URL)
        test_response = test_model.invoke("Hello")
        logger.info("✅ Ollama connection successful")
    except Exception as e:
        logger.error(f"❌ Cannot connect to Ollama: {e}")
        logger.error("Make sure Ollama is running: ollama serve")
    
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=(os.getenv('FLASK_ENV') == 'development')
    )
