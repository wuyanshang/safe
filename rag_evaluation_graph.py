#!/usr/bin/env python3
"""
RAG评估流程 - LangGraph实现

流程：
1. BM25召回节点
2. 向量召回节点
3. 混合排序节点
4. LLM判断节点
5. 置信度评估节点（混合策略 + Ragas）
"""

from typing import TypedDict, List, Dict, Annotated
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer
import numpy as np
import json
from datetime import datetime

# ============================================================================
# 状态定义
# ============================================================================

class GraphState(TypedDict):
    """图状态"""
    # 输入
    query: str                          # 查询字段名

    # 召回结果
    bm25_results: List[Dict]            # BM25召回结果
    vector_results: List[Dict]          # 向量召回结果
    merged_candidates: List[Dict]       # 合并后的候选

    # LLM判断结果
    llm_selection: Dict                 # LLM选择的结果

    # 置信度评估结果
    confidence_evaluation: Dict         # 置信度评估

    # 最终输出
    final_result: Dict                  # 最终结果

    # 元数据
    metadata: Dict                      # 元数据（时间戳等）

# ============================================================================
# 配置
# ============================================================================

class Config:
    """配置类"""

    # ES配置
    ES_HOST = "localhost"
    ES_PORT = 9200
    INDEX_NAME = "data_security_classification"

    # Embedding模型
    EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"

    # LLM配置
    LLM_MODEL = "gpt-4o-mini"
    LLM_TEMPERATURE = 0

    # 召回配置
    BM25_TOP_K = 10
    VECTOR_TOP_K = 10
    MERGED_TOP_K = 5

    # 置信度评估阈值（严格策略）
    HIGH_CONFIDENCE_SCORE = 0.9
    HIGH_CONFIDENCE_GAP = 0.3
    LOW_CONFIDENCE_SCORE = 0.6
    LOW_CONFIDENCE_GAP = 0.1

# ============================================================================
# 节点1：BM25召回
# ============================================================================

def bm25_retrieval_node(state: GraphState) -> GraphState:
    """
    BM25召回节点

    使用ES的BM25算法召回候选
    """
    query = state['query']

    print(f"\n[BM25召回] 查询: {query}")

    # 连接ES
    es = Elasticsearch([f"http://{Config.ES_HOST}:{Config.ES_PORT}"])

    # BM25查询
    response = es.search(
        index=Config.INDEX_NAME,
        body={
            "query": {
                "match": {
                    "bm25_text": query
                }
            },
            "size": Config.BM25_TOP_K
        }
    )

    # 提取结果
    bm25_results = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        bm25_results.append({
            'id': source['id'],
            'level1': source['level1'],
            'level2': source['level2'],
            'level3': source['level3'],
            'level4': source['level4'],
            'content': source['content'],
            'security_level': source['security_level'],
            'bm25_score': hit['_score'],
            'source': 'bm25'
        })

    print(f"  召回 {len(bm25_results)} 个候选")

    state['bm25_results'] = bm25_results
    return state

# ============================================================================
# 节点2：向量召回
# ============================================================================

def vector_retrieval_node(state: GraphState) -> GraphState:
    """
    向量召回节点

    使用向量相似度召回候选
    """
    query = state['query']

    print(f"\n[向量召回] 查询: {query}")

    # 加载Embedding模型
    model = SentenceTransformer(Config.EMBEDDING_MODEL)

    # 生成查询向量
    query_vector = model.encode(query, normalize_embeddings=True).tolist()

    # 连接ES
    es = Elasticsearch([f"http://{Config.ES_HOST}:{Config.ES_PORT}"])

    # 向量查询
    response = es.search(
        index=Config.INDEX_NAME,
        body={
            "knn": {
                "field": "embedding_vector",
                "query_vector": query_vector,
                "k": Config.VECTOR_TOP_K,
                "num_candidates": 100
            },
            "_source": ["id", "level1", "level2", "level3", "level4",
                       "content", "security_level"]
        }
    )

    # 提取结果
    vector_results = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        vector_results.append({
            'id': source['id'],
            'level1': source['level1'],
            'level2': source['level2'],
            'level3': source['level3'],
            'level4': source['level4'],
            'content': source['content'],
            'security_level': source['security_level'],
            'vector_score': hit['_score'],
            'source': 'vector'
        })

    print(f"  召回 {len(vector_results)} 个候选")

    state['vector_results'] = vector_results
    return state

# ============================================================================
# 节点3：混合排序
# ============================================================================

def merge_and_rank_node(state: GraphState) -> GraphState:
    """
    混合排序节点

    合并BM25和向量召回结果，重新排序
    """
    bm25_results = state['bm25_results']
    vector_results = state['vector_results']

    print(f"\n[混合排序] 合并结果")

    # 合并结果（去重）
    candidates_dict = {}

    # 添加BM25结果
    for result in bm25_results:
        candidates_dict[result['id']] = {
            **result,
            'bm25_score': result.get('bm25_score', 0),
            'vector_score': 0
        }

    # 添加向量结果
    for result in vector_results:
        if result['id'] in candidates_dict:
            candidates_dict[result['id']]['vector_score'] = result.get('vector_score', 0)
        else:
            candidates_dict[result['id']] = {
                **result,
                'bm25_score': 0,
                'vector_score': result.get('vector_score', 0)
            }

    # 归一化分数
    candidates = list(candidates_dict.values())

    if candidates:
        # 归一化BM25分数
        bm25_scores = [c['bm25_score'] for c in candidates]
        bm25_min, bm25_max = min(bm25_scores), max(bm25_scores)
        if bm25_max > bm25_min:
            for c in candidates:
                c['bm25_score_norm'] = (c['bm25_score'] - bm25_min) / (bm25_max - bm25_min)
        else:
            for c in candidates:
                c['bm25_score_norm'] = 0.5

        # 归一化向量分数
        vector_scores = [c['vector_score'] for c in candidates]
        vector_min, vector_max = min(vector_scores), max(vector_scores)
        if vector_max > vector_min:
            for c in candidates:
                c['vector_score_norm'] = (c['vector_score'] - vector_min) / (vector_max - vector_min)
        else:
            for c in candidates:
                c['vector_score_norm'] = 0.5

        # 混合分数（BM25: 0.4, Vector: 0.6）
        for c in candidates:
            c['final_score'] = 0.4 * c['bm25_score_norm'] + 0.6 * c['vector_score_norm']

        # 排序
        candidates.sort(key=lambda x: x['final_score'], reverse=True)

        # 取Top-K
        merged_candidates = candidates[:Config.MERGED_TOP_K]
    else:
        merged_candidates = []

    print(f"  合并后 {len(merged_candidates)} 个候选")
    for i, cand in enumerate(merged_candidates[:3], 1):
        print(f"    {i}. {cand['level4']} (分数: {cand['final_score']:.3f})")

    state['merged_candidates'] = merged_candidates
    return state

# ============================================================================
# 节点4：LLM判断
# ============================================================================

def llm_selection_node(state: GraphState) -> GraphState:
    """
    LLM判断节点

    让LLM从候选中选择最匹配的分类和具体项
    """
    query = state['query']
    candidates = state['merged_candidates']

    print(f"\n[LLM判断] 从 {len(candidates)} 个候选中选择")

    if not candidates:
        state['llm_selection'] = {
            'error': 'No candidates found'
        }
        return state

    # 格式化候选
    candidates_text = ""
    for i, cand in enumerate(candidates, 1):
        candidates_text += f"""
候选{i}:
  分类: {cand['level1']} > {cand['level2']} > {cand['level3']} > {cand['level4']}
  内容: {cand['content']}
  级别: {cand['security_level']}级
  分数: {cand['final_score']:.2f}

"""

    # 构建prompt
    prompt = f"""
你是一个数据安全分类专家。现在需要将一个数据字段精确分类到金融数据安全分级目录。

# 任务
给定字段名："{query}"

从以下候选分类中：
1. 选择最匹配的分类（四级子类）
2. 从该分类的"包含内容"中，选择最匹配的具体项

# 候选分类
{candidates_text}

# 输出要求
请以JSON格式输出：
{{
  "selected_candidate": 候选编号（1-{len(candidates)}）,
  "level4": "四级分类名称",
  "matched_item": "具体项名称",
  "security_level": 安全级别（数字）,
  "confidence": "置信度（high/medium/low）",
  "reason": "选择理由（不超过30字）"
}}

# 注意
- matched_item必须从"包含内容"中提取，不要自己创造
- 如果所有候选都不太匹配（最高分<0.6），confidence设为low
"""

    # 调用LLM
    llm = ChatOpenAI(model=Config.LLM_MODEL, temperature=Config.LLM_TEMPERATURE)

    messages = [
        SystemMessage(content="你是一个数据安全分类专家。"),
        HumanMessage(content=prompt)
    ]

    response = llm.invoke(messages)

    # 解析结果
    try:
        result_text = response.content
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()

        llm_result = json.loads(result_text)

        # 增强结果
        selected_idx = llm_result['selected_candidate'] - 1
        selected_candidate = candidates[selected_idx]

        llm_result.update({
            'level1': selected_candidate['level1'],
            'level2': selected_candidate['level2'],
            'level3': selected_candidate['level3'],
            'retrieval_score': selected_candidate['final_score']
        })

        print(f"  选择: {llm_result['level4']} - {llm_result['matched_item']}")
        print(f"  LLM置信度: {llm_result['confidence']}")

        state['llm_selection'] = llm_result

    except Exception as e:
        print(f"  错误: {e}")
        state['llm_selection'] = {
            'error': str(e),
            'raw_response': response.content
        }

    return state

# ============================================================================
# 节点5：置信度评估（混合策略 + Ragas）
# ============================================================================

def confidence_evaluation_node(state: GraphState) -> GraphState:
    """
    置信度评估节点

    混合策略：
    1. 数值指标快速判断（明确的高/低置信度）
    2. LLM精细评估（模糊情况，Ragas风格）
    """
    query = state['query']
    candidates = state['merged_candidates']
    llm_selection = state['llm_selection']

    print(f"\n[置信度评估]")

    if 'error' in llm_selection or not candidates:
        state['confidence_evaluation'] = {
            'confidence': 'low',
            'need_review': True,
            'method': 'error'
        }
        return state

    # 提取数值指标
    retrieval_score = llm_selection.get('retrieval_score', 0)
    score_gap = candidates[0]['final_score'] - candidates[1]['final_score'] if len(candidates) > 1 else 1.0

    print(f"  召回分数: {retrieval_score:.3f}")
    print(f"  分数差距: {score_gap:.3f}")

    # === 第1层：数值指标（严格策略）===

    # 明确的高置信度
    if retrieval_score > Config.HIGH_CONFIDENCE_SCORE and score_gap > Config.HIGH_CONFIDENCE_GAP:
        print(f"  → 明确的高置信度（规则判断）")
        state['confidence_evaluation'] = {
            'confidence': 'high',
            'score': retrieval_score,
            'need_review': False,
            'method': 'rule_based',
            'metrics': {
                'retrieval_score': retrieval_score,
                'score_gap': score_gap
            }
        }
        return state

    # 明确的低置信度
    if retrieval_score < Config.LOW_CONFIDENCE_SCORE or score_gap < Config.LOW_CONFIDENCE_GAP:
        print(f"  → 明确的低置信度（规则判断）")
        state['confidence_evaluation'] = {
            'confidence': 'low',
            'score': retrieval_score,
            'need_review': True,
            'method': 'rule_based',
            'metrics': {
                'retrieval_score': retrieval_score,
                'score_gap': score_gap
            }
        }
        return state

    # === 第2层：LLM精细评估（Ragas风格）===

    print(f"  → 模糊情况，使用LLM评估（Ragas风格）")

    ragas_result = ragas_style_evaluation(query, candidates, llm_selection)

    state['confidence_evaluation'] = ragas_result
    return state


def ragas_style_evaluation(query: str, candidates: List[Dict], selected: Dict) -> Dict:
    """
    Ragas风格的评估（批量优化版）

    一次LLM调用，评估多个维度：
    1. Context Relevance（上下文相关度）
    2. Context Precision（上下文精确度）
    3. Selection Quality（选择质量）
    4. Ambiguity（模糊程度）
    """

    # 格式化候选
    candidates_text = ""
    for i, cand in enumerate(candidates, 1):
        candidates_text += f"""
候选{i}:
  分类: {cand['level1']} > {cand['level2']} > {cand['level3']} > {cand['level4']}
  内容: {cand['content']}
  级别: {cand['security_level']}级
  分数: {cand['final_score']:.2f}
"""

    # 构建prompt
    prompt = f"""
你是一个数据安全分类专家。请评估这个数据分类结果的质量（参考Ragas评估框架）。

查询字段：{query}

召回的候选：
{candidates_text}

LLM选择的结果：
- 分类：{selected['level4']}
- 具体项：{selected['matched_item']}
- 安全级别：{selected['security_level']}级

请从以下维度评估：

1. Context Relevance（上下文相关度）：
   召回的候选与查询的相关性如何？

2. Context Precision（上下文精确度）：
   召回的候选是否包含所需信息？

3. Selection Quality（选择质量）：
   选择的结果是否合理？

4. Ambiguity（模糊程度）：
   是否有多个候选都很合适？

请输出JSON：
{{
  "context_relevance": "high/medium/low",
  "context_precision": "high/medium/low",
  "selection_quality": "excellent/good/acceptable/poor",
  "ambiguity": "clear/ambiguous/unclear",
  "overall_confidence": "high/medium/low",
  "need_review": true/false,
  "reason": "简短说明（不超过50字）"
}}
"""

    # 调用LLM
    llm = ChatOpenAI(model=Config.LLM_MODEL, temperature=Config.LLM_TEMPERATURE)

    messages = [
        SystemMessage(content="你是一个数据安全分类专家，擅长评估RAG系统的质量。"),
        HumanMessage(content=prompt)
    ]

    response = llm.invoke(messages)

    # 解析结果
    try:
        result_text = response.content
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()

        ragas_result = json.loads(result_text)

        # 计算综合分数
        quality_map = {
            'excellent': 1.0, 'good': 0.8, 'acceptable': 0.6, 'poor': 0.3
        }
        relevance_map = {'high': 1.0, 'medium': 0.6, 'low': 0.3}
        ambiguity_map = {'clear': 1.0, 'ambiguous': 0.5, 'unclear': 0.0}

        score = (
            0.25 * relevance_map.get(ragas_result.get('context_relevance', 'medium'), 0.5) +
            0.25 * relevance_map.get(ragas_result.get('context_precision', 'medium'), 0.5) +
            0.30 * quality_map.get(ragas_result.get('selection_quality', 'acceptable'), 0.6) +
            0.20 * ambiguity_map.get(ragas_result.get('ambiguity', 'ambiguous'), 0.5)
        )

        ragas_result['score'] = score
        ragas_result['method'] = 'llm_ragas'
        ragas_result['confidence'] = ragas_result.get('overall_confidence', 'medium')

        print(f"    Context Relevance: {ragas_result.get('context_relevance')}")
        print(f"    Context Precision: {ragas_result.get('context_precision')}")
        print(f"    Selection Quality: {ragas_result.get('selection_quality')}")
        print(f"    Ambiguity: {ragas_result.get('ambiguity')}")
        print(f"    综合分数: {score:.3f}")

        return ragas_result

    except Exception as e:
        print(f"    错误: {e}")
        return {
            'confidence': 'low',
            'need_review': True,
            'method': 'llm_ragas',
            'error': str(e)
        }

# ============================================================================
# 节点6：最终输出
# ============================================================================

def final_output_node(state: GraphState) -> GraphState:
    """
    最终输出节点

    整合所有结果
    """
    query = state['query']
    llm_selection = state['llm_selection']
    confidence_evaluation = state['confidence_evaluation']

    print(f"\n[最终输出]")

    final_result = {
        'query': query,
        'classification': {
            'level1': llm_selection.get('level1'),
            'level2': llm_selection.get('level2'),
            'level3': llm_selection.get('level3'),
            'level4': llm_selection.get('level4'),
            'matched_item': llm_selection.get('matched_item'),
            'security_level': llm_selection.get('security_level')
        },
        'confidence': {
            'level': confidence_evaluation.get('confidence'),
            'score': confidence_evaluation.get('score'),
            'need_review': confidence_evaluation.get('need_review'),
            'method': confidence_evaluation.get('method')
        },
        'metrics': confidence_evaluation.get('metrics', {}),
        'reason': confidence_evaluation.get('reason', llm_selection.get('reason')),
        'timestamp': datetime.now().isoformat()
    }

    print(f"  分类: {final_result['classification']['level4']}")
    print(f"  具体项: {final_result['classification']['matched_item']}")
    print(f"  置信度: {final_result['confidence']['level']}")
    print(f"  需要review: {final_result['confidence']['need_review']}")

    state['final_result'] = final_result
    state['metadata'] = {
        'timestamp': datetime.now().isoformat(),
        'num_candidates': len(state.get('merged_candidates', []))
    }

    return state

# ============================================================================
# 构建图
# ============================================================================

def build_graph() -> StateGraph:
    """构建LangGraph"""

    # 创建图
    workflow = StateGraph(GraphState)

    # 添加节点
    workflow.add_node("bm25_retrieval", bm25_retrieval_node)
    workflow.add_node("vector_retrieval", vector_retrieval_node)
    workflow.add_node("merge_and_rank", merge_and_rank_node)
    workflow.add_node("llm_selection", llm_selection_node)
    workflow.add_node("confidence_evaluation", confidence_evaluation_node)
    workflow.add_node("final_output", final_output_node)

    # 设置入口点（并行召回）
    workflow.set_entry_point("bm25_retrieval")

    # 添加边
    workflow.add_edge("bm25_retrieval", "vector_retrieval")
    workflow.add_edge("vector_retrieval", "merge_and_rank")
    workflow.add_edge("merge_and_rank", "llm_selection")
    workflow.add_edge("llm_selection", "confidence_evaluation")
    workflow.add_edge("confidence_evaluation", "final_output")
    workflow.add_edge("final_output", END)

    # 编译
    app = workflow.compile()

    return app

# ============================================================================
# 主函数
# ============================================================================

def classify_field(query: str) -> Dict:
    """
    分类单个字段

    Args:
        query: 字段名

    Returns:
        分类结果
    """

    # 构建图
    app = build_graph()

    # 初始状态
    initial_state = {
        'query': query,
        'bm25_results': [],
        'vector_results': [],
        'merged_candidates': [],
        'llm_selection': {},
        'confidence_evaluation': {},
        'final_result': {},
        'metadata': {}
    }

    # 运行图
    final_state = app.invoke(initial_state)

    return final_state['final_result']


if __name__ == "__main__":
    # 测试
    result = classify_field("客户姓名")

    print("\n" + "="*80)
    print("最终结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))
