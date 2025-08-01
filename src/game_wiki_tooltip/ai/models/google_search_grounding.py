"""
Google Search Grounding for Gemini
==================================

Use Gemini's grounding with Google Search feature to get up-to-date information
when the knowledge base is insufficient.
"""

import os
import logging
from typing import Optional, Dict, Any, AsyncGenerator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GroundingConfig:
    """Configuration for Google Search grounding"""
    api_key: str
    model_name: str = "gemini-2.5-flash"
    temperature: float = 0.3
    language: str = "auto"  # auto, zh, en


class GoogleSearchGrounding:
    """Handle web search grounding when knowledge is insufficient"""
    
    def __init__(self, config: GroundingConfig):
        """Initialize Google Search grounding"""
        self.config = config
        logger.info(f"Initialized GoogleSearchGrounding with model: {config.model_name}")
    
    async def search_and_generate_stream(
        self,
        original_query: str,
        rewritten_query: Optional[str] = None,
        game_context: Optional[str] = None,
        language: str = "auto"
    ) -> AsyncGenerator[str, None]:
        """
        Search the web and generate a response stream
        
        Args:
            original_query: Original user query
            rewritten_query: Rewritten query for better search
            game_context: Game context
            language: Response language
            
        Yields:
            Streaming response with grounded information
        """
        try:
            from google import genai
            from google.genai import types
            
            print(f"🔍 [GROUNDING-DEBUG] Starting Google Search grounding")
            print(f"   - Original query: {original_query}")
            print(f"   - Rewritten query: {rewritten_query}")
            print(f"   - Game context: {game_context}")
            print(f"   - Language: {language}")
            
            # Configure the client
            client = genai.Client(api_key=self.config.api_key)
            
            # Define the grounding tool
            grounding_tool = types.Tool(
                google_search=types.GoogleSearch()
            )
            
            # Configure generation settings
            config = types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=self.config.temperature
            )
            
            # Build the search prompt
            if language == "zh" or (language == "auto" and self._is_chinese(original_query)):
                prompt = self._build_chinese_prompt(original_query, rewritten_query, game_context)
            else:
                prompt = self._build_english_prompt(original_query, rewritten_query, game_context)
            
            print(f"📝 [GROUNDING-DEBUG] Prompt built, calling Gemini with Google Search")
            
            # Make the streaming request
            response = client.models.generate_content_stream(
                model=self.config.model_name,
                contents=prompt,
                config=config
            )
            
            print(f"✅ [GROUNDING-DEBUG] Started receiving grounded streaming response")
            
            # Stream the response
            for chunk in response:
                if chunk.text:
                    print(f"📝 [GROUNDING-DEBUG] Received chunk: {len(chunk.text)} characters")
                    yield chunk.text
            
            print(f"🎉 [GROUNDING-DEBUG] Grounded streaming completed")
            
        except Exception as e:
            logger.error(f"Error in Google Search grounding: {e}")
            print(f"❌ [GROUNDING-DEBUG] Error: {e}")
            
            # Check if it's a rate limit error
            error_str = str(e).lower()
            if "quota" in error_str or "rate limit" in error_str or "429" in error_str:
                logger.warning("⏱️ API rate limit detected in Google Search")
                if language == "zh":
                    yield (
                        "\n\n⏱️ **API 使用限制**\n\n"
                        "您已达到 Google Gemini API 的使用限制。免费账户限制：\n"
                        "• 每分钟最多 15 次请求\n"
                        "• 每天最多 1500 次请求\n\n"
                        "请稍后再试，或考虑升级到付费账户以获得更高的配额。"
                    )
                else:
                    yield (
                        "\n\n⏱️ **API Rate Limit**\n\n"
                        "You've reached the Google Gemini API usage limit. Free tier limits:\n"
                        "• Maximum 15 requests per minute\n"
                        "• Maximum 1500 requests per day\n\n"
                        "Please try again later, or consider upgrading to a paid account for higher quotas."
                    )
            else:
                # General error message
                if language == "zh":
                    yield f"\n\n抱歉，网络搜索时出现错误：{str(e)}"
                else:
                    yield f"\n\nSorry, an error occurred during web search: {str(e)}"
    
    def _build_chinese_prompt(
        self, 
        original_query: str, 
        rewritten_query: Optional[str],
        game_context: Optional[str]
    ) -> str:
        """Build Chinese prompt for grounded search"""
        base_prompt = f"请帮我搜索并回答关于游戏的问题。\n\n用户问题：{original_query}"
        
        if rewritten_query and rewritten_query != original_query:
            base_prompt += f"\n优化后的搜索查询：{rewritten_query}"
        
        if game_context:
            base_prompt += f"\n游戏背景：{game_context}"
        
        base_prompt += """

请注意：
1. 使用网络搜索获取最新、准确的游戏信息
2. 优先搜索官方wiki、游戏论坛、攻略网站等权威来源
3. 提供具体的数值、配装、策略等实用信息
4. 如果找到多个观点，请综合并说明差异
5. 用中文回答，保持游戏术语的准确性

请搜索并提供详细的游戏攻略信息。"""
        
        return base_prompt
    
    def _build_english_prompt(
        self, 
        original_query: str, 
        rewritten_query: Optional[str],
        game_context: Optional[str]
    ) -> str:
        """Build English prompt for grounded search"""
        base_prompt = f"Please search and answer this gaming question.\n\nUser question: {original_query}"
        
        if rewritten_query and rewritten_query != original_query:
            base_prompt += f"\nOptimized search query: {rewritten_query}"
        
        if game_context:
            base_prompt += f"\nGame context: {game_context}"
        
        base_prompt += """

Please note:
1. Use web search to get the latest and accurate game information
2. Prioritize official wikis, game forums, and guide websites
3. Provide specific numbers, builds, strategies, and practical information
4. If multiple viewpoints exist, synthesize and explain differences
5. Use proper gaming terminology

Please search and provide detailed game guide information."""
        
        return base_prompt
    
    def _is_chinese(self, text: str) -> bool:
        """Check if text contains Chinese characters"""
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        return chinese_chars > len(text) * 0.3


# Convenience function
def create_google_search_grounding(
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.5-flash",
    **kwargs
) -> GoogleSearchGrounding:
    """
    Create a Google Search grounding instance
    
    Args:
        api_key: Google API key
        model_name: Model to use (gemini-2.5-flash recommended)
        **kwargs: Additional config parameters
        
    Returns:
        GoogleSearchGrounding instance
    """
    if not api_key:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Google API key not provided")
    
    config = GroundingConfig(
        api_key=api_key,
        model_name=model_name,
        **kwargs
    )
    
    return GoogleSearchGrounding(config)