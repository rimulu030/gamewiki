# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GameWikiTooltip is a Windows desktop application that provides an intelligent in-game wiki overlay with AI-powered game assistance. It uses global hotkeys to display game-specific information and answers questions using RAG (Retrieval-Augmented Generation) technology.

## Essential Commands

### Development Setup
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Run as module (recommended)
python -m game_wiki_tooltip

# Alternative: direct execution
python src/game_wiki_tooltip/app.py
```

### Building the Application
```bash
# Build standalone Windows executable
pyinstaller game_wiki_tooltip.spec
# Output: dist/app.exe
```

### AI/Vector Database Commands
```bash
# Build vector index for a specific game
python src/game_wiki_tooltip/ai/build_vector_index.py --game helldiver2

# Build for all evaluate_report
python src/game_wiki_tooltip/ai/build_vector_index.py --game all

# List available evaluate_report
python src/game_wiki_tooltip/ai/build_vector_index.py --list-evaluate_report
```

## Architecture Overview

### Core Components
- **app.py**: Main application entry point, manages window lifecycle and system integration
- **overlay.py**: WebView-based overlay window that displays wiki content
- **hotkey.py**: Windows API integration for global hotkey detection (Win32 API)
- **config.py**: Configuration management, including API keys and user settings
- **tray_icon.py**: System tray integration for background operation

### AI System Architecture
The AI subsystem uses a sophisticated multi-stage pipeline:

1. **Query Processing Flow**:
   - `game_aware_query_processor.py`: Detects language, intent, and optimizes queries
   - `hybrid_retriever.py`: Combines FAISS vector search with BM25 for optimal retrieval
   - `intent_aware_reranker.py`: Re-ranks results based on detected intent
   - `gemini_summarizer.py`: Generates final responses using Google's Gemini

2. **Vector Storage**:
   - FAISS indexes stored in `ai/vectorstore/{game}_vectors/`
   - Metadata and configurations in corresponding JSON files
   - Support for both local FAISS and cloud Qdrant backends

3. **Knowledge Management**:
   - Game knowledge stored in `data/knowledge_chunk/{game}.json`
   - Batch embedding via Jina AI API for vector generation
   - Automatic chunking and metadata extraction

### Key Technical Considerations

1. **Windows-Specific Implementation**:
   - Uses `pywin32` for Windows API access
   - Global hotkeys require proper Windows message pump handling
   - Administrator privileges may be needed for some features

2. **Asynchronous Operations**:
   - AI queries run asynchronously to prevent UI blocking
   - WebView runs in separate thread for smooth overlay rendering

3. **Configuration Storage**:
   - User settings in `%APPDATA%/game_wiki_tooltip/settings.json`
   - API keys stored securely in configuration
   - Game-specific settings in `assets/games.json`

4. **AI Model Configuration**:
   - Supports multiple LLM providers (Gemini, OpenAI)
   - Configurable embedding models (Jina, text-embedding-3-small)
   - Temperature and other parameters adjustable per query type

## Important Development Notes

1. **Testing AI Features**:
   - Ensure JINA_API_KEY is set for embedding generation
   - Google Cloud credentials needed for Gemini integration
   - Test with small knowledge chunks first to verify pipeline

2. **Adding New Games**:
   - Add game configuration to `assets/games.json`
   - Create knowledge chunk JSON in `data/knowledge_chunk/`
   - Build vector index using the build script
   - Update supported games list in README

3. **Debugging Tips**:
   - Check `%APPDATA%/game_wiki_tooltip/` for logs
   - Use `--verbose` flag with AI scripts for detailed output
   - WebView console accessible via F12 in overlay window

4. **Performance Considerations**:
   - Vector searches are memory-intensive; monitor RAM usage
   - Batch process embeddings to avoid API rate limits
   - Cache frequently accessed game data in memory

5. **Security Notes**:
   - Never commit API keys to repository
   - Use environment variables or secure config for credentials
   - Validate all user input before processing AI queries

# 热键响应性能优化

## 问题描述

之前的热键响应流程存在明显的性能问题：

1. 热键触发后，系统先初始化RAG引擎（耗时1.5秒）
2. RAG初始化完成后，才显示聊天窗口
3. 用户感觉响应很慢，体验不佳

## 优化方案

改为"先显示窗口，后台初始化"的流程：

### 优化前的流程
```
热键触发 → 检测游戏窗口 → 初始化RAG引擎(1.5秒) → 显示聊天窗口
```

### 优化后的流程
```
热键触发 → 检测游戏窗口 → 立即显示聊天窗口 → 后台异步初始化RAG引擎
```

## 具体修改

### 1. 修改热键处理流程 (`qt_app.py`)
```python
# 优化流程：先快速显示窗口，再异步初始化RAG引擎
# 1. 先记录游戏窗口但不立即初始化RAG
self.assistant_ctrl.current_game_window = game_window_title

# 2. 立即显示聊天窗口（无需等待RAG初始化）
self.assistant_ctrl.expand_to_chat()

# 3. 窗口显示后，异步初始化RAG引擎
QTimer.singleShot(100, lambda: self.assistant_ctrl.set_current_game_window(game_window_title))
```

### 2. 修改RAG初始化方法 (`assistant_integration.py`)
```python
def _reinitialize_rag_for_game(self, vector_game_name: str):
    """重新初始化RAG引擎为特定向量库（异步，不阻塞UI）"""
    # 异步初始化RAG引擎（不等待完成）
    self.rag_integration._init_rag_for_game(vector_game_name, llm_config, jina_api_key, wait_for_init=False)
    
    # 标记RAG引擎正在初始化
    self._rag_initializing = True
    self._target_vector_game = vector_game_name
```

### 3. 增加查询处理时的状态检查
```python
def handle_query(self, query: str):
    """Override to handle query with RAG integration"""
    # 检查RAG引擎初始化状态
    if getattr(self, '_rag_initializing', False):
        # RAG引擎正在初始化中，显示等待状态
        self.main_window.chat_view.show_status("🚀 游戏攻略系统正在初始化中，请稍候...")
        
        # 延迟处理查询，定期检查初始化状态
        self._pending_query = query
        self._check_rag_init_status()
        return
    
    # RAG引擎已准备好，正常处理查询
    self._process_query_immediately(query)
```

## 潜在问题和解决方案

### 1. 时序问题
**问题**: 用户可能在RAG引擎还没初始化完成时就提交查询
**解决**: 增加初始化状态检查，显示等待提示，并缓存查询直到初始化完成

### 2. UI状态管理
**问题**: 需要在UI上显示加载状态
**解决**: 使用`show_status()`方法显示初始化进度

### 3. 查询队列
**问题**: 初始化期间可能有多个查询
**解决**: 使用`_pending_query`机制缓存最新查询

### 4. 错误处理
**问题**: 初始化失败时需要明确提示
**解决**: 在初始化方法中增加异常处理和状态重置

### 5. 重复初始化
**问题**: 快速切换游戏可能导致重复初始化
**解决**: 使用`_rag_initializing`状态标记防止重复初始化

## 预期效果

1. **响应速度提升**: 热键触发后立即显示窗口（从1.5秒降低到~100ms）
2. **用户体验改善**: 用户感觉工具响应更快，更流畅
3. **状态反馈**: 在RAG初始化期间提供明确的状态提示
4. **查询缓存**: 初始化期间的查询会被缓存并在完成后处理

## 测试建议

1. 测试热键响应速度
2. 测试初始化期间提交查询的处理
3. 测试快速切换不同游戏的场景
4. 测试初始化失败的错误处理