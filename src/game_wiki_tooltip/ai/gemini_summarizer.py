"""
Gemini Flash 2.5 Lite Summarizer for RAG-retrieved knowledge chunks
"""
import os
import json
import logging
from typing import List, Dict, Optional, Any
import google.generativeai as genai
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SummarizationConfig:
    """Configuration for Gemini summarization"""
    api_key: str
    model_name: str = "gemini-2.5-flash-lite-preview-06-17"
    temperature: float = 0.3
    include_sources: bool = True
    language: str = "auto"  # auto, zh, en


class GeminiSummarizer:
    """Summarizes multiple knowledge chunks using Gemini Flash 2.5 Lite"""
    
    def __init__(self, config: SummarizationConfig):
        """Initialize Gemini summarizer with configuration"""
        self.config = config
        
        # Configure Gemini API
        genai.configure(api_key=config.api_key)
        
        # Initialize model with safety settings (no max_output_tokens limit)
        self.model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": config.temperature,
                # Let the model decide output length based on query requirements
            }
        )
        
        logger.info(f"Initialized GeminiSummarizer with model: {config.model_name}")
    
    def summarize_chunks(
        self, 
        chunks: List[Dict[str, Any]], 
        query: str,
        original_query: Optional[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Summarize multiple knowledge chunks into a coherent answer
        
        Args:
            chunks: List of retrieved chunks with content and metadata
            query: Original user query
            context: Optional game context
            
        Returns:
            Dictionary with summary and metadata
        """
        print(f"📝 [SUMMARY-DEBUG] 开始通用Gemini摘要生成")
        print(f"   - 检索查询: '{query}'")
        if original_query and original_query != query:
            print(f"   - 原始查询: '{original_query}'")
            print(f"   - 双查询模式: 启用")
        else:
            print(f"   - 双查询模式: 未启用 (原始查询与检索查询相同或未提供)")
        print(f"   - 知识块数量: {len(chunks)}")
        print(f"   - 上下文: {context or 'None'}")
        print(f"   - 模型: {self.config.model_name}")
        
        # Store game context for video source extraction
        if context:
            self.current_game_name = context
            print(f"🎮 [SUMMARY-DEBUG] Stored game name: {self.current_game_name}")
        else:
            print(f"⚠️ [SUMMARY-DEBUG] No context provided, game name not stored")
        
        if not chunks:
            print(f"⚠️ [SUMMARY-DEBUG] 没有知识块可用于摘要")
            return {
                "summary": "No relevant information found.",
                "chunks_used": 0,
                "sources": []
            }
        
        # 显示知识块信息
        print(f"📋 [SUMMARY-DEBUG] 输入知识块详情:")
        for i, chunk in enumerate(chunks, 1):
            print(f"   {i}. 主题: {chunk.get('topic', 'Unknown')}")
            print(f"      分数: {chunk.get('score', 0):.4f}")
            print(f"      类型: {chunk.get('type', 'General')}")
            print(f"      关键词: {chunk.get('keywords', [])}")
            print(f"      摘要: {chunk.get('summary', '')[:100]}...")
        
        try:
            # 检测语言
            language = self._detect_language(query) if self.config.language == "auto" else self.config.language
            print(f"🌐 [SUMMARY-DEBUG] 检测到语言: {language}")
            
            # Build the summarization prompt
            print(f"📝 [SUMMARY-DEBUG] 构建通用摘要提示词")
            prompt = self._build_summarization_prompt(chunks, query, original_query, context)
            print(f"   - 提示词长度: {len(prompt)} 字符")
            print(f"   - 温度设置: {self.config.temperature}")
            print(f"   - 无输出长度限制，由LLM自行判断")
            
            # Generate summary
            print(f"🤖 [SUMMARY-DEBUG] 调用Gemini生成摘要")
            response = self.model.generate_content(prompt)
            
            print(f"✅ [SUMMARY-DEBUG] Gemini响应成功")
            print(f"   - 响应长度: {len(response.text)} 字符")
            print(f"   - 完整响应内容:")
            print(f"{response.text}")
            print(f"   - [响应内容结束]")
            
            # Parse and format the response
            formatted_response = self._format_summary_response(response.text, chunks)
            
            print(f"📊 [SUMMARY-DEBUG] 摘要生成完成")
            print(f"   - 使用的知识块数: {formatted_response['chunks_used']}")
            print(f"   - 来源数: {len(formatted_response['sources'])}")
            print(f"   - 最终摘要长度: {len(formatted_response['summary'])} 字符")
            
            return formatted_response
            
        except Exception as e:
            print(f"❌ [SUMMARY-DEBUG] 摘要生成失败: {e}")
            logger.error(f"Error in summarization: {str(e)}")
            
            # Fallback to simple concatenation
            print(f"🔄 [SUMMARY-DEBUG] 使用降级摘要策略")
            fallback_result = self._fallback_summary(chunks, query, original_query)
            
            print(f"📊 [SUMMARY-DEBUG] 降级摘要完成")
            print(f"   - 使用的知识块数: {fallback_result['chunks_used']}")
            print(f"   - 降级摘要长度: {len(fallback_result['summary'])} 字符")
            
            return fallback_result
    
    def _build_summarization_prompt(
        self, 
        chunks: List[Dict[str, Any]], 
        query: str,
        original_query: Optional[str] = None,
        context: Optional[str] = None
    ) -> str:
        """Build the universal prompt for Gemini summarization"""
        
        # Detect language from query or use config
        language = self._detect_language(query) if self.config.language == "auto" else self.config.language
        
        # Format chunks as raw JSON for the prompt
        chunks_json = self._format_chunks_as_json(chunks)
        
        # Detect if user is asking for detailed explanations
        is_detailed_query = self._is_detailed_query(query)
        
        # Build language-specific prompt
        if language == "zh":
            detail_instruction = "详细解释选择原因和策略" if is_detailed_query else "简洁明了的回答"
            
            # 构建查询信息部分
            query_section = f"[检索查询]: {query}  ← 用于判断哪些材料段落最相关"
            if original_query and original_query != query:
                query_section += f"\n[原始查询]: {original_query}  ← 用于决定回答风格、详细程度和措辞偏好"
            else:
                query_section = f"[用户查询]: {query}"
            
            prompt = f"""你是一个专业的游戏攻略助手。基于以下JSON格式的游戏知识块，回答玩家的问题。

{query_section}
{f"游戏上下文：{context}" if context else ""}

可用的游戏知识块（JSON格式）：
{chunks_json}

回答指南：
1. **理解JSON结构**：每个知识块包含topic、summary、keywords、type、score等基础信息，以及structured_data详细数据
2. **双查询理解**：
   - 检索查询帮助你理解"召回思路"，判断哪些段落最相关
   - 原始查询帮助你决定回答的措辞、详细程度、写作风格，避免"语义漂移"
3. **根据问题类型调整回答**：
   - 配装推荐：完整列出所有装备/部件信息
   - 敌人攻略：提供弱点、血量、推荐武器等关键信息
   - 游戏策略：给出具体的操作建议和技巧
   - 物品信息：详细说明属性、获取方式、用途等
4. **回答详细程度**：{detail_instruction}
5. **利用structured_data**：优先使用结构化数据中的具体数值、名称、配置等信息

格式要求：
• 按照原始查询的措辞和细节要求组织答案
• 使用友好的游戏术语和表情符号
• 基于JSON中的实际数据，不要编造信息
• 如果信息不相关或不足，请明确说明

你的回答："""
        else:
            detail_instruction = "detailed explanations with reasons and strategies" if is_detailed_query else "concise and clear responses"
            
            # 构建查询信息部分
            query_section = f"[Retrieval Query]: {query}  ← for determining which material segments are most relevant"
            if original_query and original_query != query:
                query_section += f"\n[Original Query]: {original_query}  ← for determining response style, detail level, and wording preferences"
            else:
                query_section = f"[User Query]: {query}"
            
            prompt = f"""You are a professional game guide assistant. Based on the following JSON-formatted game knowledge chunks, answer the player's question.

{query_section}
{f"Game context: {context}" if context else ""}

Available game knowledge chunks (JSON format):
{chunks_json}

Response guidelines:
1. **Understand JSON structure**: Each chunk contains topic, summary, keywords, type, score and structured_data details
2. **Dual query understanding**:
   - Retrieval query helps you understand the "recall approach" to judge which segments are most relevant
   - Original query helps you decide response wording, detail level, and writing style to avoid "semantic drift"
3. **Adapt response based on question type**:
   - Build recommendations: List complete equipment/component information
   - Enemy guides: Provide weak points, health, recommended weapons
   - Game strategies: Give specific operation suggestions and tactics
   - Item information: Detail attributes, acquisition methods, uses
4. **Response detail level**: {detail_instruction}
5. **Utilize structured_data**: Prioritize specific values, names, configurations from structured data

Format requirements:
• Organize response according to original query's wording and detail requirements
• Use friendly gaming terminology and appropriate emojis
• Base on actual data from JSON, don't fabricate information
• If information is irrelevant or insufficient, clearly state so

Your response:"""
        
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
    
    def _is_detailed_query(self, query: str) -> bool:
        """Detect if the query is asking for detailed explanations"""
        detailed_keywords = [
            # Chinese keywords
            "为什么", "原因", "详细", "解释", "说明", "分析", "机制", "深入",
            "怎么样", "如何", "策略", "技巧", "攻略", "教程",
            # English keywords  
            "why", "reason", "detailed", "explain", "explanation", "analysis", 
            "mechanism", "how", "strategy", "tactics", "guide", "tutorial",
            "in-depth", "comprehensive"
        ]
        
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in detailed_keywords)
    
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
            
            # Collect video sources
            video_sources = {}  # URL -> {title, timestamps}
            
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
                                if video_url not in video_sources:
                                    video_sources[video_url] = {
                                        "title": video_info.get("title", "Unknown Video"),
                                        "timestamps": []
                                    }
                                
                                # Add timestamp
                                timestamp = kb_chunk.get("timestamp", {})
                                start = timestamp.get("start", "")
                                end = timestamp.get("end", "")
                                if start and end:
                                    video_sources[video_url]["timestamps"].append(f"{start}-{end}")
            
            # Format video sources
            print(f"📹 [VIDEO-DEBUG] Found {len(video_sources)} video sources")
            
            if not video_sources:
                print(f"❌ [VIDEO-DEBUG] No video sources found")
                return ""
            
            # Build the sources text
            sources_lines = ["---", "<small>", "📺 **信息来源：**"]
            
            for url, info in video_sources.items():
                title = info["title"]
                timestamps = info["timestamps"]
                
                # Sort timestamps
                timestamps = sorted(set(timestamps))  # Remove duplicates and sort
                
                # Format timestamps
                if timestamps:
                    timestamp_str = "; ".join(timestamps)
                    sources_lines.append(f"- [{title} ({timestamp_str})]({url})")
                else:
                    sources_lines.append(f"- [{title}]({url})")
            
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
    model_name: str = "gemini-2.5-flash-lite-preview-06-17",
    **kwargs
) -> GeminiSummarizer:
    """
    Create a Gemini summarizer instance
    
    Args:
        api_key: Gemini API key (defaults to env var GEMINI_API_KEY)
        model_name: Model to use
        **kwargs: Additional config parameters
        
    Returns:
        GeminiSummarizer instance
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not provided and GEMINI_API_KEY env var not set")
    
    config = SummarizationConfig(
        api_key=api_key,
        model_name=model_name,
        **kwargs
    )
    
    return GeminiSummarizer(config)