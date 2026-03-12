"""Repository for chat messages in DynamoDB.

This module provides a data access layer for storing and retrieving chat messages
from a DynamoDB table. It follows the existing service patterns for error handling
and logging to maintain consistency with the main application.

STUDENT IMPLEMENTATION REQUIRED:
- save_message(): Implement DynamoDB message persistence
- get_messages(): Implement DynamoDB message retrieval

Both methods include detailed TODO comments with implementation guidance.
"""

import logging
import time
from typing import Dict, List, Optional, Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .exceptions import (
    ChatServiceUnavailableError,
    ChatSessionNotFoundError,
    ChatError,
)

logger = logging.getLogger(__name__)


class MessageRepository:
    """Repository for chat messages in DynamoDB.

    This class provides methods for storing and retrieving chat messages from a DynamoDB table.
    The table schema is as follows:
    - Partition Key: session_id (String) - Unique identifier for each conversation session
    - Sort Key: message_id (String) - Unique identifier for each message within a session
    """

    def __init__(self, table_name: str, dynamodb_client=None):
        """Initialize the repository with the DynamoDB table name.

        Args:
            table_name: The name of the DynamoDB table to use
            dynamodb_client: Optional DynamoDB client for testing
        """
        self.table_name = table_name
        self.dynamodb = dynamodb_client or boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(table_name)

    def save_message(
        self, session_id: str, message_id: str, message_type: str, message: str,
        intent: Optional[str] = None, sources: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Save a message to the DynamoDB table.

        Args:
            session_id: The session ID
            message_id: The message ID
            message_type: The message type (HUMAN or BOT)
            message: The message content
            intent: The message intent (CHAT or QUERY)
            sources: List of source documents used for RAG responses

        Returns:
            The saved message item
            
        Raises:
            ChatServiceUnavailableError: If the DynamoDB service is unavailable
            ChatError: For other DynamoDB errors
        """
        # Create the item dictionary with required fields
        item = {
            "session_id": session_id,
            "message_id": message_id,
            "message_type": message_type,
            "message": message,
            "timestamp": int(time.time()),
        }
        
        # Add optional fields if provided
        if intent is not None:
            item["intent"] = intent
        if sources is not None:
            item["sources"] = sources
        
        try:
            # Save to DynamoDB
            self.table.put_item(Item=item)
            logger.info(f"Saved message {message_id} for session {session_id}")
            return item
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            
            # Handle service unavailability
            if error_code in ["ServiceUnavailable", "InternalServerError", "ThrottlingException"]:
                logger.error(f"DynamoDB service unavailable: {error_code}")
                raise ChatServiceUnavailableError("DynamoDB")
            
            # Handle throughput exceeded
            if error_code == "ProvisionedThroughputExceededException":
                logger.error("DynamoDB throughput exceeded")
                raise ChatServiceUnavailableError("DynamoDB throughput exceeded")
            
            # Handle other errors
            logger.error(f"DynamoDB error saving message: {str(e)}")
            raise ChatError(f"DynamoDB error: {str(e)}", 500)

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a session.

        Args:
            session_id: The session ID

        Returns:
            A list of message items
            
        Raises:
            ChatServiceUnavailableError: If the DynamoDB service is unavailable
            ChatError: For other DynamoDB errors
        """
        try:
            # Query DynamoDB for all messages in the session
            response = self.table.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
                ScanIndexForward=True  # Chronological order (oldest first)
            )
            
            # Extract items from response
            items = response.get("Items", [])
            logger.info(f"Retrieved {len(items)} messages for session {session_id}")
            return items
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            
            # Handle service unavailability
            if error_code in ["ServiceUnavailable", "InternalServerError", "ThrottlingException"]:
                logger.error(f"DynamoDB service unavailable: {error_code}")
                raise ChatServiceUnavailableError("DynamoDB")
            
            # Handle throughput exceeded
            if error_code == "ProvisionedThroughputExceededException":
                logger.error("DynamoDB throughput exceeded")
                raise ChatServiceUnavailableError("DynamoDB throughput exceeded")
            
            # Handle other errors
            logger.error(f"DynamoDB error retrieving messages: {str(e)}")
            raise ChatError(f"DynamoDB error: {str(e)}", 500)

