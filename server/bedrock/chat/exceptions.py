"""Custom exceptions for the chat feature.

This module defines custom exception classes for the chat feature to provide
more specific error handling and better error messages.
"""

from typing import Dict, Any, List, Optional

import json


class ChatError(Exception):
    """Base class for all chat-related exceptions."""
    
    def __init__(self, message: str, status_code: int = 500):
        """Initialize the exception.
        
        Args:
            message: The error message
            status_code: The HTTP status code to return
        """
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ChatSessionNotFoundError(ChatError):
    """Exception raised when a session is not found."""
    
    def __init__(self, session_id: str):
        """Initialize the exception.
        
        Args:
            session_id: The session ID that was not found
        """
        message = f"Session not found: {session_id}"
        super().__init__(message, status_code=404)
        self.session_id = session_id


class ChatMessageTooLongError(ChatError):
    """Exception raised when a message is too long."""
    
    def __init__(self, max_length: int, actual_length: int):
        """Initialize the exception.
        
        Args:
            max_length: The maximum allowed length
            actual_length: The actual length of the message
        """
        message = f"Message too long: {actual_length} characters (maximum {max_length})"
        super().__init__(message, status_code=400)
        self.max_length = max_length
        self.actual_length = actual_length



class ChatServiceUnavailableError(ChatError):
    """Exception raised when a dependent service is unavailable."""
    
    def __init__(self, service_name: str):
        """Initialize the exception.
        
        Args:
            service_name: The name of the service that is unavailable
        """
        message = f"Service unavailable: {service_name}"
        super().__init__(message, status_code=503)
        self.service_name = service_name


class ChatTokenLimitExceededError(ChatError):
    """Exception raised when the token limit is exceeded."""
    
    def __init__(self, max_tokens: int):
        """Initialize the exception.
        
        Args:
            max_tokens: The maximum allowed tokens
        """
        message = f"Token limit exceeded: maximum {max_tokens} tokens"
        super().__init__(message, status_code=400)
        self.max_tokens = max_tokens


class ChatInvalidRequestError(ChatError):
    """Exception raised when the request is invalid."""
    
    def __init__(self, message: str):
        """Initialize the exception.
        
        Args:
            message: The error message
        """
        super().__init__(message, status_code=400)


class GuardrailInterventionError(ChatError):
    """Exception raised when guardrails intervene and block content.
    
    This exception is consistent with the existing service's guardrail handling
    and provides detailed assessment information for debugging.
    """
    
    def __init__(self, source_type: str, assessments: List[Dict[str, Any]]):
        """Initialize the exception.
        
        Args:
            source_type: The source type (INPUT or OUTPUT)
            assessments: The guardrail assessments from Bedrock
        """
        message = f"Guardrail intervention for {source_type}"
        super().__init__(message, status_code=400)
        self.source_type = source_type
        self.assessments = assessments
    
    def error_message(self) -> str:
        """Return a detailed error message for logging and debugging.
        
        This method is consistent with the existing service's error handling pattern.
        """
        # Only keep the assessment. No need to keep the invocation metrics.
        trimmed_assessment = [
            {k: v for (k, v) in a.items() if k != "invocationMetrics"} 
            for a in self.assessments
        ]
        return (
            f"Guardrail intervened on {self.source_type}. "
            f"Assessment: {json.dumps(trimmed_assessment)}"
        )
        self.assessments = assessments
