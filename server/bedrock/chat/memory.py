"""LangChain memory adapter for DynamoDB storage.

This module provides an adapter between DynamoDB storage and LangChain's memory components.
It converts between DynamoDB message formats and LangChain message formats.
"""

import logging
from typing import Dict, List, Any, Optional

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    BaseMessage,
)

from .session import ChatSessionManager

logger = logging.getLogger(__name__)


class DynamoDBMemoryAdapter:
    """Adapter between DynamoDB storage and LangChain memory components.

    This class provides methods for loading messages from DynamoDB into LangChain memory
    and converting between DynamoDB and LangChain message formats.
    """

    def __init__(self, session_manager: ChatSessionManager):
        """Initialize the memory adapter with a session manager.

        Args:
            session_manager: The session manager to use for retrieving messages
        """
        self.session_manager = session_manager

    def get_messages(self, session_id: str) -> List[BaseMessage]:
        """Get all messages for a session as LangChain messages.

        Args:
            session_id: The session ID

        Returns:
            A list of LangChain messages
        """
        dynamo_messages = self.session_manager.get_session(session_id)
        langchain_messages = [
            self._convert_to_langchain_message(message) for message in dynamo_messages
        ]
        logger.info(
            f"Converted {len(dynamo_messages)} DynamoDB messages to LangChain messages for session {session_id}"
        )
        return langchain_messages

    def _convert_to_langchain_message(self, dynamo_message: Dict[str, Any]) -> BaseMessage:
        """Convert a DynamoDB message to a LangChain message.

        Args:
            dynamo_message: The DynamoDB message

        Returns:
            A LangChain message
        """
        message_type = dynamo_message["message_type"]
        content = dynamo_message["message"]

        if message_type == "HUMAN":
            return HumanMessage(content=content)
        elif message_type == "BOT":
            return AIMessage(content=content)
        elif message_type == "SYSTEM":
            return SystemMessage(content=content)
        else:
            logger.warning(f"Unknown message type: {message_type}, treating as human message")
            return HumanMessage(content=content)

    def convert_to_dynamo_message_type(self, langchain_message: BaseMessage) -> str:
        """Convert a LangChain message to a DynamoDB message type.

        Args:
            langchain_message: The LangChain message

        Returns:
            The DynamoDB message type
        """
        if isinstance(langchain_message, HumanMessage):
            return "HUMAN"
        elif isinstance(langchain_message, AIMessage):
            return "BOT"
        elif isinstance(langchain_message, SystemMessage):
            return "SYSTEM"
        else:
            logger.warning(
                f"Unknown LangChain message type: {type(langchain_message)}, treating as human message"
            )
            return "HUMAN"

    def add_langchain_message(
        self, session_id: str, message: BaseMessage
    ) -> Dict[str, Any]:
        """Add a LangChain message to a session.

        Args:
            session_id: The session ID
            message: The LangChain message

        Returns:
            The saved DynamoDB message
        """
        message_type = self.convert_to_dynamo_message_type(message)
        content = message.content
        
        # Convert content to string if it's not already
        if not isinstance(content, str):
            content = str(content)

        if message_type == "HUMAN":
            return self.session_manager.add_human_message(session_id, content)
        elif message_type == "BOT":
            return self.session_manager.add_bot_message(session_id, content)
        else:
            # For system messages or other types, use add_bot_message as a fallback
            logger.warning(
                f"Using add_bot_message for message type: {message_type}"
            )
            return self.session_manager.add_bot_message(session_id, content)
