# AI Module - Knowledge Base Builder

This module provides tools for building and managing vector stores and BM25 search indexes for game wikis.

## Knowledge Base Format

### File Structure
Your knowledge base file should be a JSON file located in `data/knowledge_chunk/` with the following structure:

```json
[
  {
    "video_info": {
      "url": "https://www.youtube.com/watch?v=example",
      "title": "Game Guide Title",
      "uploader": "Channel Name",
      "game": "Game Name",
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
        "topic": "Topic Title",
        "summary": "Detailed description of the knowledge chunk content...",
        "keywords": [
          "keyword1",
          "keyword2",
          "keyword3"
        ],
        "type": "Build_Recommendation",
        "build": {
          "name": "Build Name",
          "focus": "Build focus description",
          "armor": {
            "name": "Armor Name",
            "type": "Armor Type",
            "passive": "Passive Ability",
            "rationale": "Why this armor is recommended"
          },
          "primary_weapon": {
            "name": "Weapon Name",
            "rationale": "Why this weapon is recommended"
          },
          "stratagems": [
            {
              "name": "Stratagem Name",
              "rationale": "Why this stratagem is recommended"
            }
          ]
        },
        "structured_data": {
          "enemy_name": "Enemy Name",
          "faction": "Faction Name",
          "weak_points": [
            {
              "name": "Weak Point Name",
              "health": 1500,
              "notes": "Additional notes about the weak point"
            }
          ],
          "recommended_weapons": ["Weapon1", "Weapon2"]
        }
      }
    ]
  }
]
```

### Required Fields
- `chunk_id`: Unique identifier for each knowledge chunk
- `topic`: Main topic/title of the knowledge chunk
- `summary`: Detailed description of the content
- `keywords`: Array of relevant keywords for search

### Optional Fields
- `build`: Detailed build information for loadout recommendations
- `structured_data`: Structured information about enemies, weapons, etc.
- `timestamp`: Video timestamp if sourced from video content
- `type`: Content type (e.g., "Build_Recommendation", "Enemy_Guide", "Strategy")

## Commands

### Build Vector Store and BM25 Index for a New Game

To build both vector store and BM25 index for a specific game:

```bash
# Using game name (requires data/knowledge_chunk/GAME_NAME.json)
python src/game_wiki_tooltip/ai/build_vector_index.py --game GAME_NAME

# Using direct file path
python src/game_wiki_tooltip/ai/build_vector_index.py --file data/knowledge_chunk/GAME_NAME.json

# Build all games at once
python src/game_wiki_tooltip/ai/build_vector_index.py --game all
```

**Examples:**
```bash
# Build for Terraria
python src/game_wiki_tooltip/ai/build_vector_index.py --game terraria

# Build for a test file
python src/game_wiki_tooltip/ai/build_vector_index.py --file data/knowledge_chunk/terraria_test.json --collection-name terraria_test_vectors

# Build all existing games
python src/game_wiki_tooltip/ai/build_vector_index.py --game all
```

### Rebuild Only BM25 Indexes

If you only need to rebuild BM25 indexes (keeping existing vector stores):

```bash
# Rebuild BM25 for all games
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py

# Rebuild BM25 for specific game
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py GAME_NAME

# Clean old BM25 files before rebuilding
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py --clean

# Verify BM25 indexes without rebuilding
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py --verify-only
```

**Examples:**
```bash
# Rebuild BM25 for Terraria only
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py terraria

# Clean and rebuild all BM25 indexes
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py --clean
```

## Prerequisites

### Environment Variables
Set your JINA API key for vector embeddings:
```bash
export JINA_API_KEY="your_jina_api_key_here"
```

### Required Dependencies
```bash
pip install bm25s faiss-cpu
```

## Output Structure

After building, the following files will be created:

```
src/game_wiki_tooltip/ai/vectorstore/
├── GAME_NAME_vectors/
│   ├── index.faiss                              # FAISS vector index
│   ├── metadata.json                            # Document metadata
│   ├── enhanced_bm25_index.pkl                  # BM25 additional data
│   └── enhanced_bm25_index_bm25s/              # BM25s native index
│       ├── data.csc.index.npy                  # Sparse matrix data
│       ├── indices.csc.index.npy               # Document indices
│       ├── indptr.csc.index.npy                # Pointer array
│       ├── params.index.json                   # BM25 parameters
│       └── vocab.index.json                    # Vocabulary mapping
└── GAME_NAME_vectors_config.json               # Configuration file
```

## Features

- **Hybrid Search**: Combines vector similarity and BM25 keyword matching
- **Multi-language Support**: Handles both Chinese and English text
- **Game-specific Optimization**: Customized processing for different games
- **High Performance**: Uses bm25s (Rust-based) for fast BM25 operations
- **Smart Text Processing**: Intelligent tokenization, stemming, and stop word filtering

## Troubleshooting

### Common Issues

1. **BM25 package unavailable**: Install bm25s with `pip install bm25s`
2. **JINA API key missing**: Set the JINA_API_KEY environment variable
3. **File not found**: Ensure your JSON file exists in `data/knowledge_chunk/`
4. **Index build failed**: Check your JSON file format matches the required structure

### Logs
Build logs are saved to `vector_build.log` for debugging purposes. 