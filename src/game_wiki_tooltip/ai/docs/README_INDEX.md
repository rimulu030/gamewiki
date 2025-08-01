# AI Module Documentation / AI 模块文档

## Quick Start / 快速开始

This directory contains tools for building vector stores and BM25 search indexes for game knowledge bases.

本目录包含用于构建游戏知识库向量存储和 BM25 搜索索引的工具。

## Documentation / 文档

📖 **[English Documentation](./README.md)** - Complete guide in English

📖 **[中文文档](./README.zh-CN.md)** - 完整中文指南

## Quick Commands / 快速命令

### Build for new game / 为新游戏构建
```bash
# English / 英文
python src/game_wiki_tooltip/ai/build_vector_index.py --game GAME_NAME

# Example / 示例
python src/game_wiki_tooltip/ai/build_vector_index.py --game terraria
```

### Rebuild BM25 only / 仅重建 BM25
```bash
# English / 英文
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py GAME_NAME

# Example / 示例  
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py terraria
```

## Prerequisites / 先决条件

```bash
# Set API key / 设置 API 密钥
export JINA_API_KEY="your_api_key"

# Install dependencies / 安装依赖
pip install bm25s faiss-cpu
```

For detailed instructions, please refer to the documentation links above.

详细说明请参考上面的文档链接。 