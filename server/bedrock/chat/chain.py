"""Conversation chain for chat functionality.

This module provides a conversation chain that integrates with LangChain's
ConversationalRetrievalChain and ConversationBufferWindowMemory.
"""

import logging
import os
from typing import Dict, List, Any, Optional

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.retrievers import BaseRetriever
# Using DynamoDBMemoryAdapter directly instead of deprecated ConversationBufferWindowMemory

from .memory import DynamoDBMemoryAdapter

logger = logging.getLogger(__name__)


class ChatConversationChain:
    """Conversation chain for chat functionality.

    This class provides a conversation chain that integrates with LangChain's
    ConversationalRetrievalChain and ConversationBufferWindowMemory.
    """

    def __init__(
        self,
        memory_adapter: DynamoDBMemoryAdapter,
        retriever: BaseRetriever,
        model_id: str = "anthropic.claude-3-5-haiku-20241022-v1:0",
        window_size: int = 15,
    ):
        """Initialize the conversation chain.

        Args:
            memory_adapter: The memory adapter to use for storing and retrieving messages
            retriever: The retriever to use for retrieving documents
            model_id: The Bedrock model ID to use
            window_size: The number of messages to include in the conversation window
        """
        self.memory_adapter = memory_adapter
        self.retriever = retriever
        self.model_id = model_id
        self.window_size = window_size
        aws_region = os.getenv("AWS_REGION", "us-east-1")        
        self.llm = ChatBedrockConverse(
            model=model_id,
            region_name=aws_region,
            model_kwargs={
                "temperature": 0.0,
                "top_p": 0.9,
                "max_tokens": 4096,
            },
        )
        self.chain = self._create_chain()

    def _create_chain(self):
        """Create the conversation chain.

        Returns:
            The conversation chain
        """
        # Create a system prompt that includes context from retrieved documents
        system_prompt = """You are a helpful assistant that answers questions based on the provided context.
If the context doesn't contain the answer, say that you don't know and suggest the user provide more information.
Always be polite, helpful, and concise in your responses.

Context:
{context}
"""

        # Create a prompt template that includes the system prompt, chat history, and user question
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{question}"),
            ]
        )

        # Create the chain
        chain = (
            {
                "context": self.retriever | self._format_docs,
                "question": RunnablePassthrough(),
                "chat_history": lambda _: self._get_chat_history(),
            }
            | prompt
            | self.llm
            | StrOutputParser()
        )

        return chain

    def _get_chat_history(self) -> List[BaseMessage]:
        """Get chat history messages with sliding window applied.
        
        Returns:
            List of recent messages within the window size
        """
        if hasattr(self, '_current_session_id'):
            messages = self.memory_adapter.get_messages(self._current_session_id)
            # Apply sliding window
            return messages[-self.window_size:] if len(messages) > self.window_size else messages
        return []

    def _format_docs(self, docs):
        """Format documents for inclusion in the prompt.

        Args:
            docs: The documents to format

        Returns:
            A formatted string containing the document content
        """
        return "\n\n".join(doc.page_content for doc in docs)

    def process_message(self, session_id: str, message: str) -> str:
        """Process a message and generate a response.

        Args:
            session_id: The session ID
            message: The message content

        Returns:
            The response content
        """
        # Store session ID for use in _get_chat_history
        self._current_session_id = session_id

        # Generate a response
        response = self.chain.invoke(message)

        logger.info(f"Generated response for session {session_id}")
        return response
