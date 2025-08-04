#!/usr/bin/env python3
"""
BM25索引重构脚本
================

仅重构BM25部分，保留现有的FAISS向量库
使用bm25s替换rank_bm25，解决兼容性问题并提升性能

用法:
    python rebuild_bm25_only.py           # 重建所有游戏的BM25索引
    python rebuild_bm25_only.py dst       # 重建单个游戏的BM25索引
    python rebuild_bm25_only.py --clean   # 清理旧BM25索引后重建
"""

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[3]  # 向上3级到达项目根目录
sys.path.insert(0, str(project_root))

# 导入必要的模块
try:
    from enhanced_bm25_indexer import EnhancedBM25Indexer, BM25UnavailableError
except ImportError:
    from src.game_wiki_tooltip.ai.enhanced_bm25_indexer import EnhancedBM25Indexer, BM25UnavailableError

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def get_vectorstore_dir() -> Path:
    """获取向量库目录的正确路径"""
    # 尝试多个可能的向量库路径
    possible_paths = [
        Path("vectorstore"),
        Path("src/game_wiki_tooltip/ai/vectorstore"),
        Path(__file__).parent / "vectorstore"
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # 如果都不存在，返回默认路径
    return Path(__file__).parent / "vectorstore"

def check_environment():
    """检查环境和依赖"""
    logger = logging.getLogger(__name__)
    
    # 检查bm25s是否可用
    try:
        import bm25s
        logger.info(f"✅ bm25s版本: {bm25s.__version__}")
    except ImportError:
        logger.error("❌ bm25s未安装")
        logger.info("请运行: pip install bm25s>=0.2.13")
        return False
    
    return True

def get_existing_games() -> List[str]:
    """获取现有向量库的游戏列表"""
    vectorstore_dir = get_vectorstore_dir()
    if not vectorstore_dir.exists():
        return []
    
    games = []
    for item in vectorstore_dir.iterdir():
        if item.is_dir() and item.name.endswith("_vectors"):
            game_name = item.name.replace("_vectors", "")
            # 检查是否有FAISS索引和元数据
            if (item / "index.faiss").exists() and (item / "metadata.json").exists():
                games.append(game_name)
    
    return games

def load_game_chunks(game_name: str) -> List[tuple]:
    """从现有的metadata.json加载知识块，并尝试匹配原始数据中的video_info"""
    logger = logging.getLogger(__name__)
    
    vectorstore_dir = get_vectorstore_dir()
    game_dir = vectorstore_dir / f"{game_name}_vectors"
    metadata_file = game_dir / "metadata.json"
    
    if not metadata_file.exists():
        raise FileNotFoundError(f"元数据文件不存在: {metadata_file}")
    
    logger.info(f"📖 加载知识块数据: {metadata_file}")
    
    with open(metadata_file, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    
    logger.info(f"✅ 成功加载 {len(chunks)} 个知识块")
    
    # 尝试加载原始knowledge_chunk文件以获取video_info
    chunks_with_video_info = []
    chunk_to_video_map = {}
    
    # 查找knowledge_chunk文件
    knowledge_chunk_paths = [
        Path("../../data/knowledge_chunk") / f"{game_name}.json",
        Path("data/knowledge_chunk") / f"{game_name}.json",
        Path(__file__).parent.parent.parent.parent / "data" / "knowledge_chunk" / f"{game_name}.json"
    ]
    
    knowledge_chunk_file = None
    for path in knowledge_chunk_paths:
        if path.exists():
            knowledge_chunk_file = path
            break
    
    if knowledge_chunk_file:
        logger.info(f"📄 找到原始知识库文件: {knowledge_chunk_file}")
        try:
            with open(knowledge_chunk_file, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
            
            # 构建topic到video_info的映射（使用topic作为匹配键更可靠）
            topic_to_video_map = {}
            for item in original_data:
                if isinstance(item, dict) and "video_info" in item and "knowledge_chunks" in item:
                    video_info = item["video_info"]
                    for chunk in item["knowledge_chunks"]:
                        if "topic" in chunk:
                            topic_to_video_map[chunk["topic"]] = video_info
                        # 也保留chunk_id映射作为备用
                        if "chunk_id" in chunk:
                            chunk_to_video_map[chunk["chunk_id"]] = video_info
            
            logger.info(f"🎬 成功映射 {len(topic_to_video_map)} 个topic到video_info")
            logger.info(f"📝 成功映射 {len(chunk_to_video_map)} 个chunk_id到video_info")
            
        except Exception as e:
            logger.warning(f"⚠️ 无法加载原始知识库文件: {e}")
            topic_to_video_map = {}
    else:
        logger.warning("⚠️ 未找到原始knowledge_chunk文件，将不包含video_info")
        topic_to_video_map = {}
    
    # 组合chunks和video_info（优先使用topic匹配，其次使用chunk_id）
    matched_count = 0
    for chunk in chunks:
        topic = chunk.get("topic", "")
        chunk_id = chunk.get("chunk_id", "")
        
        # 优先使用topic匹配
        video_info = topic_to_video_map.get(topic, {})
        if not video_info and chunk_id:
            # 如果topic没匹配到，尝试用chunk_id
            video_info = chunk_to_video_map.get(chunk_id, {})
        
        if video_info:
            matched_count += 1
            
        chunks_with_video_info.append((chunk, video_info))
    
    logger.info(f"✅ 最终匹配 {matched_count}/{len(chunks)} 个chunk到video_info")
    
    return chunks_with_video_info

def clean_old_bm25_files(game_name: str):
    """清理旧的BM25索引文件"""
    logger = logging.getLogger(__name__)
    
    vectorstore_dir = get_vectorstore_dir()
    game_dir = vectorstore_dir / f"{game_name}_vectors"
    
    if not game_dir.exists():
        return
    
    logger.info(f"🧹 清理游戏 {game_name} 的旧BM25文件...")
    
    # 删除旧的BM25索引文件
    old_bm25_files = [
        game_dir / "enhanced_bm25_index.pkl",
        game_dir / "bm25_index.pkl"
    ]
    
    for old_file in old_bm25_files:
        if old_file.exists():
            logger.info(f"  删除: {old_file}")
            old_file.unlink()
    
    # 删除旧的bm25s目录
    for bm25s_dir in game_dir.glob("*_bm25s"):
        if bm25s_dir.is_dir():
            logger.info(f"  删除目录: {bm25s_dir}")
            shutil.rmtree(bm25s_dir)

def rebuild_bm25_for_game(game_name: str) -> bool:
    """为单个游戏重建BM25索引"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"🎮 开始重建游戏 '{game_name}' 的BM25索引...")
        
        # 加载现有的知识块数据（现在包含video_info）
        chunks_with_video_info = load_game_chunks(game_name)
        
        # 创建新的BM25索引器
        bm25_indexer = EnhancedBM25Indexer(game_name=game_name)
        
        # 构建索引（传递包含video_info的数据）
        logger.info("🔨 构建新的BM25索引（包含视频标题）...")
        bm25_indexer.build_index(chunks_with_video_info)
        
        # 保存新索引
        vectorstore_dir = get_vectorstore_dir()
        game_dir = vectorstore_dir / f"{game_name}_vectors"
        bm25_index_path = game_dir / "enhanced_bm25_index.pkl"
        
        logger.info(f"💾 保存新索引到: {bm25_index_path}")
        bm25_indexer.save_index(str(bm25_index_path))
        
        # 更新配置文件，启用混合搜索
        config_file = vectorstore_dir / f"{game_name}_vectors_config.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 更新BM25相关配置
            config["hybrid_search_enabled"] = True
            config["bm25_index_path"] = f"{game_name}_vectors/enhanced_bm25_index.pkl"
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"📝 更新配置文件: {config_file}")
        
        # 获取统计信息
        stats = bm25_indexer.get_stats()
        logger.info(f"📊 索引统计: {stats}")
        
        # 测试新索引
        logger.info("🧪 测试新索引...")
        test_query = "武器" if game_name in ["helldiver2", "dst", "eldenring"] else "strategy"
        results = bm25_indexer.search(test_query, top_k=3)
        logger.info(f"测试查询 '{test_query}' 返回 {len(results)} 个结果")
        
        if results:
            logger.info("✅ 索引测试成功")
        else:
            logger.warning("⚠️ 测试查询无结果，但索引可能仍然有效")
        
        logger.info(f"✅ 游戏 '{game_name}' 的BM25索引重建成功!")
        return True
        
    except BM25UnavailableError as e:
        logger.error(f"❌ BM25不可用: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 重建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_bm25_indexes():
    """验证BM25索引的完整性"""
    logger = logging.getLogger(__name__)
    
    vectorstore_dir = get_vectorstore_dir()
    if not vectorstore_dir.exists():
        logger.error("❌ 向量库目录不存在")
        return False
    
    logger.info("🔍 验证BM25索引...")
    
    games = get_existing_games()
    success_count = 0
    
    for game in games:
        game_dir = vectorstore_dir / f"{game}_vectors"
        config_file = vectorstore_dir / f"{game}_vectors_config.json"
        
        checks = {
            "BM25索引文件": (game_dir / "enhanced_bm25_index.pkl").exists(),
            "配置文件": config_file.exists(),
        }
        
        # 检查bm25s目录
        bm25s_dirs = list(game_dir.glob("*_bm25s"))
        checks["BM25S目录"] = len(bm25s_dirs) > 0
        
        # 检查配置文件中的混合搜索设置
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                checks["混合搜索启用"] = config.get("hybrid_search_enabled", False)
            except:
                checks["混合搜索启用"] = False
        else:
            checks["混合搜索启用"] = False
        
        all_good = all(checks.values())
        status = "✅" if all_good else "❌"
        
        logger.info(f"  {status} {game}:")
        for check_name, result in checks.items():
            symbol = "✓" if result else "✗"
            logger.info(f"    {symbol} {check_name}")
        
        if all_good:
            success_count += 1
    
    logger.info(f"📊 验证完成: {success_count}/{len(games)} 个游戏的BM25索引正常")
    return success_count == len(games)

def main():
    parser = argparse.ArgumentParser(description="BM25索引重构工具")
    parser.add_argument("game", nargs="?", help="游戏名称（如果不指定则重建所有）")
    parser.add_argument("--clean", action="store_true", help="清理旧BM25索引")
    parser.add_argument("--verify-only", action="store_true", help="仅验证BM25索引")
    
    args = parser.parse_args()
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 BM25索引重构工具启动")
    logger.info("=" * 50)
    logger.info("📋 说明：此工具仅重构BM25索引，保留现有FAISS向量库")
    
    # 检查环境
    if not check_environment():
        sys.exit(1)
    
    # 获取现有游戏列表
    games = get_existing_games()
    if not games:
        logger.error("❌ 未找到任何现有的向量库")
        logger.info("请先使用 build_vector_index.py 构建向量库")
        sys.exit(1)
    
    logger.info(f"📋 找到 {len(games)} 个现有游戏: {', '.join(games)}")
    
    # 仅验证模式
    if args.verify_only:
        success = verify_bm25_indexes()
        sys.exit(0 if success else 1)
    
    # 重建BM25索引
    if args.game:
        # 重建单个游戏
        if args.game not in games:
            logger.error(f"❌ 游戏 '{args.game}' 不存在或没有向量库")
            logger.info(f"可用游戏: {', '.join(games)}")
            sys.exit(1)
        
        if args.clean:
            clean_old_bm25_files(args.game)
        
        success = rebuild_bm25_for_game(args.game)
        if not success:
            sys.exit(1)
    else:
        # 重建所有游戏
        success_count = 0
        for game in games:
            logger.info(f"\n{'='*20} {game} {'='*20}")
            
            if args.clean:
                clean_old_bm25_files(game)
            
            if rebuild_bm25_for_game(game):
                success_count += 1
        
        logger.info(f"\n📊 重建完成: {success_count}/{len(games)} 个游戏成功")
    
    # 验证BM25索引
    logger.info("\n" + "=" * 50)
    verify_bm25_indexes()
    
    logger.info("🎉 BM25索引重构完成！")
    logger.info("💡 提示：现在可以启动程序测试混合搜索功能")

if __name__ == "__main__":
    main() 