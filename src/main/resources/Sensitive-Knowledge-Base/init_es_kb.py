#!/usr/bin/env python3
"""
知识库 chunk → Elasticsearch 索引导入脚本

功能：
1. 扫描 Knowledge-Base-Chunks 目录下所有 .md 文件
2. 解析路径元数据 (standard / section / chunk_range)
3. 调用 embedding API 生成向量
4. 创建 ES 索引并 bulk 写入

依赖：
  pip install elasticsearch openai

用法：
  python init_es_kb.py                                  # 默认参数
  python init_es_kb.py --es-url http://es:9200          # 指定 ES 地址
  python init_es_kb.py --recreate                       # 删除旧索引并重建
  python init_es_kb.py --chunks-dir /path/to/chunks     # 指定 chunks 目录
"""

import argparse
import os
import sys
from pathlib import Path

from elasticsearch import Elasticsearch
from openai import OpenAI

# ============ 配置 ============

DEFAULT_ES_URL = "http://localhost:9200"
INDEX_NAME = "kb-chunks"
EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_DIMS = 1024
EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
BATCH_SIZE = 20  # embedding 批次大小

# 默认 chunks 目录（相对于本脚本）
DEFAULT_CHUNKS_DIR = "Knowledge-Base-Chunks"

# ============ 索引 mapping ============

INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
    },
    "mappings": {
        "properties": {
            "content": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
            "standard": {"type": "keyword"},
            "section": {"type": "keyword"},
            "chunk_range": {"type": "keyword"},
            "path": {"type": "keyword"},
            "embedding": {
                "type": "dense_vector",
                "dims": EMBEDDING_DIMS,
                "index": True,
                "similarity": "cosine"
            }
        }
    }
}


def scan_chunks(chunks_dir: Path) -> list[dict]:
    """扫描 chunks 目录，解析每个 .md 文件的元数据"""
    docs = []
    for md_file in sorted(chunks_dir.rglob("*.md")):
        rel = md_file.relative_to(chunks_dir)
        parts = rel.parts  # e.g. ('JRT-0171-...', '正文-安全技术要求', '1-62.md')

        content = md_file.read_text(encoding="utf-8").strip()
        if not content:
            continue

        if len(parts) == 3:
            # 已拆分的 chunk: standard/section/range.md
            standard = parts[0]
            section = parts[1]
            chunk_range = parts[2].replace(".md", "")
        elif len(parts) == 2:
            # 未拆分的独立文件: standard/file.md
            standard = parts[0]
            section = parts[1].replace(".md", "")
            chunk_range = "full"
        else:
            continue

        path = f"{standard}/{section}/{chunk_range}"

        docs.append({
            "content": content,
            "standard": standard,
            "section": section,
            "chunk_range": chunk_range,
            "path": path,
        })

    return docs


def embed_batch(client: OpenAI, texts: list[str], model: str) -> list[list[float]]:
    """批量调用 embedding API"""
    resp = client.embeddings.create(model=model, input=texts, encoding_format="float")
    return [item.embedding for item in resp.data]


def create_index(es: Elasticsearch, recreate: bool = False):
    """创建 ES 索引"""
    if es.indices.exists(index=INDEX_NAME):
        if recreate:
            print(f"  删除旧索引 {INDEX_NAME}...")
            es.indices.delete(index=INDEX_NAME)
        else:
            print(f"  索引 {INDEX_NAME} 已存在，跳过（使用 --recreate 重建）")
            return False
    print(f"  创建索引 {INDEX_NAME}...")
    es.indices.create(index=INDEX_NAME, body=INDEX_SETTINGS)
    return True


def bulk_index(es: Elasticsearch, docs: list[dict], embeddings: list[list[float]]):
    """批量写入 ES"""
    actions = []
    for doc, emb in zip(docs, embeddings):
        doc_id = doc["path"].replace("/", "_")
        body = {**doc, "embedding": emb}
        actions.append({"index": {"_index": INDEX_NAME, "_id": doc_id}})
        actions.append(body)

    if actions:
        es.bulk(body=actions, refresh=True)


def main():
    parser = argparse.ArgumentParser(description="知识库 chunk → ES 索引导入")
    parser.add_argument("--es-url", default=DEFAULT_ES_URL)
    parser.add_argument("--api-key", default=None, help="Embedding API Key（默认读 DASHSCOPE_API_KEY）")
    parser.add_argument("--chunks-dir", default=None, help="Knowledge-Base-Chunks 目录路径")
    parser.add_argument("--recreate", action="store_true", help="删除旧索引并重建")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误: 请设置 DASHSCOPE_API_KEY 环境变量或使用 --api-key 参数")
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    chunks_dir = Path(args.chunks_dir) if args.chunks_dir else script_dir / DEFAULT_CHUNKS_DIR
    if not chunks_dir.exists():
        print(f"错误: chunks 目录不存在: {chunks_dir}")
        sys.exit(1)

    print(f"=== 知识库 ES 索引导入 ===")
    print(f"  ES:         {args.es_url}")
    print(f"  索引:       {INDEX_NAME}")
    print(f"  Chunks 目录: {chunks_dir}")
    print(f"  Embedding:  {EMBEDDING_MODEL} ({EMBEDDING_DIMS}维)")
    print()

    # 1. 扫描文件
    print("[1/4] 扫描 chunk 文件...")
    docs = scan_chunks(chunks_dir)
    print(f"  发现 {len(docs)} 个 chunk")
    if not docs:
        print("错误: 未找到任何 .md 文件")
        sys.exit(1)

    # 2. 生成向量
    print(f"[2/4] 生成 embedding（批次大小 {BATCH_SIZE}）...")
    oai = OpenAI(api_key=api_key, base_url=EMBEDDING_BASE_URL)
    all_embeddings = []
    texts = [d["content"] for d in docs]
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        embs = embed_batch(oai, batch, EMBEDDING_MODEL)
        all_embeddings.extend(embs)
        print(f"  {min(i + BATCH_SIZE, len(texts))}/{len(texts)}")
    print(f"  向量维度: {len(all_embeddings[0])}")

    # 3. 创建索引
    print("[3/4] 连接 Elasticsearch...")
    es = Elasticsearch(args.es_url)
    if not es.ping():
        print(f"错误: 无法连接 ES: {args.es_url}")
        sys.exit(1)
    info = es.info()
    print(f"  ES 版本: {info['version']['number']}")
    create_index(es, recreate=args.recreate)

    # 4. 写入
    print("[4/4] 写入文档...")
    bulk_index(es, docs, all_embeddings)
    count = es.count(index=INDEX_NAME)["count"]
    print(f"  索引 {INDEX_NAME} 共 {count} 条文档")

    print()
    print("=== 导入完成 ===")
    for d in docs:
        print(f"  {d['path']}")


if __name__ == "__main__":
    main()
