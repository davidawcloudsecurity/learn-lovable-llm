"""Data models for chat requests and responses.

This module defines the Pydantic models used for validating chat API requests
and formatting chat API responses.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import ulid


class MessageType(str, Enum):
    """Enumeration for message types."""
    HUMAN = "HUMAN"
    BOT = "BOT"


class MessageIntent(str, Enum):
    """Enumeration for message intents."""
    CHAT = "CHAT"
    QUERY = "QUERY"


def generate_session_id() -> str:
    """Generate a new session ID using ULID format.
    
    Returns:
        A session ID in format 'session_{ulid}'
    """
    return f"session_{ulid.new().str.lower()}"


def generate_message_id() -> str:
    """Generate a new message ID using ULID format.
    
    Returns:
        A message ID in format 'message_{ulid}'
    """
    return f"message_{ulid.new().str.lower()}"


class SourceDocument(BaseModel):
    """Model representing a source document used for RAG responses."""
    
    source: str = Field(
        description="Source identifier for the document"
    )
    title: Optional[str] = Field(
        default=None,
        description="Title of the document"
    )
    page: Optional[int] = Field(
        default=None,
        description="Page number in the document"
    )


class ChatMessage(BaseModel):
    """Model representing a single chat message."""
    
    message_id: str = Field(
        description="Unique identifier for the message"
    )
    message_type: MessageType = Field(
        description="Type of message (HUMAN or BOT)"
    )
    message: str = Field(
        description="The message content",
        min_length=1,
        max_length=2048
    )
    timestamp: int = Field(
        description="Unix timestamp when the message was created"
    )
    intent: Optional[MessageIntent] = Field(
        default=None,
        description="Message intent (CHAT or QUERY)"
    )
    sources: Optional[List[SourceDocument]] = Field(
        default=None,
        description="List of source documents used for RAG responses"
    )
    
    @field_validator('message_id')
    @classmethod
    def validate_message_id(cls, v):
        """Validate message ID format."""
        if not v.startswith('message_'):
            raise ValueError('Message ID must start with "message_"')
        return v


class ChatRequest(BaseModel):
    """Model representing a chat API request."""
    
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID for continuing a conversation"
    )
    message: str = Field(
        description="The message to send",
        min_length=1,
        max_length=2048
    )
    
    @field_validator('session_id')
    @classmethod
    def validate_session_id(cls, v):
        """Validate session ID format if provided."""
        if v is not None and not v.startswith('session_'):
            raise ValueError('Session ID must start with "session_"')
        return v


class ChatResponse(BaseModel):
    """Model representing a chat API response."""
    
    session_id: str = Field(
        description="Unique identifier for the conversation session"
    )
    messages: List[ChatMessage] = Field(
        description="List of messages in the conversation",
        default_factory=list
    )
class ChatHistoryRequest(BaseModel):
    """Request model for retrieving chat session history."""
    session_id: str = Field(description="The ID of the session to retrieve history for")
    
    @field_validator('session_id')
    @classmethod
    def validate_session_id(cls, v):
        """Validate session ID format."""
        if not v.startswith('session_'):
            raise ValueError('Session ID must start with "session_"')
        return v


class ChatHistoryResponse(BaseModel):
    """Response model for chat session history."""
    session_id: str = Field(description="The ID of the session")
    messages: List[ChatMessage] = Field(description="List of messages in the session")
