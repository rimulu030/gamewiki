#!/usr/bin/env python3
"""
Vector Index Building Tool
==========================

Command-line tool for batch processing knowledge base files and building vector indexes.

Usage:
    python build_vector_index.py --game helldiver2
    python build_vector_index.py --game all
    python build_vector_index.py --file data/knowledge_chunk/helldiver2.json
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List

# Add project root directory to Python path
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from src.game_wiki_tooltip.ai.indexing.batch_embedding import BatchEmbeddingProcessor, process_game_knowledge

def setup_logging(verbose: bool = False):
    """Set up logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('vector_build.log', encoding='utf-8')
        ]
    )

def get_available_games(knowledge_dir: str = "data/knowledge_chunk") -> List[str]:
    """Get available game list"""
    knowledge_path = Path(knowledge_dir)
    if not knowledge_path.exists():
        return []
    
    json_files = list(knowledge_path.glob("*.json"))
    return [f.stem for f in json_files]

def process_single_game(game_name: str, 
                       knowledge_dir: str = "data/knowledge_chunk",
                       output_dir: str = "src/game_wiki_tooltip/ai/vectorstore",
                       vector_store_type: str = "faiss",
                       batch_size: int = 64) -> bool:
    """
    Process a single game's knowledge base
    
    Args:
        game_name: Game name
        knowledge_dir: Knowledge base directory
        output_dir: Output directory
        vector_store_type: Vector store type
        batch_size: Batch size
        
    Returns:
        Success or failure
    """
    try:
        print(f"\nProcessing game: {game_name}")
        
        # 检查API密钥
        import os
        if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
            print("Error: GOOGLE_API_KEY or GEMINI_API_KEY environment variable is required")
            return False
        
        # 处理知识库
        config_path = process_game_knowledge(
            game_name=game_name,
            knowledge_dir=knowledge_dir,
            output_dir=output_dir
        )
        
        print(f"✓ Game {game_name} processed: {config_path}")
        return True
        
    except FileNotFoundError as e:
        print(f"✗ Game {game_name} processing failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Game {game_name} processing failed: {e}")
        return False

def process_all_games(knowledge_dir: str = "data/knowledge_chunk",
                     output_dir: str = "src/game_wiki_tooltip/ai/vectorstore",
                     vector_store_type: str = "faiss",
                     batch_size: int = 64) -> None:
    """
    Process all games' knowledge bases
    
    Args:
        knowledge_dir: Knowledge base directory
        output_dir: Output directory
        vector_store_type: Vector store type
        batch_size: Batch size
    """
    games = get_available_games(knowledge_dir)
    
    if not games:
        print("No game knowledge base files found")
        return
    
    print(f"Found {len(games)} games: {', '.join(games)}")
    
    success_count = 0
    for game in games:
        if process_single_game(game, knowledge_dir, output_dir, vector_store_type, batch_size):
            success_count += 1
    
    print(f"\nProcessing completed: {success_count}/{len(games)} games successfully")

def process_custom_file(file_path: str,
                       output_dir: str = "src/game_wiki_tooltip/ai/vectorstore",
                       collection_name: str = "custom_vectors",
                       vector_store_type: str = "faiss",
                       batch_size: int = 64) -> bool:
    """
    Process custom file
    
    Args:
        file_path: File path
        output_dir: Output directory
        collection_name: Collection name
        vector_store_type: Vector store type
        batch_size: Batch size
        
    Returns:
        Success or failure
    """
    try:
        print(f"Processing file: {file_path}")
        
        # 检查API密钥
        import os
        if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
            print("Error: GOOGLE_API_KEY or GEMINI_API_KEY environment variable is required")
            return False
        
        # 创建处理器
        processor = BatchEmbeddingProcessor(vector_store_type=vector_store_type)
        
        # 处理文件
        config_path = processor.process_json_file(
            json_path=file_path,
            output_dir=output_dir,
            batch_size=batch_size,
            collection_name=collection_name
        )
        
        print(f"✓ File processed: {config_path}")
        return True
        
    except Exception as e:
        print(f"✗ File processing failed: {e}")
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Batch process knowledge base files and build vector indexes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process specific game
  python build_vector_index.py --game helldiver2
  
  # Process all games
  python build_vector_index.py --game all
  
  # Process custom file
  python build_vector_index.py --file data/knowledge_chunk/helldiver2.json
  
  # Use Qdrant vector store
  python build_vector_index.py --game helldiver2 --vector-store qdrant
  
  # Set batch size
  python build_vector_index.py --game helldiver2 --batch-size 32
        """
    )
    
    # 添加参数
    parser.add_argument(
        "--game", 
        type=str,
        help="Game name (use 'all' to process all games)"
    )
    
    parser.add_argument(
        "--file",
        type=str,
        help="Custom JSON file path"
    )
    
    parser.add_argument(
        "--knowledge-dir",
        type=str,
        default="data/knowledge_chunk",
        help="Knowledge base directory (default: data/knowledge_chunk)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="src/game_wiki_tooltip/ai/vectorstore",
        help="Output directory (default: src/game_wiki_tooltip/ai/vectorstore)"
    )
    
    parser.add_argument(
        "--vector-store",
        type=str,
        choices=["faiss", "qdrant"],
        default="faiss",
        help="Vector store type (default: faiss)"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size (default: 64)"
    )
    
    parser.add_argument(
        "--collection-name",
        type=str,
        default="custom_vectors",
        help="Collection name (only used for custom files)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--list-games",
        action="store_true",
        help="List available games"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.verbose)
    
    # 列出可用游戏
    if args.list_games:
        games = get_available_games(args.knowledge_dir)
        if games:
            print("Available games:")
            for game in games:
                print(f"  - {game}")
        else:
            print("No game knowledge base files found")
        return
    
    # 检查参数
    if not args.game and not args.file:
        parser.error("Need to specify --game or --file parameter")
    
    if args.game and args.file:
        parser.error("Cannot specify both --game and --file parameters")
    
    # 处理请求
    if args.game:
        if args.game.lower() == "all":
            process_all_games(
                knowledge_dir=args.knowledge_dir,
                output_dir=args.output_dir,
                vector_store_type=args.vector_store,
                batch_size=args.batch_size
            )
        else:
            success = process_single_game(
                game_name=args.game,
                knowledge_dir=args.knowledge_dir,
                output_dir=args.output_dir,
                vector_store_type=args.vector_store,
                batch_size=args.batch_size
            )
            if not success:
                sys.exit(1)
    
    elif args.file:
        success = process_custom_file(
            file_path=args.file,
            output_dir=args.output_dir,
            collection_name=args.collection_name,
            vector_store_type=args.vector_store,
            batch_size=args.batch_size
        )
        if not success:
            sys.exit(1)

if __name__ == "__main__":
    main() 