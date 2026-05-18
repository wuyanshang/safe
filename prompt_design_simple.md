# LLM提示词设计文档（简化版）

## 一、提示词模板（简化版）

### 基础模板

```python
PROMPT_TEMPLATE = """
你是一个数据安全分类专家。现在需要将一个数据字段精确分类到金融数据安全分级目录。

# 任务
给定字段名："{query}"

从以下候选分类中：
1. 选择最匹配的分类（四级子类）
2. 从该分类的"包含内容"中，选择最匹配的具体项

# 候选分类
{candidates}

# 输出要求
请以JSON格式输出：
{{
  "selected_candidate": 候选编号（1-{num_candidates}）,
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
```

---

## 二、候选格式化

### 简洁格式

```python
def format_candidates(candidates: List[Dict]) -> str:
    """
    格式化候选分类
    
    Args:
        candidates: 召回的候选列表
    
    Returns:
        格式化后的文本
    """
    text = ""
    for i, cand in enumerate(candidates, 1):
        text += f"""
候选{i}:
  分类: {cand['level1']} > {cand['level2']} > {cand['level3']} > {cand['level4']}
  内容: {cand['content']}
  级别: {cand['security_level']}级
  分数: {cand['score']:.2f}

"""
    return text.strip()
```

**示例输出**：
```
候选1:
  分类: 客户 > 个人 > 个人自然信息 > 个人基本概况信息
  内容: 个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等
  级别: 3级
  分数: 0.87

候选2:
  分类: 客户 > 单位 > 单位基本信息 > 管理层信息
  内容: 姓名、证件类型、证件号码、联系方式等
  级别: 3级
  分数: 0.72
```

---

## 三、完整Prompt构建

```python
def build_prompt(query: str, candidates: List[Dict]) -> str:
    """
    构建完整的prompt
    
    Args:
        query: 字段名
        candidates: 召回的候选列表
    
    Returns:
        完整的prompt字符串
    """
    
    # 格式化候选
    candidates_text = format_candidates(candidates)
    
    # 填充模板
    prompt = PROMPT_TEMPLATE.format(
        query=query,
        candidates=candidates_text,
        num_candidates=len(candidates)
    )
    
    return prompt
```

---

## 四、LLM调用

### OpenAI

```python
import openai
import json

def call_openai(prompt: str, model: str = "gpt-4o-mini") -> Dict:
    """
    调用OpenAI API
    
    Args:
        prompt: 完整的prompt
        model: 模型名称
    
    Returns:
        解析后的JSON结果
    """
    
    response = openai.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你是一个数据安全分类专家。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    
    result_text = response.choices[0].message.content
    result = json.loads(result_text)
    
    return result
```

### Claude

```python
import anthropic
import json
import re

def call_claude(prompt: str, model: str = "claude-3-5-haiku-20241022") -> Dict:
    """
    调用Claude API
    
    Args:
        prompt: 完整的prompt
        model: 模型名称
    
    Returns:
        解析后的JSON结果
    """
    
    client = anthropic.Anthropic()
    
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0,
        system="你是一个数据安全分类专家。",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )
    
    result_text = response.content[0].text
    
    # 提取JSON（Claude可能返回markdown格式）
    if "```json" in result_text:
        result_text = result_text.split("```json")[1].split("```")[0].strip()
    elif "```" in result_text:
        result_text = result_text.split("```")[1].split("```")[0].strip()
    
    result = json.loads(result_text)
    
    return result
```

---

## 五、完整分类流程

```python
from datetime import datetime

def classify_field(
    query: str,
    candidates: List[Dict],
    model: str = "gpt-4o-mini"
) -> Dict:
    """
    完整的字段分类流程
    
    Args:
        query: 字段名
        candidates: 召回的候选列表
        model: LLM模型
    
    Returns:
        分类结果
    """
    
    # 1. 构建prompt
    prompt = build_prompt(query, candidates)
    
    # 2. 调用LLM
    if model.startswith("gpt"):
        llm_result = call_openai(prompt, model)
    elif model.startswith("claude"):
        llm_result = call_claude(prompt, model)
    else:
        raise ValueError(f"Unsupported model: {model}")
    
    # 3. 增强结果
    selected_idx = llm_result['selected_candidate'] - 1
    selected_candidate = candidates[selected_idx]
    
    final_result = {
        **llm_result,
        'query': query,
        'level1': selected_candidate['level1'],
        'level2': selected_candidate['level2'],
        'level3': selected_candidate['level3'],
        'retrieval_score': selected_candidate['score'],
        'timestamp': datetime.now().isoformat()
    }
    
    return final_result


# 使用示例
result = classify_field(
    query="客户姓名",
    candidates=candidates,  # 从ES召回的结果
    model="gpt-4o-mini"
)

print(json.dumps(result, ensure_ascii=False, indent=2))
```

**输出示例**：
```json
{
  "selected_candidate": 1,
  "level4": "个人基本概况信息",
  "matched_item": "姓名",
  "security_level": 3,
  "confidence": "high",
  "reason": "字段名包含'姓名'，精确匹配",
  "query": "客户姓名",
  "level1": "客户",
  "level2": "个人",
  "level3": "个人自然信息",
  "retrieval_score": 0.87,
  "timestamp": "2024-05-18T12:00:00"
}
```

---

## 六、错误处理

### JSON解析失败

```python
def safe_parse_json(text: str) -> Dict:
    """安全解析JSON"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "{" in text and "}" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            text = text[start:end]
        
        return json.loads(text)
```

### 降级策略

```python
def classify_with_fallback(query: str, candidates: List[Dict]) -> Dict:
    """带降级的分类"""
    try:
        # 尝试LLM
        result = classify_field(query, candidates)
        return result
    
    except Exception as e:
        print(f"LLM failed: {e}, using fallback")
        
        # 降级：直接返回top-1
        best = candidates[0]
        
        # 简单提取第一个词作为matched_item
        content_items = best['content'].split('、')
        matched_item = content_items[0] if content_items else best['content'][:10]
        
        return {
            'level4': best['level4'],
            'matched_item': matched_item,
            'security_level': best['security_level'],
            'confidence': 'low',
            'reason': 'LLM失败，使用降级策略',
            'method': 'fallback',
            'query': query,
            'level1': best['level1'],
            'level2': best['level2'],
            'level3': best['level3'],
            'retrieval_score': best['score']
        }
```

---

## 七、批量处理

### 批量分类

```python
def classify_batch(
    queries: List[str],
    all_candidates: List[List[Dict]],
    model: str = "gpt-4o-mini",
    batch_size: int = 1
) -> List[Dict]:
    """
    批量分类
    
    Args:
        queries: 字段名列表
        all_candidates: 每个字段的候选列表
        model: LLM模型
        batch_size: 批次大小（目前只支持1）
    
    Returns:
        分类结果列表
    """
    results = []
    
    for i, (query, candidates) in enumerate(zip(queries, all_candidates)):
        print(f"处理 {i+1}/{len(queries)}: {query}")
        
        result = classify_with_fallback(query, candidates)
        results.append(result)
    
    return results
```

### 缓存优化

```python
import hashlib

# 简单的内存缓存
_cache = {}

def classify_with_cache(query: str, candidates: List[Dict], **kwargs) -> Dict:
    """带缓存的分类"""
    
    # 生成缓存key
    cache_key = hashlib.md5(query.encode()).hexdigest()
    
    # 检查缓存
    if cache_key in _cache:
        print(f"  从缓存返回: {query}")
        return _cache[cache_key]
    
    # 调用LLM
    result = classify_field(query, candidates, **kwargs)
    
    # 存入缓存
    _cache[cache_key] = result
    
    return result
```

---

## 八、完整示例

### 端到端示例

```python
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer

# 1. 初始化
es = Elasticsearch(["http://localhost:9200"])
model = SentenceTransformer('BAAI/bge-large-zh-v1.5')

# 2. 查询字段
query = "客户姓名"

# 3. 生成查询向量
query_vector = model.encode(query, normalize_embeddings=True).tolist()

# 4. 混合检索（BM25 + 向量）
response = es.search(
    index="data_security_classification",
    body={
        "size": 5,
        "query": {
            "match": {
                "bm25_text": query
            }
        },
        "knn": {
            "field": "embedding_vector",
            "query_vector": query_vector,
            "k": 5,
            "num_candidates": 100
        }
    }
)

# 5. 提取候选
candidates = []
for hit in response['hits']['hits']:
    source = hit['_source']
    candidates.append({
        'level1': source['level1'],
        'level2': source['level2'],
        'level3': source['level3'],
        'level4': source['level4'],
        'content': source['content'],
        'security_level': source['security_level'],
        'score': hit['_score']
    })

# 6. LLM判断
result = classify_field(query, candidates, model="gpt-4o-mini")

# 7. 输出结果
print(f"\n字段: {query}")
print(f"分类: {result['level1']} > {result['level2']} > {result['level3']} > {result['level4']}")
print(f"具体项: {result['matched_item']}")
print(f"安全级别: {result['security_level']}级")
print(f"置信度: {result['confidence']}")
print(f"理由: {result['reason']}")
```

---

## 九、配置建议

### 推荐配置

| 配置项 | 推荐值 | 说明 |
|--------|--------|------|
| 模型 | gpt-4o-mini | 性价比最高 |
| Temperature | 0 | 降低随机性 |
| 候选数量 | 3-5个 | 平衡准确率和成本 |
| 输出格式 | JSON | 便于解析 |

### 成本估算

**假设**：
- 5000个字段
- 模型：gpt-4o-mini
- 价格：$0.15/1M input tokens, $0.6/1M output tokens

**单次调用**：
- Input：~400 tokens
- Output：~80 tokens
- 成本：~$0.00008/次

**总成本**：
- 5000字段 × $0.00008 = **$0.4**

---

## 十、总结

### 简化点

1. **去除Few-shot示例**：简化prompt，降低token消耗
2. **简化候选格式**：只保留必要信息
3. **简化错误处理**：基本的降级策略

### 核心流程

```
召回（ES混合检索）→ 构建Prompt → LLM判断 → 返回结果
```

### 预期效果

- 准确率：85-90%
- 成本：$0.4（5000字段）
- 延迟：1-3秒/次
