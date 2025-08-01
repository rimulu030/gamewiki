"""
Simplified BM25 Indexer - Focused on efficient retrieval
=================================

Features:
1. Intelligent text preprocessing
2. Multi-language support (Chinese and English)
3. Simplified BM25 retrieval
4. Query optimization by LLM
"""

import jieba
import json
import pickle
import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from pathlib import Path

# Import translation function
from src.game_wiki_tooltip.core.i18n import t

# Try importing bm25s, a more modern and faster BM25 implementation
try:
    import bm25s
    BM25_AVAILABLE = True
    BM25_IMPORT_ERROR = None
except ImportError as e:
    BM25_AVAILABLE = False
    bm25s = None
    BM25_IMPORT_ERROR = str(e)

logger = logging.getLogger(__name__)

class BM25UnavailableError(Exception):
    """BM25 functionality unavailable error"""
    pass

class EnhancedBM25Indexer:
    """Simplified BM25 indexer, focused on efficient retrieval, query optimization by LLM"""
    
    def __init__(self, game_name: str = "helldiver2", stop_words: Optional[List[str]] = None):
        """
        Initialize simplified BM25 indexer
        
        Args:
            game_name: Game name (for enemy name standardization)
            stop_words: Stop words list
            
        Raises:
            BM25UnavailableError: When bm25s package is unavailable
        """
        self.game_name = game_name
        self.bm25 = None
        self.documents = []
        
        if not BM25_AVAILABLE:
            error_msg = t("bm25_package_unavailable", error=BM25_IMPORT_ERROR)
            error_msg += "\nPlease try the following solutions:"
            error_msg += "\n1. Install bm25s: pip install bm25s"
            error_msg += "\n2. If there are still problems, try reinstalling: pip uninstall bm25s && pip install bm25s"
            error_msg += "\n3. Ensure numpy and scipy are installed correctly: pip install numpy scipy"
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)
            
        self.stop_words = self._load_stop_words(stop_words)
        logger.info(f"BM25 indexer initialized successfully - game: {game_name}")

    def _load_stop_words(self, stop_words: Optional[List[str]] = None) -> Set[str]:
        """Load stop words, but keep important tactical terms"""
        default_stop_words = {
            # 中文停用词
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这',
            # English stop words  
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must', 'shall',
            # General game vocabulary (excluding tactical terms)
            'game', 'player', 'mission', 'level'
        }
        
        if stop_words:
            default_stop_words.update(stop_words)
            
        return default_stop_words

    def _normalize_enemy_name(self, text: str) -> str:
        """Standardize enemy name - based on current game configuration"""
        text = text.lower()

        # Standardize enemy name based on game-specific keywords
        # Here we use a generic method, no longer hard-coding specific game mappings
        # Can add alias mappings in game configuration if needed

        return text
        
    def preprocess_text(self, text: str) -> List[str]:
        """
        Simplified text preprocessing, focused on efficient tokenization
        Remove complex weighting logic, query optimization by LLM
        
        Args:
            text: Input text
            
        Returns:
            Processed token list
        """
        if not text:
            return []

        # Convert to lowercase and standardize enemy name
        text = self._normalize_enemy_name(text.lower())
        
        # Remove special characters, but keep Chinese, English, numbers, and spaces
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', text)
        
        # Check if it contains Chinese
        has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', text))
        
        # Tokenization processing
        if has_chinese:
            # Contains Chinese, use jieba tokenization
            tokens = list(jieba.cut(text))
        else:
            # Pure English, use space tokenization (more accurate)
            tokens = text.split()
        
        # Simple English stem extraction
        def simple_stem(word):
            """Simple stem extraction, handling common English变形"""
            if len(word) <= 2:
                return word
                
            # Handle plural forms
            if word.endswith('s') and len(word) > 3:
                # Special plural forms
                if word.endswith('ies') and len(word) > 4:
                    return word[:-3] + 'y'  # strategies -> strategy
                elif word.endswith('es') and len(word) > 4:
                    return word[:-2]  # boxes -> box
                else:
                    return word[:-1]  # recommendations -> recommendation
                    
            # Handle other common suffixes
            if word.endswith('ing') and len(word) > 5:
                return word[:-3]  # running -> run
            if word.endswith('ed') and len(word) > 4:
                return word[:-2]  # played -> play
            if word.endswith('ly') and len(word) > 4:
                return word[:-2]  # quickly -> quick
                
            return word
        
        # Process tokens - simplified version
        processed_tokens = []
        for token in tokens:
            token = token.strip()
            
            # Filter conditions: not empty, not a stop word, length > 1 or is a number
            if (token and 
                token not in self.stop_words and 
                (len(token) > 1 or token.isdigit())):
                
                # Apply stem extraction to English words
                if not re.search(r'[\u4e00-\u9fa5]', token):  # Not Chinese
                    stemmed = simple_stem(token)
                    processed_tokens.append(stemmed)
                    
                    # If the stem is different from the original word, also add the original word
                    if stemmed != token:
                        processed_tokens.append(token)
                else:
                    # Chinese words are processed directly
                    processed_tokens.append(token)
        
        return processed_tokens
    
    def build_enhanced_text(self, chunk: Dict[str, Any]) -> str:
        """
        Build search text, focused on content extraction
        Remove weighting logic, query optimization by LLM
        
        Args:
            chunk: Knowledge chunk
            
        Returns:
            Search text
        """
        text_parts = []
        
        # 1. Topic (important content)
        topic = chunk.get("topic", "")
        if topic:
            text_parts.append(topic)
            
        # 2. Keywords
        keywords = chunk.get("keywords", [])
        if keywords:
            text_parts.extend(keywords)
            
        # 3. Summary
        summary = chunk.get("summary", "")
        if summary:
            text_parts.append(summary)
            
        # 4. Structured data processing
        self._extract_structured_content(chunk, text_parts)
        
        return " ".join(text_parts)
    
    def _extract_structured_content(self, chunk: Dict[str, Any], text_parts: List[str]) -> None:
        """Extract structured content, focused on content rather than weight"""
        
        # Enemy weakness information
        if "structured_data" in chunk:
            structured = chunk["structured_data"]
            
            # Enemy name
            if "enemy_name" in structured:
                text_parts.append(structured["enemy_name"])
                
            # Weakness information
            if "weak_points" in structured:
                for weak_point in structured["weak_points"]:
                    if "name" in weak_point:
                        text_parts.append(weak_point["name"])
                    if "notes" in weak_point:
                        text_parts.append(weak_point["notes"])
                        
            # Recommended weapons
            if "recommended_weapons" in structured:
                for weapon in structured["recommended_weapons"]:
                    text_parts.append(weapon)
                    
        # Build information
        if "build" in chunk:
            build = chunk["build"]
            
            # Build name
            if "name" in build:
                text_parts.append(build["name"])
                
            # Tactical focus
            if "focus" in build:
                text_parts.append(build["focus"])
                
            # Strategy information
            if "stratagems" in build:
                for stratagem in build["stratagems"]:
                    if "name" in stratagem:
                        text_parts.append(stratagem["name"])
                    if "rationale" in stratagem:
                        text_parts.append(stratagem["rationale"])
    
    def build_index(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Build enhanced BM25 index
        
        Args:
            chunks: Knowledge chunk list
            
        Raises:
            BM25UnavailableError: When BM25 functionality is unavailable
        """
        if not BM25_AVAILABLE:
            raise BM25UnavailableError(t("bm25_build_failed"))
            
        logger.info(f"Start building enhanced BM25 index, {len(chunks)} knowledge chunks")
        
        self.documents = chunks
        
        # Build enhanced search text
        search_texts = []
        for i, chunk in enumerate(chunks):
            try:
                # Build enhanced text
                enhanced_text = self.build_enhanced_text(chunk)
                
                # Preprocess and weight
                tokenized = self.preprocess_text(enhanced_text)
                search_texts.append(tokenized)
                
                # Debug information
                if i < 3:  # Only print the first 3 for debugging
                    logger.info(f"Sample {i}: {chunk.get('topic', 'Unknown')}")
                    logger.info(f"Enhanced text: {enhanced_text[:200]}...")
                    logger.info(f"Token sample: {tokenized[:10]}")
                    logger.info(f"Token total: {len(tokenized)}")
                
            except Exception as e:
                logger.error(f"Error processing the {i}th knowledge chunk: {e}")
                search_texts.append([])
        
        # Create BM25 index
        try:
            self.bm25 = bm25s.BM25()
            self.bm25.index(search_texts)
            # Save original documents for later use
            self.corpus_tokens = search_texts
            logger.info("Enhanced BM25 index built successfully")
        except Exception as e:
            error_msg = t("bm25_build_error", error=str(e))
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Enhanced BM25 search
        
        Args:
            query: Query text
            top_k: Number of results to return
            
        Returns:
            Search result list
            
        Raises:
            BM25UnavailableError: When BM25 functionality is unavailable
        """
        if not BM25_AVAILABLE:
            raise BM25UnavailableError(t("bm25_search_failed"))
            
        if not self.bm25:
            raise BM25UnavailableError(t("bm25_search_not_initialized"))
            
        # Preprocess query - using the same logic as index building
        normalized_query = self._normalize_enemy_name(query.lower())
        tokenized_query = self.preprocess_text(normalized_query)
        
        if not tokenized_query:
            logger.warning("Query preprocessing resulted in an empty list")
            return []
        
        print(f"🔍 [BM25-DEBUG] Simplified BM25 search - original query: {query}")
        print(f"   📝 [BM25-DEBUG] Normalized query: {normalized_query}")
        print(f"   🔤 [BM25-DEBUG] Tokenized query: {tokenized_query}")
        print(f"   🔤 [BM25-DEBUG] Token type: {type(tokenized_query)}")
        logger.info(f"Simplified BM25 search - original query: {query}")
        logger.info(f"Normalized query: {normalized_query}")
        logger.info(f"Tokenized query: {tokenized_query}")
        logger.info(f"Token type: {type(tokenized_query)}")
        
        try:
            # Ensure tokenized_query is in the correct format
            if isinstance(tokenized_query, str):
                # If still a string, need to tokenize again
                tokenized_query = tokenized_query.split()
            elif not isinstance(tokenized_query, list):
                # If not a list, convert to list
                tokenized_query = list(tokenized_query) if hasattr(tokenized_query, '__iter__') else [str(tokenized_query)]
            
            # Use bm25s's retrieve method
            # bm25s.retrieve expects input format: List[List[str]] or List[str]
            # If it's a single query, need to wrap it in a list
            if tokenized_query and isinstance(tokenized_query[0], str):
                # For single query, wrap it in [query]
                query_batch = [tokenized_query]
            else:
                query_batch = tokenized_query
            
            print(f"   🔤 [BM25-DEBUG] query_batch: {query_batch}")
            print(f"   🔤 [BM25-DEBUG] query_batch type: {type(query_batch)}")
            logger.info(f"query_batch: {query_batch}")
            logger.info(f"query_batch type: {type(query_batch)}")
                
            results_ids, scores = self.bm25.retrieve(query_batch, k=top_k)
            # results_ids shape: (1, top_k), scores shape: (1, top_k)
            top_indices = results_ids[0]  # Get the results of the first query
            top_scores = scores[0]  # Get the score of the first query
            
            print(f"   📊 [BM25-DEBUG] Top {len(top_scores)} results scores: {top_scores}")
            print(f"   📋 [BM25-DEBUG] Top {top_k} indices: {top_indices}")
            print(f"   📋 [BM25-DEBUG] Corresponding scores: {top_scores}")
            
            results = []
            for i, idx in enumerate(top_indices):
                score = top_scores[i]  # Use sorted scores
                if score > 0:
                    chunk = self.documents[idx]
                    match_info = {
                        "topic": chunk.get("topic", ""),
                        "enemy": self._extract_enemy_from_chunk(chunk),
                        "relevance_reason": self._explain_relevance(tokenized_query, chunk, original_query=query)
                    }
                    result = {
                        "chunk": chunk,
                        "score": float(score),
                        "rank": i + 1,
                        "match_info": match_info
                    }
                    results.append(result)
                    
                    # Detailed matching debug information
                    print(f"   📋 [BM25-DEBUG] 结果 {i+1}:")
                    print(f"      - 索引: {idx}")
                    print(f"      - 分数: {score:.4f}")
                    print(f"      - 主题: {chunk.get('topic', 'Unknown')}")
                    print(f"      - 敌人: {match_info['enemy']}")
                    print(f"      - 匹配理由: {match_info['relevance_reason']}")
                    print(f"      - 摘要: {chunk.get('summary', '')[:100]}...")
                    
                    # Display keyword matching information
                    chunk_text = self.build_enhanced_text(chunk).lower()
                    matched_keywords = []
                    for token in set(tokenized_query):
                        if token in chunk_text:
                            matched_keywords.append(token)
                    if matched_keywords:
                        print(f"      - 匹配关键词: {', '.join(matched_keywords[:10])}")
            
            print(f"✅ [BM25-DEBUG] Enhanced BM25 search completed, found {len(results)} results")
            logger.info(f"Enhanced BM25 search completed, found {len(results)} results")
            return results
            
        except Exception as e:
            error_msg = t("bm25_search_execution_failed", error=str(e))
            logger.error(error_msg)
            logger.error(f"查询详情 - tokenized_query: {tokenized_query}, 类型: {type(tokenized_query)}")
            logger.error(f"查询详情 - query_batch: {query_batch if 'query_batch' in locals() else 'N/A'}")
            logger.error(f"BM25对象状态: {self.bm25 is not None}")
            logger.error(f"文档数量: {len(self.documents) if self.documents else 0}")
            raise BM25UnavailableError(error_msg)
    
    def _extract_enemy_from_chunk(self, chunk: Dict[str, Any]) -> str:
        """从chunk中提取敌人/目标名称"""
        # 检查结构化数据
        if "structured_data" in chunk and "enemy_name" in chunk["structured_data"]:
            return chunk["structured_data"]["enemy_name"]
            
        # 简单提取：从topic中查找可能的敌人名称
        topic = chunk.get("topic", "")
        
        # 基本的敌人/目标识别关键词
        target_indicators = ["enemy", "boss", "敌人", "首领", "怪物", "对手"]
        if any(indicator in topic.lower() for indicator in target_indicators):
            # 提取topic中的主要词汇作为目标名称
            words = topic.split()
            if len(words) >= 2:
                # 取前两个词作为目标名称
                return " ".join(words[:2])
        
        # 如果没有明确的敌人标识，返回通用标识
        return "Target"
    
    def _explain_relevance(self, query_tokens: List[str], chunk: Dict[str, Any], original_query: str = None) -> str:
        """Explain matching relevance, focusing on lexical matching rather than weight"""
        chunk_text = self.build_enhanced_text(chunk).lower()
        
        matched_terms = []
        original_terms = []
        
        # If there is an original query, analyze the matching situation of the original query words
        if original_query:
            original_tokens = original_query.lower().split()
            for token in original_tokens:
                # Check the matching of the original word and the stemmed form
                if token in chunk_text:
                    original_terms.append(token)
                else:
                    # Check stemmed matching
                    # Simple stem extraction logic (consistent with preprocess_text)
                    if token.endswith('s') and len(token) > 3:
                        stemmed = token[:-1]
                        if stemmed in chunk_text:
                            original_terms.append(f"{token}->{stemmed}")
        
        # Analyze the matching of processed tokens
        for token in set(query_tokens):  # Remove duplicates
            if token in chunk_text:
                matched_terms.append(token)
        
        # Build matching explanation
        if original_terms and matched_terms:
            return f"Matching: {', '.join(original_terms[:3])} | Processed: {', '.join(matched_terms[:3])}"
        elif matched_terms:
            return f"Matching: {', '.join(matched_terms[:5])}"
        elif original_terms:
            return f"Matching: {', '.join(original_terms[:5])}"
        else:
            return "No obvious matching"
    
    def save_index(self, path: str) -> None:
        """
        Save simplified BM25 index
        
        Raises:
            BM25UnavailableError: When BM25 functionality is unavailable
        """
        if not BM25_AVAILABLE:
            raise BM25UnavailableError(t("bm25_save_not_available"))
            
        try:
            # Use bm25s's save method
            path_obj = Path(path)
            bm25_dir = path_obj.parent / f"{path_obj.stem}_bm25s"
            
            # Save BM25 index
            self.bm25.save(str(bm25_dir))
            
            # Save additional data (documents and stop words)
            additional_data = {
                'documents': self.documents,
                'stop_words': list(self.stop_words),
                'corpus_tokens': getattr(self, 'corpus_tokens', [])
            }
            
            with open(path, 'wb') as f:
                pickle.dump(additional_data, f)
            
            logger.info(f"Simplified BM25 index saved to: {path} (BM25 data: {bm25_dir})")
            
        except Exception as e:
            error_msg = t("bm25_save_failed", error=str(e))
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)
    
    def load_index(self, path: str) -> None:
        """
        Load simplified BM25 index
        
        Raises:
            BM25UnavailableError: When BM25 functionality is unavailable
        """
        if not BM25_AVAILABLE:
            error_msg = t("bm25_package_unavailable", error=BM25_IMPORT_ERROR)
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)
            
        try:
            # Load additional data
            with open(path, 'rb') as f:
                data = pickle.load(f)
                
            self.documents = data['documents']
            self.stop_words = set(data.get('stop_words', []))
            self.corpus_tokens = data.get('corpus_tokens', [])
            
            # Load BM25 index
            path_obj = Path(path)
            bm25_dir = path_obj.parent / f"{path_obj.stem}_bm25s"
            
            if bm25_dir.exists():
                self.bm25 = bm25s.BM25.load(str(bm25_dir))
            else:
                # If the bm25s directory does not exist, try to rebuild the index
                logger.warning(f"BM25 index directory does not exist: {bm25_dir}, trying to rebuild the index")
                if self.corpus_tokens:
                    self.bm25 = bm25s.BM25()
                    self.bm25.index(self.corpus_tokens)
                else:
                    raise FileNotFoundError(t("bm25_index_missing", path=str(bm25_dir)))
            
            logger.info(f"Simplified BM25 index loaded: {path}")
            
        except Exception as e:
            error_msg = t("bm25_load_failed", error=str(e))
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get enhanced index statistics
        
        Raises:
            BM25UnavailableError: When BM25 functionality is unavailable
        """
        if not BM25_AVAILABLE:
            raise BM25UnavailableError(t("bm25_stats_failed"))
            
        if not self.bm25:
            return {"status": "Not initialized", "error": "BM25 index not built"}
        
        # Analyze enemy distribution
        enemy_distribution = {}
        for chunk in self.documents:
            enemy = self._extract_enemy_from_chunk(chunk)
            enemy_distribution[enemy] = enemy_distribution.get(enemy, 0) + 1
        
        # Calculate average document length (fix corpus_size access error)
        try:
            # bm25s's corpus is a list of document token lists
            if hasattr(self.bm25, 'corpus') and self.bm25.corpus:
                avg_doc_length = sum(len(doc) for doc in self.bm25.corpus) / len(self.bm25.corpus)
            elif hasattr(self.bm25, 'corpus_size') and isinstance(self.bm25.corpus_size, int):
                # If corpus_size is an integer, it means the number of documents
                avg_doc_length = float(self.bm25.corpus_size)
            else:
                avg_doc_length = 0.0
        except Exception as e:
            logger.warning(f"Failed to calculate average document length: {e}")
            avg_doc_length = 0.0
        
        return {
            "status": "已初始化",
            "document_count": len(self.documents),
            "stop_words_count": len(self.stop_words),
            "enemy_distribution": enemy_distribution,
            "average_document_length": avg_doc_length,
            "top_enemies": list(sorted(enemy_distribution.items(), key=lambda x: x[1], reverse=True)[:5])
        }