#!/usr/bin/env python3
"""
Elasticsearch 初始化脚本（简化版）
用于创建数据安全分类知识库的索引

简化点：
1. 去除了definition字段
2. 简化了chunk构建逻辑
3. 保留bm25_text优化
"""

from elasticsearch import Elasticsearch, helpers
from sentence_transformers import SentenceTransformer
import json
from datetime import datetime
from typing import List, Dict

# ============================================================================
# 配置
# ============================================================================

# ES连接配置
ES_HOST = "localhost"
ES_PORT = 9200
ES_USER = "elastic"  # 如果有认证
ES_PASSWORD = "your_password"  # 如果有认证

# 索引名称
INDEX_NAME = "data_security_classification"

# Embedding模型
EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"
EMBEDDING_DIM = 1024

# ============================================================================
# 索引Mapping定义（简化版）
# ============================================================================

INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
        "analysis": {
            "analyzer": {
                # 中文分词器（使用IK）
                "ik_smart_analyzer": {
                    "type": "custom",
                    "tokenizer": "ik_smart"
                },
                "ik_max_word_analyzer": {
                    "type": "custom",
                    "tokenizer": "ik_max_word"
                }
            }
        },
        # 向量检索配置
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 100
        }
    },
    "mappings": {
        "properties": {
            # ID
            "id": {
                "type": "keyword"
            },

            # === 层级字段 ===
            "level1": {
                "type": "keyword"
            },
            "level2": {
                "type": "keyword"
            },
            "level3": {
                "type": "keyword"
            },
            "level4": {
                "type": "keyword"
            },

            # === 内容字段 ===
            "content": {
                "type": "text",
                "analyzer": "ik_max_word_analyzer",
                "search_analyzer": "ik_smart_analyzer"
            },

            # === 安全级别 ===
            "security_level": {
                "type": "integer"
            },

            # === BM25检索文本（优化版）===
            "bm25_text": {
                "type": "text",
                "analyzer": "ik_max_word_analyzer",
                "search_analyzer": "ik_smart_analyzer"
            },

            # === Embedding文本（不参与检索，仅用于生成向量）===
            "embedding_text": {
                "type": "text",
                "index": False
            },

            # === 向量字段（kNN检索）===
            "embedding_vector": {
                "type": "dense_vector",
                "dims": EMBEDDING_DIM,
                "index": True,
                "similarity": "cosine"
            }
        }
    }
}

# ============================================================================
# ES客户端
# ============================================================================

def create_es_client():
    """创建ES客户端"""
    # 如果没有认证
    es = Elasticsearch([f"http://{ES_HOST}:{ES_PORT}"])

    # 如果有认证，使用下面这个
    # es = Elasticsearch(
    #     [f"http://{ES_HOST}:{ES_PORT}"],
    #     basic_auth=(ES_USER, ES_PASSWORD)
    # )

    # 测试连接
    if not es.ping():
        raise Exception("Cannot connect to Elasticsearch")

    print(f"✓ Connected to Elasticsearch at {ES_HOST}:{ES_PORT}")
    return es

# ============================================================================
# 索引管理
# ============================================================================

def create_index(es: Elasticsearch, index_name: str = INDEX_NAME):
    """创建索引"""

    # 检查索引是否存在
    if es.indices.exists(index=index_name):
        print(f"⚠ Index '{index_name}' already exists")
        response = input("Delete and recreate? (yes/no): ")
        if response.lower() == 'yes':
            es.indices.delete(index=index_name)
            print(f"✓ Deleted index '{index_name}'")
        else:
            print("Aborted")
            return False

    # 创建索引
    es.indices.create(index=index_name, body=INDEX_MAPPING)
    print(f"✓ Created index '{index_name}'")

    return True

def delete_index(es: Elasticsearch, index_name: str = INDEX_NAME):
    """删除索引"""
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"✓ Deleted index '{index_name}'")
    else:
        print(f"⚠ Index '{index_name}' does not exist")

# ============================================================================
# Chunk构建（简化版）
# ============================================================================

def build_bm25_text(category: Dict) -> str:
    """
    构建BM25文本（简化版）

    公式：level4 + level1 + level2 + content
    """
    return f"{category['level4']} {category['level1']} {category['level2']} {category['content']}"

def build_embedding_text(category: Dict) -> str:
    """
    构建Embedding文本（简化版）

    公式：层级路径 + content + 安全级别
    """
    return f"{category['level1']}-{category['level2']}-{category['level3']}-{category['level4']}。包含：{category['content']}。安全级别{category['security_level']}级。"

def build_chunk(category: Dict, chunk_id: str, model: SentenceTransformer) -> Dict:
    """
    构建完整的chunk（简化版）

    Args:
        category: 原始分类数据
        chunk_id: chunk ID
        model: embedding模型

    Returns:
        完整的chunk
    """

    # 1. 构建BM25文本
    bm25_text = build_bm25_text(category)

    # 2. 构建Embedding文本
    embedding_text = build_embedding_text(category)

    # 3. 生成向量
    embedding_vector = model.encode(
        embedding_text,
        normalize_embeddings=True
    ).tolist()

    # 4. 组装chunk
    chunk = {
        'id': chunk_id,
        'level1': category['level1'],
        'level2': category['level2'],
        'level3': category['level3'],
        'level4': category['level4'],
        'content': category['content'],
        'security_level': category['security_level'],
        'bm25_text': bm25_text,
        'embedding_text': embedding_text,
        'embedding_vector': embedding_vector
    }

    return chunk

# ============================================================================
# 批量导入
# ============================================================================

def bulk_index_chunks(es: Elasticsearch, chunks: List[Dict], index_name: str = INDEX_NAME):
    """批量导入chunks到ES"""

    # 构建bulk操作
    actions = [
        {
            "_index": index_name,
            "_id": chunk['id'],
            "_source": chunk
        }
        for chunk in chunks
    ]

    # 执行bulk
    success, failed = helpers.bulk(es, actions, raise_on_error=False)

    print(f"✓ Indexed {success} chunks")
    if failed:
        print(f"⚠ Failed to index {len(failed)} chunks")

    return success, failed

# ============================================================================
# 主流程
# ============================================================================

def main():
    """主流程"""

    print("="*80)
    print("Elasticsearch 初始化脚本（简化版）")
    print("="*80)

    # 1. 连接ES
    print("\n[1/5] 连接Elasticsearch...")
    es = create_es_client()

    # 2. 创建索引
    print("\n[2/5] 创建索引...")
    if not create_index(es):
        return

    # 3. 加载Embedding模型
    print("\n[3/5] 加载Embedding模型...")
    print(f"模型: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("✓ 模型加载完成")

    # 4. 加载分类数据
    print("\n[4/5] 加载分类数据...")

    # 从JSON文件加载（假设你已经解析好了附录A）
    with open('categories.json', 'r', encoding='utf-8') as f:
        categories = json.load(f)

    print(f"✓ 加载了 {len(categories)} 个分类")

    # 5. 构建并导入chunks
    print("\n[5/5] 构建并导入chunks...")

    chunks = []
    for i, category in enumerate(categories):
        chunk_id = f"chunk_{i+1:03d}"
        chunk = build_chunk(category, chunk_id, model)
        chunks.append(chunk)

        if (i + 1) % 10 == 0:
            print(f"  已构建 {i+1}/{len(categories)} 个chunks...")

    print(f"✓ 构建完成，共 {len(chunks)} 个chunks")

    # 批量导入
    print("\n导入到Elasticsearch...")
    success, failed = bulk_index_chunks(es, chunks)

    # 6. 验证
    print("\n验证...")
    count = es.count(index=INDEX_NAME)['count']
    print(f"✓ 索引中共有 {count} 个文档")

    print("\n" + "="*80)
    print("初始化完成！")
    print("="*80)

    # 打印示例查询
    print("\n示例查询：")
    print(f"""
# BM25查询
GET /{INDEX_NAME}/_search
{{
  "query": {{
    "match": {{
      "bm25_text": "客户姓名"
    }}
  }}
}}

# 向量查询
GET /{INDEX_NAME}/_search
{{
  "knn": {{
    "field": "embedding_vector",
    "query_vector": [...],
    "k": 5,
    "num_candidates": 100
  }}
}}

# 混合查询（BM25 + 向量）
GET /{INDEX_NAME}/_search
{{
  "query": {{
    "match": {{
      "bm25_text": "客户姓名"
    }}
  }},
  "knn": {{
    "field": "embedding_vector",
    "query_vector": [...],
    "k": 5,
    "num_candidates": 100
  }},
  "rank": {{
    "rrf": {{}}
  }}
}}
    """)

# ============================================================================
# 工具函数
# ============================================================================

def test_search(es: Elasticsearch, query: str, index_name: str = INDEX_NAME):
    """测试BM25搜索"""

    print(f"\n测试BM25查询: '{query}'")
    print("-" * 80)

    # BM25搜索
    response = es.search(
        index=index_name,
        body={
            "query": {
                "match": {
                    "bm25_text": query
                }
            },
            "size": 5
        }
    )

    print("\nBM25结果:")
    for hit in response['hits']['hits']:
        source = hit['_source']
        print(f"  - {source['level4']} (分数: {hit['_score']:.2f})")
        print(f"    路径: {source['level1']} > {source['level2']} > {source['level3']}")
        print(f"    内容: {source['content'][:50]}...")
        print()

def export_chunks_to_json(chunks: List[Dict], output_file: str = 'chunks.json'):
    """导出chunks到JSON文件（用于备份或调试）"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"✓ 导出到 {output_file}")

# ============================================================================
# 示例：构建测试数据
# ============================================================================

def create_sample_categories():
    """创建示例分类数据（用于测试）"""
    return [
        {
            'level1': '客户',
            'level2': '个人',
            'level3': '个人自然信息',
            'level4': '个人基本概况信息',
            'content': '个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等',
            'security_level': 3
        },
        {
            'level1': '客户',
            'level2': '个人',
            'level3': '个人自然信息',
            'level4': '个人联系信息',
            'content': '手机、固定电话、电子邮箱地址、微信号等',
            'security_level': 3
        },
        {
            'level1': '客户',
            'level2': '个人',
            'level3': '个人身份鉴别信息',
            'level4': '传统鉴别信息',
            'content': '银行卡磁道（或芯片等效信息）、卡片验证码（CVN和CVN2）、卡片有效期、银行卡密码、支付密码、账户的登录密码、交易密码、账户查询密码、USBKEY、U盾等',
            'security_level': 4
        }
    ]

# ============================================================================
# 命令行入口
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "create":
            # 创建索引
            es = create_es_client()
            create_index(es)

        elif command == "delete":
            # 删除索引
            es = create_es_client()
            delete_index(es)

        elif command == "test":
            # 测试搜索
            es = create_es_client()
            query = sys.argv[2] if len(sys.argv) > 2 else "客户姓名"
            test_search(es, query)

        elif command == "sample":
            # 使用示例数据初始化
            print("使用示例数据初始化...")

            es = create_es_client()
            create_index(es)

            model = SentenceTransformer(EMBEDDING_MODEL)
            categories = create_sample_categories()

            chunks = []
            for i, category in enumerate(categories):
                chunk_id = f"chunk_{i+1:03d}"
                chunk = build_chunk(category, chunk_id, model)
                chunks.append(chunk)

            bulk_index_chunks(es, chunks)

            print(f"\n✓ 导入了 {len(chunks)} 个示例chunks")
            print("\n测试查询：")
            test_search(es, "客户姓名")

        else:
            print(f"Unknown command: {command}")
            print("Usage: python init_es_simple.py [create|delete|test|sample]")

    else:
        # 默认：完整初始化流程
        main()
