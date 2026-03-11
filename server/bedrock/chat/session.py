"""Chat session manager for handling chat sessions and messages.

This module provides a session manager for creating, retrieving, and managing chat sessions.
It uses ULIDs for generating session and message IDs.
"""

import logging
import os
from typing import Dict, List, Optional, Any

import ulid
from botocore.exceptions import ClientError

from .repository import MessageRepository
from .exceptions import (
    ChatSessionNotFoundError,
    ChatServiceUnavailableError,
)

logger = logging.getLogger(__name__)


class ChatSessionManager:
    """Manager for chat sessions.

    This class provides methods for creating, retrieving, and managing chat sessions.
    It uses ULIDs for generating session and message IDs.
    """

    def __init__(self, message_repository: MessageRepository):
        """Initialize the session manager with a message repository.

        Args:
            message_repository: The message repository to use for storing and retrieving messages
        """
        self.message_repository = message_repository

    def create_session(self) -> str:
        """Create a new chat session.

        Returns:
            The session ID
        """
        session_id = f"session_{ulid.new().str.lower()}"
        logger.info(f"Created new session: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a session.

        Args:
            session_id: The session ID

        Returns:
            A list of message items

        Raises:
            ChatSessionNotFoundError: If the session does not exist
            ChatServiceUnavailableError: If the DynamoDB service is unavailable
        """
        try:
            messages = self.message_repository.get_messages(session_id)
            logger.info(f"Retrieved {len(messages)} messages for session {session_id}")
            
            # If no messages are found, the session doesn't exist
            if not messages:
                logger.warning(f"Session not found: {session_id}")
                raise ChatSessionNotFoundError(session_id)
                
            return messages
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            
            if error_code in ["ServiceUnavailable", "InternalServerError"]:
                logger.error(f"DynamoDB service unavailable: {str(e)}")
                raise ChatServiceUnavailableError("DynamoDB")
            
            # Re-raise other client errors
            logger.error(f"Error retrieving session {session_id}: {str(e)}")
            raise

    def add_human_message(
        self, session_id: str, message: str, intent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a human message to a session.

        Args:
            session_id: The session ID
            message: The message content
            intent: The message intent (CHAT or QUERY)

        Returns:
            The saved message item

        Raises:
            ChatServiceUnavailableError: If the DynamoDB service is unavailable
        """
        try:
            message_id = f"message_{ulid.new().str.lower()}"
            saved_message = self.message_repository.save_message(
                session_id, message_id, "HUMAN", message, intent=intent
            )
            logger.info(f"Added human message {message_id} to session {session_id}")
            return saved_message
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            
            if error_code in ["ServiceUnavailable", "InternalServerError"]:
                logger.error(f"DynamoDB service unavailable: {str(e)}")
                raise ChatServiceUnavailableError("DynamoDB")
            
            # Re-raise other client errors
            logger.error(f"Error adding human message to session {session_id}: {str(e)}")
            raise

    def add_bot_message(
        self, session_id: str, message: str, 
        intent: Optional[str] = None, 
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Add a bot message to a session.

        Args:
            session_id: The session ID
            message: The message content
            intent: The message intent (CHAT or QUERY)
            sources: List of source documents used for RAG responses

        Returns:
            The saved message item

        Raises:
            ChatServiceUnavailableError: If the DynamoDB service is unavailable
        """
        try:
            message_id = f"message_{ulid.new().str.lower()}"
            saved_message = self.message_repository.save_message(
                session_id, message_id, "BOT", message, intent=intent, sources=sources
            )
            logger.info(f"Added bot message {message_id} to session {session_id}")
            return saved_message
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            
            if error_code in ["ServiceUnavailable", "InternalServerError"]:
                logger.error(f"DynamoDB service unavailable: {str(e)}")
                raise ChatServiceUnavailableError("DynamoDB")
            
            # Re-raise other client errors
            logger.error(f"Error adding bot message to session {session_id}: {str(e)}")
            raise



    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: The session ID

        Returns:
            True if the session exists, False otherwise

        Raises:
            ChatServiceUnavailableError: If the DynamoDB service is unavailable
        """
        try:
            messages = self.message_repository.get_messages(session_id)
            exists = len(messages) > 0
            logger.info(f"Session {session_id} exists: {exists}")
            return exists
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            
            if error_code in ["ServiceUnavailable", "InternalServerError"]:
                logger.error(f"DynamoDB service unavailable: {str(e)}")
                raise ChatServiceUnavailableError("DynamoDB")
            
            # Re-raise other client errors
            logger.error(f"Error checking if session {session_id} exists: {str(e)}")
            raise
