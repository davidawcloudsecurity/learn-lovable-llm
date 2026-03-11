"""
Message Intent Classifier for the chat feature.

This module provides a classifier that determines whether a message requires
knowledge retrieval (QUERY) or is just conversational (CHAT).
"""

import logging
from typing import Literal, Optional

from langchain_core.language_models import BaseLanguageModel

logger = logging.getLogger(__name__)

# Intent types
IntentType = Literal["CHAT", "QUERY"]

# Classification prompt template
MESSAGE_INTENT_CLASSIFICATION_PROMPT = """
You are a message intent classifier. Your task is to determine whether a message requires knowledge retrieval or is just conversational.

Classify the message into one of these categories:
1. CHAT: Simple conversational messages that don't require knowledge lookup (greetings, thanks, personal questions, etc.)
2. QUERY: Questions or requests that likely need knowledge base retrieval (specific information requests, technical questions, etc.)

Examples:
- "Hello, how are you?" -> CHAT
- "What's your name?" -> CHAT
- "Thanks for the help!" -> CHAT
- "What is AWS Lambda?" -> QUERY
- "How do I configure DynamoDB?" -> QUERY
- "Can you explain the difference between S3 and EFS?" -> QUERY
- "I'm looking for information about Amazon Bedrock." -> QUERY
- "Tell me about the chatbot feature design." -> QUERY
- "What's in the implementation plan?" -> QUERY
- "Can you explain that further?" -> CHAT (follow-up without specific knowledge request)
- "I don't understand what you mean." -> CHAT
- "That's interesting." -> CHAT

Message: {message}

Classification (respond with only CHAT or QUERY):
"""


class MessageIntentClassifier:
    """
    Classifies messages as either conversational (CHAT) or requiring knowledge retrieval (QUERY).
    
    This classifier uses a prompt-based approach with an LLM to determine the intent of a message.
    """

    def __init__(self, model: BaseLanguageModel):
        """
        Initialize the classifier with a language model.
        
        Args:
            model: The language model to use for classification
        """
        self.model = model

    def classify(self, message: str) -> IntentType:
        """
        Classify a message as either 'CHAT' or 'QUERY' based on content.
        
        Args:
            message: The message to classify
            
        Returns:
            IntentType: Either 'CHAT' or 'QUERY'
        """
        if not message or not message.strip():
            logger.warning("Empty message provided to classifier, defaulting to CHAT")
            return "CHAT"
            
        # Format the prompt with the message
        prompt = MESSAGE_INTENT_CLASSIFICATION_PROMPT.format(message=message)
        
        try:
            # Get the classification from the model
            response = self.model.invoke(prompt).content.strip()
            
            # Extract just the classification from the response
            if "QUERY" in response.upper():
                logger.info(f"Message classified as QUERY: {message[:50]}...")
                return "QUERY"
            else:
                logger.info(f"Message classified as CHAT: {message[:50]}...")
                return "CHAT"  # Default to CHAT if unclear
        except Exception as e:
            logger.error(f"Error classifying message: {str(e)}")
            # Default to QUERY in case of error to ensure knowledge retrieval
            return "QUERY"
            
    async def classify_async(self, message: str) -> IntentType:
        """
        Classify a message asynchronously as either 'CHAT' or 'QUERY' based on content.
        
        Args:
            message: The message to classify
            
        Returns:
            IntentType: Either 'CHAT' or 'QUERY'
        """
        if not message or not message.strip():
            logger.warning("Empty message provided to classifier, defaulting to CHAT")
            return "CHAT"
            
        # Format the prompt with the message
        prompt = MESSAGE_INTENT_CLASSIFICATION_PROMPT.format(message=message)
        
        try:
            # Get the classification from the model asynchronously
            response = await self.model.ainvoke(prompt)
            response_text = response.content.strip()
            
            # Extract just the classification from the response
            if "QUERY" in response_text.upper():
                logger.info(f"Message classified as QUERY: {message[:50]}...")
                return "QUERY"
            else:
                logger.info(f"Message classified as CHAT: {message[:50]}...")
                return "CHAT"  # Default to CHAT if unclear
        except Exception as e:
            logger.error(f"Error classifying message asynchronously: {str(e)}")
            # Default to QUERY in case of error to ensure knowledge retrieval
            return "QUERY"
