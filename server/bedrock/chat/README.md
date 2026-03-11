# Bedrock Chat Module

This is a production-ready chat module copied from the AWS MLU Agent Coding Lab. It provides a complete chatbot implementation with session management, RAG (Retrieval-Augmented Generation), and guardrails.

## Architecture

### Core Components

- **models.py** - Pydantic models for request/response validation
- **repository.py** - DynamoDB data access layer (requires implementation)
- **session.py** - Session management with ULID-based IDs
- **memory.py** - Adapter between DynamoDB and LangChain message formats

### Conversation Logic

- **chain.py** - Basic conversation chain with RAG support
- **classifier.py** - Intent classifier (CHAT vs QUERY)
- **hybrid_chain.py** - Routes messages based on intent
- **retriever.py** - Bedrock Knowledge Base retriever

### API & Error Handling

- **handler.py** - Main API handler with guardrails and metrics
- **exceptions.py** - Custom exception classes

## Features

✅ Session persistence in DynamoDB  
✅ Sliding window memory (15 messages)  
✅ Intent-based routing (conversational vs knowledge queries)  
✅ RAG with Bedrock Knowledge Bases  
✅ Guardrail integration for input/output filtering  
✅ CloudWatch metrics integration  
✅ Comprehensive error handling  

## Setup

### 1. Install Dependencies

```bash
pip install boto3 langchain langchain-aws pydantic ulid-py aws-lambda-powertools
```

### 2. Environment Variables

Create a `.env` file or set these environment variables:

```bash
# Required
AWS_REGION=us-west-2
CHAT_SESSIONS_TABLE_NAME=ChatSessions
KNOWLEDGE_BASE_ID=your-kb-id

# Optional
MODEL_ID=anthropic.claude-3-5-haiku-20241022-v1:0
GUARDRAIL_ID=your-guardrail-id
GUARDRAIL_VERSION=1
```

### 3. DynamoDB Table Setup

Create a DynamoDB table with:
- **Table Name**: ChatSessions (or your custom name)
- **Partition Key**: `session_id` (String)
- **Sort Key**: `message_id` (String)

### 4. Complete the Implementation

The `repository.py` file has two methods marked with `NotImplementedError`:

#### `save_message()` - Save a message to DynamoDB
#### `get_messages()` - Retrieve messages from DynamoDB

These are intentionally left for you to implement as a learning exercise.

## Usage

### Basic Example

```python
from chat.handler import chat_handler
from chat.models import ChatRequest

# Create a chat request
event = {
    "body": json.dumps({
        "session_id": None,  # None creates a new session
        "message": "What is AWS Lambda?"
    })
}

# Process the request
response = chat_handler(event)
print(response.body)
```

### With Existing Session

```python
event = {
    "body": json.dumps({
        "session_id": "session_01hqx...",
        "message": "Tell me more about it"
    })
}

response = chat_handler(event)
```

### Get Session History

```python
from chat.handler import get_session_history_handler

event = {
    "body": json.dumps({
        "session_id": "session_01hqx..."
    })
}

response = get_session_history_handler(event)
```

## API Endpoints

### POST /chat

**Request:**
```json
{
  "session_id": "session_01hqx..." or null,
  "message": "Your question here"
}
```

**Response:**
```json
{
  "session_id": "session_01hqx...",
  "messages": [
    {
      "message_id": "message_01hqy...",
      "message_type": "HUMAN",
      "message": "Your question here",
      "timestamp": 1234567890,
      "intent": "QUERY"
    },
    {
      "message_id": "message_01hqz...",
      "message_type": "BOT",
      "message": "The answer...",
      "timestamp": 1234567891,
      "intent": "QUERY",
      "sources": []
    }
  ]
}
```

### POST /chat/history

**Request:**
```json
{
  "session_id": "session_01hqx..."
}
```

**Response:** Same as chat response

## Intent Classification

The system automatically classifies messages:

- **CHAT**: Conversational messages (greetings, thanks, follow-ups)
- **QUERY**: Knowledge requests that need RAG retrieval

Examples:
- "Hello!" → CHAT
- "What is AWS Lambda?" → QUERY
- "Thanks!" → CHAT
- "How do I configure DynamoDB?" → QUERY

## Integration with FastAPI

```python
from fastapi import FastAPI, HTTPException
from chat.handler import chat_handler, get_session_history_handler
from chat.models import ChatRequest, ChatHistoryRequest
import json

app = FastAPI()

@app.post("/api/chat")
async def chat(request: ChatRequest):
    event = {"body": request.model_dump_json()}
    response = chat_handler(event)
    return json.loads(response.body)

@app.post("/api/chat/history")
async def history(request: ChatHistoryRequest):
    event = {"body": request.model_dump_json()}
    response = get_session_history_handler(event)
    return json.loads(response.body)
```

## Testing

```python
# Test without DynamoDB (mock the repository)
from unittest.mock import Mock
from chat.session import ChatSessionManager
from chat.repository import MessageRepository

# Mock repository
mock_repo = Mock(spec=MessageRepository)
mock_repo.get_messages.return_value = []
mock_repo.save_message.return_value = {
    "session_id": "test",
    "message_id": "msg_1",
    "message_type": "HUMAN",
    "message": "Hello",
    "timestamp": 123456
}

# Create session manager with mock
session_manager = ChatSessionManager(mock_repo)
```

## Next Steps

1. **Implement repository.py** - Complete the DynamoDB methods
2. **Set up DynamoDB table** - Create the table with proper schema
3. **Configure Knowledge Base** - Set up Bedrock Knowledge Base for RAG
4. **Add guardrails** - Configure Bedrock Guardrails (optional)
5. **Test locally** - Use moto or LocalStack for local DynamoDB
6. **Deploy** - Deploy to Lambda or run as FastAPI service

## Troubleshooting

### "NotImplementedError: Students need to implement..."
Complete the `save_message()` and `get_messages()` methods in `repository.py`

### "Service unavailable: DynamoDB"
Check AWS credentials and DynamoDB table exists

### "Session not found"
The session_id doesn't exist or has no messages

### Guardrail errors
Set `GUARDRAIL_ID=fake-guardrail-id` to disable guardrails during development

## Learn More

- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [LangChain Documentation](https://python.langchain.com/)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
