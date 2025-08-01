"""
Gemini Embedding Client - Replace Jina with Google Gemini embeddings
=====================================================

Features:
1. Use Gemini embedding-001 model
2. Support RETRIEVAL_DOCUMENT for knowledge base
3. Support QUESTION_ANSWERING for user queries
4. Configurable output dimensions (768)
"""

import os
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
import numpy as np
import logging

logger = logging.getLogger(__name__)


class GeminiEmbeddingClient:
    """Gemini Embedding Client"""
    
    def __init__(self,
                 api_key: Optional[str] = None,
                 model: str = "gemini-embedding-001",
                 output_dim: int = 768):
        """
        Initialize Gemini embedding client
        
        Args:
            api_key: Google API key, if None will get from environment variable
            model: Embedding model to use
            output_dim: Output vector dimension (768 recommended)
        """
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable or parameter is required")
        
        self.model = model
        self.output_dim = output_dim
        
        # Initialize Gemini client
        os.environ["GOOGLE_API_KEY"] = self.api_key
        self.client = genai.Client()
        
        logger.info(f"Initialized Gemini embedding client with model: {model}, output_dim: {output_dim}")
    
    def embed_batch(self, 
                    texts: List[str], 
                    task_type: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
        """
        Batch embed texts using Gemini API
        
        Args:
            texts: List of texts to embed
            task_type: Task type - "RETRIEVAL_DOCUMENT" for knowledge base,
                      "QUESTION_ANSWERING" for user queries
                      
        Returns:
            List of embedding vectors
        """
        try:
            # Prepare config with task type and output dimensions
            config = types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self.output_dim
            )
            
            # Call Gemini API for embeddings
            result = self.client.models.embed_content(
                model=self.model,
                contents=texts,
                config=config
            )
            
            # Extract embeddings
            embeddings = [np.array(e.values).tolist() for e in result.embeddings]
            
            # Log first embedding info for debugging
            if embeddings and len(embeddings[0]) > 0:
                logger.info(f"Generated {len(embeddings)} embeddings, dimension: {len(embeddings[0])}")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Gemini embedding API call failed: {e}")
            raise
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed documents for knowledge base (using RETRIEVAL_DOCUMENT task type)
        
        Args:
            texts: List of document texts
            
        Returns:
            List of embedding vectors
        """
        return self.embed_batch(texts, task_type="RETRIEVAL_DOCUMENT")
    
    def embed_query(self, query: str) -> List[float]:
        """
        Embed a single query (using QUESTION_ANSWERING task type)
        
        Args:
            query: Query text
            
        Returns:
            Embedding vector
        """
        embeddings = self.embed_batch([query], task_type="QUESTION_ANSWERING")
        return embeddings[0] if embeddings else []
    
    def embed_queries(self, queries: List[str]) -> List[List[float]]:
        """
        Embed multiple queries (using QUESTION_ANSWERING task type)
        
        Args:
            queries: List of query texts
            
        Returns:
            List of embedding vectors
        """
        return self.embed_batch(queries, task_type="QUESTION_ANSWERING")