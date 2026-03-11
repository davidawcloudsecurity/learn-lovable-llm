"""Custom retriever for Bedrock Agent Runtime.

This module provides a custom retriever that uses Bedrock Agent Runtime to retrieve documents.
"""

import logging
from typing import List, Dict, Any, Optional

import boto3
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class BedrockAgentRetriever(BaseRetriever):
    """Retriever that uses Bedrock Agent Runtime to retrieve documents."""
    
    def __init__(
        self,
        knowledge_base_id: str,
        region_name: str,
        client=None,
        top_k: int = 10
    ):
        """Initialize the retriever.
        
        Args:
            knowledge_base_id: The ID of the knowledge base
            region_name: The AWS region name
            client: The Bedrock Agent Runtime client (optional)
            top_k: The number of results to return
        """
        # Call the parent class constructor first
        super().__init__()
        # Store the parameters as instance variables
        self._knowledge_base_id = knowledge_base_id
        self._region_name = region_name
        self._top_k = top_k
        self._client = client or boto3.client("bedrock-agent-runtime", region_name=region_name)
    
    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        """Get documents relevant to the query.
        
        Args:
            query: The query to search for
            
        Returns:
            List of relevant documents
        """
        try:
            response = self._client.retrieve(
                knowledgeBaseId=self._knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {
                        "numberOfResults": self._top_k,
                    }
                },
            )
            
            documents = []
            for result in response.get("retrievalResults", []):
                content = result.get("content", {}).get("text", "")
                metadata = {
                    "source": result.get("location", {}).get("s3Location", {}).get("uri", ""),
                    "score": result.get("score", 0),
                }
                documents.append(Document(page_content=content, metadata=metadata))
            
            return documents
        except Exception as e:
            logger.error(f"Error retrieving documents: {str(e)}", exc_info=True)
            return []
