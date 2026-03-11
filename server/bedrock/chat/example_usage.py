"""
Example usage of the Bedrock Chat module.

This file demonstrates how to use the chat module in different scenarios.
"""

import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Example 1: Basic chat request (creates new session)
def example_new_chat():
    """Example of starting a new chat session."""
    from chat.handler import chat_handler
    
    event = {
        "body": json.dumps({
            "session_id": None,  # None creates a new session
            "message": "Hello! What is AWS Bedrock?"
        })
    }
    
    response = chat_handler(event)
    result = json.loads(response.body)
    
    print("New Chat Response:")
    print(f"Session ID: {result['session_id']}")
    print(f"Messages: {len(result['messages'])}")
    for msg in result['messages']:
        print(f"  [{msg['message_type']}]: {msg['message'][:50]}...")
    
    return result['session_id']


# Example 2: Continue existing conversation
def example_continue_chat(session_id):
    """Example of continuing an existing chat session."""
    from chat.handler import chat_handler
    
    event = {
        "body": json.dumps({
            "session_id": session_id,
            "message": "Can you tell me more about its features?"
        })
    }
    
    response = chat_handler(event)
    result = json.loads(response.body)
    
    print("\nContinued Chat Response:")
    print(f"Session ID: {result['session_id']}")
    print(f"Total Messages: {len(result['messages'])}")


# Example 3: Get session history
def example_get_history(session_id):
    """Example of retrieving session history."""
    from chat.handler import get_session_history_handler
    
    event = {
        "body": json.dumps({
            "session_id": session_id
        })
    }
    
    response = get_session_history_handler(event)
    result = json.loads(response.body)
    
    print("\nSession History:")
    print(f"Session ID: {result['session_id']}")
    print(f"Total Messages: {len(result['messages'])}")
    for msg in result['messages']:
        print(f"  [{msg['message_type']}] {msg['message'][:50]}...")


# Example 4: Using the models directly
def example_using_models():
    """Example of using Pydantic models directly."""
    from chat.models import ChatRequest, ChatResponse, ChatMessage, MessageType
    
    # Create a request
    request = ChatRequest(
        session_id=None,
        message="What is machine learning?"
    )
    
    print("\nRequest Model:")
    print(request.model_dump_json(indent=2))
    
    # Create a response (example)
    response = ChatResponse(
        session_id="session_01hqx123",
        messages=[
            ChatMessage(
                message_id="message_01hqy456",
                message_type=MessageType.HUMAN,
                message="What is machine learning?",
                timestamp=1234567890,
                intent="QUERY"
            )
        ]
    )
    
    print("\nResponse Model:")
    print(response.model_dump_json(indent=2))


# Example 5: Direct use of session manager
def example_session_manager():
    """Example of using the session manager directly."""
    import boto3
    from chat.repository import MessageRepository
    from chat.session import ChatSessionManager
    
    # Initialize components
    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-west-2'))
    table_name = os.getenv('CHAT_SESSIONS_TABLE_NAME', 'ChatSessions')
    
    repository = MessageRepository(table_name, dynamodb)
    session_manager = ChatSessionManager(repository)
    
    # Create a new session
    session_id = session_manager.create_session()
    print(f"\nCreated session: {session_id}")
    
    # Add messages
    session_manager.add_human_message(session_id, "Hello!", intent="CHAT")
    session_manager.add_bot_message(session_id, "Hi! How can I help you?", intent="CHAT")
    
    # Check if session exists
    exists = session_manager.session_exists(session_id)
    print(f"Session exists: {exists}")
    
    # Get all messages
    messages = session_manager.get_session(session_id)
    print(f"Messages in session: {len(messages)}")


# Example 6: Using the hybrid chain directly
def example_hybrid_chain():
    """Example of using the hybrid conversation chain directly."""
    import boto3
    from chat.repository import MessageRepository
    from chat.session import ChatSessionManager
    from chat.memory import DynamoDBMemoryAdapter
    from chat.retriever import BedrockAgentRetriever
    from chat.hybrid_chain import HybridConversationChain
    
    # Initialize components
    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-west-2'))
    table_name = os.getenv('CHAT_SESSIONS_TABLE_NAME', 'ChatSessions')
    kb_id = os.getenv('KNOWLEDGE_BASE_ID', 'FAKE-KB-ID')
    
    repository = MessageRepository(table_name, dynamodb)
    session_manager = ChatSessionManager(repository)
    memory_adapter = DynamoDBMemoryAdapter(session_manager)
    
    # Create retriever
    bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=os.getenv('AWS_REGION', 'us-west-2'))
    retriever = BedrockAgentRetriever(
        knowledge_base_id=kb_id,
        region_name=os.getenv('AWS_REGION', 'us-west-2'),
        client=bedrock_agent_runtime,
        top_k=5
    )
    
    # Create hybrid chain
    chain = HybridConversationChain(
        memory_adapter=memory_adapter,
        retriever=retriever,
        model_id=os.getenv('MODEL_ID', 'anthropic.claude-3-5-haiku-20241022-v1:0'),
        window_size=15
    )
    
    # Create session and process message
    session_id = session_manager.create_session()
    result = chain.process_message(session_id, "What is AWS Lambda?")
    
    print("\nHybrid Chain Result:")
    print(f"Intent: {result['intent']}")
    print(f"Response: {result['response'][:100]}...")
    print(f"Sources: {result.get('sources', 'None')}")


# Example 7: Error handling
def example_error_handling():
    """Example of handling errors."""
    from chat.handler import chat_handler
    from chat.exceptions import ChatSessionNotFoundError
    
    # Try to use non-existent session
    event = {
        "body": json.dumps({
            "session_id": "session_nonexistent",
            "message": "Hello"
        })
    }
    
    response = chat_handler(event)
    
    print("\nError Handling:")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.body}")


if __name__ == "__main__":
    print("=" * 60)
    print("Bedrock Chat Module - Usage Examples")
    print("=" * 60)
    
    # Check environment variables
    required_vars = ['AWS_REGION', 'CHAT_SESSIONS_TABLE_NAME', 'KNOWLEDGE_BASE_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"\n⚠️  Warning: Missing environment variables: {', '.join(missing_vars)}")
        print("Set these in your .env file or environment before running examples.\n")
    
    # Run examples (comment out as needed)
    try:
        # Example 4: Using models (doesn't require AWS)
        example_using_models()
        
        # Uncomment these when you have AWS configured and DynamoDB table ready:
        # session_id = example_new_chat()
        # example_continue_chat(session_id)
        # example_get_history(session_id)
        # example_session_manager()
        # example_hybrid_chain()
        # example_error_handling()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you have:")
        print("1. Implemented repository.py methods")
        print("2. Created DynamoDB table")
        print("3. Set environment variables")
        print("4. Configured AWS credentials")
