"""
Unified Query Processor - Complete Multiple Tasks in One LLM Call
===================================================

Combine query translation, rewriting, and intent analysis into a single LLM call to improve response speed
"""

import json
import hashlib
import time
import logging
from typing import Dict, Any, Optional, Literal
from dataclasses import dataclass

from .rag_config import LLMSettings
from .rag_config import RAGConfig, get_default_config

logger = logging.getLogger(__name__)

@dataclass
class UnifiedQueryResult:
    """Unified query processing result"""
    original_query: str
    detected_language: str
    translated_query: str
    rewritten_query: str
    bm25_optimized_query: str  # New: query specifically optimized for BM25
    intent: str
    confidence: float
    search_type: str
    reasoning: str
    translation_applied: bool
    rewrite_applied: bool
    processing_time: float

class UnifiedQueryProcessor:
    """Unified query processor - complete translation+rewrite+intent analysis in one LLM call"""
    
    def __init__(self, llm_config: Optional[LLMSettings] = None, rag_config: Optional[RAGConfig] = None):
        # Use RAGConfig if provided, otherwise fall back to LLMConfig
        if rag_config:
            self.llm_config = rag_config.llm_settings
            self.rag_config = rag_config
        else:
            self.llm_config = llm_config or LLMSettings()
            self.rag_config = None
        self.llm_client = None
        
        # Cache mechanism
        self.query_cache = {}
        
        # Statistics
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "successful_processing": 0,
            "failed_processing": 0,
            "average_processing_time": 0.0
        }
        
        # Initialize LLM client
        if self.llm_config.is_valid():
            self._initialize_llm_client()
        else:
            logger.warning("LLM configuration invalid, will use basic processing mode")
    
    def _initialize_llm_client(self):
        """Initialize LLM client"""
        try:
            if "gemini" in self.llm_config.model.lower():
                self._initialize_gemini_client()
            elif "gpt" in self.llm_config.model.lower():
                self._initialize_openai_client()
            else:
                logger.error(f"Unsupported model type: {self.llm_config.model}")
                return
                
            logger.info(f"Unified query processor initialized successfully, model: {self.llm_config.model}")
        except Exception as e:
            logger.error(f"LLM client initialization failed: {e}")
            
    def _initialize_gemini_client(self):
        """Initialize Gemini client"""
        try:
            import google.generativeai as genai
            
            api_key = self.llm_config.get_api_key()
            if not api_key:
                raise ValueError("Gemini API key not found")
                
            genai.configure(api_key=api_key)
            
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=self.llm_config.max_tokens,
                temperature=self.llm_config.temperature,
            )
            
            self.llm_client = genai.GenerativeModel(
                model_name=self.llm_config.model,
                generation_config=generation_config,
            )
            
        except Exception as e:
            logger.error(f"Gemini client initialization failed: {e}")
            raise
    
    def _initialize_openai_client(self):
        """Initialize OpenAI client"""
        try:
            import openai
            
            api_key = self.llm_config.get_api_key()
            if not api_key:
                raise ValueError("OpenAI API key not found")
                
            self.llm_client = openai.OpenAI(
                api_key=api_key,
                base_url=self.llm_config.base_url if self.llm_config.base_url else None,
                timeout=self.llm_config.timeout
            )
            
        except Exception as e:
            logger.error(f"OpenAI client initialization failed: {e}")
            raise
    
    def _generate_cache_key(self, query: str) -> str:
        """Generate cache key"""
        return hashlib.md5(f"{query}_{self.llm_config.model}".encode()).hexdigest()
    
    def _get_cached_result(self, query: str) -> Optional[UnifiedQueryResult]:
        """Get cached result"""
        if not self.llm_config.enable_cache:
            return None
            
        cache_key = self._generate_cache_key(query)
        if cache_key in self.query_cache:
            cached_data, timestamp = self.query_cache[cache_key]
            if time.time() - timestamp < self.llm_config.cache_ttl:
                self.stats["cache_hits"] += 1
                return cached_data
            else:
                del self.query_cache[cache_key]
        return None
    
    def _cache_result(self, query: str, result: UnifiedQueryResult):
        """Cache result"""
        if not self.llm_config.enable_cache:
            return
            
        cache_key = self._generate_cache_key(query)
        self.query_cache[cache_key] = (result, time.time())
    
    def _create_unified_prompt(self, query: str) -> str:
        """Create unified processing prompt"""
        prompt = f"""You are an AI assistant that processes search queries for a universal game wiki and guide system.

Your task is to analyze the user's query and perform the following tasks in ONE response:
1. **Language Detection**: Detect the language of the query
2. **Translation**: If the query is in Chinese, translate it to English
3. **Intent Classification**: Classify the intent (wiki/guide/unknown)
4. **Query Rewriting**: Optimize the query for semantic search
5. **BM25 Optimization**: Create a specialized query for keyword-based BM25 search

Original Query: "{query}"

Please provide a JSON response with the following structure:
{{
    "detected_language": "zh|en|other",
    "translated_query": "English translation if needed, otherwise same as original",
    "intent": "wiki|guide|unknown",
    "confidence": 0.0-1.0,
    "rewritten_query": "optimized query for semantic search",
    "bm25_optimized_query": "specialized query for BM25 keyword search",
    "reasoning": "explanation of your analysis and optimizations",
    "search_type": "semantic|keyword|hybrid"
}}

**Analysis Guidelines:**

**Language Detection:**
- If >30% characters are Chinese (\\u4e00-\\u9fff), mark as "zh"
- Otherwise mark as "en" or "other"

**Intent Classification:**
- **wiki**: User wants factual information, definitions, stats, or specific item/character/enemy data
  - Single words or short phrases that look like game-specific terms should be classified as wiki
  - **Game-specific term indicators:**
    - Proper nouns (capitalized words like "Excalibur", "Gandalf", "Dragonbone")
    - Uncommon word combinations that sound like item/character names (e.g. Democratic detonation)
    - Single technical-sounding words without common modifiers
    - Foreign or fantasy-sounding terms
    - Compound words that suggest game items (e.g., "Bloodstone", "Frostbolt", "Ironhelm")
  - Examples: "wizard", "sword stats", "Excalibur", "什么是法师", "角色属性", "Bloodstone", "铁剑", "法师塔"
  - Keywords: "what is", "info", "stats", "damage", "是什么", "信息", "数据", "属性"
  - **Rule**: If the query is 1-2 words and doesn't contain guide keywords, classify as wiki

- **guide**: User wants strategies, recommendations, progression advice, or how-to instructions
  - Examples: "how to beat boss", "best build", "progression guide", "选择什么职业", "longsword build"
  - Keywords: "how", "best", "recommend", "next", "after", "should", "build", "guide", "strategy", "tips", "怎么", "推荐", "下一个", "选择", "配置", "攻略", "策略"
  - **Strategy-related terms**: "build", "setup", "loadout", "combo", "synergy", "meta", "tier", "rotation", "counter", "optimal", "efficient", "playstyle", "progression", "priority", "comparison", "vs", "choice", "unlock", "配置", "搭配", "组合", "连击", "克制", "最优", "高效", "玩法", "进阶", "优先级", "比较", "解锁", "协同"
  - **Build-related queries**: Any query containing strategy-related terms should be classified as guide
  - Special attention: Queries about "what's next", "what to unlock after X", "progression order" are GUIDE queries
  - **Rule**: Classify as guide if the query asks for advice, strategy, how-to information, OR contains build/setup-related terms

**Query Rewriting (for semantic search):**
- DO NOT add any specific game names or prefixes unless they exist in the original query
- For general terms, keep them general (e.g., "法师" -> "mage" or "wizard", not "GameName mage")
- For strategy queries, add keywords like "strategy", "guide"
- For recommendation queries, add "best", "recommendation"
- Keep original game-specific terms unchanged only if they appear in the query
- Preserve the original meaning and scope of the query

**BM25 Query Optimization (CRITICAL - for keyword search):**
This is a specialized query designed to enhance important game terms while preserving the original query intent.

**Key Principles:**
1. **Preserve original query structure**: Keep the user's original words and intent
2. **Enhance game-specific nouns**: Repeat weapon names, character names, item names, location names
3. **Boost core topic words**: Repeat important concepts like "build", "weapon", "character", "strategy"
4. **Maintain query coherence**: Don't add unrelated terms that might match wrong content
5. **Weight through repetition**: Use repetition to increase BM25 term frequency scores

**Examples:**
- "best warbond" -> "best warbond warbond warbond recommendations"
- "wizard build guide" -> "wizard wizard build build loadout guide"  
- "sword recommendations" -> "sword sword weapon recommendations guide"
- "法师推荐装备" -> "法师 法师 推荐 装备 装备 配置"

**Rules for BM25 optimization:**
- Keep ALL original query terms
- Identify game-specific proper nouns and repeat them 2-3 times
- Identify core topic words (build, weapon, character, boss, etc.) and repeat them 1-2 times
- Add closely related game terms only if they enhance the topic (e.g., "build" -> add "loadout")
- For build queries, add: "loadout", "setup", "configuration" 
- For weapon queries, add: "gear", "equipment"
- For character queries, add: "class", "hero"
- NEVER replace words - only enhance through repetition and related terms
- Maintain readability and avoid excessive repetition (max 3 times per term)

**Search Type:**
- "semantic": For conceptual queries requiring understanding (recommendations, strategies)
- "keyword": For specific item/character lookups
- "hybrid": When both approaches would be beneficial

**Important Notes:**
- Queries asking for recommendations or "what's next" are ALWAYS guide intents
- Queries about progression order or unlock priorities are ALWAYS guide intents
- Only classify as "wiki" when user explicitly wants factual data/definitions
- DO NOT assume any specific game context unless explicitly mentioned in the query
- Keep translations and rewrites GENERIC and GAME-AGNOSTIC
- BM25 optimization should focus on KEYWORDS and SPECIFIC TERMS, not generic descriptors
"""
        
        return prompt
    
    def _call_llm_with_retry(self, prompt: str) -> Optional[Dict]:
        """LLM call with retry"""
        for attempt in range(self.llm_config.max_retries):
            try:
                if "gemini" in self.llm_config.model.lower():
                    response = self.llm_client.generate_content(prompt)
                    response_text = response.text.strip()
                elif "gpt" in self.llm_config.model.lower():
                    response = self.llm_client.chat.completions.create(
                        model=self.llm_config.model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=self.llm_config.max_tokens,
                        temperature=self.llm_config.temperature
                    )
                    response_text = response.choices[0].message.content.strip()
                else:
                    return None
                
                # Parse JSON response
                if response_text.startswith('```json'):
                    response_text = response_text[7:-3]
                elif response_text.startswith('```'):
                    response_text = response_text[3:-3]
                
                return json.loads(response_text)
                
            except Exception as e:
                logger.warning(f"Unified processing LLM call failed (attempt {attempt + 1}/{self.llm_config.max_retries}): {e}")
                if attempt < self.llm_config.max_retries - 1:
                    time.sleep(self.llm_config.retry_delay * (2 ** attempt))
                
        return None
    
    def _basic_processing(self, query: str) -> UnifiedQueryResult:
        """Basic processing mode (fallback when LLM is unavailable)"""
        # Simple language detection
        chinese_chars = sum(1 for char in query if '\u4e00' <= char <= '\u9fff')
        detected_language = "zh" if chinese_chars / len(query) > 0.3 else "en"
        
        # Basic intent classification
        intent = "guide"
        confidence = 0.6
        
        # Check if it's a wiki query asking for definitions
        wiki_patterns = ["what is", "什么是", "是什么", "info", "stats", "数据", "属性"]
        if any(pattern in query.lower() for pattern in wiki_patterns):
            intent = "wiki"
            confidence = 0.8
        # Check if it's a guide query
        elif any(word in query.lower() for word in ["how", "如何", "怎么", "best", "recommend", "推荐", "next", "下一个", "选择", "该"]):
            intent = "guide"
            confidence = 0.8
        # Special handling for "什么" cases
        elif "什么" in query:
            # If it's recommendation queries like "该xxx什么" or "选什么"
            if any(pattern in query for pattern in ["该", "选", "下一个", "推荐"]):
                intent = "guide"
                confidence = 0.7
            else:
                intent = "wiki"
                confidence = 0.6
        
        # Basic rewriting - keep generic, not specific to any game
        rewritten_query = query
        
        # Generic recommendation query processing
        if any(word in query.lower() for word in ["推荐", "选择", "recommend", "choice", "next", "下一个"]):
            # Check if it's a recommendation query
            if not any(word in rewritten_query.lower() for word in ["guide", "recommendation", "攻略"]):
                rewritten_query += " guide recommendation"
            intent = "guide"
            confidence = 0.8
        
        # Generic strategy query processing
        elif any(word in query.lower() for word in ["怎么", "如何", "how to", "strategy", "攻略"]):
            if not any(word in rewritten_query.lower() for word in ["guide", "strategy", "攻略"]):
                rewritten_query += " strategy guide"
            intent = "guide"
            confidence = 0.8
        
        # Basic BM25 optimization: remove generic words, keep core words
        bm25_optimized_query = self._basic_bm25_optimization(query)
        
        return UnifiedQueryResult(
            original_query=query,
            detected_language=detected_language,
            translated_query=query,  # No translation in basic mode
            rewritten_query=rewritten_query,
            bm25_optimized_query=bm25_optimized_query,  # BM25 optimization in basic mode
            intent=intent,
            confidence=confidence,
            search_type="hybrid",
            reasoning="Basic processing mode - LLM unavailable",
            translation_applied=False,
            rewrite_applied=rewritten_query != query,
            processing_time=0.001
        )
    
    def _basic_bm25_optimization(self, query: str) -> str:
        """Basic BM25 optimization (simple version when LLM is unavailable) - using weight enhancement"""
        
        words = query.lower().split()
        optimized_words = []
        
        # Game-specific noun indicators (possible game terms)
        game_terms = [
            # Common game terms
            'build', 'weapon', 'character', 'boss', 'enemy', 'skill', 'spell', 'item', 'gear',
            'armor', 'shield', 'sword', 'bow', 'staff', 'magic', 'fire', 'ice', 'poison',
            # Helldivers 2 related
            'warbond', 'stratagem', 'helldiver', 'terminid', 'automaton', 'bile', 'charger',
            # Chinese game terms
            '配装', '武器', '角色', '技能', '装备', '护甲', '法术', '魔法', '敌人', '首领'
        ]
        
        # Topic words (core concepts)
        topic_words = [
            'build', 'weapon', 'character', 'boss', 'strategy', 'guide', 'tip',
            '配装', '武器', '角色', '策略', '攻略', '技巧'
        ]
        
        # Generic words (reduce weight but don't delete)
        generic_words = [
            'best', 'good', 'great', 'top', 'recommendation', 'guide', 'tutorial', 'help',
            '最好', '最佳', '推荐', '攻略', '教程', '帮助'
        ]
        
        for word in words:
            # Keep original words
            optimized_words.append(word)
            
            # If it's a game-specific noun, repeat 2-3 times to enhance weight
            if word in game_terms:
                optimized_words.extend([word] * 2)  # Additional 2 repetitions
                
            # If it's a topic word, repeat once to enhance weight
            elif word in topic_words:
                optimized_words.append(word)  # Additional 1 repetition
                
            # Generic words remain unchanged, neither enhanced nor deleted
        
        # Add related terms based on query type
        query_lower = query.lower()
        
        # If it's a build-related query, add related terms
        if any(term in query_lower for term in ['build', 'setup', 'loadout', '配装', '搭配']):
            optimized_words.extend(['loadout', 'setup', 'configuration'])
            
        # If it's a weapon-related query, add related terms  
        elif any(term in query_lower for term in ['weapon', 'sword', 'gun', '武器', '剑', '枪']):
            optimized_words.extend(['gear', 'equipment'])
            
        # If it's a character-related query, add related terms
        elif any(term in query_lower for term in ['character', 'class', 'hero', '角色', '职业', '英雄']):
            optimized_words.extend(['class', 'hero'])
        
        # Clean up extra spaces and return
        optimized = " ".join(optimized_words)
        return optimized if optimized.strip() else query
    
    def process_query(self, query: str) -> UnifiedQueryResult:
        """
        Unified query processing: translation + rewriting + intent analysis
        
        Args:
            query: Original query
            
        Returns:
            UnifiedQueryResult: Unified processing result
        """
        print(f"🔄 [QUERY-DEBUG] Starting unified query processing: '{query}'")
        
        start_time = time.time()
        self.stats["total_queries"] += 1
        
        # Check cache
        cached_result = self._get_cached_result(query)
        if cached_result:
            print(f"💾 [QUERY-DEBUG] Using cached result")
            print(f"   - Original query: '{cached_result.original_query}'")
            print(f"   - Translation result: '{cached_result.translated_query}'")
            print(f"   - Rewrite result: '{cached_result.rewritten_query}'")
            print(f"   - BM25 optimization: '{cached_result.bm25_optimized_query}'")
            print(f"   - Intent: {cached_result.intent} (confidence: {cached_result.confidence:.3f})")
            logger.info(f"Using cached result: {query}")
            return cached_result
        
        # If LLM is unavailable, use basic processing
        if not self.llm_client:
            print(f"⚠️ [QUERY-DEBUG] LLM unavailable, using basic processing")
            result = self._basic_processing(query)
            print(f"   - Detected language: {result.detected_language}")
            print(f"   - Intent: {result.intent} (confidence: {result.confidence:.3f})")
            print(f"   - Rewritten query: '{result.rewritten_query}'")
            print(f"   - BM25 optimization: '{result.bm25_optimized_query}'")
            print(f"   - Rewrite applied: {result.rewrite_applied}")
            self._cache_result(query, result)
            return result
        
        try:
            # Use LLM for unified processing
            print(f"🤖 [QUERY-DEBUG] Calling LLM for unified processing")
            prompt = self._create_unified_prompt(query)
            print(f"   - Using model: {self.llm_config.model}")
            print(f"   - Prompt length: {len(prompt)} characters")
            
            llm_response = self._call_llm_with_retry(prompt)
            
            if llm_response:
                # Parse LLM response
                detected_language = llm_response.get("detected_language", "en")
                translated_query = llm_response.get("translated_query", query)
                rewritten_query = llm_response.get("rewritten_query", translated_query)
                
                processing_time = time.time() - start_time
                
                print(f"✅ [QUERY-DEBUG] LLM processing successful:")
                print(f"   - Detected language: {detected_language}")
                print(f"   - Translation result: '{translated_query}'")
                print(f"   - Rewrite result: '{rewritten_query}'")
                print(f"   - BM25 optimization: '{llm_response.get('bm25_optimized_query', rewritten_query)}'")
                print(f"   - Intent: {llm_response.get('intent', 'guide')} (confidence: {llm_response.get('confidence', 0.7):.3f})")
                print(f"   - Search type: {llm_response.get('search_type', 'hybrid')}")
                print(f"   - Processing time: {processing_time:.3f} seconds")
                print(f"   - Reasoning: {llm_response.get('reasoning', 'LLM unified processing')}")
                
                result = UnifiedQueryResult(
                    original_query=query,
                    detected_language=detected_language,
                    translated_query=translated_query,
                    rewritten_query=rewritten_query,
                    bm25_optimized_query=llm_response.get("bm25_optimized_query", rewritten_query), # LLM processing not optimized
                    intent=llm_response.get("intent", "guide"),
                    confidence=llm_response.get("confidence", 0.7),
                    search_type=llm_response.get("search_type", "hybrid"),
                    reasoning=llm_response.get("reasoning", "LLM unified processing"),
                    translation_applied=translated_query != query,
                    rewrite_applied=rewritten_query != translated_query,
                    processing_time=processing_time
                )
                
                self.stats["successful_processing"] += 1
                logger.info(f"Unified processing successful: '{query}' -> translation: '{translated_query}' -> rewrite: '{rewritten_query}'")
                
            else:
                # LLM call failed, use basic processing
                print(f"❌ [QUERY-DEBUG] LLM call failed, using basic processing")
                result = self._basic_processing(query)
                print(f"   - Detected language: {result.detected_language}")
                print(f"   - Intent: {result.intent} (confidence: {result.confidence:.3f})")
                print(f"   - Rewritten query: '{result.rewritten_query}'")
                print(f"   - BM25 optimization: '{result.bm25_optimized_query}'")
                print(f"   - Rewrite applied: {result.rewrite_applied}")
                self.stats["failed_processing"] += 1
                logger.warning(f"LLM unified processing failed, using basic processing: {query}")
                
        except Exception as e:
            print(f"❌ [QUERY-DEBUG] Unified processing exception: {e}")
            logger.error(f"Unified processing exception: {e}")
            result = self._basic_processing(query)
            print(f"   - Fallback to basic processing")
            print(f"   - Detected language: {result.detected_language}")
            print(f"   - Intent: {result.intent} (confidence: {result.confidence:.3f})")
            print(f"   - Rewritten query: '{result.rewritten_query}'")
            print(f"   - BM25 optimization: '{result.bm25_optimized_query}'")
            self.stats["failed_processing"] += 1
        
        # Update average processing time
        self.stats["average_processing_time"] = (
            (self.stats["average_processing_time"] * (self.stats["total_queries"] - 1) + 
             result.processing_time) / self.stats["total_queries"]
        )
        
        print(f"📊 [QUERY-DEBUG] Query processing completed, caching result")
        print(f"   - Total queries: {self.stats['total_queries']}")
        print(f"   - Cache hits: {self.stats['cache_hits']}")
        print(f"   - Successful processing: {self.stats['successful_processing']}")
        print(f"   - Failed processing: {self.stats['failed_processing']}")
        
        # Cache result
        self._cache_result(query, result)
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "successful_processing": 0,
            "failed_processing": 0,
            "average_processing_time": 0.0
        }

# Global instance
_unified_processor = None

def get_unified_processor(llm_config: Optional[LLMSettings] = None, rag_config: Optional[RAGConfig] = None) -> UnifiedQueryProcessor:
    """Get singleton instance of unified query processor"""
    global _unified_processor
    if _unified_processor is None:
        _unified_processor = UnifiedQueryProcessor(llm_config=llm_config, rag_config=rag_config)
    return _unified_processor

def process_query_unified(query: str, llm_config: Optional[LLMSettings] = None, rag_config: Optional[RAGConfig] = None) -> UnifiedQueryResult:
    """
    Convenience function for unified query processing
    
    Args:
        query: User query
        llm_config: LLM configuration (deprecated, use rag_config)
        rag_config: RAG configuration with LLM settings
        
    Returns:
        UnifiedQueryResult: Processing result
    """
    processor = get_unified_processor(llm_config, rag_config)
    return processor.process_query(query) 