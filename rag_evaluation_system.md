# RAG评估系统 - 完整文档

## 一、系统概述

### 1.1 系统架构

本系统使用LangGraph实现了一个完整的RAG（检索增强生成）评估流程，用于数据安全分类场景。

```
┌─────────────────────────────────────────────────────────────┐
│                      RAG评估系统                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  输入：字段名（如"客户姓名"）                                │
│                                                             │
│  ┌─────────────┐                                           │
│  │ 节点1：BM25召回 │                                         │
│  │ - ES全文检索  │                                          │
│  │ - Top-10候选  │                                          │
│  └──────┬──────┘                                           │
│         │                                                   │
│  ┌──────▼──────┐                                           │
│  │ 节点2：向量召回 │                                         │
│  │ - 语义检索    │                                          │
│  │ - Top-10候选  │                                          │
│  └──────┬──────┘                                           │
│         │                                                   │
│  ┌──────▼──────┐                                           │
│  │ 节点3：混合排序 │                                         │
│  │ - 合并去重    │                                          │
│  │ - 加权排序    │                                          │
│  │ - Top-5候选   │                                          │
│  └──────┬──────┘                                           │
│         │                                                   │
│  ┌──────▼──────┐                                           │
│  │ 节点4：LLM判断  │                                         │
│  │ - 选择分类    │                                          │
│  │ - 提取具体项  │                                          │
│  └──────┬──────┘                                           │
│         │                                                   │
│  ┌──────▼──────┐                                           │
│  │ 节点5：置信度评估│                                        │
│  │ - 混合策略    │                                          │
│  │ - Ragas评估   │                                          │
│  └──────┬──────┘                                           │
│         │                                                   │
│  ┌──────▼──────┐                                           │
│  │ 节点6：最终输出 │                                         │
│  │ - 整合结果    │                                          │
│  └─────────────┘                                           │
│                                                             │
│  输出：分类结果 + 置信度 + 是否需要review                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、核心组件

### 2.1 节点1：BM25召回

**功能**：使用Elasticsearch的BM25算法进行全文检索

**输入**：
- 查询字段名（如"客户姓名"）

**处理**：
```python
# ES查询
{
  "query": {
    "match": {
      "bm25_text": "客户姓名"
    }
  },
  "size": 10
}
```

**输出**：
- Top-10候选
- 每个候选包含：分类信息、内容、BM25分数

**特点**：
- ✅ 精确关键词匹配
- ✅ 快速（<100ms）
- ✅ 对短查询效果好

---

### 2.2 节点2：向量召回

**功能**：使用向量相似度进行语义检索

**输入**：
- 查询字段名

**处理**：
```python
# 1. 生成查询向量
query_vector = embedding_model.encode("客户姓名")

# 2. ES向量查询
{
  "knn": {
    "field": "embedding_vector",
    "query_vector": query_vector,
    "k": 10,
    "num_candidates": 100
  }
}
```

**输出**：
- Top-10候选
- 每个候选包含：分类信息、内容、向量分数

**特点**：
- ✅ 语义理解
- ✅ 可以匹配同义词
- ✅ 对长查询效果好

---

### 2.3 节点3：混合排序

**功能**：合并BM25和向量召回结果，重新排序

**输入**：
- BM25召回结果（10个）
- 向量召回结果（10个）

**处理**：
```python
# 1. 合并去重
candidates = merge(bm25_results, vector_results)

# 2. 归一化分数
bm25_score_norm = normalize(bm25_score)
vector_score_norm = normalize(vector_score)

# 3. 加权融合
final_score = 0.4 * bm25_score_norm + 0.6 * vector_score_norm

# 4. 排序并取Top-5
candidates = sort_and_top_k(candidates, k=5)
```

**输出**：
- Top-5候选
- 每个候选包含：分类信息、内容、混合分数

**权重说明**：
- BM25: 0.4（关键词匹配）
- 向量: 0.6（语义匹配）

---

### 2.4 节点4：LLM判断

**功能**：让LLM从候选中选择最匹配的分类和具体项

**输入**：
- 查询字段名
- Top-5候选

**处理**：
```python
prompt = f"""
你是一个数据安全分类专家。

查询字段：{query}

候选分类：
{format_candidates(candidates)}

请选择最匹配的分类和具体项。

输出JSON：
{{
  "selected_candidate": 候选编号,
  "level4": "四级分类名称",
  "matched_item": "具体项名称",
  "security_level": 安全级别,
  "confidence": "high/medium/low",
  "reason": "选择理由"
}}
"""

response = llm.invoke(prompt)
```

**输出**：
- 选择的分类（四级）
- 匹配的具体项
- 安全级别
- LLM的置信度
- 选择理由

**模型**：
- GPT-4o-mini（默认）
- Temperature: 0（确定性）

---

### 2.5 节点5：置信度评估（核心）

**功能**：评估分类结果的置信度，决定是否需要人工review

**策略**：混合策略 + Ragas评估

#### 第1层：数值指标（严格策略）

```python
retrieval_score = selected['final_score']
score_gap = candidates[0]['score'] - candidates[1]['score']

# 明确的高置信度
if retrieval_score > 0.9 and score_gap > 0.3:
    confidence = "high"
    need_review = False
    method = "rule_based"

# 明确的低置信度
elif retrieval_score < 0.6 or score_gap < 0.1:
    confidence = "low"
    need_review = True
    method = "rule_based"

# 模糊情况 → 进入第2层
else:
    # 使用LLM评估
```

**阈值说明**（严格策略）：
- 高置信度：score > 0.9 且 gap > 0.3
- 低置信度：score < 0.6 或 gap < 0.1

#### 第2层：LLM评估（Ragas风格）

对于模糊情况，使用LLM进行精细评估：

```python
prompt = f"""
评估这个数据分类结果的质量（参考Ragas评估框架）。

查询字段：{query}
候选：{candidates}
选择：{selected}

请从以下维度评估：

1. Context Relevance（上下文相关度）：
   召回的候选与查询的相关性如何？

2. Context Precision（上下文精确度）：
   召回的候选是否包含所需信息？

3. Selection Quality（选择质量）：
   选择的结果是否合理？

4. Ambiguity（模糊程度）：
   是否有多个候选都很合适？

输出JSON：
{{
  "context_relevance": "high/medium/low",
  "context_precision": "high/medium/low",
  "selection_quality": "excellent/good/acceptable/poor",
  "ambiguity": "clear/ambiguous/unclear",
  "overall_confidence": "high/medium/low",
  "need_review": true/false,
  "reason": "简短说明"
}}
"""
```

**Ragas维度说明**：

| 维度 | 说明 | 来源 |
|------|------|------|
| Context Relevance | 召回的候选与查询的相关性 | Ragas |
| Context Precision | 候选是否包含所需信息 | Ragas |
| Selection Quality | 选择的结果是否合理 | 自定义 |
| Ambiguity | 是否存在多个合适的候选 | 自定义 |

**综合评分**：
```python
score = (
    0.25 * context_relevance +
    0.25 * context_precision +
    0.30 * selection_quality +  # 权重最高
    0.20 * (1 - ambiguity)      # 越清晰越好
)

if score >= 0.8:
    confidence = "high"
    need_review = False
elif score >= 0.6:
    confidence = "medium"
    need_review = True
else:
    confidence = "low"
    need_review = True
```

---

### 2.6 节点6：最终输出

**功能**：整合所有结果，生成最终输出

**输出格式**：
```json
{
  "query": "客户姓名",
  "classification": {
    "level1": "客户",
    "level2": "个人",
    "level3": "个人自然信息",
    "level4": "个人基本概况信息",
    "matched_item": "姓名",
    "security_level": 3
  },
  "confidence": {
    "level": "high",
    "score": 0.87,
    "need_review": false,
    "method": "rule_based"
  },
  "metrics": {
    "retrieval_score": 0.92,
    "score_gap": 0.45
  },
  "reason": "字段名包含'姓名'，精确匹配",
  "timestamp": "2024-05-19T12:00:00"
}
```

---

## 三、使用方法

### 3.1 环境准备

#### 安装依赖

```bash
pip install langgraph langchain langchain-openai elasticsearch sentence-transformers pandas tqdm
```

#### 配置环境变量

```bash
# OpenAI API Key
export OPENAI_API_KEY="your-api-key"

# Elasticsearch
export ES_HOST="localhost"
export ES_PORT="9200"
```

#### 启动Elasticsearch

```bash
# 确保ES运行在localhost:9200
# 并且已经创建了索引（使用init_es_simple.py）
```

---

### 3.2 单个字段分类

```python
from rag_evaluation_graph import classify_field

# 分类单个字段
result = classify_field("客户姓名")

print(result)
# {
#   "query": "客户姓名",
#   "classification": {
#     "level4": "个人基本概况信息",
#     "matched_item": "姓名",
#     "security_level": 3
#   },
#   "confidence": {
#     "level": "high",
#     "need_review": false
#   }
# }
```

---

### 3.3 批量处理

#### 方式1：从列表处理

```python
from batch_process import process_batch

queries = [
    "客户姓名",
    "用户手机号",
    "身份证号码",
    "银行卡号"
]

stats = process_batch(
    queries,
    output_file="results.json",
    review_file="need_review.json"
)
```

#### 方式2：从CSV文件处理

```python
from batch_process import process_from_csv

stats = process_from_csv(
    csv_file="data_dictionary.csv",
    field_column="field_name_cn",
    output_file="results.json",
    review_file="need_review.json"
)
```

**CSV格式**：
```csv
table_name,field_name_cn,field_name_en
user_table,客户姓名,customer_name
user_table,手机号,mobile_phone
...
```

#### 命令行使用

```bash
# 批量处理CSV文件
python batch_process.py data_dictionary.csv field_name_cn

# 测试模式（使用内置测试数据）
python batch_process.py
```

---

### 3.4 输出文件

#### results.json（所有结果）

```json
[
  {
    "query": "客户姓名",
    "classification": {
      "level4": "个人基本概况信息",
      "matched_item": "姓名",
      "security_level": 3
    },
    "confidence": {
      "level": "high",
      "score": 0.92,
      "need_review": false,
      "method": "rule_based"
    },
    "timestamp": "2024-05-19T12:00:00"
  },
  ...
]
```

#### need_review.json（需要人工review的）

```json
[
  {
    "query": "名称",
    "classification": {
      "level4": "个人基本概况信息",
      "matched_item": "姓名",
      "security_level": 3
    },
    "confidence": {
      "level": "low",
      "score": 0.55,
      "need_review": true,
      "method": "llm_ragas"
    },
    "reason": "字段名过短，存在多个可能的分类",
    "timestamp": "2024-05-19T12:01:00"
  },
  ...
]
```

#### data_dictionary_classified.csv（带分类结果的CSV）

```csv
table_name,field_name_cn,field_name_en,level4,matched_item,security_level,confidence,need_review
user_table,客户姓名,customer_name,个人基本概况信息,姓名,3,high,false
user_table,手机号,mobile_phone,个人联系信息,手机,3,high,false
...
```

---

## 四、配置说明

### 4.1 核心配置

在 `rag_evaluation_graph.py` 中的 `Config` 类：

```python
class Config:
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
```

### 4.2 调整策略

#### 宽松策略（更少review）

```python
HIGH_CONFIDENCE_SCORE = 0.8
HIGH_CONFIDENCE_GAP = 0.15
LOW_CONFIDENCE_SCORE = 0.4
LOW_CONFIDENCE_GAP = 0.03
```

**效果**：
- 需要review的比例：~10%
- LLM调用比例：~20%

#### 严格策略（更多review，默认）

```python
HIGH_CONFIDENCE_SCORE = 0.9
HIGH_CONFIDENCE_GAP = 0.3
LOW_CONFIDENCE_SCORE = 0.6
LOW_CONFIDENCE_GAP = 0.1
```

**效果**：
- 需要review的比例：~30%
- LLM调用比例：~50%

#### 极严格策略（最高准确性）

```python
HIGH_CONFIDENCE_SCORE = 0.95
HIGH_CONFIDENCE_GAP = 0.4
LOW_CONFIDENCE_SCORE = 0.7
LOW_CONFIDENCE_GAP = 0.15
```

**效果**：
- 需要review的比例：~50%
- LLM调用比例：~70%

---

## 五、性能和成本

### 5.1 性能指标

| 指标 | 数值 |
|------|------|
| 单个字段延迟（规则判断） | <1秒 |
| 单个字段延迟（LLM评估） | 4-12秒 |
| 批量处理速度 | ~100字段/分钟 |
| 准确率（预期） | 90-95% |

### 5.2 成本估算

**假设**：5000个字段，严格策略

| 项目 | 比例 | 调用次数 | 单价 | 成本 |
|------|------|---------|------|------|
| 规则判断 | 50% | 0 | $0 | $0 |
| LLM判断 | 100% | 5000 | $0.0001 | $0.5 |
| LLM评估（Ragas） | 50% | 2500 | $0.0001 | $0.25 |
| **总计** | - | - | - | **$0.75** |

**说明**：
- LLM判断：所有字段都需要
- LLM评估：只有模糊情况需要（~50%）

### 5.3 优化建议

#### 降低成本

1. **调整策略为宽松**：
   - LLM调用比例降到20%
   - 成本降到$0.6

2. **使用更便宜的模型**：
   - Claude Haiku: 成本降低50%
   - 总成本: $0.4

#### 提高速度

1. **并行处理**：
   ```python
   from concurrent.futures import ThreadPoolExecutor

   with ThreadPoolExecutor(max_workers=5) as executor:
       results = list(executor.map(classify_field, queries))
   ```

2. **批量LLM调用**：
   - 一次调用处理多个字段
   - 速度提升3-5倍

---

## 六、监控和调优

### 6.1 统计信息

批量处理后会输出统计信息：

```
统计信息：
  总数: 5000
  高置信度: 2500 (50.0%)
  中置信度: 1500 (30.0%)
  低置信度: 1000 (20.0%)
  需要review: 2500 (50.0%)

方法分布：
  规则判断: 2500 (50.0%)
  LLM评估: 2500 (50.0%)
  错误: 0
```

### 6.2 质量监控

#### 人工review反馈

```python
# 收集人工review的反馈
review_feedback = {
    "query": "名称",
    "system_result": "个人基本概况信息 - 姓名",
    "human_result": "产品信息 - 产品名称",
    "is_correct": False
}

# 分析错误原因
# 1. 字段名过短
# 2. 缺少上下文
# 3. 需要加入质检规则
```

#### 调整阈值

根据反馈调整阈值：

```python
# 如果高置信度的错误率 > 5%
# → 提高HIGH_CONFIDENCE_SCORE

# 如果需要review的比例 > 40%
# → 降低阈值，减少review
```

---

## 七、常见问题

### Q1: 如何提高准确率？

**A**: 
1. 使用极严格策略（更多review）
2. 优化Embedding文本（加入更多上下文）
3. 调整混合排序权重
4. 使用更强的LLM模型（GPT-4o）

### Q2: 如何降低成本？

**A**:
1. 使用宽松策略（减少LLM调用）
2. 使用更便宜的模型（Claude Haiku）
3. 批量处理（减少API调用次数）
4. 缓存结果（相同查询不重复调用）

### Q3: 如何处理短字段名？

**A**:
短字段名（如"名称"、"ID"）容易产生歧义，建议：
1. 加入表名作为上下文："用户表.名称"
2. 加入字段英文名："名称 name"
3. 设置质检规则，拦截过短的字段名

### Q4: 如何集成到现有系统？

**A**:
```python
# 作为API服务
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/classify', methods=['POST'])
def classify():
    query = request.json['query']
    result = classify_field(query)
    return jsonify(result)

if __name__ == '__main__':
    app.run(port=5000)
```

### Q5: 如何处理错误？

**A**:
系统会自动捕获错误并记录：
```python
{
  "query": "xxx",
  "error": "错误信息",
  "timestamp": "2024-05-19T12:00:00"
}
```

建议：
1. 检查ES连接
2. 检查LLM API Key
3. 检查输入格式

---

## 八、总结

### 8.1 核心优势

1. **高准确性**：
   - 混合召回（BM25 + 向量）
   - LLM判断
   - Ragas风格评估
   - 预期准确率：90-95%

2. **智能置信度评估**：
   - 混合策略（规则 + LLM）
   - 多维度评估（Ragas）
   - 自动识别需要review的字段

3. **成本可控**：
   - 明确情况用规则（免费）
   - 模糊情况用LLM（按需）
   - 5000字段成本：~$0.75

4. **易于使用**：
   - 单个字段分类
   - 批量处理
   - CSV导入导出

### 8.2 适用场景

- ✅ 数据安全分类
- ✅ 数据字典管理
- ✅ 数据治理
- ✅ 合规检查

### 8.3 下一步

1. **质检规则**：根据review反馈，建立质检规则
2. **持续优化**：调整阈值和权重
3. **扩展功能**：支持更多数据源
4. **API服务**：部署为REST API

---

## 附录

### A. 文件清单

```
simplified_version/
├── rag_evaluation_graph.py      # 主程序（LangGraph实现）
├── batch_process.py              # 批量处理脚本
├── init_es_simple.py             # ES初始化脚本
├── chunk_design_simple.md        # Chunk设计文档
├── prompt_design_simple.md       # 提示词设计文档
└── rag_evaluation_system.md      # 本文档
```

### B. 依赖版本

```
langgraph>=0.0.20
langchain>=0.1.0
langchain-openai>=0.0.5
elasticsearch>=8.0.0
sentence-transformers>=2.2.0
pandas>=2.0.0
tqdm>=4.65.0
```

### C. 参考资料

- [Ragas评估框架](https://github.com/explodinggradients/ragas)
- [LangGraph文档](https://python.langchain.com/docs/langgraph)
- [Elasticsearch向量检索](https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html)
