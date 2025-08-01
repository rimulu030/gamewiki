"""
Gemini Flash 2.5 Lite Summarizer for RAG-retrieved knowledge chunks
"""
import os
import json
import logging
from typing import List, Dict, Optional, Any, AsyncGenerator
import google.generativeai as genai
import google.generativeai.types as types
from dataclasses import dataclass
from pathlib import Path
import re

# Import i18n for internationalization
from src.game_wiki_tooltip.core.i18n import t
from .rag_config import RAGConfig, get_default_config

logger = logging.getLogger(__name__)


@dataclass
class SummarizationConfig:
    """Configuration for Gemini summarization"""
    api_key: str
    model_name: str = "gemini-2.5-flash-lite"
    temperature: float = 0.3
    include_sources: bool = True
    language: str = "auto"  # auto, zh, en
    enable_google_search: bool = True  # Enable Google search tool


class GeminiSummarizer:
    """Summarizes multiple knowledge chunks using Gemini Flash 2.5 Lite"""
    
    def __init__(self, config: SummarizationConfig = None, rag_config: RAGConfig = None):
        """Initialize Gemini summarizer with configuration"""
        # Use RAGConfig if provided, otherwise use SummarizationConfig
        if rag_config:
            self.rag_config = rag_config
            # Extract settings from RAGConfig
            self.config = SummarizationConfig(
                api_key=rag_config.llm_settings.get_api_key(),
                model_name=rag_config.summarization.model_name,
                temperature=rag_config.summarization.temperature,
                include_sources=rag_config.summarization.include_sources,
                language=rag_config.summarization.language,
                enable_google_search=True  # Default to True
            )
        else:
            self.config = config
            self.rag_config = None
        
        # Configure Gemini API
        genai.configure(api_key=self.config.api_key)
        
        # Initialize model with safety settings (no max_output_tokens limit)
        self.model = genai.GenerativeModel(
            model_name=self.config.model_name,
            generation_config={
                "temperature": self.config.temperature,
                # Let the model decide output length based on query requirements
            }
        )
        
        logger.info(f"Initialized GeminiSummarizer with model: {self.config.model_name}")
    
    async def summarize_chunks_stream(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        original_query: Optional[str] = None,
        context: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streaming summary generation, using real Gemini streaming API
        
        Args:
            chunks: Retrieved knowledge chunks
            query: Processed query
            original_query: Original query
            context: Game context
            
        Yields:
            Streaming fragments of summary content
        """
        print(f"🌊 [STREAM-DEBUG] Start streaming summary generation")
        print(f"   - Knowledge chunk count: {len(chunks)}")
        print(f"   - Query: {query}")
        if original_query and original_query != query:
            print(f"   - Original query: {original_query}")
        print(f"   - Game context: {context}")
        
        # Store game context for video source extraction
        if context:
            self.current_game_name = context
            print(f"🎮 [STREAM-DEBUG] Stored game name: {self.current_game_name}")
        else:
            print(f"⚠️ [STREAM-DEBUG] No context provided, game name not stored")
        
        if not chunks:
            yield "Sorry, no relevant game information found."
            return
            
        try:
            print(f"🚀 [STREAM-DEBUG] Calling Gemini streaming API")
            
            # Detect language from query
            language = self._detect_language(query) if self.config.language == "auto" else self.config.language
            
            # Build system instruction
            system_instruction = self._build_system_instruction(language)
            
            # Build prompt
            prompt = self._build_summarization_prompt(chunks, query, original_query, context)
            
            # For collecting complete response text to extract video sources
            complete_response = ""
            
            # Use new Client API for streaming calls
            import google.generativeai as genai
            try:
                from google import genai as new_genai
                from google.genai import types as new_types
                NEW_GENAI_AVAILABLE = True
            except ImportError:
                NEW_GENAI_AVAILABLE = False
            
            if NEW_GENAI_AVAILABLE:
                try:
                    # Try to use new Client API (recommended way)
                    client = new_genai.Client(api_key=self.config.api_key)
                    
                    # Configure Google Search tool if enabled
                    tools = []
                    if self.config.enable_google_search:
                        print(f"🔍 [STREAM-DEBUG] Enabling Google Search tool (new API)")
                        grounding_tool = new_types.Tool(
                            google_search=new_types.GoogleSearch()
                        )
                        tools = [grounding_tool]
                    
                    # Build config with system instruction
                    config = new_types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=tools if tools else None,
                        # Allow model to generate appropriate length based on query
                        temperature=self.config.temperature
                    )
                    
                    # Stream content generation
                    response = client.models.generate_content_stream(
                        model=self.config.model_name,
                        contents=[prompt],
                        config=config
                    )
                
                    print(f"✅ [STREAM-DEBUG] Started receiving streaming response (new Client API)")
                    
                    # Real-time streaming content output
                    for chunk in response:
                        if chunk.text:
                            print(f"📝 [STREAM-DEBUG] Received streaming chunk: {len(chunk.text)} characters")
                            complete_response += chunk.text
                            yield chunk.text
                        
                    print(f"🎉 [STREAM-DEBUG] Streaming response completed (new Client API)")
                    
                except Exception as e:
                    print(f"❌ [STREAM-DEBUG] New Client API failed: {e}")
                    raise e
            else:
                # If new API is not available, fallback to old API
                print(f"⚠️ [STREAM-DEBUG] New Client API not available, trying old API method")
                
                # Configure generation parameters
                generation_config = genai.types.GenerationConfig(
                    temperature=self.config.temperature,
                    max_output_tokens=8192,
                )
                
                # Configure Google Search tool if enabled  
                tools = []
                if self.config.enable_google_search:
                    print(f"🔍 [STREAM-DEBUG] Google Search not supported in old API, using knowledge base only")
                    # Note: Old API may not support Google Search in the same way
                    tools = []
                
                # Use old GenerativeModel API
                model = genai.GenerativeModel(
                    model_name=self.config.model_name,
                    generation_config=generation_config,
                    tools=tools if tools else None
                )
                
                # Check if streaming method exists
                if hasattr(model, 'generate_content_stream'):
                    print(f"✅ [STREAM-DEBUG] Using old API streaming method")
                    response = model.generate_content_stream(prompt)
                    
                    for chunk in response:
                        if chunk.text:
                            print(f"📝 [STREAM-DEBUG] Received streaming chunk: {len(chunk.text)} characters")
                            complete_response += chunk.text
                            yield chunk.text
                    
                else:
                    print(f"❌ [STREAM-DEBUG] Old API doesn't support streaming, fallback to sync method")
                    # Complete fallback to sync method
                    response = model.generate_content(prompt)
                    if response and response.text:
                        complete_response = response.text
                        yield response.text
                        
            
            # After streaming output completes, add video source information
            print(f"🎬 [STREAM-DEBUG] Streaming output completed, starting video source extraction")
            video_sources_text = self._extract_video_sources(chunks, complete_response)
            if video_sources_text:
                print(f"✅ [STREAM-DEBUG] Found video sources, adding to streaming output")
                # Add separator to ensure proper identification
                separator = "\n\n---\n"
                yield separator + video_sources_text
            else:
                print(f"❌ [STREAM-DEBUG] No video sources found")
                    
        except Exception as e:
            print(f"❌ [STREAM-DEBUG] Streaming API call failed: {e}")
            print(f"🔄 [STREAM-DEBUG] Fallback to sync method")
            import traceback
            print(f"❌ [STREAM-DEBUG] Detailed error info: {traceback.format_exc()}")
            
            # Check if it's an API key issue
            error_msg = str(e).lower()
            if 'api_key' in error_msg or 'authentication' in error_msg or 'unauthorized' in error_msg or 'inputs argument' in error_msg:
                print(f"🔑 [STREAM-DEBUG] Detected API key related error")
                yield "❌ API key configuration issue, please check if Gemini API key is correctly configured.\n\n"
                return
    
    def _build_system_instruction(self, language: str = "auto") -> str:
        """Build system instruction for Gemini"""
        # Detect language if auto
        if language == "auto":
            language = "en"  # Default to Chinese, will be overridden by actual query language
        
        if language == "zh":
            return """你是一个专业的游戏攻略助手。你的任务是基于提供的游戏知识库内容，为玩家提供准确、有用的游戏攻略信息。

回答指南：
1. **开头必须提供一句话总结**：在正式回答之前，用一句话概括答案要点（例如："💡 **总结**：推荐使用火箭筒配合重装甲来对付这个BOSS"）
2. **理解JSON结构**：每个知识块包含topic、summary、keywords、type、score等基础信息，以及structured_data详细数据
3. **双查询理解**：
   - 检索查询帮助你理解"召回思路"，判断哪些段落最相关
   - 原始查询帮助你决定回答的措辞、详细程度、写作风格，避免"语义漂移"
4. **根据问题类型调整回答**：
   - 配装推荐：完整列出所有装备/部件信息
   - 敌人攻略：提供弱点、血量、推荐武器等关键信息
   - 游戏策略：给出具体的操作建议和技巧
   - 物品信息：详细说明属性、获取方式、用途等
5. **智能判断回答详细程度**：
   - 仔细分析[原始查询]中的表述，理解用户期望的回答长度
   - 如果用户要求"一句话"、"简短"、"简要"等，提供简洁答案
   - 如果用户询问"为什么"、"如何"、"详细解释"等，提供完整深入的回答
   - 如果没有明确要求，根据问题复杂度提供适中长度的回答
6. **利用structured_data**：优先使用结构化数据中的具体数值、名称、配置等信息

格式要求：
• 开头先给出一句话总结（用💡标记）
• 不要添加任何寒暄或开场白（如"我来帮你..."、"好的，让我..."）
• 如果提供的知识块足以回答问题，直接给出答案
• 如果使用了Google搜索工具，在开头说明："我使用了Google搜索为你找到了以下信息"
• 严格按照[原始查询]的要求组织答案
• 使用友好的游戏术语
• 基于实际数据，不要编造信息"""
        else:
            return """You are a professional game guide assistant. Your task is to provide accurate and useful game strategy information to players based on the provided game knowledge base content.

Response guidelines:
1. **Start with a one-sentence summary**: Before the detailed answer, provide a one-sentence summary of the key points (e.g., "💡 **Summary**: Recommended to use rocket launcher with heavy armor against this boss")
2. **Understand JSON structure**: Each chunk contains topic, summary, keywords, type, score and structured_data details
3. **Dual query understanding**:
   - Retrieval query helps you understand the "recall approach" to judge which segments are most relevant
   - Original query helps you decide response wording, detail level, and writing style to avoid "semantic drift"
4. **Adapt response based on question type**:
   - Build recommendations: List complete equipment/component information
   - Enemy guides: Provide weak points, health, recommended weapons
   - Game strategies: Give specific operation suggestions and tactics
   - Item information: Detail attributes, acquisition methods, uses
5. **Intelligently determine response detail level**:
   - Carefully analyze the wording in [Original Query] to understand the user's expected response length
   - If user asks for "one sentence", "brief", "short", etc., provide concise answer
   - If user asks "why", "how", "detailed explanation", etc., provide complete in-depth response
   - If no explicit requirement, provide moderate length response based on question complexity
6. **Utilize structured_data**: Prioritize specific values, names, configurations from structured data

Format requirements:
• Start with a one-sentence summary (marked with 💡)
• Don't add any greetings or introductions (like "I'm ready to help...", "Okay, let me...")
• If knowledge chunks are sufficient, directly provide the answer
• If Google Search tool was used, mention at the beginning: "I used Google search to find the following information"
• Strictly follow the [Original Query] requirements
• Use friendly gaming terminology
• Base on actual data, don't fabricate information"""
    
    def _build_summarization_prompt(
        self, 
        chunks: List[Dict[str, Any]], 
        query: str,
        original_query: Optional[str] = None,
        context: Optional[str] = None
    ) -> str:
        """Build the simplified prompt for Gemini summarization (guidelines moved to system instruction)"""
        
        # Detect language from query or use config
        language = self._detect_language(query) if self.config.language == "auto" else self.config.language
        
        # Format chunks as raw JSON for the prompt
        chunks_json = self._format_chunks_as_json(chunks)
        
        # Build language-specific prompt
        if language == "zh":
            # 构建查询信息部分
            query_section = f"[检索查询]: {query}  ← 用于判断哪些材料段落最相关"
            if original_query and original_query != query:
                query_section += f"\n[原始查询]: {original_query}  ← **关键**：必须严格按照此查询的格式要求回答"
            else:
                query_section = f"[用户查询]: {query}  ← **关键**：必须严格按照此查询的格式要求回答"
            
            prompt = f"""{query_section}
{f"游戏上下文：{context}" if context else ""}

可用的游戏知识块（JSON格式）：
{chunks_json}

请基于以上知识块回答用户的问题。"""
        else:
            # 构建查询信息部分
            query_section = f"[Retrieval Query]: {query}  ← for determining which material segments are most relevant"
            if original_query and original_query != query:
                query_section += f"\n[Original Query]: {original_query}  ← **CRITICAL**: You MUST strictly follow this query's format requirements"
            else:
                query_section = f"[User Query]: {query}  ← **CRITICAL**: You MUST strictly follow this query's format requirements"
            
            prompt = f"""{query_section}
{f"Game context: {context}" if context else ""}

Available game knowledge chunks (JSON format):
{chunks_json}

Please answer the user's question based on the above knowledge chunks."""
        
        return prompt
    
    def _format_chunks_as_json(self, chunks: List[Dict[str, Any]]) -> str:
        """Format chunks as clean JSON for the prompt"""
        formatted_chunks = []
        
        for i, chunk in enumerate(chunks, 1):
            # Create a clean chunk representation
            clean_chunk = {
                "chunk_id": i,
                "topic": chunk.get("topic", "Unknown Topic"),
                "summary": chunk.get("summary", ""),
                "keywords": chunk.get("keywords", []),
                "type": chunk.get("type", "General"),
                "relevance_score": chunk.get("score", 0),
                "structured_data": chunk.get("structured_data", {}),
                "content": chunk.get("content", "")
            }
            
            formatted_chunks.append(clean_chunk)
        
        try:
            return json.dumps(formatted_chunks, ensure_ascii=False, indent=2)
        except Exception as e:
            # Fallback to string representation if JSON serialization fails
            logger.warning(f"Failed to serialize chunks as JSON: {e}")
            return str(formatted_chunks)
    
    
    def _format_summary_response(
        self, 
        summary_text: str, 
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Format the summary response with metadata"""
        
        print(f"📦 [FORMAT-DEBUG] Formatting summary response")
        print(f"   - Has current_game_name: {hasattr(self, 'current_game_name')}")
        if hasattr(self, 'current_game_name'):
            print(f"   - current_game_name value: {self.current_game_name}")
        
        # Extract source references if present
        sources = []
        if self.config.include_sources:
            # Extract chunk indices used in summary
            for i, chunk in enumerate(chunks, 1):
                if any(keyword in summary_text for keyword in chunk.get("keywords", [])):
                    sources.append({
                        "index": i,
                        "topic": chunk.get("topic", ""),
                        "score": chunk.get("score", 0)
                    })
        
        # Add video sources to the summary
        print(f"🎬 [FORMAT-DEBUG] Extracting video sources...")
        video_sources_text = self._extract_video_sources(chunks, summary_text)
        if video_sources_text:
            print(f"✅ [FORMAT-DEBUG] Video sources found, adding to summary")
            summary_text = summary_text.strip() + "\n\n" + video_sources_text
        else:
            print(f"❌ [FORMAT-DEBUG] No video sources returned")
        
        return {
            "summary": summary_text.strip(),
            "chunks_used": len(chunks),
            "sources": sources,
            "model": self.config.model_name,
            "language": self._detect_language(summary_text)
        }
    
    def _fallback_summary(
        self, 
        chunks: List[Dict[str, Any]], 
        query: str,
        original_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fallback summary when Gemini fails"""
        # Simple concatenation of top chunks
        summary_parts = []
        
        for i, chunk in enumerate(chunks[:2], 1):  # Use top 2 chunks
            topic = chunk.get("topic", "")
            content = chunk.get("summary", chunk.get("content", ""))
            
            # Add basic info
            if topic:
                summary_parts.append(f"💡 {topic}")
            
            summary_parts.append(content)
            
            # Add key structured data if available
            structured_data = chunk.get("structured_data", {})
            if structured_data:
                # Extract some key information generically
                for key, value in list(structured_data.items())[:3]:  # Top 3 items
                    if isinstance(value, (str, int, float)):
                        summary_parts.append(f"🔧 {key}: {value}")
                    elif isinstance(value, dict) and value:
                        first_item = next(iter(value.items()))
                        summary_parts.append(f"🔧 {key}: {first_item[0]} = {first_item[1]}")
            
            summary_parts.append("")  # Add spacing between chunks
        
        summary = "\n".join(summary_parts).strip()
        
        return {
            "summary": summary,
            "chunks_used": min(2, len(chunks)),
            "sources": [{"index": i+1, "topic": c.get("topic", "")} for i, c in enumerate(chunks[:2])],
            "model": "fallback",
            "language": self._detect_language(summary)
        }
    
    def _convert_timestamp_to_seconds(self, timestamp: str) -> int:
        """Convert MM:SS or HH:MM:SS format to seconds"""
        if not timestamp:
            return 0
        
        try:
            parts = timestamp.split(':')
            if len(parts) == 2:  # MM:SS
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:  # HH:MM:SS
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            return 0
        except (ValueError, AttributeError):
            return 0
    
    def _extract_video_sources(self, chunks: List[Dict[str, Any]], summary_text: str) -> str:
        """Extract video source information from chunks"""
        try:
            # Get game name from config
            game_name = None
            if hasattr(self, 'current_game_name'):
                game_name = self.current_game_name
            
            print(f"🎥 [VIDEO-DEBUG] Starting video source extraction")
            print(f"   - Game name: {game_name}")
            print(f"   - Number of chunks: {len(chunks)}")
            
            if not game_name:
                logger.debug("No game name available for video source extraction")
                print(f"❌ [VIDEO-DEBUG] No game name available")
                return ""
            
            # Load original knowledge chunk file
            # __file__ is in src/game_wiki_tooltip/ai/, need to go up to project root
            kb_path = Path(__file__).parent.parent.parent.parent / "data" / "knowledge_chunk" / f"{game_name}.json"
            print(f"📁 [VIDEO-DEBUG] Looking for knowledge chunk file: {kb_path}")
            
            if not kb_path.exists():
                logger.debug(f"Knowledge chunk file not found: {kb_path}")
                print(f"❌ [VIDEO-DEBUG] Knowledge chunk file not found")
                return ""
            
            with open(kb_path, 'r', encoding='utf-8') as f:
                kb_data = json.load(f)
            
            # Collect video sources - now as a list of individual entries
            video_sources = []  # List of {url, topic, start_seconds}
            
            # Check which chunks were actually used in the summary
            used_chunks = []
            for chunk in chunks:
                # Check if chunk content appears in summary or has high score
                chunk_keywords = chunk.get("keywords", [])
                chunk_topic = chunk.get("topic", "")
                chunk_score = chunk.get("score", 0)
                
                # Simple heuristic: check if keywords or topic appear in summary
                keyword_match = any(keyword.lower() in summary_text.lower() for keyword in chunk_keywords)
                topic_match = chunk_topic.lower() in summary_text.lower()
                high_score = chunk_score > 0.5
                
                if keyword_match or topic_match or high_score:
                    used_chunks.append(chunk)
                    print(f"✅ [VIDEO-DEBUG] Chunk used: {chunk_topic} (score: {chunk_score:.3f})")
                    print(f"   - Keyword match: {keyword_match}, Topic match: {topic_match}, High score: {high_score}")
            
            print(f"📊 [VIDEO-DEBUG] Used chunks count: {len(used_chunks)}")
            
            # Match chunks with original data using topic matching
            for chunk in used_chunks:
                chunk_topic = chunk.get("topic", "")
                
                print(f"🔍 [VIDEO-DEBUG] Matching chunk by topic: {chunk_topic}")
                
                if not chunk_topic:
                    print(f"⚠️ [VIDEO-DEBUG] Chunk missing topic, skipping")
                    continue
                
                # Search in all videos' knowledge chunks
                for video_entry in kb_data:
                    video_info = video_entry.get("video_info", {})
                    if not video_info:
                        continue
                    
                    for kb_chunk in video_entry.get("knowledge_chunks", []):
                        # Match by topic only
                        if kb_chunk.get("topic", "").strip() == chunk_topic.strip():
                            
                            video_url = video_info.get("url", "")
                            if video_url:
                                # Get timestamp
                                timestamp = kb_chunk.get("timestamp", {})
                                start = timestamp.get("start", "")
                                
                                # Create individual video source entry
                                video_source_entry = {
                                    "url": video_url,
                                    "topic": chunk_topic,
                                    "title": video_info.get("title", "Unknown Video")
                                }
                                
                                # Convert start time to seconds for YouTube link
                                if start:
                                    start_seconds = self._convert_timestamp_to_seconds(start)
                                    video_source_entry["start_seconds"] = start_seconds
                                    print(f"   - Timestamp: {start} -> {start_seconds} seconds")
                                
                                video_sources.append(video_source_entry)
                                print(f"   - Added video source: {video_url} at {start}")
            
            # Format video sources
            print(f"📹 [VIDEO-DEBUG] Found {len(video_sources)} video sources")
            
            if not video_sources:
                print(f"❌ [VIDEO-DEBUG] No video sources found")
                return ""
            
            # Build the sources text
            sources_lines = ["---", "<small>", f"📺 **{t('video_sources_label')}**"]
            
            # Remove duplicates based on topic and URL with timestamp
            seen_entries = set()
            unique_sources = []
            
            for source in video_sources:
                # Create unique key with topic and time
                if "start_seconds" in source:
                    unique_key = f"{source['topic']}_{source['url']}_{source['start_seconds']}"
                else:
                    unique_key = f"{source['topic']}_{source['url']}"
                
                if unique_key not in seen_entries:
                    seen_entries.add(unique_key)
                    unique_sources.append(source)
            
            # Sort by topic for consistent ordering
            unique_sources.sort(key=lambda x: x.get('topic', ''))
            
            # Format each video source
            for source in unique_sources:
                topic = source.get("topic", "Video Source")
                url = source.get("url", "")
                
                # Add timestamp parameter for YouTube videos
                if "youtube.com" in url and "start_seconds" in source:
                    # Append time parameter to URL
                    time_param = f"&t={source['start_seconds']}"
                    link_url = f"{url}{time_param}"
                else:
                    link_url = url
                
                # Create markdown link with topic as text
                sources_lines.append(f"- [{topic}]({link_url})")
            
            sources_lines.append("</small>")
            
            return "\n".join(sources_lines)
            
        except Exception as e:
            logger.error(f"Error extracting video sources: {e}")
            print(f"❌ [VIDEO-DEBUG] Error extracting video sources: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character composition"""
        # Check for Chinese characters
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        
        if chinese_chars > len(text) * 0.3:  # If more than 30% Chinese
            return "zh"
        else:
            return "en"
    
    


# Convenience function for creating summarizer
def create_gemini_summarizer(
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.5-flash-lite",
    enable_google_search: bool = True,
    rag_config: Optional[RAGConfig] = None,
    **kwargs
) -> GeminiSummarizer:
    """
    Create a Gemini summarizer instance
    
    Args:
        api_key: Gemini API key (defaults to env var GEMINI_API_KEY)
        model_name: Model to use
        enable_google_search: Enable Google search tool (default: True)
        **kwargs: Additional config parameters
        
    Returns:
        GeminiSummarizer instance
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not provided and GEMINI_API_KEY env var not set")
    
    # If RAGConfig is provided, use it
    if rag_config:
        return GeminiSummarizer(rag_config=rag_config)
    
    # Otherwise, use individual parameters
    config = SummarizationConfig(
        api_key=api_key,
        model_name=model_name,
        enable_google_search=enable_google_search,
        **kwargs
    )
    
    return GeminiSummarizer(config)