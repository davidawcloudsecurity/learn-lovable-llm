"""
Hybrid conversation chain for the chatbot feature.

This module provides a hybrid conversation chain that routes messages to either a simple
conversation chain or a RAG-enabled chain based on message intent.
"""

import logging
from typing import Any, Dict, List, Optional

from langchain_aws import ChatBedrock
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.retrievers import BaseRetriever

from .chain import ChatConversationChain
from .classifier import MessageIntentClassifier
from .memory import DynamoDBMemoryAdapter

logger = logging.getLogger(__name__)


class HybridConversationChain:
    """
    Hybrid conversation chain that routes messages based on intent.
    
    This chain uses a message intent classifier to determine whether a message requires
    knowledge retrieval (QUERY) or is just conversational (CHAT). It then routes the
    message to either a simple conversation chain or a RAG-enabled chain.
    """

    def __init__(
        self,
        memory_adapter: DynamoDBMemoryAdapter,
        retriever: BaseRetriever,
        model_id: str = "anthropic.claude-3-5-haiku-20241022-v1:0",
        window_size: int = 15,
    ):
        """
        Initialize the hybrid conversation chain.
        
        Args:
            memory_adapter: The memory adapter to use for storing and retrieving messages
            retriever: The retriever to use for RAG
            model_id: The model ID to use
            window_size: The number of messages to keep in memory
        """
        self.memory_adapter = memory_adapter
        self.retriever = retriever
        self.model_id = model_id
        self.window_size = window_size
        
        # Create the LLM
        self.llm = ChatBedrock(
            model=model_id,
            model_kwargs={
                "temperature": 0.0,
                "top_p": 0.9,
                "max_tokens": 4096,
            },
        )
        
        # Create the classifier
        self.classifier = MessageIntentClassifier(model=self.llm)
        
        # Create the conversation chain (for simple conversational messages)
        # This chain uses the same retriever but we'll ignore the retrieved documents
        self.conversation_chain = ChatConversationChain(
            memory_adapter=memory_adapter,
            retriever=retriever,  # Use the same retriever but we'll ignore the results
            model_id=model_id,
            window_size=window_size,
        )
        
        # Create the RAG chain (for knowledge queries)
        self.rag_chain = ChatConversationChain(
            memory_adapter=memory_adapter,
            retriever=retriever,
            model_id=model_id,
            window_size=window_size,
        )
        
        logger.info("Initialized HybridConversationChain")

    def process_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """
        Process a message and generate a response.
        
        This method classifies the message intent and routes it to the appropriate chain.
        
        Args:
            session_id: The session ID
            message: The message to process
            
        Returns:
            Dict with response text and metadata
        """
        try:
            # Step 1: Classify the message intent
            logger.info(f"Classifying message intent for session {session_id}")
            intent = self.classifier.classify(message)
            logger.info(f"Message classified as: {intent}")
            
            # Step 2: Route message based on intent
            if intent == "QUERY":
                logger.info(f"Routing to RAG chain for session {session_id}")
                response = self.rag_chain.process_message(session_id, message)
                
                # For QUERY intent, include empty sources list (will be populated in future tasks)
                return {
                    "response": response,
                    "intent": intent,
                    "sources": []  # Empty list for now, will be populated with actual sources later
                }
            
            elif intent == "CHAT":
                logger.info(f"Routing to conversation chain for session {session_id}")
                response = self.conversation_chain.process_message(session_id, message)
                
                # For CHAT intent, sources should be None
                return {
                    "response": response,
                    "intent": intent,
                    "sources": None
                }
            
            else:
                # Handle unexpected intent (should not happen with proper classifier)
                logger.warning(f"Unknown intent '{intent}', defaulting to QUERY")
                response = self.rag_chain.process_message(session_id, message)
                
                return {
                    "response": response,
                    "intent": "QUERY",  # Default to QUERY for safety
                    "sources": []
                }
                
        except Exception as e:
            logger.error(f"Error processing message for session {session_id}: {str(e)}", exc_info=True)
            
            # On classification or processing failure, default to conversation chain
            # This provides a fallback in case of errors
            try:
                logger.info(f"Falling back to conversation chain for session {session_id}")
                response = self.conversation_chain.process_message(session_id, message)
                
                return {
                    "response": response,
                    "intent": "CHAT",  # Default to CHAT for fallback
                    "sources": None
                }
            except Exception as fallback_error:
                logger.error(f"Fallback processing also failed for session {session_id}: {str(fallback_error)}", exc_info=True)
                # Re-raise the original error if fallback also fails
                raise e
