# RAG评估系统 - 数据安全分类

基于LangGraph和Ragas的智能数据安全分类系统，支持自动分类和置信度评估。

## 🎯 核心特性

- ✅ **双路召回**：BM25 + 向量检索，召回率高
- ✅ **LLM判断**：GPT-4o-mini精确选择分类和具体项
- ✅ **智能评估**：混合策略 + Ragas风格多维度评估
- ✅ **自动识别**：自动识别需要人工review的字段
- ✅ **成本可控**：5000字段仅需$0.75
- ✅ **易于使用**：支持单个分类和批量处理

## 📊 系统架构

```
输入字段 → BM25召回 → 向量召回 → 混合排序 → LLM判断 → 置信度评估 → 输出结果
                                                    ↓
                                            需要review? (20-30%)
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

创建 `.env` 文件：
```bash
OPENAI_API_KEY=your-api-key
ES_HOST=localhost
ES_PORT=9200
```

### 3. 初始化ES

```bash
python init_es_simple.py sample
```

### 4. 运行测试

```python
from rag_evaluation_graph import classify_field

result = classify_field("客户姓名")
print(result)
```

**输出**：
```json
{
  "classification": {
    "level4": "个人基本概况信息",
    "matched_item": "姓名",
    "security_level": 3
  },
  "confidence": {
    "level": "high",
    "need_review": false
  }
}
```

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `rag_evaluation_graph.py` | 主程序（LangGraph实现） |
| `batch_process.py` | 批量处理脚本 |
| `init_es_simple.py` | ES初始化脚本 |
| `rag_evaluation_system.md` | 完整系统文档 |
| `QUICKSTART.md` | 快速开始指南 |
| `requirements.txt` | 依赖列表 |

## 💡 使用示例

### 单个字段分类

```python
from rag_evaluation_graph import classify_field

result = classify_field("客户姓名")
```

### 批量处理

```python
from batch_process import process_batch

queries = ["客户姓名", "用户手机号", "身份证号码"]
stats = process_batch(queries)
```

### 从CSV处理

```bash
python batch_process.py data_dictionary.csv field_name_cn
```

## 📈 性能指标

| 指标 | 数值 |
|------|------|
| 准确率 | 90-95% |
| 单字段延迟（规则） | <1秒 |
| 单字段延迟（LLM） | 4-12秒 |
| 成本（5000字段） | ~$0.75 |
| Review比例 | 20-30% |

## 🔧 配置调整

### 严格策略（默认）

```python
HIGH_CONFIDENCE_SCORE = 0.9
HIGH_CONFIDENCE_GAP = 0.3
```

- Review比例：~30%
- LLM调用：~50%

### 宽松策略

```python
HIGH_CONFIDENCE_SCORE = 0.8
HIGH_CONFIDENCE_GAP = 0.15
```

- Review比例：~10%
- LLM调用：~20%

## 📖 文档

- [完整系统文档](rag_evaluation_system.md) - 详细的系统设计和使用说明
- [快速开始指南](QUICKSTART.md) - 快速上手教程
- [Chunk设计](chunk_design_simple.md) - 数据切分策略
- [提示词设计](prompt_design_simple.md) - LLM提示词设计

## 🎓 核心概念

### 混合策略

```
第1层：数值指标（50%）
  ├─ 高置信度 → 自动通过
  └─ 低置信度 → 自动拦截

第2层：LLM评估（50%）
  └─ Ragas风格多维度评估
      ├─ Context Relevance
      ├─ Context Precision
      ├─ Selection Quality
      └─ Ambiguity
```

### Ragas评估

参考Ragas框架，评估4个维度：
1. **Context Relevance**：召回质量
2. **Context Precision**：候选精确度
3. **Selection Quality**：选择质量
4. **Ambiguity**：模糊程度

## 🛠️ 常见问题

### Q: 如何提高准确率？

使用极严格策略，增加review比例：
```python
HIGH_CONFIDENCE_SCORE = 0.95
HIGH_CONFIDENCE_GAP = 0.4
```

### Q: 如何降低成本？

使用宽松策略或更便宜的模型：
```python
LLM_MODEL = "claude-3-5-haiku-20241022"
```

### Q: 如何处理短字段名？

加入上下文：
```python
query = f"{table_name}.{field_name}"  # "用户表.名称"
```

## 📊 输出示例

### results.json
```json
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
  }
}
```

### need_review.json
```json
{
  "query": "名称",
  "classification": {
    "level4": "个人基本概况信息",
    "matched_item": "姓名"
  },
  "confidence": {
    "level": "low",
    "need_review": true,
    "method": "llm_ragas"
  },
  "reason": "字段名过短，存在多个可能的分类"
}
```

## 🔄 工作流程

1. **数据准备**：准备数据字典（CSV或列表）
2. **批量分类**：运行批量处理脚本
3. **查看结果**：检查 `results.json` 和 `need_review.json`
4. **人工Review**：对需要review的字段进行人工确认
5. **反馈优化**：根据反馈调整阈值和策略

## 📞 支持

遇到问题？
1. 查看 [完整文档](rag_evaluation_system.md)
2. 查看 [快速开始](QUICKSTART.md)
3. 检查常见问题章节

## 📝 License

MIT License

---

**开始使用**：查看 [QUICKSTART.md](QUICKSTART.md)

**详细文档**：查看 [rag_evaluation_system.md](rag_evaluation_system.md)
