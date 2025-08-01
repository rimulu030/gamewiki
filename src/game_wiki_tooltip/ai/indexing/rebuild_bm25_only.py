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
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

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
    vectorstore_dir = Path("vectorstore")
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

def load_game_chunks(game_name: str) -> List[Dict[str, Any]]:
    """从现有的metadata.json加载知识块"""
    logger = logging.getLogger(__name__)
    
    vectorstore_dir = Path("vectorstore")
    game_dir = vectorstore_dir / f"{game_name}_vectors"
    metadata_file = game_dir / "metadata.json"
    
    if not metadata_file.exists():
        raise FileNotFoundError(f"元数据文件不存在: {metadata_file}")
    
    logger.info(f"📖 加载知识块数据: {metadata_file}")
    
    with open(metadata_file, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    
    logger.info(f"✅ 成功加载 {len(chunks)} 个知识块")
    return chunks

def clean_old_bm25_files(game_name: str):
    """清理旧的BM25索引文件"""
    logger = logging.getLogger(__name__)
    
    vectorstore_dir = Path("vectorstore")
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
        
        # 加载现有的知识块数据
        chunks = load_game_chunks(game_name)
        
        # 创建新的BM25索引器
        from src.game_wiki_tooltip.ai.enhanced_bm25_indexer import EnhancedBM25Indexer, BM25UnavailableError
        
        bm25_indexer = EnhancedBM25Indexer(game_name=game_name)
        
        # 构建索引
        logger.info("🔨 构建新的BM25索引...")
        bm25_indexer.build_index(chunks)
        
        # 保存新索引
        vectorstore_dir = Path("vectorstore")
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
    
    vectorstore_dir = Path("vectorstore")
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