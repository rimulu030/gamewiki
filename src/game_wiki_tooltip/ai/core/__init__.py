"""
AI core module for game wiki tooltip application.
Contains core RAG functionality and query processing.
"""

from .rag_query import EnhancedRagQuery, VectorStoreUnavailableError, map_window_title_to_game_name
from .rag_config import RAGConfig, LLMSettings, get_default_config
from .unified_query_processor import UnifiedQueryProcessor, UnifiedQueryResult, process_query_unified
from .hybrid_retriever import HybridSearchRetriever, VectorRetrieverAdapter

__all__ = [
    'EnhancedRagQuery',
    'VectorStoreUnavailableError',
    'map_window_title_to_game_name',
    'RAGConfig',
    'LLMSettings', 
    'get_default_config',
    'UnifiedQueryProcessor',
    'UnifiedQueryResult',
    'process_query_unified',
    'HybridSearchRetriever',
    'VectorRetrieverAdapter'
]