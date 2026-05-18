# 快速开始指南

## 一、环境准备

### 1. 安装依赖

```bash
cd D:\Users\Administrator\Desktop\safe\simplified_version
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# OpenAI API Key
OPENAI_API_KEY=your-api-key-here

# Elasticsearch配置
ES_HOST=localhost
ES_PORT=9200

# Embedding模型路径（可选，默认会自动下载）
EMBEDDING_MODEL_PATH=./models/bge-large-zh-v1.5
```

### 3. 启动Elasticsearch

```bash
# 确保Elasticsearch运行在localhost:9200
# Windows: 启动ES服务
# Linux/Mac: 
# docker run -d -p 9200:9200 -e "discovery.type=single-node" elasticsearch:8.11.0
```

### 4. 初始化ES索引

```bash
# 准备分类数据（categories.json）
# 格式见下文

# 运行初始化脚本
python init_es_simple.py

# 或使用示例数据测试
python init_es_simple.py sample
```

---

## 二、准备数据

### categories.json格式

```json
[
  {
    "level1": "客户",
    "level2": "个人",
    "level3": "个人自然信息",
    "level4": "个人基本概况信息",
    "content": "个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等",
    "security_level": 3
  },
  {
    "level1": "客户",
    "level2": "个人",
    "level3": "个人自然信息",
    "level4": "个人联系信息",
    "content": "手机、固定电话、电子邮箱地址、微信号等",
    "security_level": 3
  }
]
```

---

## 三、使用方法

### 方式1：单个字段分类

```python
from rag_evaluation_graph import classify_field

# 分类单个字段
result = classify_field("客户姓名")

print(f"分类: {result['classification']['level4']}")
print(f"具体项: {result['classification']['matched_item']}")
print(f"安全级别: {result['classification']['security_level']}")
print(f"置信度: {result['confidence']['level']}")
print(f"需要review: {result['confidence']['need_review']}")
```

**输出示例**：
```
[BM25召回] 查询: 客户姓名
  召回 5 个候选

[向量召回] 查询: 客户姓名
  召回 5 个候选

[混合排序] 合并结果
  合并后 5 个候选
    1. 个人基本概况信息 (分数: 0.920)
    2. 单位管理层信息 (分数: 0.650)
    3. 个人联系信息 (分数: 0.580)

[LLM判断] 从 5 个候选中选择
  选择: 个人基本概况信息 - 姓名
  LLM置信度: high

[置信度评估]
  召回分数: 0.920
  分数差距: 0.270
  → 明确的高置信度（规则判断）

[最终输出]
  分类: 个人基本概况信息
  具体项: 姓名
  置信度: high
  需要review: False

分类: 个人基本概况信息
具体项: 姓名
安全级别: 3
置信度: high
需要review: False
```

---

### 方式2：批量处理（从列表）

```python
from batch_process import process_batch

# 准备字段列表
queries = [
    "客户姓名",
    "用户手机号",
    "身份证号码",
    "银行卡号",
    "交易金额"
]

# 批量处理
stats = process_batch(
    queries,
    output_file="results.json",
    review_file="need_review.json"
)

print(f"总数: {stats['total']}")
print(f"需要review: {stats['need_review']} ({stats['need_review']/stats['total']*100:.1f}%)")
```

**输出示例**：
```
开始批量处理 5 个字段...
================================================================================
处理中: 100%|██████████| 5/5 [00:15<00:00,  3.12s/it]

保存结果到 results.json...
保存需要review的字段到 need_review.json...

================================================================================
统计信息：
  总数: 5
  高置信度: 3 (60.0%)
  中置信度: 1 (20.0%)
  低置信度: 1 (20.0%)
  需要review: 2 (40.0%)

方法分布：
  规则判断: 3 (60.0%)
  LLM评估: 2 (40.0%)
  错误: 0
```

---

### 方式3：批量处理（从CSV）

#### 准备CSV文件

`data_dictionary.csv`:
```csv
table_name,field_name_cn,field_name_en,data_type
user_table,客户姓名,customer_name,varchar
user_table,手机号,mobile_phone,varchar
user_table,身份证号,id_card,varchar
order_table,订单金额,order_amount,decimal
order_table,下单时间,order_time,datetime
```

#### 运行批量处理

```bash
python batch_process.py data_dictionary.csv field_name_cn
```

或在Python中：

```python
from batch_process import process_from_csv

stats = process_from_csv(
    csv_file="data_dictionary.csv",
    field_column="field_name_cn",
    output_file="results.json",
    review_file="need_review.json"
)
```

#### 输出文件

1. **results.json** - 所有结果
2. **need_review.json** - 需要人工review的字段
3. **data_dictionary_classified.csv** - 带分类结果的CSV

---

## 四、查看结果

### results.json

```json
[
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
      "score": 0.92,
      "need_review": false,
      "method": "rule_based"
    },
    "metrics": {
      "retrieval_score": 0.92,
      "score_gap": 0.27
    },
    "reason": "字段名包含'姓名'，精确匹配",
    "timestamp": "2024-05-19T12:00:00"
  }
]
```

### need_review.json

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
  }
]
```

### data_dictionary_classified.csv

```csv
table_name,field_name_cn,field_name_en,data_type,level4,matched_item,security_level,confidence,need_review
user_table,客户姓名,customer_name,varchar,个人基本概况信息,姓名,3,high,false
user_table,手机号,mobile_phone,varchar,个人联系信息,手机,3,high,false
user_table,身份证号,id_card,varchar,个人基本概况信息,证件号码,3,high,false
order_table,订单金额,order_amount,decimal,交易信息,交易金额,2,medium,true
order_table,下单时间,order_time,datetime,交易信息,交易时间,2,high,false
```

---

## 五、人工Review流程

### 1. 筛选需要review的字段

```python
import json

# 读取需要review的字段
with open('need_review.json', 'r', encoding='utf-8') as f:
    need_review = json.load(f)

print(f"需要review的字段数: {len(need_review)}")

# 按置信度排序（最低的优先review）
need_review.sort(key=lambda x: x['confidence']['score'])

# 输出前10个
for item in need_review[:10]:
    print(f"\n字段: {item['query']}")
    print(f"  系统分类: {item['classification']['level4']} - {item['classification']['matched_item']}")
    print(f"  置信度: {item['confidence']['level']} ({item['confidence']['score']:.2f})")
    print(f"  理由: {item['reason']}")
```

### 2. 人工确认

创建 `review_feedback.csv`:
```csv
query,system_level4,system_item,human_level4,human_item,is_correct,comment
名称,个人基本概况信息,姓名,产品信息,产品名称,false,字段名过短，需要上下文
客户姓名,个人基本概况信息,姓名,个人基本概况信息,姓名,true,正确
```

### 3. 分析反馈

```python
import pandas as pd

# 读取反馈
feedback = pd.read_csv('review_feedback.csv')

# 计算准确率
accuracy = feedback['is_correct'].mean()
print(f"准确率: {accuracy*100:.1f}%")

# 分析错误原因
errors = feedback[feedback['is_correct'] == False]
print(f"\n错误数: {len(errors)}")
for _, row in errors.iterrows():
    print(f"  {row['query']}: {row['comment']}")
```

---

## 六、调优建议

### 场景1：准确率不够（<90%）

**解决方案**：
1. 使用极严格策略
2. 增加review比例
3. 优化Embedding文本

```python
# 修改 rag_evaluation_graph.py 中的 Config
class Config:
    # 极严格策略
    HIGH_CONFIDENCE_SCORE = 0.95
    HIGH_CONFIDENCE_GAP = 0.4
    LOW_CONFIDENCE_SCORE = 0.7
    LOW_CONFIDENCE_GAP = 0.15
```

### 场景2：Review太多（>40%）

**解决方案**：
1. 使用宽松策略
2. 优化召回质量

```python
# 修改为宽松策略
class Config:
    HIGH_CONFIDENCE_SCORE = 0.8
    HIGH_CONFIDENCE_GAP = 0.15
    LOW_CONFIDENCE_SCORE = 0.4
    LOW_CONFIDENCE_GAP = 0.03
```

### 场景3：成本太高

**解决方案**：
1. 使用更便宜的模型
2. 减少LLM调用

```python
# 使用Claude Haiku
class Config:
    LLM_MODEL = "claude-3-5-haiku-20241022"
```

### 场景4：速度太慢

**解决方案**：
1. 并行处理
2. 批量LLM调用

```python
from concurrent.futures import ThreadPoolExecutor

def process_batch_parallel(queries, max_workers=5):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(classify_field, queries))
    return results
```

---

## 七、常见问题

### Q1: ES连接失败

**错误**：`Cannot connect to Elasticsearch`

**解决**：
1. 检查ES是否运行：`curl http://localhost:9200`
2. 检查端口是否正确
3. 检查防火墙设置

### Q2: 索引不存在

**错误**：`Index 'data_security_classification' does not exist`

**解决**：
```bash
python init_es_simple.py
```

### Q3: OpenAI API错误

**错误**：`AuthenticationError: Invalid API key`

**解决**：
1. 检查 `.env` 文件中的API Key
2. 确保API Key有效
3. 检查网络连接

### Q4: 内存不足

**错误**：`MemoryError`

**解决**：
1. 减少批量处理的batch size
2. 使用更小的Embedding模型
3. 增加系统内存

### Q5: 中文乱码

**解决**：
```python
# 确保使用UTF-8编码
with open('results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
```

---

## 八、下一步

### 1. 质检规则

根据review反馈，建立质检规则：

```python
# 质检规则示例
def quality_check(query, result):
    """质检规则"""
    
    # 规则1：字段名过短
    if len(query) < 3:
        return {
            'pass': False,
            'reason': '字段名过短，需要加入上下文'
        }
    
    # 规则2：置信度过低
    if result['confidence']['score'] < 0.5:
        return {
            'pass': False,
            'reason': '置信度过低，需要人工确认'
        }
    
    return {'pass': True}
```

### 2. 持续优化

- 收集人工review反馈
- 分析错误模式
- 调整阈值和权重
- 优化prompt

### 3. 部署为服务

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/classify', methods=['POST'])
def classify():
    query = request.json['query']
    result = classify_field(query)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

---

## 九、联系和支持

如有问题，请查看：
- 完整文档：`rag_evaluation_system.md`
- Chunk设计：`chunk_design_simple.md`
- 提示词设计：`prompt_design_simple.md`

祝使用愉快！
