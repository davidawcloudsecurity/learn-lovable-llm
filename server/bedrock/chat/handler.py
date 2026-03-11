"""Chat API handler for BurnerGenaiPythonLambdaKrobrian20250828.

This module provides the API handler for the chat endpoint.
"""

from http import HTTPStatus
import json
import logging
import os
import time
from typing import Optional, Dict, Any, List

import boto3
from aws_lambda_powertools import Metrics
from aws_lambda_powertools.event_handler import Response, content_types
from aws_lambda_powertools.metrics import MetricUnit
from botocore.exceptions import ClientError
from langchain_aws import ChatBedrockConverse
from pydantic import ValidationError

from .exceptions import (
    ChatError,
    ChatSessionNotFoundError,
    ChatMessageTooLongError,
    ChatServiceUnavailableError,
    ChatTokenLimitExceededError,
    ChatInvalidRequestError,
    GuardrailInterventionError,
)
from .models import ChatRequest, ChatResponse, ChatMessage, ChatHistoryRequest, ChatHistoryResponse
from .repository import MessageRepository
from .session import ChatSessionManager
from .memory import DynamoDBMemoryAdapter
from .chain import ChatConversationChain
from .hybrid_chain import HybridConversationChain
from .retriever import BedrockAgentRetriever

logger = logging.getLogger(__name__)
metrics = Metrics(namespace="BurnerGenaiPythonLambdaKrobrian20250828")
metrics.set_default_dimensions(service="ChatHandler")

# Get environment variables
CHAT_SESSIONS_TABLE_NAME = os.environ.get("CHAT_SESSIONS_TABLE_NAME", "BurnerGenaiPythonLambdaKrobrian20250828-ChatSessions")
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "FAKE-KB-ID")
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID", "fake-guardrail-id")
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "fake-guardrail-version")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
MODEL_ID = os.environ.get("MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")

# Module-level variables that can be mocked in tests
bedrock_runtime = boto3.client("bedrock-runtime", region_name=AWS_REGION)
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

# Initialize components
message_repository = MessageRepository(CHAT_SESSIONS_TABLE_NAME, dynamodb)
session_manager = ChatSessionManager(message_repository)

# Initialize Bedrock Agent retriever
bedrock_retriever = BedrockAgentRetriever(
    knowledge_base_id=KNOWLEDGE_BASE_ID,
    region_name=AWS_REGION,
    client=bedrock_agent_runtime,
    top_k=5
)

# Initialize hybrid conversation chain
memory_adapter = DynamoDBMemoryAdapter(session_manager)
hybrid_chain = HybridConversationChain(
    memory_adapter=memory_adapter,
    retriever=bedrock_retriever,
    model_id=MODEL_ID,
    window_size=15,
)


def apply_guardrails(text: str, source_type: str) -> str:
    """Apply guardrails to text.

    Args:
        text: The text to apply guardrails to
        source_type: The source type (INPUT or OUTPUT)

    Returns:
        The text after guardrails are applied

    Raises:
        GuardrailInterventionError: If guardrails block the text
        ChatServiceUnavailableError: If the Bedrock service is unavailable
    """
    try:
        # Skip guardrails if not configured
        if GUARDRAIL_ID == "fake-guardrail-id" or GUARDRAIL_VERSION == "fake-guardrail-version":
            logger.warning("Guardrails not configured, skipping")
            return text

        # Apply guardrails
        try:
            response = bedrock_runtime.apply_guardrail(
                guardrailIdentifier=GUARDRAIL_ID,
                guardrailVersion=GUARDRAIL_VERSION,
                source=source_type,  # Changed from sourceType to source to match main handler
                content=[
                    {
                        "text": {
                            "text": text,
                            "qualifiers": [
                                "guard_content",
                            ],
                        }
                    },
                ],
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            if error_code in ["ServiceUnavailable", "InternalServerError", "ThrottlingException"]:
                logger.error(f"Bedrock service unavailable: {str(e)}")
                metrics.add_metric(name="BedrockServiceErrors", unit=MetricUnit.Count, value=1)
                raise ChatServiceUnavailableError("Bedrock")

            # Re-raise other client errors
            logger.error(f"Error applying guardrails: {str(e)}")
            raise

        # Add metric for guardrail intervention
        metrics.add_metric(
            name="GuardrailIntervened",
            unit=MetricUnit.Count,
            value=int(response["action"] != "NONE")
        )
        # Add dimension for source
        metrics.add_dimension(name="source", value=source_type)

        # Check if guardrails blocked the text - using action != "NONE" to match main handler
        if response["action"] != "NONE":
            logger.warning(
                f"Guardrail ({GUARDRAIL_ID}) intervened ({response['ResponseMetadata']['RequestId']})"
            )
            raise GuardrailInterventionError(
                source_type=source_type,
                assessments=response.get("assessments", []),
            )

        # Return the text after guardrails are applied
        return text  # Return original text as main handler does
    except Exception as e:
        if isinstance(e, (GuardrailInterventionError, ChatServiceUnavailableError)):
            raise
        logger.error(f"Error applying guardrails: {str(e)}", exc_info=True)
        metrics.add_metric(name="GuardrailErrors", unit=MetricUnit.Count, value=1)
        # If there's an error applying guardrails, return the original text
        return text


def chat_handler(event: Optional[Dict[str, Any]] = None) -> Response:
    """Handle chat API requests.

    Args:
        event: The API Gateway event containing the request body.

    Returns:
        Response: A response containing the chat messages or an error.
    """
    # If we have an event, try to validate the request
    if event and event.get("body"):
        try:
            # Parse the request body as JSON and validate it against the ChatRequest model
            try:
                request_body = json.loads(event.get("body", "{}"))
            except json.JSONDecodeError:
                logger.error("Invalid JSON in request body")
                metrics.add_metric(name="InvalidJsonErrors", unit=MetricUnit.Count, value=1)
                return Response(
                    status_code=HTTPStatus.BAD_REQUEST,
                    content_type=content_types.APPLICATION_JSON,
                    body=json.dumps({"error": "Invalid JSON in request body"}),
                )

            try:
                chat_request = ChatRequest(**request_body)
            except ValidationError as e:
                logger.error(f"Validation error: {str(e)}")
                metrics.add_metric(name="ValidationErrors", unit=MetricUnit.Count, value=1)
                return Response(
                    status_code=HTTPStatus.BAD_REQUEST,
                    content_type=content_types.APPLICATION_JSON,
                    body=json.dumps({"error": "Validation error", "details": e.errors()}),
                )

            # Check message length
            if len(chat_request.message) > 2048:
                logger.error(f"Message too long: {len(chat_request.message)} characters")
                metrics.add_metric(name="MessageTooLongErrors", unit=MetricUnit.Count, value=1)
                return Response(
                    status_code=HTTPStatus.BAD_REQUEST,
                    content_type=content_types.APPLICATION_JSON,
                    body=json.dumps({
                        "error": "Message too long",
                        "details": {
                            "max_length": 2048,
                            "actual_length": len(chat_request.message)
                        }
                    }),
                )

            # Process the chat request
            return process_chat_request(chat_request)

        except GuardrailInterventionError as e:
            # Return a 400 Bad Request response for guardrail interventions
            logger.warning(f"Guardrail intervention: {e.source_type}")
            # No need to add metric here as it's already added in apply_guardrails
            return Response(
                status_code=HTTPStatus.BAD_REQUEST,
                content_type=content_types.APPLICATION_JSON,
                body=json.dumps({
                    "error": "Guardrail intervention",
                    "details": {
                        "source": e.source_type,
                        "assessments": e.assessments,
                    }
                }),
            )
        except ChatError as e:
            # Return a response with the appropriate status code for chat errors
            logger.error(f"Chat error: {str(e)}")
            metrics.add_metric(name="ChatErrors", unit=MetricUnit.Count, value=1)

            return Response(
                status_code=e.status_code,
                content_type=content_types.APPLICATION_JSON,
                body=json.dumps({"error": e.message}),
            )
        except Exception as e:
            # Log the error and return a 500 Internal Server Error response
            logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
            metrics.add_metric(name="UnhandledErrors", unit=MetricUnit.Count, value=1)
            return Response(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                content_type=content_types.APPLICATION_JSON,
                body=json.dumps({"error": "Internal server error"}),
            )

    # If no event or body, return a 400 Bad Request response
    logger.error("Missing request body")
    metrics.add_metric(name="MissingBodyErrors", unit=MetricUnit.Count, value=1)
    return Response(
        status_code=HTTPStatus.BAD_REQUEST,
        content_type=content_types.APPLICATION_JSON,
        body=json.dumps({"error": "Missing request body"}),
    )


def process_chat_request(chat_request: ChatRequest) -> Response:
    """Process a chat request.

    Args:
        chat_request: The validated chat request.

    Returns:
        Response: A response containing the chat messages.
    """
    start_time = time.time()
    session_id = chat_request.session_id

    try:
        # Step 1: Handle session creation/retrieval logic
        if session_id is None:
            # Create a new session
            session_id = session_manager.create_session()
            logger.info(f"Created new session: {session_id}")
            metrics.add_metric(name="NewSessionsCreated", unit=MetricUnit.Count, value=1)
        else:
            # Check if the session exists
            if not session_manager.session_exists(session_id):
                logger.error(f"Session {session_id} not found")
                metrics.add_metric(name="SessionNotFoundErrors", unit=MetricUnit.Count, value=1)
                raise ChatSessionNotFoundError(session_id)
            logger.info(f"Using existing session: {session_id}")

        # Step 2: Apply input guardrails
        logger.info(f"Applying input guardrails for session {session_id}")
        filtered_message = apply_guardrails(chat_request.message, "INPUT")

        # Step 3: Add the human message to the session
        logger.info(f"Adding human message to session {session_id}")
        session_manager.add_human_message(session_id, filtered_message)

        # Step 4: Process the message using hybrid chain
        logger.info(f"Processing message with hybrid chain for session {session_id}")
        chain_response = hybrid_chain.process_message(session_id, filtered_message)

        response_text = chain_response["response"]
        intent = chain_response["intent"]
        sources = chain_response.get("sources")

        logger.info(f"Generated response with intent: {intent}")
        metrics.add_metric(name="MessagesProcessed", unit=MetricUnit.Count, value=1)
        metrics.add_dimension(name="intent", value=intent)

        # Step 5: Apply output guardrails to the response
        logger.info(f"Applying output guardrails for session {session_id}")
        filtered_response = apply_guardrails(response_text, "OUTPUT")

        # Step 6: Add the bot message to the session
        logger.info(f"Adding bot message to session {session_id}")
        session_manager.add_bot_message(
            session_id, 
            filtered_response, 
            intent=intent, 
            sources=sources
        )

        # Step 7: Retrieve all messages and format the response
        logger.info(f"Retrieving all messages for session {session_id}")
        all_messages = session_manager.get_session(session_id)

        # Convert to ChatMessage objects
        chat_messages = []
        for message in all_messages:
            chat_message = ChatMessage(
                message_id=message["message_id"],
                message_type=message["message_type"],
                message=message["message"],
                timestamp=message["timestamp"],
                intent=message.get("intent"),
                sources=message.get("sources"),
            )
            chat_messages.append(chat_message)

        # Create the response
        chat_response = ChatResponse(
            session_id=session_id,
            messages=chat_messages,
        )

        # Add performance metrics
        processing_time = time.time() - start_time
        metrics.add_metric(name="ProcessingTimeMs", unit=MetricUnit.Milliseconds, value=processing_time * 1000)
        metrics.add_metric(name="MessagesInResponse", unit=MetricUnit.Count, value=len(chat_messages))

        logger.info(f"Successfully processed chat request for session {session_id} in {processing_time:.3f}s")

        # Return the response
        return Response(
            status_code=HTTPStatus.OK,
            content_type=content_types.APPLICATION_JSON,
            body=chat_response.model_dump_json(),
        )

    except GuardrailInterventionError:
        # Re-raise guardrail interventions to be handled by the main handler
        raise
    except ChatError:
        # Re-raise chat errors to be handled by the main handler
        raise
    except Exception as e:
        # Log unexpected errors and convert to ChatError
        logger.error(f"Unexpected error processing chat request for session {session_id}: {str(e)}", exc_info=True)
        metrics.add_metric(name="UnexpectedErrors", unit=MetricUnit.Count, value=1)
        raise ChatError(f"Error processing chat request: {str(e)}", 500)


def handle_chat_request(event: Optional[Dict[str, Any]] = None) -> Response:
    """Handle chat API requests - wrapper for chat_handler.

    Args:
        event: The API Gateway event containing the request body.

    Returns:
        Response: A response containing the chat messages or an error.
    """
    return chat_handler(event)


def handle_history_request(event: Optional[Dict[str, Any]] = None) -> Response:
    """Handle chat history API requests - wrapper for get_session_history_handler.

    Args:
        event: The API Gateway event containing the request body.

    Returns:
        Response: A response containing the chat session history or an error.
    """
    return get_session_history_handler(event)


def get_session_history_handler(event: Optional[Dict[str, Any]] = None) -> Response:
    """Handle requests to retrieve chat session history.

    Args:
        event: The API Gateway event containing the request body.

    Returns:
        Response: A response containing the chat session history or an error.
    """
    # If we have an event, try to validate the request
    if event and event.get("body"):
        try:
            # Parse the request body as JSON and validate it against the ChatHistoryRequest model
            try:
                request_body = json.loads(event.get("body", "{}"))
            except json.JSONDecodeError:
                logger.error("Invalid JSON in request body")
                metrics.add_metric(name="InvalidJsonErrors", unit=MetricUnit.Count, value=1)
                return Response(
                    status_code=HTTPStatus.BAD_REQUEST,
                    content_type=content_types.APPLICATION_JSON,
                    body=json.dumps({"error": "Invalid JSON in request body"}),
                )

            try:
                chat_request = ChatHistoryRequest(**request_body)
            except ValidationError as e:
                logger.error(f"Validation error: {str(e)}")
                metrics.add_metric(name="ValidationErrors", unit=MetricUnit.Count, value=1)
                return Response(
                    status_code=HTTPStatus.BAD_REQUEST,
                    content_type=content_types.APPLICATION_JSON,
                    body=json.dumps({"error": "Validation error", "details": e.errors()}),
                )

            # Check if session exists
            if not session_manager.session_exists(chat_request.session_id):
                logger.error(f"Session {chat_request.session_id} not found")
                metrics.add_metric(name="SessionNotFoundErrors", unit=MetricUnit.Count, value=1)
                return Response(
                    status_code=HTTPStatus.NOT_FOUND,
                    content_type=content_types.APPLICATION_JSON,
                    body=json.dumps({"error": f"Session {chat_request.session_id} not found"}),
                )

            # Get all messages for the session
            messages = session_manager.get_session(chat_request.session_id)
            metrics.add_metric(name="MessagesPerSession", unit=MetricUnit.Count, value=len(messages))

            # Convert to ChatMessage objects
            chat_messages = [
                ChatMessage(
                    message_id=message["message_id"],
                    message_type=message["message_type"],
                    message=message["message"],
                    timestamp=message["timestamp"],
                    intent=message.get("intent"),
                    sources=message.get("sources"),
                )
                for message in messages
            ]

            # Create the response
            chat_response = ChatHistoryResponse(
                session_id=chat_request.session_id,
                messages=chat_messages,
            )

            # Return the response
            return Response(
                status_code=HTTPStatus.OK,
                content_type=content_types.APPLICATION_JSON,
                body=chat_response.model_dump_json(),
            )

        except Exception as e:
            # Log the error and return a 500 Internal Server Error response
            logger.error(f"Error retrieving session history: {str(e)}", exc_info=True)
            metrics.add_metric(name="UnhandledErrors", unit=MetricUnit.Count, value=1)
            return Response(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                content_type=content_types.APPLICATION_JSON,
                body=json.dumps({"error": "Internal server error"}),
            )

    # If no event or body, return a 400 Bad Request response
    logger.error("Missing request body")
    metrics.add_metric(name="MissingBodyErrors", unit=MetricUnit.Count, value=1)
    return Response(
        status_code=HTTPStatus.BAD_REQUEST,
        content_type=content_types.APPLICATION_JSON,
        body=json.dumps({"error": "Missing request body"}),
    )
