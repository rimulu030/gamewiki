"""
Enhanced RAG query interface - integrated batch embedding and vector store retrieval
============================================

Features:
1. Load pre-built vector store
2. Perform semantic retrieval
3. Support LLM query rewriting
4. Hybrid search (vector + BM25)
5. Return relevant game strategy information
"""

import logging
import asyncio
import json
import numpy as np
from typing import Optional, Dict, Any, List, AsyncGenerator
from pathlib import Path
import time
import sys
import os

class VectorStoreUnavailableError(Exception):
    """Vector store unavailable error"""
    pass

def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path for resource files, compatible with development and PyInstaller packaging
    
    Args:
        relative_path: Path relative to project root or temporary directory
        
    Returns:
        Absolute path for resource files
    """
    try:
        # PyInstaller packaged temporary directory
        base_path = Path(sys._MEIPASS)
        # 在PyInstaller环境中，assets被打包到src/game_wiki_tooltip/路径下
        resource_path = base_path / "src" / "game_wiki_tooltip" / relative_path
        print(f"🔧 [RAG-DEBUG] Using PyInstaller temp directory: {base_path}")
        print(f"🔧 [RAG-DEBUG] Building resource path: {resource_path}")
    except AttributeError:
        # Development environment: find project root from current file location
        current_file = Path(__file__).parent  # .../ai/
        project_root = current_file.parent.parent.parent  # Go up to project root
        resource_path = project_root / "src" / "game_wiki_tooltip" / relative_path
        print(f"🔧 [RAG-DEBUG] Using development environment")
        print(f"🔧 [RAG-DEBUG] Project root: {project_root}")
        print(f"🔧 [RAG-DEBUG] Building resource path: {resource_path}")
    
    return resource_path

# Import batch embedding processor
try:
    from ..indexing.batch_embedding import BatchEmbeddingProcessor
    BATCH_EMBEDDING_AVAILABLE = True
except ImportError:
    BATCH_EMBEDDING_AVAILABLE = False
    logging.warning("Batch embedding module not available")

# Vector store support - lazy import to avoid startup crashes
FAISS_AVAILABLE = None

def _check_faiss_available():
    """Check and lazy import faiss"""
    global FAISS_AVAILABLE
    if FAISS_AVAILABLE is None:
        try:
            import faiss
            FAISS_AVAILABLE = True
        except ImportError:
            FAISS_AVAILABLE = False
            logging.warning("FAISS not available")
    return FAISS_AVAILABLE

try:
    import qdrant_client
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logging.warning("Qdrant not available")

# Import Gemini summarizer
try:
    from ..models.gemini_summarizer import create_gemini_summarizer, SummarizationConfig
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Gemini summarization module not available")

# Import intent-aware reranker
try:
    from ..retrieval.intent_aware_reranker import IntentAwareReranker
    RERANKER_AVAILABLE = True
except ImportError:
    RERANKER_AVAILABLE = False
    logging.warning("Intent reranking module not available")

# Import hybrid retriever and BM25 error class
try:
    from .hybrid_retriever import HybridSearchRetriever, VectorRetrieverAdapter
    from ..indexing.enhanced_bm25_indexer import BM25UnavailableError
    HYBRID_RETRIEVER_AVAILABLE = True
except ImportError as e:
    HybridSearchRetriever = None
    VectorRetrieverAdapter = None
    BM25UnavailableError = Exception  # Fallback to base exception class
    HYBRID_RETRIEVER_AVAILABLE = False
    logging.warning(f"Hybrid retriever module not available: {e}")

# Import configuration and query rewrite
from .rag_config import LLMSettings
from .rag_config import RAGConfig, get_default_config

logger = logging.getLogger(__name__)

# Global cache for vector store mapping configuration
_vector_mappings_cache = None
_vector_mappings_last_modified = None

def load_vector_mappings() -> Dict[str, str]:
    """
    Load vector store mapping configuration
    
    Returns:
        Mapping dictionary from window title to vector store name
    """
    global _vector_mappings_cache, _vector_mappings_last_modified
    
    try:
        # Use get_resource_path to handle packaged environment correctly
        mapping_file = get_resource_path("assets/vector_mappings.json")
        
        # Check if file exists
        if not mapping_file.exists():
            logger.warning(f"Vector store mapping configuration file does not exist: {mapping_file}")
            return {}  # Return empty dict instead of None
        
        # Check file modification time, implement cache mechanism
        current_modified = mapping_file.stat().st_mtime
        if (_vector_mappings_cache is not None and 
            _vector_mappings_last_modified == current_modified):
            return _vector_mappings_cache
        
        # Read configuration file
        with open(mapping_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Build mapping dictionary
        mappings = {}
        for mapping in config.get("mappings", []):
            vector_db_name = mapping.get("vector_db_name")
            window_titles = mapping.get("window_titles", [])
            
            for title in window_titles:
                mappings[title.lower()] = vector_db_name
        
        # Update cache
        _vector_mappings_cache = mappings
        _vector_mappings_last_modified = current_modified
        
        logger.info(f"Successfully loaded vector store mapping configuration, containing {len(mappings)} mappings")
        return mappings
    except Exception as e:
        logger.error(f"Failed to load vector store mapping configuration: {e}")
        return {}  # Return empty dict instead of None

def map_window_title_to_game_name(window_title: str) -> Optional[str]:
    """
    Map window title to vector store file name
    
    Args:
        window_title: Window title
        
    Returns:
        Corresponding vector store file name (without .json extension), if not found return None
    """
    # Convert to lowercase for matching
    title_lower = window_title.lower()
    
    # Load vector store mapping configuration
    title_to_vectordb_mapping = load_vector_mappings()
    
    # Additional safety check - though load_vector_mappings() should never return None now
    if not title_to_vectordb_mapping:
        logger.warning(f"Vector mapping configuration is empty or invalid")
        return None
    
    # Try exact match
    for title_key, vectordb_name in title_to_vectordb_mapping.items():
        if title_key in title_lower:
            logger.info(f"Window title '{window_title}' mapped to vector store '{vectordb_name}'")
            return vectordb_name
    
    # If no mapping found, record warning and return None
    logger.warning(f"No mapping found for window title '{window_title}'")
    return None

class EnhancedRagQuery:
    """Enhanced RAG query interface, supporting vector store retrieval and LLM query rewriting"""
    
    def __init__(self, vector_store_path: Optional[str] = None,
                 enable_hybrid_search: bool = True,
                 hybrid_config: Optional[Dict] = None,
                 llm_config: Optional[LLMSettings] = None,
                 google_api_key: Optional[str] = None,
                 enable_query_rewrite: bool = True,
                 enable_summarization: bool = True,
                 summarization_config: Optional[Dict] = None,
                 enable_intent_reranking: bool = True,
                 reranking_config: Optional[Dict] = None,
                 rag_config: Optional[RAGConfig] = None):
        """
        Initialize RAG query
        
        Args:
            vector_store_path: Vector store path, if None use default path
            enable_hybrid_search: Whether to enable hybrid search
            hybrid_config: Hybrid search configuration
            llm_config: LLM configuration
            enable_query_rewrite: Whether to enable query rewriting
            enable_summarization: Whether to enable Gemini summary
            summarization_config: Summary configuration
            enable_intent_reranking: Whether to enable intent-aware reranking
            reranking_config: Reranking configuration
        """
        self.is_initialized = False
        self.vector_store_path = vector_store_path
        self.vector_store = None
        self.metadata = None
        self.config = None
        self.processor = None
        self.enable_hybrid_search = enable_hybrid_search
        self.hybrid_config = hybrid_config or {
            "fusion_method": "rrf",
            "vector_weight": 0.5,
            "bm25_weight": 0.5,
            "rrf_k": 60
        }
        # Use RAGConfig if provided, otherwise create from individual parameters
        if rag_config:
            self.rag_config = rag_config
            # Override individual settings from RAGConfig
            self.llm_config = rag_config.llm_settings
            self.enable_hybrid_search = rag_config.hybrid_search.enabled
            self.hybrid_config = rag_config.hybrid_search.to_dict()
            self.enable_summarization = rag_config.summarization.enabled
            self.summarization_config = rag_config.summarization.to_dict()
            self.enable_intent_reranking = rag_config.intent_reranking.enabled
            self.reranking_config = rag_config.intent_reranking.to_dict()
            self.enable_query_rewrite = rag_config.query_processing.enable_query_rewrite
        else:
            # Use individual parameters for backward compatibility
            self.rag_config = None
            self.llm_config = llm_config
        
        self.google_api_key = google_api_key or (self.llm_config.get_api_key() if self.llm_config else None)
        self.enable_query_rewrite = enable_query_rewrite
        self.hybrid_retriever = None
        
        # Summary configuration
        self.enable_summarization = enable_summarization and GEMINI_AVAILABLE
        self.summarization_config = summarization_config or {}
        self.summarizer = None
        
        # Intent reranking configuration
        self.enable_intent_reranking = enable_intent_reranking and RERANKER_AVAILABLE
        self.reranking_config = reranking_config or {
            "intent_weight": 0.4,
            "semantic_weight": 0.6
        }
        self.reranker = None
        
        # Initialize summarizer
        if self.enable_summarization:
            self._initialize_summarizer()
            
        # Initialize reranker
        if self.enable_intent_reranking:
            self._initialize_reranker()
        
    async def initialize(self, game_name: Optional[str] = None):
        """
        Initialize RAG system
        
        Args:
            game_name: Game name, used to automatically find vector store
        """
        try:
            print(f"🔧 [RAG-DEBUG] Starting to initialize RAG system - game: {game_name}")
            logger.info("Initializing enhanced RAG system...")
            
            if not BATCH_EMBEDDING_AVAILABLE:
                error_msg = "Vector search feature unavailable: batch embedding module import failed. Please check if the following dependencies are correctly installed:\n1. numpy\n2. faiss-cpu\n3. other embedding related dependencies"
                print(f"❌ [RAG-DEBUG] {error_msg}")
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            # Determine vector store path
            if self.vector_store_path is None and game_name:
                # Automatically find vector store - use resource path function
                vector_dir = get_resource_path("ai/vectorstore")
                
                print(f"🔍 [RAG-DEBUG] Finding vector store directory: {vector_dir}")
                logger.info(f"Finding vector store directory: {vector_dir}")
                config_files = list(vector_dir.glob(f"{game_name}_vectors_config.json"))
                
                if config_files:
                    self.vector_store_path = str(config_files[0])
                    print(f"✅ [RAG-DEBUG] Found vector store configuration: {self.vector_store_path}")
                    logger.info(f"Found vector store configuration: {self.vector_store_path}")
                else:
                    error_msg = f"Vector store not found: No vector store configuration file found for game '{game_name}'\nSearch path: {vector_dir}\nSearch pattern: {game_name}_vectors_config.json"
                    
                    # List existing files for debugging
                    try:
                        existing_files = list(vector_dir.glob("*_vectors_config.json"))
                        if existing_files:
                            available_games = [f.stem.replace("_vectors_config", "") for f in existing_files]
                            error_msg += f"\nAvailable vector stores: {', '.join(available_games)}"
                        else:
                            error_msg += "\nNo vector store configuration files found"
                    except Exception as e:
                        error_msg += f"\nFailed to list existing files: {e}"
                    
                    print(f"❌ [RAG-DEBUG] {error_msg}")
                    logger.error(error_msg)
                    raise VectorStoreUnavailableError(error_msg)
            
            if not self.vector_store_path or not Path(self.vector_store_path).exists():
                error_msg = f"Vector store configuration file not found: {self.vector_store_path}"
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            # Load vector store
            try:
                self.processor = BatchEmbeddingProcessor(api_key=self.google_api_key)
                self.vector_store = self.processor.load_vector_store(self.vector_store_path)
                
                # Load configuration and metadata
                with open(self.vector_store_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                
                if self.config["vector_store_type"] == "faiss":
                    self.metadata = self.vector_store["metadata"]
                
                logger.info(f"Vector store loaded: {self.config['chunk_count']} chunks")
                
                # Store game name from initial parameter
                self.game_name = game_name
                
                # Initialize hybrid retriever
                if self.enable_hybrid_search:
                    self._initialize_hybrid_retriever()
                    
            except Exception as e:
                error_msg = f"Failed to load vector store: {e}"
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            self.is_initialized = True
            logger.info("Enhanced RAG system initialized")
            
        except VectorStoreUnavailableError:
            # Re-throw vector store specific error
            self.is_initialized = False
            raise
        except Exception as e:
            error_msg = f"RAG system initialization failed: {e}"
            logger.error(error_msg)
            self.is_initialized = False
            raise VectorStoreUnavailableError(error_msg)
    
    def _initialize_hybrid_retriever(self):
        """
        Initialize hybrid retriever
        
        Raises:
            VectorStoreUnavailableError: When hybrid search initialization fails
        """
        if not self.enable_hybrid_search:
            logger.warning("Hybrid search is not enabled, only vector search will be used")
            return
        
        if not HYBRID_RETRIEVER_AVAILABLE:
            error_msg = "Hybrid search initialization failed: hybrid retriever module is not available"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
        
        try:
            # Check if BM25 index file exists - fix path parsing problem
            from pathlib import Path
            bm25_index_path = self.config.get("bm25_index_path")
            if not bm25_index_path:
                error_msg = "Hybrid search initialization failed: BM25 index path not found in configuration"
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            # If it's a relative path, build absolute path based on resource path
            bm25_path = Path(bm25_index_path)
            if not bm25_path.is_absolute():
                # Use resource path function to build path
                vectorstore_dir = get_resource_path("ai/vectorstore")
                # Try to build path based on vectorstore directory
                bm25_path = vectorstore_dir / bm25_index_path
            
            # Create vector retriever adapter
            vector_retriever = VectorRetrieverAdapter(self)
            
            # Create hybrid retriever - read unified processing settings from configuration
            enable_unified_processing = self.hybrid_config.get("enable_unified_processing", True)
            enable_query_rewrite = self.hybrid_config.get("enable_query_rewrite", self.enable_query_rewrite)
            
            self.hybrid_retriever = HybridSearchRetriever(
                vector_retriever=vector_retriever,
                bm25_index_path=str(bm25_path),
                fusion_method=self.hybrid_config.get("fusion_method", "rrf"),
                vector_weight=self.hybrid_config.get("vector_weight", 0.5),
                bm25_weight=self.hybrid_config.get("bm25_weight", 0.5),
                rrf_k=self.hybrid_config.get("rrf_k", 60),
                llm_config=self.llm_config,
                enable_unified_processing=enable_unified_processing,  # Read from configuration
                enable_query_rewrite=enable_query_rewrite
            )
            
            if enable_unified_processing:
                logger.info("Hybrid retriever initialized successfully (unified processing mode)")
            else:
                logger.info("Hybrid retriever initialized successfully (independent processing mode, unified processing disabled)")
            
        except BM25UnavailableError as e:
            # BM25 specific error, re-wrap as vector store error
            error_msg = f"Hybrid search initialization failed: {e}"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
        except (FileNotFoundError, RuntimeError) as e:
            # File not found or other runtime error
            error_msg = f"Hybrid search initialization failed: {e}"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
        except Exception as e:
            error_msg = f"Hybrid retriever initialization failed: {e}"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
    
    def _initialize_summarizer(self):
        """Initialize Gemini summarizer"""
        try:
            import os
            
            # Get API key from centralized config
            api_key = self.google_api_key
            
            if not api_key:
                logger.warning("Gemini API key not found, summary feature will be disabled")
                self.enable_summarization = False
                return
            
            # Create summary configuration (remove deprecated max_summary_length parameter)
            config = SummarizationConfig(
                api_key=api_key,
                model_name=self.summarization_config.get("model_name", "gemini-2.5-flash-lite"),
                temperature=self.summarization_config.get("temperature", 0.3),
                include_sources=self.summarization_config.get("include_sources", True),
                language=self.summarization_config.get("language", "auto")
            )
            
            # Create summarizer (remove deprecated max_summary_length parameter)
            self.summarizer = create_gemini_summarizer(
                api_key=api_key,
                model_name=config.model_name,
                temperature=config.temperature,
                include_sources=config.include_sources,
                language=config.language,
                enable_google_search=self.summarization_config.get("enable_google_search", True)
            )
            
            logger.info(f"Gemini summarizer initialized successfully: {config.model_name}")
            
        except Exception as e:
            logger.error(f"Gemini summarizer initialization failed: {e}")
            self.enable_summarization = False
    
    def _initialize_reranker(self):
        """Initialize intent-aware reranker"""
        try:
            self.reranker = IntentAwareReranker()
            logger.info("Intent-aware reranker initialized successfully")
        except Exception as e:
            logger.error(f"Intent-aware reranker initialization failed: {e}")
            self.enable_intent_reranking = False
    
    def _search_faiss(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Use FAISS for vector search
        
        Args:
            query: Query text
            top_k: Number of results to return
            
        Returns:
            List of search results
        """
        print(f"🔍 [VECTOR-DEBUG] Starting FAISS vector search: query='{query}', top_k={top_k}")
        
        if not self.vector_store or not self.metadata:
            print(f"⚠️ [VECTOR-DEBUG] Vector store or metadata not initialized")
            logger.warning("Vector store or metadata not initialized")
            return []
        
        try:
            # Get query vector
            query_text = self.processor.build_text({"topic": query, "summary": query, "keywords": []})
            print(f"📄 [VECTOR-DEBUG] Building query text: '{query_text[:100]}...'")
            
            # Use Gemini embeddings with QUESTION_ANSWERING task type for queries
            if hasattr(self.processor, 'embedding_client'):
                query_vectors = [self.processor.embedding_client.embed_query(query_text)]
            else:
                query_vectors = self.processor.embed_batch([query_text])
            query_vector = np.array(query_vectors[0], dtype=np.float32).reshape(1, -1)
            print(f"🔢 [VECTOR-DEBUG] Query vector dimension: {query_vector.shape}, first 5 values: {query_vector[0][:5]}")
            
            # Build correct index file path
            # Use the same path logic as BatchEmbeddingProcessor._load_faiss_store
            index_path_str = self.config["index_path"]
            if not Path(index_path_str).is_absolute():
                # Use resource path function to build absolute path
                vectorstore_dir = get_resource_path("ai/vectorstore")
                index_path = vectorstore_dir / Path(index_path_str).name
            else:
                index_path = Path(index_path_str)
            
            index_file_path = index_path / "index.faiss"
            print(f"📂 [VECTOR-DEBUG] FAISS index file path: {index_file_path}")
            logger.info(f"Attempting to load FAISS index file: {index_file_path}")
            
            if not index_file_path.exists():
                print(f"❌ [VECTOR-DEBUG] FAISS index file does not exist: {index_file_path}")
                logger.error(f"FAISS index file does not exist: {index_file_path}")
                return []
            
            # Load FAISS index
            try:
                import faiss
            except ImportError:
                logger.error("Failed to import faiss library")
                print(f"❌ [VECTOR-DEBUG] Failed to import faiss library, please ensure faiss-cpu is installed")
                return []
            
            index = faiss.read_index(str(index_file_path))
            print(f"📊 [VECTOR-DEBUG] FAISS index information: total vectors={index.ntotal}, dimension={index.d}")
            
            # Execute search
            scores, indices = index.search(query_vector, top_k)
            print(f"🔍 [VECTOR-DEBUG] FAISS search raw results:")
            print(f"   - Retrieved indices: {indices[0]}")
            print(f"   - Similarity scores: {scores[0]}")
            
            # Return results
            results = []
            for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                if idx < len(self.metadata):
                    chunk = self.metadata[idx]
                    chunk_info = {
                        "chunk": chunk,
                        "score": float(score),
                        "rank": i + 1
                    }
                    results.append(chunk_info)
                    
                    # Detailed result debugging information
                    print(f"   📋 [VECTOR-DEBUG] Result {i+1}:")
                    print(f"      - Similarity score: {score:.4f}")
                    print(f"      - Index ID: {idx}")
                    print(f"      - Topic: {chunk.get('topic', 'Unknown')}")
                    print(f"      - Summary: {chunk.get('summary', '')[:100]}...")
                    print(f"      - Keywords: {chunk.get('keywords', [])}")
                    
                    # If it's structured data, display enemy information
                    if "structured_data" in chunk:
                        structured = chunk["structured_data"]
                        if "enemy_name" in structured:
                            print(f"      - Enemy name: {structured['enemy_name']}")
                        if "weak_points" in structured:
                            weak_points = [wp.get("name", "Unknown") for wp in structured["weak_points"]]
                            print(f"      - Weak points: {weak_points}")
            
            print(f"✅ [VECTOR-DEBUG] FAISS search completed, found {len(results)} results")
            logger.info(f"FAISS search completed, found {len(results)} results")
            return results
            
        except Exception as e:
            print(f"❌ [VECTOR-DEBUG] FAISS search failed: {e}")
            logger.error(f"FAISS search failed: {e}")
            return []
    
    def _search_qdrant(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Use Qdrant for vector search
        
        Args:
            query: Query text
            top_k: Number of results to return
            
        Returns:
            List of search results
        """
        print(f"🔍 [VECTOR-DEBUG] Starting Qdrant vector search: query='{query}', top_k={top_k}")
        
        if not self.vector_store or not QDRANT_AVAILABLE:
            print(f"⚠️ [VECTOR-DEBUG] Qdrant vector store not initialized or not available")
            logger.warning("Qdrant vector store not initialized or not available")
            return []
        
        try:
            # Get query vector
            query_text = self.processor.build_text({"topic": query, "summary": query, "keywords": []})
            print(f"📄 [VECTOR-DEBUG] Building query text: '{query_text[:100]}...'")
            
            # Use Gemini embeddings with QUESTION_ANSWERING task type for queries
            if hasattr(self.processor, 'embedding_client'):
                query_vectors = [self.processor.embedding_client.embed_query(query_text)]
            else:
                query_vectors = self.processor.embed_batch([query_text])
            query_vector = query_vectors[0]
            print(f"🔢 [VECTOR-DEBUG] Query vector dimension: {len(query_vector)}, first 5 values: {query_vector[:5]}")
            
            # Execute search
            print(f"🔍 [VECTOR-DEBUG] Calling Qdrant search: collection={self.config['collection_name']}")
            results = self.vector_store.search(
                collection_name=self.config["collection_name"],
                query_vector=query_vector,
                limit=top_k
            )
            
            print(f"📊 [VECTOR-DEBUG] Qdrant search raw results count: {len(results)}")
            
            # Format results
            formatted_results = []
            for i, result in enumerate(results):
                chunk_info = {
                    "chunk": result.payload,
                    "score": result.score,
                    "rank": i + 1
                }
                formatted_results.append(chunk_info)
                
                # Detailed result debugging information
                print(f"   📋 [VECTOR-DEBUG] Result {i+1}:")
                print(f"      - Similarity score: {result.score:.4f}")
                print(f"      - Topic: {result.payload.get('topic', 'Unknown')}")
                print(f"      - Summary: {result.payload.get('summary', '')[:100]}...")
                print(f"      - Keywords: {result.payload.get('keywords', [])}")
                
                # If it's structured data, display enemy information
                if "structured_data" in result.payload:
                    structured = result.payload["structured_data"]
                    if "enemy_name" in structured:
                        print(f"      - Enemy name: {structured['enemy_name']}")
                    if "weak_points" in structured:
                        weak_points = [wp.get("name", "Unknown") for wp in structured["weak_points"]]
                        print(f"      - Weak points: {weak_points}")
            
            print(f"✅ [VECTOR-DEBUG] Qdrant search completed, found {len(formatted_results)} results")
            logger.info(f"Qdrant search completed, found {len(formatted_results)} results")
            return formatted_results
            
        except Exception as e:
            print(f"❌ [VECTOR-DEBUG] Qdrant search failed: {e}")
            logger.error(f"Qdrant search failed: {e}")
            return []

    def _search_hybrid_with_processed_query(self, unified_query_result, top_k: int = 3) -> Dict[str, Any]:
        """
        Use preprocessed unified query results for hybrid search
        
        Args:
            unified_query_result: Unified query processing result object
            top_k: Number of results to return
            
        Returns:
            Hybrid search results (including metadata)
        """
        print(f"🔍 [RAG-DEBUG] Starting hybrid search (preprocessed mode): top_k={top_k}")
        
        if not self.hybrid_retriever:
            print(f"⚠️ [RAG-DEBUG] Hybrid retriever not initialized, falling back to vector search")
            logger.warning("Hybrid retriever not initialized, falling back to vector search")
            # Use rewritten query for vector search
            semantic_query = unified_query_result.rewritten_query
            results = self._search_faiss(semantic_query, top_k) if self.config["vector_store_type"] == "faiss" else self._search_qdrant(semantic_query, top_k)
            return {
                "results": results,
                "query": {
                    "original": unified_query_result.original_query,
                    "processed_query": semantic_query,
                    "bm25_optimized_query": unified_query_result.bm25_optimized_query,
                    "translation_applied": unified_query_result.translation_applied,
                    "rewrite_applied": unified_query_result.rewrite_applied,
                    "intent": unified_query_result.intent,
                    "confidence": unified_query_result.confidence
                },
                "metadata": {
                    "total_results": len(results),
                    "search_type": "vector_fallback", 
                    "fusion_method": "none",
                    "rewrite_info": {
                        "intent": unified_query_result.intent,
                        "confidence": unified_query_result.confidence,
                        "reasoning": unified_query_result.reasoning
                    }
                }
            }
        
        # Directly call hybrid retriever, disable internal unified processing (avoid duplicate processing)
        try:
            print(f"🚀 [RAG-DEBUG] Starting hybrid search (using preprocessed results)")
            print(f"   - Semantic query: '{unified_query_result.rewritten_query}'")
            print(f"   - BM25 query: '{unified_query_result.bm25_optimized_query}'")
            
            # Manually execute hybrid search process, using preprocessed query
            # Vector search uses rewritten query
            vector_search_count = 10
            bm25_search_count = 10
            
            print(f"🔍 [HYBRID-DEBUG] Starting vector search: query='{unified_query_result.rewritten_query}', top_k={vector_search_count}")
            vector_results = self.hybrid_retriever.vector_retriever.search(unified_query_result.rewritten_query, vector_search_count)
            print(f"📊 [HYBRID-DEBUG] Vector search results count: {len(vector_results)}")
            
            # BM25 search uses optimized query
            bm25_results = []
            if self.hybrid_retriever.bm25_indexer:
                print(f"🔍 [HYBRID-DEBUG] Starting BM25 search:")
                print(f"   - Original query: '{unified_query_result.original_query}'")
                print(f"   - Semantic query: '{unified_query_result.rewritten_query}'")
                print(f"   - BM25 optimized: '{unified_query_result.bm25_optimized_query}'")
                print(f"   - Search count: {bm25_search_count}")
                
                bm25_results = self.hybrid_retriever.bm25_indexer.search(unified_query_result.bm25_optimized_query, bm25_search_count)
                print(f"📊 [HYBRID-DEBUG] BM25 search results count: {len(bm25_results)}")
            else:
                print(f"⚠️ [HYBRID-DEBUG] BM25 indexer not initialized, skipping BM25 search")
            
            # Score fusion
            final_result_count = 5
            print(f"🔄 [HYBRID-DEBUG] Starting score fusion: method={self.hybrid_retriever.fusion_method}")
            
            final_results = self.hybrid_retriever._fuse_results(vector_results, bm25_results, final_result_count)
            
            print(f"✅ [HYBRID-DEBUG] Score fusion completed, final results count: {len(final_results)}")
            
            # Build return results
            return {
                "results": final_results,
                "query": {
                    "original": unified_query_result.original_query,
                    "processed_query": unified_query_result.rewritten_query,
                    "bm25_optimized_query": unified_query_result.bm25_optimized_query,
                    "translation_applied": unified_query_result.translation_applied,
                    "rewrite_applied": unified_query_result.rewrite_applied,
                    "intent": unified_query_result.intent,
                    "confidence": unified_query_result.confidence,
                    "detected_language": unified_query_result.detected_language,
                    "processing_method": "preprocessed",
                    "reasoning": unified_query_result.reasoning
                },
                "metadata": {
                    "fusion_method": self.hybrid_retriever.fusion_method,
                    "vector_results_count": len(vector_results),
                    "bm25_results_count": len(bm25_results),
                    "final_results_count": len(final_results),
                    "vector_search_count": vector_search_count,
                    "bm25_search_count": bm25_search_count,
                    "target_final_count": final_result_count,
                    "processing_stats": {
                        "preprocessed_mode": True,
                        "avoided_duplicate_processing": True
                    }
                }
            }
            
        except Exception as e:
            print(f"❌ [RAG-DEBUG] Hybrid search failed: {e}")
            logger.error(f"Hybrid search failed: {e}")
            # Fall back to vector search
            semantic_query = unified_query_result.rewritten_query
            results = self._search_faiss(semantic_query, top_k) if self.config["vector_store_type"] == "faiss" else self._search_qdrant(semantic_query, top_k)
            return {
                "results": results,
                "query": {
                    "original": unified_query_result.original_query,
                    "processed_query": semantic_query,
                    "bm25_optimized_query": unified_query_result.bm25_optimized_query,
                    "translation_applied": unified_query_result.translation_applied,
                    "rewrite_applied": unified_query_result.rewrite_applied
                },
                "metadata": {
                    "total_results": len(results),
                    "search_type": "vector_fallback",
                    "fusion_method": "none",
                    "rewrite_info": {
                        "intent": unified_query_result.intent,
                        "confidence": unified_query_result.confidence,
                        "reasoning": f"Hybrid search failed: {str(e)}"
                    }
                }
            }
    
    def _format_answer(self, search_response: Dict[str, Any], question: str) -> str:
        """
        Format search results as an answer
        
        Args:
            search_response: Search response (contains results and metadata)
            question: Original question
            
        Returns:
            Formatted answer
        """
        results = search_response.get("results", [])
        metadata = search_response.get("metadata", {})
        query_info = search_response.get("query", {})
        
        if not results:
            return f"Sorry, I couldn't find any information about '{question}'."
        
        # Build answer
        answer_parts = [f"About '{question}' information:\n"]
        
        # If query is translated, display translation information
        if query_info.get("translation_applied", False):
            translation_info = metadata.get("translation_info", {})
            translated_query = translation_info.get("translated_query", "")
            if translated_query:
                answer_parts.append(f"Translation: '{question}' -> '{translated_query}'")
        
        # If query is rewritten, display related information
        if query_info.get("rewrite_applied", False):
            rewrite_info = metadata.get("rewrite_info", {})
            answer_parts.append(f"Intent analysis: {rewrite_info.get('intent', 'unknown')}")
            answer_parts.append(f"Query optimization: {rewrite_info.get('reasoning', 'Unknown')}")
        
        # If there is translation or rewrite information, add an empty line
        if query_info.get("translation_applied", False) or query_info.get("rewrite_applied", False):
            answer_parts.append("")
        
        for result in results:
            chunk = result["chunk"]
            score = result["score"]
            
            # Extract key information
            topic = chunk.get("topic", "Unknown topic")
            summary = chunk.get("summary", "")
            
            answer_parts.append(f"\n【{topic}】")
            
            # Display score information (distinguish between hybrid search and single search)
            if "fusion_method" in result:
                # Hybrid search results
                fusion_method = result.get("fusion_method", "unknown")
                vector_score = result.get("vector_score", 0)
                bm25_score = result.get("bm25_score", 0)
                answer_parts.append(f"Relevance: {score:.3f}")
                if vector_score > 0 and bm25_score > 0:
                    answer_parts.append(f"(Semantic match: {vector_score:.3f} | Keyword match: {bm25_score:.3f})")
            else:
                # Single search results
                answer_parts.append(f"Relevance: {score:.3f}")
            
            answer_parts.append(f"{summary}")
            
            # If there is build information, add build suggestions
            if "build" in chunk:
                build = chunk["build"]
                if "name" in build:
                    answer_parts.append(f"\nRecommended build: {build['name']}")
                if "focus" in build:
                    answer_parts.append(f"Build focus: {build['focus']}")
                
                # Add key equipment information
                if "stratagems" in build:
                    stratagems = [s["name"] for s in build["stratagems"]]
                    answer_parts.append(f"Core equipment: {', '.join(stratagems[:3])}")
        
        return "\n".join(answer_parts)

    async def _format_answer_with_summary_stream(self, search_response: Dict[str, Any], question: str, original_query: str = None) -> AsyncGenerator[str, None]:
        """
        Use Gemini summarizer to format search results in streaming mode
        
        Args:
            search_response: Search response (contains results and metadata)
            question: Original question
            original_query: Original query
            
        Yields:
            Streaming summary content
        """
        results = search_response.get("results", [])
        
        if not results:
            yield "Sorry, I couldn't find any information. Please try asking with different keywords."
            return
            
        try:
            print(f"🌊 [RAG-STREAM-DEBUG] Starting streaming summary formatting")
            print(f"   - Number of search results: {len(results)}")
            
            # Build summary data
            chunks = []
            for result in results:
                chunk = result.get("chunk", result)
                chunks.append(chunk)
            
            # Extract game context
            game_context = None
            # Try multiple ways to get game context
            if chunks:
                first_chunk = chunks[0]
                # Way 1: Get game field directly from chunk
                if "game" in first_chunk:
                    game_context = first_chunk["game"]
                # Way 2: Get game field from video_info
                elif "video_info" in first_chunk and isinstance(first_chunk["video_info"], dict):
                    game_context = first_chunk["video_info"].get("game")
            
            # Way 3: Get game field from config or initialization parameters
            if not game_context and hasattr(self, 'config') and self.config:
                game_context = self.config.get("game_name", None)
            
            # Way 4: Use stored game_name
            if not game_context and hasattr(self, 'game_name'):
                game_context = self.game_name
            
            print(f"🎮 [RAG-STREAM-DEBUG] Game context: {game_context}")
            
            # Set game name to summarizer for video source extraction
            if game_context and hasattr(self.summarizer, 'current_game_name'):
                self.summarizer.current_game_name = game_context
            
            # Call summarizer to generate structured reply
            print(f"🚀 [RAG-STREAM-DEBUG] Calling summarizer")
            async for chunk in self.summarizer.summarize_chunks_stream(
                chunks=chunks,
                query=question,
                original_query=original_query,
                context=game_context
            ):
                print(f"📦 [RAG-STREAM-DEBUG] Received summary chunk: {len(chunk)} characters")
                yield chunk
            
            print(f"✅ [RAG-STREAM-DEBUG] Streaming summary formatting completed")
            
        except Exception as e:
            logger.error(f"Streaming summary generation failed: {e}")
            print(f"❌ [RAG-STREAM-DEBUG] Streaming summary generation failed: {e}")
            # Fall back to friendly error message
            yield "😅 Sorry, I encountered a problem while organizing information. Let me answer you in a simple way:\n\n"
            yield self._format_simple_answer(results)

    def _format_simple_answer(self, results: List[Dict[str, Any]]) -> str:
        """Simple format answer (for fallback when summary fails)"""
        if not results:
            return "No related information found."
        
        # Only take the most relevant result
        top_result = results[0]
        chunk = top_result.get("chunk", top_result)
        
        topic = chunk.get("topic", "")
        summary = chunk.get("summary", "")
        
        return f"About {topic}:\n{summary}"

    async def query_stream(self, question: str, top_k: int = 3, original_query: str = None, unified_query_result = None) -> AsyncGenerator[str, None]:
        """
        Execute streaming RAG query
        
        Args:
            question: User question
            top_k: Number of search results
            original_query: Original query
            unified_query_result: Preprocessed unified query result (from assistant_integration)
            
        Yields:
            Streaming answer content
        """
        if not self.is_initialized:
            await self.initialize()
            
        # If initialization fails, return fallback information
        if not self.is_initialized or not self.vector_store:
            print(f"❌ [RAG-STREAM-DEBUG] RAG system not initialized correctly, switch to wiki mode")
            yield "Sorry, the guide query system encountered an issue, please try again later."
            return
            
        start_time = time.time()
        
        try:
            print(f"🌊 [RAG-STREAM-DEBUG] Starting streaming RAG query: '{question}'")
            if unified_query_result:
                print(f"📝 [RAG-STREAM-DEBUG] Using preprocessed unified query result:")
                print(f"   - Original query: '{unified_query_result.original_query}'")
                print(f"   - Translated query: '{unified_query_result.translated_query}'") 
                print(f"   - Rewritten query: '{unified_query_result.rewritten_query}'")
                print(f"   - BM25 optimization: '{unified_query_result.bm25_optimized_query}'")
                print(f"   - Intent: {unified_query_result.intent} (Confidence: {unified_query_result.confidence:.3f})")
            
            if hasattr(self, 'vector_store') and self.vector_store:
                # Execute search (same logic as query method)
                if self.enable_hybrid_search and self.hybrid_retriever:
                    print(f"🔍 [RAG-STREAM-DEBUG] Using hybrid search")
                    # If there is a preprocessed result, pass it to hybrid search
                    if unified_query_result:
                        search_response = self._search_hybrid_with_processed_query(unified_query_result, top_k)
                    
                    results = search_response.get("results", [])
                    
                    # Apply intent-aware reranking
                    if self.enable_intent_reranking and self.reranker and results:
                        print(f"🔄 [RAG-STREAM-DEBUG] Applying intent-aware reranking")
                        results = self.reranker.rerank_results(
                            results, 
                            question,
                            intent_weight=self.reranking_config.get("intent_weight", 0.4),
                            semantic_weight=self.reranking_config.get("semantic_weight", 0.6)
                        )
                        search_response["results"] = results
                        # Record reranking information in metadata
                        search_response.setdefault("metadata", {})["reranking_applied"] = True
                    
                    # Format answer (using streaming summary)
                    print(f"🔍 [SUMMARY-STREAM-DEBUG] Checking streaming summary conditions:")
                    print(f"   - enable_summarization: {self.enable_summarization}")
                    print(f"   - summarizer exists: {self.summarizer is not None}")
                    print(f"   - number of results: {len(results)}")
                    
                    if self.enable_summarization and self.summarizer and len(results) > 0:
                        print(f"💬 [RAG-STREAM-DEBUG] Using Gemini streaming summary to format answer")
                        async for chunk in self._format_answer_with_summary_stream(search_response, question, original_query=original_query):
                            yield chunk
                    else:
                        print(f"💬 [RAG-STREAM-DEBUG] Using original format to format answer")
                        if not self.enable_summarization:
                            print(f"   Reason: Summary function not enabled")
                        elif not self.summarizer:
                            print(f"   Reason: Summarizer not initialized")
                        elif len(results) == 0:
                            print(f"   Reason: No search results")
                        answer = self._format_answer(search_response, question)
                        yield answer
                        
                else:
                    # Single vector search
                    print(f"🔍 [RAG-STREAM-DEBUG] Using single vector search")
                    if self.config["vector_store_type"] == "faiss":
                        results = self._search_faiss(question, top_k)
                    else:
                        results = self._search_qdrant(question, top_k)
                    
                    # Apply intent-aware reranking
                    if self.enable_intent_reranking and self.reranker and results:
                        print(f"🔄 [RAG-STREAM-DEBUG] Applying intent-aware reranking (single vector search mode)")
                        results = self.reranker.rerank_results(
                            results, 
                            question,
                            intent_weight=self.reranking_config.get("intent_weight", 0.4),
                            semantic_weight=self.reranking_config.get("semantic_weight", 0.6)
                        )
                    
                    # Build compatible search_response format
                    search_response = {
                        "results": results,
                        "query": {"original": question, "rewritten": question, "rewrite_applied": False},
                        "metadata": {
                            "total_results": len(results),
                            "search_type": "vector_only",
                            "fusion_method": "none",
                            "rewrite_info": {
                                "intent": "unknown",
                                "confidence": 0.0,
                                "reasoning": "Query rewrite not used"
                            },
                            "reranking_applied": self.enable_intent_reranking and self.reranker is not None
                        }
                    }
                    
                    # Format answer (using streaming summary)
                    print(f"🔍 [SUMMARY-STREAM-DEBUG] Checking streaming summary conditions (single vector search):")
                    print(f"   - enable_summarization: {self.enable_summarization}")
                    print(f"   - summarizer exists: {self.summarizer is not None}")
                    print(f"   - number of results: {len(results)}")
                    
                    if self.enable_summarization and self.summarizer and len(results) > 0:
                        print(f"💬 [RAG-STREAM-DEBUG] Using Gemini streaming summary to format answer")
                        async for chunk in self._format_answer_with_summary_stream(search_response, question, original_query=original_query):
                            yield chunk
                    else:
                        print(f"💬 [RAG-STREAM-DEBUG] Using original format to format answer")
                        if not self.enable_summarization:
                            print(f"   Reason: Summary function not enabled")
                        elif not self.summarizer:
                            print(f"   Reason: Summarizer not initialized")
                        elif len(results) == 0:
                            print(f"   Reason: No search results")
                        answer = self._format_answer(search_response, question)
                        yield answer
            else:
                # Vector store query failed
                print(f"❌ [RAG-STREAM-DEBUG] Vector store query failed")
                yield "Sorry, the guide query system encountered an issue, please try again later."
                
        except Exception as e:
            print(f"❌ [RAG-STREAM-DEBUG] Streaming query exception: {e}")
            logger.error(f"Streaming query error: {str(e)}")
            yield f"Sorry, an error occurred during the query, please try again later."

# Global instance
_enhanced_rag_query = None