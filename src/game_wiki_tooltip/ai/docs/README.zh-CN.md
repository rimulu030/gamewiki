# AI 模块 - 知识库构建器

本模块提供用于构建和管理游戏百科向量库和 BM25 搜索索引的工具。

## 知识库格式

### 文件结构
您的知识库文件应为位于 `data/knowledge_chunk/` 目录下的 JSON 文件，具有以下结构：

```json
[
  {
    "video_info": {
      "url": "https://www.youtube.com/watch?v=example",
      "title": "游戏攻略标题",
      "uploader": "频道名称",
      "game": "游戏名称",
      "views": "10k",
      "upload_time": "March 2025"
    },
    "knowledge_chunks": [
      {
        "chunk_id": "unique_id_001",
        "timestamp": {
          "start": "00:00",
          "end": "00:57"
        },
        "topic": "主题标题",
        "summary": "知识块内容的详细描述...",
        "keywords": [
          "关键词1",
          "关键词2",
          "关键词3"
        ],
        "type": "Build_Recommendation",
        "build": {
          "name": "构建名称",
          "focus": "构建焦点描述",
          "armor": {
            "name": "装甲名称",
            "type": "装甲类型",
            "passive": "被动技能",
            "rationale": "推荐该装甲的原因"
          },
          "primary_weapon": {
            "name": "武器名称",
            "rationale": "推荐该武器的原因"
          },
          "stratagems": [
            {
              "name": "战术装备名称",
              "rationale": "推荐该战术装备的原因"
            }
          ]
        },
        "structured_data": {
          "enemy_name": "敌人名称",
          "faction": "阵营名称",
          "weak_points": [
            {
              "name": "弱点名称",
              "health": 1500,
              "notes": "关于弱点的额外说明"
            }
          ],
          "recommended_weapons": ["武器1", "武器2"]
        }
      }
    ]
  }
]
```

### 必需字段
- `chunk_id`: 每个知识块的唯一标识符
- `topic`: 知识块的主要主题/标题
- `summary`: 内容的详细描述
- `keywords`: 用于搜索的相关关键词数组

### 可选字段
- `build`: 装备推荐的详细构建信息
- `structured_data`: 关于敌人、武器等的结构化信息
- `timestamp`: 如果来源于视频内容的时间戳
- `type`: 内容类型（如 "Build_Recommendation"、"Enemy_Guide"、"Strategy"）

## 命令

### 为新游戏构建向量库和 BM25 索引

为特定游戏构建向量库和 BM25 索引：

```bash
# 使用游戏名称（需要 data/knowledge_chunk/游戏名称.json）
python src/game_wiki_tooltip/ai/build_vector_index.py --game 游戏名称

# 使用直接文件路径
python src/game_wiki_tooltip/ai/build_vector_index.py --file data/knowledge_chunk/游戏名称.json

# 一次性构建所有游戏
python src/game_wiki_tooltip/ai/build_vector_index.py --game all
```

**示例：**
```bash
# 为 Terraria 构建
python src/game_wiki_tooltip/ai/build_vector_index.py --game terraria

# 为测试文件构建
python src/game_wiki_tooltip/ai/build_vector_index.py --file data/knowledge_chunk/terraria_test.json --collection-name terraria_test_vectors

# 构建所有现有游戏
python src/game_wiki_tooltip/ai/build_vector_index.py --game all
```

### 仅重建 BM25 索引

如果您只需要重建 BM25 索引（保留现有向量库）：

```bash
# 为所有游戏重建 BM25
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py

# 为特定游戏重建 BM25
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py 游戏名称

# 重建前清理旧的 BM25 文件
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py --clean

# 验证 BM25 索引而不重建
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py --verify-only
```

**示例：**
```bash
# 仅为 Terraria 重建 BM25
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py terraria

# 清理并重建所有 BM25 索引
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py --clean
```

## 先决条件

### 环境变量
为向量嵌入设置您的 JINA API 密钥：
```bash
export JINA_API_KEY="your_jina_api_key_here"
```

### 必需依赖
```bash
pip install bm25s faiss-cpu
```

## 输出结构

构建完成后，将创建以下文件：

```
src/game_wiki_tooltip/ai/vectorstore/
├── 游戏名称_vectors/
│   ├── index.faiss                              # FAISS 向量索引
│   ├── metadata.json                            # 文档元数据
│   ├── enhanced_bm25_index.pkl                  # BM25 附加数据
│   └── enhanced_bm25_index_bm25s/              # BM25s 原生索引
│       ├── data.csc.index.npy                  # 稀疏矩阵数据
│       ├── indices.csc.index.npy               # 文档索引
│       ├── indptr.csc.index.npy                # 指针数组
│       ├── params.index.json                   # BM25 参数
│       └── vocab.index.json                    # 词汇表映射
└── 游戏名称_vectors_config.json               # 配置文件
```

## 功能特性

- **混合搜索**：结合向量相似性和 BM25 关键词匹配
- **多语言支持**：处理中文和英文文本
- **游戏特定优化**：针对不同游戏的定制化处理
- **高性能**：使用 bm25s（基于 Rust）进行快速 BM25 操作
- **智能文本处理**：智能分词、词干提取和停用词过滤

## 故障排除

### 常见问题

1. **BM25 包不可用**：使用 `pip install bm25s` 安装 bm25s
2. **JINA API 密钥缺失**：设置 JINA_API_KEY 环境变量
3. **文件未找到**：确保您的 JSON 文件存在于 `data/knowledge_chunk/` 中
4. **索引构建失败**：检查您的 JSON 文件格式是否符合要求的结构

### 日志
构建日志保存到 `vector_build.log` 用于调试。

## 使用流程

### 1. 准备知识库文件
将您的知识库 JSON 文件放在 `data/knowledge_chunk/` 目录下，文件名格式为 `游戏名称.json`。

### 2. 设置环境
```bash
# 设置 API 密钥
export JINA_API_KEY="your_api_key"

# 安装依赖
pip install bm25s faiss-cpu
```

### 3. 构建索引
```bash
# 为新游戏构建完整的向量库和 BM25 索引
python src/game_wiki_tooltip/ai/build_vector_index.py --game 游戏名称

# 或者仅重建 BM25 索引（如果向量库已存在）
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py 游戏名称
```

### 4. 验证结果
```bash
# 验证索引是否正确构建
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py --verify-only
```

构建完成后，您的知识库将可用于游戏内的智能搜索和问答功能。 