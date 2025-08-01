"""
Web history manager for tracking visited pages.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class WebHistoryManager:
    """Manages web browsing history for the application"""
    
    def __init__(self, history_file: Optional[Path] = None, max_items: int = 20):
        """
        Initialize the history manager.
        
        Args:
            history_file: Path to the history JSON file. If None, uses default location.
            max_items: Maximum number of history items to keep (default: 20)
        """
        if history_file is None:
            from .utils import APPDATA_DIR
            self.history_file = Path(APPDATA_DIR) / "web_history.json"
        else:
            self.history_file = Path(history_file)
            
        self.max_items = max_items
        self.history: List[Dict[str, str]] = []
        
        # Ensure directory exists
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing history
        self._load_history()
    
    def _load_history(self):
        """Load history from file"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.history = data
                    else:
                        # Handle old format or corrupted data
                        self.history = []
                logger.info(f"Loaded {len(self.history)} history items")
            else:
                logger.info("No existing history file found")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            self.history = []
    
    def _save_history(self):
        """Save history to file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.history)} history items")
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    def add_entry(self, url: str, title: str, source: str = "wiki"):
        """
        Add a new entry to history.
        
        Args:
            url: The URL of the page
            title: The title of the page
            source: The source type (e.g., "wiki", "web", "guide")
        """
        # Create new entry
        entry = {
            "url": url,
            "title": title,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "visit_count": 1
        }
        
        # Check if URL already exists in history
        existing_index = None
        for i, item in enumerate(self.history):
            if item.get("url") == url:
                existing_index = i
                break
        
        if existing_index is not None:
            # Update existing entry
            existing = self.history.pop(existing_index)
            entry["visit_count"] = existing.get("visit_count", 0) + 1
            # Preserve first visit time if available
            if "first_visit" not in existing:
                existing["first_visit"] = existing.get("timestamp", entry["timestamp"])
            entry["first_visit"] = existing.get("first_visit", entry["timestamp"])
        
        # Add to beginning of list
        self.history.insert(0, entry)
        
        # Trim to max items
        if len(self.history) > self.max_items:
            self.history = self.history[:self.max_items]
        
        # Save to file
        self._save_history()
        
        logger.info(f"Added history entry: {title} ({url})")
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Get history entries.
        
        Args:
            limit: Maximum number of entries to return. If None, returns all.
            
        Returns:
            List of history entries
        """
        if limit is None:
            return self.history.copy()
        else:
            return self.history[:limit].copy()
    
    def clear_history(self):
        """Clear all history"""
        self.history = []
        self._save_history()
        logger.info("History cleared")
    
    def remove_entry(self, url: str):
        """Remove a specific entry by URL"""
        self.history = [item for item in self.history if item.get("url") != url]
        self._save_history()
        logger.info(f"Removed history entry: {url}")
    
    def search_history(self, query: str) -> List[Dict[str, str]]:
        """
        Search history by title or URL.
        
        Args:
            query: Search query
            
        Returns:
            List of matching history entries
        """
        query_lower = query.lower()
        results = []
        
        for item in self.history:
            title = item.get("title", "").lower()
            url = item.get("url", "").lower()
            
            if query_lower in title or query_lower in url:
                results.append(item)
        
        return results
    
    def get_stats(self) -> Dict[str, any]:
        """Get history statistics"""
        stats = {
            "total_entries": len(self.history),
            "sources": {},
            "most_visited": []
        }
        
        # Count by source
        for item in self.history:
            source = item.get("source", "unknown")
            stats["sources"][source] = stats["sources"].get(source, 0) + 1
        
        # Find most visited (top 5)
        sorted_by_visits = sorted(
            self.history, 
            key=lambda x: x.get("visit_count", 0), 
            reverse=True
        )[:5]
        
        stats["most_visited"] = [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "visits": item.get("visit_count", 0)
            }
            for item in sorted_by_visits
        ]
        
        return stats