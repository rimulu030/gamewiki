"""
Batch Embedding Processor - Integrates Jina API and Vector Store
===========================================

Features:
1. Read knowledge_chunks JSON file
2. Batch call Jina API for embeddings
3. Store to FAISS/Qdrant vector store
4. Optimize storage and retrieval performance
"""

import os
import json
import requests
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from tqdm import tqdm
import logging
import sys

# 尝试加载.env文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 如果没有dotenv，就跳过
from dotenv import load_dotenv
load_dotenv()

# 向量库支持
try:
    import qdrant_client
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logging.warning("qdrant-client not installed, will use FAISS as fallback")

# 延迟导入faiss - 只在需要时导入以避免启动时崩溃
FAISS_AVAILABLE = None

def _check_faiss_available():
    """Check and lazily import faiss"""
    global FAISS_AVAILABLE
    if FAISS_AVAILABLE is None:
        try:
            import faiss
            FAISS_AVAILABLE = True
        except ImportError:
            FAISS_AVAILABLE = False
            logging.warning("faiss-cpu not installed, vector store functionality unavailable")
    return FAISS_AVAILABLE

logger = logging.getLogger(__name__)

def get_resource_path(relative_path: str) -> Path:
    """
    Get the absolute path of a resource file, compatible with both development and PyInstaller environments
    
    Args:
        relative_path: Path relative to the project root or temp directory
        
    Returns:
        Absolute path to the resource file
    """
    try:
        # PyInstaller temp directory after packaging
        base_path = Path(sys._MEIPASS)
        resource_path = base_path / relative_path
    except AttributeError:
        # Development environment: find project root upwards from current file
        current_file = Path(__file__).parent  # .../ai/
        base_path = current_file  # For files under ai directory, use current dir
        # If relative_path starts with "ai/", remove this prefix
        if relative_path.startswith("ai/"):
            relative_path = relative_path[3:]  # Remove "ai/" prefix
        resource_path = base_path / relative_path
    
    return resource_path

# 导入翻译函数
from src.game_wiki_tooltip.core.i18n import t

# Import Gemini embedding client
try:
    from .gemini_embedding import GeminiEmbeddingClient
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Gemini embedding client not available")

class BatchEmbeddingProcessor:
    """Batch Embedding Processor"""
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 model: str = "gemini-embedding-001",
                 output_dim: int = 768,
                 vector_store_type: str = "faiss"):
        """
        Initialize the batch embedding processor
        
        Args:
            api_key: Google API key, if None will get from environment variable
            model: Embedding model to use (default: gemini-embedding-001)
            output_dim: Output vector dimension
            vector_store_type: Vector store type ("faiss" or "qdrant")
        """
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable or parameter is required")
        
        if not GEMINI_AVAILABLE:
            raise ImportError("Gemini embedding client not available")
            
        self.model = model
        self.output_dim = output_dim
        self.vector_store_type = vector_store_type.lower()
        
        # Initialize Gemini client
        self.embedding_client = GeminiEmbeddingClient(api_key=self.api_key, model=model, output_dim=output_dim)
        
        # Validate vector store support
        if self.vector_store_type == "qdrant" and not QDRANT_AVAILABLE:
            logger.warning("Qdrant not available, switching to FAISS")
            self.vector_store_type = "faiss"
            
        if not _check_faiss_available():
            raise ImportError("faiss-cpu or qdrant-client must be installed")
    
    def build_text(self, chunk: Dict[str, Any]) -> str:
        """
        Build text for embedding
        
        Args:
            chunk: knowledge_chunk dictionary
            
        Returns:
            Formatted text string
        """
        text_parts = [
            f"Topic: {chunk.get('topic', 'Unknown')}",
            chunk.get('summary', ''),
            f"Keywords: {', '.join(chunk.get('keywords', []))}"
        ]
            
        return "\n".join(text_parts)
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Batch call Gemini API for embeddings
        
        Args:
            texts: List of text
            
        Returns:
            List of embedding vectors
        """
        # Use Gemini embeddings with RETRIEVAL_DOCUMENT task type for knowledge base
        return self.embedding_client.embed_documents(texts)
    
    def process_json_file(self, 
                         json_path: str, 
                         output_dir: str = "vectorstore",
                         batch_size: int = 64,
                         collection_name: str = "gamefloaty") -> str:
        """
        Process JSON file and build vector store
        
        Args:
            json_path: Path to JSON file
            output_dir: Output directory
            batch_size: Batch size
            collection_name: Collection name
            
        Returns:
            Vector store path
        """
        # Read JSON file
        logger.info(f"Reading JSON file: {json_path}")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract knowledge_chunks
        if isinstance(data, list):
            chunks = []
            for item in data:
                if isinstance(item, dict):
                    if "knowledge_chunks" in item:
                        # Object directly containing knowledge_chunks
                        chunks.extend(item["knowledge_chunks"])
                    elif "videos" in item:
                        # Object containing videos array, skip (these are video lists, not knowledge chunks)
                        continue
            if not chunks:
                # If no knowledge_chunks found, maybe it's a direct chunks array
                chunks = data
        elif isinstance(data, dict) and "knowledge_chunks" in data:
            chunks = data["knowledge_chunks"]
        else:
            raise ValueError("Incorrect JSON file format, must contain knowledge_chunks array")
        
        logger.info(f"Found {len(chunks)} knowledge chunks")
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        if self.vector_store_type == "qdrant":
            return self._build_qdrant_index(chunks, output_path, batch_size, collection_name)
        else:
            return self._build_faiss_index(chunks, output_path, batch_size, collection_name)
    
    def _build_qdrant_index(self, 
                           chunks: List[Dict], 
                           output_path: Path,
                           batch_size: int,
                           collection_name: str) -> str:
        """Build Qdrant index"""
        # Initialize Qdrant client
        client = qdrant_client.QdrantClient(":memory:")  # In-memory mode, use file path in production
        client.recreate_collection(
            collection_name, 
            vector_size=self.output_dim, 
            distance="Cosine"
        )
        
        # Batch processing
        for i in tqdm(range(0, len(chunks), batch_size), desc="Building Qdrant index"):
            batch = chunks[i:i + batch_size]
            texts = [self.build_text(c) for c in batch]
            vectors = self.embed_batch(texts)
            
            # Upload to Qdrant
            client.upload_collection(
                collection_name=collection_name,
                vectors=vectors,
                payload=batch,  # Original JSON as payload
                ids=[c.get("chunk_id", f"chunk_{i+j}") for j, c in enumerate(batch)]
            )
        
        # Save config
        config = {
            "vector_store_type": "qdrant",
            "collection_name": collection_name,
            "model": self.model,
            "output_dim": self.output_dim,
            "chunk_count": len(chunks)
        }
        
        config_path = output_path / f"{collection_name}_config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Qdrant index built, config saved to: {config_path}")
        return str(config_path)
    
    def _build_faiss_index(self, 
                          chunks: List[Dict], 
                          output_path: Path,
                          batch_size: int,
                          collection_name: str) -> str:
        """Build FAISS index and BM25 index"""
        all_vectors = []
        all_metadatas = []
        
        # Batch processing
        for i in tqdm(range(0, len(chunks), batch_size), desc="Building FAISS index"):
            batch = chunks[i:i + batch_size]
            texts = [self.build_text(c) for c in batch]
            vectors = self.embed_batch(texts)
            
            all_vectors.extend(vectors)
            all_metadatas.extend(batch)
        
        # Convert to numpy array
        vectors_array = np.array(all_vectors, dtype=np.float32)
        
        # Add debug info
        logger.info(f"vectors_array.shape={vectors_array.shape}, self.output_dim={self.output_dim}")
        
        # Check vector dimension
        if vectors_array.shape[1] != self.output_dim:
            logger.error(f"Vector dimension mismatch: actual={vectors_array.shape[1]}, expected={self.output_dim}")
            raise ValueError(f"Vector dimension mismatch: actual={vectors_array.shape[1]}, expected={self.output_dim}")
        
        # Create FAISS index
        index_path = output_path / collection_name
        index_path.mkdir(exist_ok=True)
        
        # Create and save FAISS index
        try:
            import faiss
        except ImportError:
            raise ImportError("Cannot import faiss library, please ensure faiss-cpu is installed")
        
        index = faiss.IndexFlatIP(vectors_array.shape[1])  # Use actual dimension
        index.add(vectors_array)
        faiss.write_index(index, str(index_path / "index.faiss"))
        
        # Save metadata
        metadata_path = index_path / "metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(all_metadatas, f, ensure_ascii=False, indent=2)
        
        # Build enhanced BM25 index
        logger.info("Building enhanced BM25 index...")
        try:
            from .enhanced_bm25_indexer import EnhancedBM25Indexer, BM25UnavailableError
            
            # Extract game name from collection_name
            game_name = collection_name.replace("_vectors", "") if "_vectors" in collection_name else collection_name
            
            enhanced_bm25_indexer = EnhancedBM25Indexer(game_name=game_name)
            enhanced_bm25_indexer.build_index(chunks)
            
            # Save enhanced BM25 index
            bm25_path = index_path / "enhanced_bm25_index.pkl"
            enhanced_bm25_indexer.save_index(str(bm25_path))
            
            logger.info(f"Enhanced BM25 index built (game: {game_name}), saved to: {bm25_path}")
            bm25_path_str = f"{collection_name}/enhanced_bm25_index.pkl"
            
        except BM25UnavailableError as e:
            error_msg = t("bm25_index_build_failed", error=str(e))
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = t("enhanced_bm25_index_build_failed", error=str(e))
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # Save config - fix: use relative path instead of absolute path
        config = {
            "vector_store_type": "faiss",
            "collection_name": collection_name,
            "game_name": game_name,  # Add game name
            "model": self.model,
            "output_dim": self.output_dim,
            "chunk_count": len(chunks),
            "index_path": collection_name,  # Use relative path, not absolute
            "bm25_index_path": bm25_path_str,  # Use relative path
            "hybrid_search_enabled": True  # BM25 index built successfully
        }
        
        config_path = output_path / f"{collection_name}_config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"FAISS index built, saved to: {index_path}")
        return str(config_path)
    
    def load_vector_store(self, config_path: str):
        """
        Load vector store
        
        Args:
            config_path: Path to config file
            
        Returns:
            Vector store instance
        """
        # Save config file path for other methods to use
        self._config_file_path = config_path
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if config["vector_store_type"] == "qdrant":
            return self._load_qdrant_store(config)
        else:
            return self._load_faiss_store(config)
    
    def _load_qdrant_store(self, config: Dict) -> Any:
        """Load Qdrant store"""
        if not QDRANT_AVAILABLE:
            raise ImportError("qdrant-client not installed")
        
        client = qdrant_client.QdrantClient(":memory:")
        return client
    
    def _load_faiss_store(self, config: Dict) -> Any:
        """Load FAISS store"""
        if not _check_faiss_available():
            raise ImportError("faiss-cpu not installed")
        
        # Get directory of config file
        if hasattr(self, '_config_file_path') and self._config_file_path:
            config_dir = Path(self._config_file_path).parent
            index_path = config_dir / Path(config["index_path"]).name
        else:
            # If no config file path, use resource path function
            index_path_str = config["index_path"]
            if not Path(index_path_str).is_absolute():
                # Use resource path function to build absolute path
                vectorstore_dir = get_resource_path("ai/vectorstore")
                index_path = vectorstore_dir / Path(index_path_str).name
            else:
                index_path = Path(index_path_str)
        
        metadata_path = index_path / "metadata.json"
        
        logger.info(f"Attempting to load FAISS store, index path: {index_path}")
        logger.info(f"Metadata path: {metadata_path}")
        
        if not metadata_path.exists():
            logger.error(f"Metadata file not found: {metadata_path}")
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        return {
            "index_path": str(index_path),
            "metadata": metadata,
            "config": config
        }


def process_game_knowledge(game_name: str, 
                          knowledge_dir: str = "data/knowledge_chunk",
                          output_dir: str = "src/game_wiki_tooltip/ai/vectorstore") -> str:
    """
    Process the knowledge base for the specified game
    
    Args:
        game_name: Game name (e.g. "helldiver2")
        knowledge_dir: Knowledge base directory
        output_dir: Output directory
        
    Returns:
        Vector store config path
    """
    json_path = Path(knowledge_dir) / f"{game_name}.json"
    
    if not json_path.exists():
        raise FileNotFoundError(f"Knowledge base file not found: {json_path}")
    
    processor = BatchEmbeddingProcessor()
    return processor.process_json_file(
        str(json_path),
        output_dir=output_dir,
        collection_name=f"{game_name}_vectors"
    )


if __name__ == "__main__":
    # Example usage
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Process Helldivers 2 knowledge base
    try:
        config_path = process_game_knowledge("helldiver2")
        print(f"Vector store built: {config_path}")
    except Exception as e:
        print(f"Processing failed: {e}") 