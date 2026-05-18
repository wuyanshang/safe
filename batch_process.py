#!/usr/bin/env python3
"""
批量处理脚本

批量处理数据字典中的字段，进行分类和置信度评估
"""

import pandas as pd
import json
from typing import List, Dict
from tqdm import tqdm
from rag_evaluation_graph import classify_field, build_graph
from datetime import datetime

# ============================================================================
# 批量处理
# ============================================================================

def process_batch(
    queries: List[str],
    output_file: str = "classification_results.json",
    review_file: str = "need_review.json"
) -> Dict:
    """
    批量处理字段

    Args:
        queries: 字段名列表
        output_file: 输出文件
        review_file: 需要review的字段文件

    Returns:
        统计信息
    """

    print(f"开始批量处理 {len(queries)} 个字段...")
    print("="*80)

    # 构建图（复用）
    app = build_graph()

    results = []
    need_review = []

    stats = {
        'total': len(queries),
        'high_confidence': 0,
        'medium_confidence': 0,
        'low_confidence': 0,
        'need_review': 0,
        'rule_based': 0,
        'llm_ragas': 0,
        'errors': 0
    }

    # 处理每个字段
    for query in tqdm(queries, desc="处理中"):
        try:
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
            result = final_state['final_result']

            results.append(result)

            # 统计
            confidence = result['confidence']['level']
            method = result['confidence']['method']

            if confidence == 'high':
                stats['high_confidence'] += 1
            elif confidence == 'medium':
                stats['medium_confidence'] += 1
            else:
                stats['low_confidence'] += 1

            if result['confidence']['need_review']:
                stats['need_review'] += 1
                need_review.append(result)

            if method == 'rule_based':
                stats['rule_based'] += 1
            elif method == 'llm_ragas':
                stats['llm_ragas'] += 1

        except Exception as e:
            print(f"\n错误: {query} - {e}")
            stats['errors'] += 1
            results.append({
                'query': query,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })

    # 保存结果
    print(f"\n保存结果到 {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"保存需要review的字段到 {review_file}...")
    with open(review_file, 'w', encoding='utf-8') as f:
        json.dump(need_review, f, ensure_ascii=False, indent=2)

    # 打印统计
    print("\n" + "="*80)
    print("统计信息：")
    print(f"  总数: {stats['total']}")
    print(f"  高置信度: {stats['high_confidence']} ({stats['high_confidence']/stats['total']*100:.1f}%)")
    print(f"  中置信度: {stats['medium_confidence']} ({stats['medium_confidence']/stats['total']*100:.1f}%)")
    print(f"  低置信度: {stats['low_confidence']} ({stats['low_confidence']/stats['total']*100:.1f}%)")
    print(f"  需要review: {stats['need_review']} ({stats['need_review']/stats['total']*100:.1f}%)")
    print(f"\n方法分布：")
    print(f"  规则判断: {stats['rule_based']} ({stats['rule_based']/stats['total']*100:.1f}%)")
    print(f"  LLM评估: {stats['llm_ragas']} ({stats['llm_ragas']/stats['total']*100:.1f}%)")
    print(f"  错误: {stats['errors']}")

    return stats


def process_from_csv(
    csv_file: str,
    field_column: str = "field_name_cn",
    output_file: str = "classification_results.json",
    review_file: str = "need_review.json"
) -> Dict:
    """
    从CSV文件读取字段并处理

    Args:
        csv_file: CSV文件路径
        field_column: 字段名列名
        output_file: 输出文件
        review_file: 需要review的字段文件

    Returns:
        统计信息
    """

    print(f"从 {csv_file} 读取字段...")

    # 读取CSV
    df = pd.read_csv(csv_file)

    if field_column not in df.columns:
        raise ValueError(f"列 '{field_column}' 不存在于CSV文件中")

    # 提取字段名
    queries = df[field_column].dropna().tolist()

    print(f"读取到 {len(queries)} 个字段")

    # 批量处理
    stats = process_batch(queries, output_file, review_file)

    # 保存带分类结果的CSV
    results_df = pd.read_json(output_file)

    # 合并到原始数据
    df_with_results = df.merge(
        results_df,
        left_on=field_column,
        right_on='query',
        how='left'
    )

    output_csv = csv_file.replace('.csv', '_classified.csv')
    df_with_results.to_csv(output_csv, index=False, encoding='utf-8-sig')

    print(f"\n保存带分类结果的CSV到 {output_csv}")

    return stats


# ============================================================================
# 主函数
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 从CSV文件处理
        csv_file = sys.argv[1]
        field_column = sys.argv[2] if len(sys.argv) > 2 else "field_name_cn"

        stats = process_from_csv(csv_file, field_column)

    else:
        # 测试数据
        test_queries = [
            "客户姓名",
            "用户手机号",
            "身份证号码",
            "银行卡号",
            "交易金额",
            "账户余额",
            "登录密码",
            "邮箱地址",
            "家庭住址",
            "公司名称"
        ]

        stats = process_batch(test_queries)
