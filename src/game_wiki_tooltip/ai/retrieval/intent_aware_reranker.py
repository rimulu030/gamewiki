"""
Intent-Aware Reranker
=====================

Solves the problem where semantic similarity does not match user intent.
By analyzing the user's query intent, it reorders the retrieval results
to ensure that the content most relevant to the user's needs appears at the top.

Main features:
1. Intent type recognition (recommendation, explanation, strategy, comparison, etc.)
2. Intent-based result re-ranking
3. Combined scoring of semantic similarity and intent matching
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Query intent types"""
    RECOMMENDATION = "recommendation"  # Recommendation: selection, next, which is better
    EXPLANATION = "explanation"        # Explanation: what is, how to use
    STRATEGY = "strategy"              # Strategy: how to beat, how to clear
    COMPARISON = "comparison"          # Comparison: which is better, difference
    LOCATION = "location"              # Location: where, how to get to
    BUILD = "build"                    # Build: build recommendation, equipment combination
    UNLOCK = "unlock"                  # Unlock: how to unlock, unlock conditions
    GENERAL = "general"                # General query


@dataclass
class IntentPattern:
    """Intent recognition patterns"""
    intent: QueryIntent
    keywords: List[str]  # Keyword list
    patterns: List[str]  # Regular expression pattern
    weight: float = 1.0  # Intent weight


class IntentAwareReranker:
    """Intent-aware reranker"""
    
    def __init__(self):
        """Initialize reranker"""
        self.intent_patterns = self._initialize_intent_patterns()
        self.chunk_type_mapping = self._initialize_chunk_type_mapping()
        
    def _initialize_intent_patterns(self) -> List[IntentPattern]:
        """Initialize intent recognition patterns"""
        return [
            # Recommendation intent
            IntentPattern(
                intent=QueryIntent.RECOMMENDATION,
                keywords=["推荐", "选择", "选哪个", "下一个", "下个", "应该", "最好", "最强", "recommend", "choice", "next", "should", "best", "which"],
                patterns=[
                    r"(推荐|建议).*(选择|选哪个)",
                    r"下[一个]?.*选",
                    r"(解锁|买)了.*下[一个]?",
                    r"which.*next",
                    r"what.*after",
                    r"recommend.*after"
                ],
                weight=1.5
            ),
            
            # Explanation intent
            IntentPattern(
                intent=QueryIntent.EXPLANATION,
                keywords=["是什么", "什么是", "介绍", "explain", "what is", "introduction"],
                patterns=[
                    r".*是什么",
                    r"什么是.*",
                    r"介绍一下.*",
                    r"what\s+is\s+",
                    r"explain\s+"
                ],
                weight=1.2
            ),
            
            # Strategy intent
            IntentPattern(
                intent=QueryIntent.STRATEGY,
                keywords=["怎么打", "如何击败", "攻略", "打法", "strategy", "how to beat", "defeat"],
                patterns=[
                    r"(怎么|如何).*(打|击败|通关)",
                    r".*攻略",
                    r"how\s+to\s+(beat|defeat)",
                    r"strategy\s+for"
                ],
                weight=1.3
            ),
            
            # Comparison intent
            IntentPattern(
                intent=QueryIntent.COMPARISON,
                keywords=["哪个好", "哪个更", "对比", "比较", "区别", "which better", "compare", "difference", "vs"],
                patterns=[
                    r"哪个.*(好|强|优)",
                    r".*对比|比较",
                    r".*区别",
                    r"which.*better",
                    r".*vs\.*",
                    r"compare\s+"
                ],
                weight=1.4
            ),
            
            # Build intent
            IntentPattern(
                intent=QueryIntent.BUILD,
                keywords=["配装", "装备", "搭配", "build", "loadout", "equipment"],
                patterns=[
                    r".*配装",
                    r"装备.*搭配",
                    r".*build",
                    r"loadout\s+for"
                ],
                weight=1.3
            ),
            
            # Unlock intent
            IntentPattern(
                intent=QueryIntent.UNLOCK,
                keywords=["解锁", "获得", "获取", "unlock", "obtain", "get"],
                patterns=[
                    r"(如何|怎么).*(解锁|获得)",
                    r".*解锁条件",
                    r"how\s+to\s+(unlock|get|obtain)",
                    r"unlock\s+requirements?"
                ],
                weight=1.2
            )
        ]
    
    def _initialize_chunk_type_mapping(self) -> Dict[QueryIntent, List[str]]:
        """Initialize mapping between chunk types and intents"""
        return {
            QueryIntent.RECOMMENDATION: [
                "recommendation", "warbond recommendation", "build recommendation", 
                "weapon recommendation", "priority", "tier list", "best choice"
            ],
            QueryIntent.EXPLANATION: [
                "explanation", "introduction", "overview", "basic info", 
                "what is", "description", "guide introduction"
            ],
            QueryIntent.STRATEGY: [
                "strategy", "tactics", "boss guide", "enemy guide", 
                "how to beat", "walkthrough", "tips"
            ],
            QueryIntent.COMPARISON: [
                "comparison", "versus", "difference", "pros and cons",
                "which is better", "analysis"
            ],
            QueryIntent.BUILD: [
                "build guide", "loadout", "equipment setup", "gear recommendation",
                "build recommendation", "optimal build"
            ],
            QueryIntent.UNLOCK: [
                "unlock guide", "how to unlock", "requirements", "prerequisites",
                "unlock conditions", "acquisition"
            ]
        }
    
    def identify_query_intent(self, query: str) -> Tuple[QueryIntent, float]:
        """
        Identify query intent
        
        Args:
            query: User query
            
        Returns:
            (Intent type, confidence)
        """
        print(f"🎯 [INTENT-DEBUG] Start intent recognition: query='{query}'")
        
        query_lower = query.lower()
        intent_scores = {}
        
        print(f"   📊 [INTENT-DEBUG] Intent pattern matching results:")
        for pattern in self.intent_patterns:
            score = 0.0
            matches = []
            
            # Keyword matching
            keyword_matches = sum(1 for keyword in pattern.keywords if keyword in query_lower)
            if keyword_matches > 0:
                keyword_score = keyword_matches * 0.3 * pattern.weight
                score += keyword_score
                matches.append(f"Keyword matching: {keyword_matches} keywords, score: {keyword_score:.3f}")
            
            # Regular pattern matching
            for regex_pattern in pattern.patterns:
                if re.search(regex_pattern, query_lower, re.IGNORECASE):
                    regex_score = 0.5 * pattern.weight
                    score += regex_score
                    matches.append(f"Regular pattern matching: '{regex_pattern}', score: {regex_score:.3f}")
                    break
            
            if score > 0:
                intent_scores[pattern.intent] = score
                print(f"      {pattern.intent.value}: Total score={score:.3f}")
                for match in matches:
                    print(f"         - {match}")
        
        # If no intent is matched, return general intent
        if not intent_scores:
            print(f"   ⚠️ [INTENT-DEBUG] No intent matched, returning general intent")
            return QueryIntent.GENERAL, 0.5
        
        # Return the intent with the highest score
        best_intent = max(intent_scores.items(), key=lambda x: x[1])
        
        # Normalize confidence to 0-1
        confidence = min(best_intent[1] / 2.0, 1.0)
        
        print(f"   🏆 [INTENT-DEBUG] Best intent: {best_intent[0].value}")
        print(f"      - Original score: {best_intent[1]:.3f}")
        print(f"      - Confidence: {confidence:.3f}")
        
        # Display other candidate intents
        sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_intents) > 1:
            print(f"   📋 [INTENT-DEBUG] Other candidate intents:")
            for i, (intent, score) in enumerate(sorted_intents[1:3], 2):
                print(f"      {i}. {intent.value}: {score:.3f}")
        
        logger.info(f"Intent recognition: {query} -> {best_intent[0].value} (confidence: {confidence:.2f})")
        return best_intent[0], confidence
    
    def _calculate_intent_relevance(self, chunk: Dict[str, Any], intent: QueryIntent) -> float:
        """
        Calculate the relevance of a chunk to a query intent
        
        Args:
            chunk: Chunk
            intent: Query intent
            
        Returns:
            Intent relevance score (0-1)
        """
        # Get the topic and content of the chunk
        topic = chunk.get("topic", "").lower()
        summary = chunk.get("summary", "").lower()
        keywords = [kw.lower() for kw in chunk.get("keywords", [])]
        
        # Get the chunk types relevant to the intent
        relevant_types = self.chunk_type_mapping.get(intent, [])
        
        score = 0.0
        
        # Check if the topic contains relevant type keywords
        for chunk_type in relevant_types:
            if chunk_type in topic:
                score += 0.5
                break
        
        # Check keyword matching
        for chunk_type in relevant_types:
            type_words = chunk_type.split()
            matching_words = sum(1 for word in type_words if any(word in kw for kw in keywords))
            if matching_words > 0:
                score += 0.3 * (matching_words / len(type_words))
        
        # Special rules: additional judgment based on intent type
        if intent == QueryIntent.RECOMMENDATION:
            # Recommendation intent prioritizes content containing "recommendation", "priority", "tier", etc.
            recommendation_keywords = ["recommendation", "推荐", "priority", "优先", "tier", "best", "top"]
            if any(kw in topic or kw in summary for kw in recommendation_keywords):
                score += 0.4
                
        elif intent == QueryIntent.EXPLANATION:
            # Explanation intent prioritizes content containing "explained", "introduction", etc.
            explanation_keywords = ["explained", "解释", "introduction", "介绍", "what is", "overview"]
            if any(kw in topic or kw in summary for kw in explanation_keywords):
                score += 0.3
                
        elif intent == QueryIntent.STRATEGY:
            # Strategy intent prioritizes content containing specific tactics
            strategy_keywords = ["guide", "攻略", "strategy", "tactics", "tips", "weak point"]
            if any(kw in topic or kw in summary for kw in strategy_keywords):
                score += 0.3
        
        return min(score, 1.0)
    
    def rerank_results(
        self, 
        results: List[Dict[str, Any]], 
        query: str,
        intent_weight: float = 0.4,
        semantic_weight: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Rerank search results based on intent
        
        Args:
            results: Original search results
            query: User query
            intent_weight: Intent matching weight
            semantic_weight: Semantic similarity weight
            
        Returns:
            Reranked results
        """
        print(f"🔄 [RERANK-DEBUG] Start intent reranking: query='{query}', result count={len(results)}")
        
        if not results:
            print(f"⚠️ [RERANK-DEBUG] No results to rerank")
            return results
        
        # Identify query intent
        intent, intent_confidence = self.identify_query_intent(query)
        print(f"🎯 [RERANK-DEBUG] Identify query intent: {intent.value}, confidence: {intent_confidence:.3f}")
        
        # Dynamic weight adjustment: higher intent confidence means higher intent weight
        adjusted_intent_weight = intent_weight * (0.5 + intent_confidence * 0.5)
        adjusted_semantic_weight = 1.0 - adjusted_intent_weight
        
        print(f"⚖️ [RERANK-DEBUG] Weight adjustment:")
        print(f"   - Original intent weight: {intent_weight:.3f}")
        print(f"   - Adjusted intent weight: {adjusted_intent_weight:.3f}")
        print(f"   - Semantic weight: {adjusted_semantic_weight:.3f}")
        
        # Calculate the combined score for each result
        scored_results = []
        print(f"📊 [RERANK-DEBUG] Calculate the combined score for each result:")
        
        for i, result in enumerate(results):
            # Get the original semantic similarity score
            semantic_score = result.get("score", 0.0)
            
            # Add detailed score source debugging
            print(f"   🔍 [RERANK-DEBUG] Result {i+1} score source analysis:")
            print(f"      Main score field: {semantic_score:.4f}")
            if "fusion_score" in result:
                print(f"      fusion_score field: {result['fusion_score']:.4f}")
            if "vector_score" in result:
                print(f"      vector_score field: {result['vector_score']:.4f}")
            if "bm25_score" in result:
                print(f"      bm25_score field: {result['bm25_score']:.4f}")
            if "original_vector_score" in result:
                print(f"      original_vector_score field: {result['original_vector_score']:.4f}")
            if "original_bm25_score" in result:
                print(f"      original_bm25_score field: {result['original_bm25_score']:.4f}")
            
            # Verify the reasonableness of the scores
            if semantic_score > 20.0:
                print(f"      ⚠️ [RERANK-DEBUG] Detected abnormal high score, possibly due to incorrect source")
                # If there is a fusion_score, use it as the semantic score
                if "fusion_score" in result:
                    semantic_score = result["fusion_score"]
                    print(f"      🔧 [RERANK-DEBUG] Use fusion_score as semantic score: {semantic_score:.4f}")
                elif "vector_score" in result and result["vector_score"] > 0:
                    semantic_score = result["vector_score"]
                    print(f"      🔧 [RERANK-DEBUG] Use vector_score as semantic score: {semantic_score:.4f}")
            
            # Calculate intent relevance score
            chunk = result.get("chunk", result)
            intent_score = self._calculate_intent_relevance(chunk, intent)
            
            # Calculate combined score
            combined_score = (
                semantic_score * adjusted_semantic_weight +
                intent_score * adjusted_intent_weight
            )
            
            # Create a new result object, preserving original information
            reranked_result = result.copy()
            reranked_result["original_score"] = semantic_score
            reranked_result["intent_score"] = intent_score
            reranked_result["combined_score"] = combined_score
            reranked_result["detected_intent"] = intent.value
            reranked_result["intent_confidence"] = intent_confidence
            
            scored_results.append(reranked_result)
            
            # Debug information
            print(f"   {i+1}. Topic: {chunk.get('topic', 'Unknown')}")
            print(f"      - Original score: {semantic_score:.4f}")
            print(f"      - Intent score: {intent_score:.4f}")
            print(f"      - Combined score: {combined_score:.4f}")
            print(f"      - Calculation: {semantic_score:.4f} × {adjusted_semantic_weight:.3f} + {intent_score:.4f} × {adjusted_intent_weight:.3f} = {combined_score:.4f}")
        
        # Sort by combined score
        scored_results.sort(key=lambda x: x["combined_score"], reverse=True)
        
        print(f"📈 [RERANK-DEBUG] Reranked results:")
        for i, result in enumerate(scored_results):
            chunk = result.get("chunk", result)
            print(f"   {i+1}. Topic: {chunk.get('topic', 'Unknown')}")
            print(f"      - Final score: {result['combined_score']:.4f}")
            print(f"      - Rank change: {result.get('rank', 'N/A')} -> {i+1}")
        
        # Update score field to combined_score
        for result in scored_results:
            result["score"] = result["combined_score"]
        
        print(f"✅ [RERANK-DEBUG] Reranking completed")
        logger.info(f"Reranking completed - Intent: {intent.value}, Confidence: {intent_confidence:.2f}")
        logger.info(f"Weight adjustment - Intent weight: {adjusted_intent_weight:.2f}, Semantic weight: {adjusted_semantic_weight:.2f}")
        
        # Record the score changes of the first 3 results
        for i, result in enumerate(scored_results[:3]):
            chunk = result.get("chunk", result)
            logger.info(
                f"  #{i+1} {chunk.get('topic', 'Unknown')}: "
                f"Semantic={result['original_score']:.3f}, "
                f"Intent={result['intent_score']:.3f}, "
                f"Combined={result['combined_score']:.3f}"
            )
        
        return scored_results


# Convenience function
def rerank_by_intent(
    results: List[Dict[str, Any]], 
    query: str,
    intent_weight: float = 0.4
) -> List[Dict[str, Any]]:
    """
    Convenience function: rerank results based on intent
    
    Args:
        results: Search results
        query: User query
        intent_weight: Intent weight (0-1)
        
    Returns:
        Reranked results
    """
    reranker = IntentAwareReranker()
    return reranker.rerank_results(results, query, intent_weight=intent_weight)