# Chunk设计文档（简化版）

## 一、设计原则

### 切分粒度
**按四级子类切分**：每个四级分类 = 1个独立的chunk

### 双文本策略
- **content**：原始内容，用于BM25检索
- **bm25_text**：content + 层级关键词，优化BM25召回
- **embedding_text**：层级路径 + content，用于生成向量

---

## 二、Chunk结构（最简版）

```json
{
  "id": "chunk_001",
  
  // === 层级信息 ===
  "level1": "客户",
  "level2": "个人",
  "level3": "个人自然信息",
  "level4": "个人基本概况信息",
  
  // === 内容 ===
  "content": "个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等",
  
  // === 安全级别 ===
  "security_level": 3,
  
  // === BM25检索文本（优化版）===
  "bm25_text": "个人基本概况信息 客户 个人 个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等",
  
  // === Embedding文本（用于生成向量）===
  "embedding_text": "客户-个人-个人自然信息-个人基本概况信息。包含：个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等。安全级别3级。",
  
  // === 向量（由embedding模型生成）===
  "embedding_vector": [0.123, -0.456, 0.789, ...]
}
```

---

## 三、字段说明

### 必需字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 唯一标识 |
| level1 | string | 一级分类（如：客户） |
| level2 | string | 二级分类（如：个人） |
| level3 | string | 三级分类（如：个人自然信息） |
| level4 | string | 四级分类（如：个人基本概况信息） |
| content | string | 具体内容（如：姓名、性别、国籍...） |
| security_level | integer | 安全级别（1-5） |
| bm25_text | string | BM25检索文本 |
| embedding_text | string | 用于生成向量的文本 |
| embedding_vector | array | 向量（1024维） |

---

## 四、文本构建规则

### 1. content（原始内容）

**来源**：直接从附录A提取

**示例**：
```
"个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等"
```

**用途**：
- BM25检索的基础
- LLM从中提取具体项

---

### 2. bm25_text（BM25优化文本）

**构建规则**：
```python
bm25_text = f"{level4} {level1} {level2} {content}"
```

**示例**：
```
"个人基本概况信息 客户 个人 个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等"
```

**优化点**：
- 加入level4（分类名称）
- 加入level1（客户/单位）
- 加入level2（个人/单位）
- 保留原始content

**为什么这样做？**
```
查询："客户姓名"
分词：["客户", "姓名"]

原始content：
  "个人姓名、性别、国籍..."
  → 只包含"姓名"，不包含"客户" ❌

bm25_text：
  "个人基本概况信息 客户 个人 个人姓名、性别、国籍..."
  → 包含"客户"和"姓名" ✅
  → BM25得分更高
```

---

### 3. embedding_text（向量生成文本）

**构建规则**：
```python
embedding_text = f"{level1}-{level2}-{level3}-{level4}。包含：{content}。安全级别{security_level}级。"
```

**示例**：
```
"客户-个人-个人自然信息-个人基本概况信息。包含：个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等。安全级别3级。"
```

**为什么需要层级路径？**
```
查询："客户姓名"
向量包含：["客户", "姓名"]

只用content生成向量：
  "个人姓名、性别、国籍..."
  → 向量只包含["姓名", "性别", "国籍"]
  → 不包含"客户" ❌
  → 相似度低

用embedding_text生成向量：
  "客户-个人-个人自然信息-个人基本概况信息。包含：个人姓名、性别..."
  → 向量包含["客户", "个人", "姓名", "性别", "国籍"]
  → 包含"客户" ✅
  → 相似度高
```

---

## 五、Chunk构建流程

### 完整代码

```python
from sentence_transformers import SentenceTransformer

def build_chunk(category: dict, chunk_id: str, model: SentenceTransformer) -> dict:
    """
    构建chunk（简化版）
    
    Args:
        category: 原始分类数据
        chunk_id: chunk ID
        model: embedding模型
    
    Returns:
        完整的chunk
    """
    
    # 1. 构建bm25_text
    bm25_text = f"{category['level4']} {category['level1']} {category['level2']} {category['content']}"
    
    # 2. 构建embedding_text
    embedding_text = f"{category['level1']}-{category['level2']}-{category['level3']}-{category['level4']}。包含：{category['content']}。安全级别{category['security_level']}级。"
    
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
```

---

## 六、完整示例

### 示例1：个人基本概况信息

```json
{
  "id": "chunk_001",
  "level1": "客户",
  "level2": "个人",
  "level3": "个人自然信息",
  "level4": "个人基本概况信息",
  "content": "个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等",
  "security_level": 3,
  "bm25_text": "个人基本概况信息 客户 个人 个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等",
  "embedding_text": "客户-个人-个人自然信息-个人基本概况信息。包含：个人姓名、性别、国籍、民族、婚姻状况、证件类型、证件号码、证件生效日期、证件到期日期、家庭住址等。安全级别3级。",
  "embedding_vector": [0.123, -0.456, 0.789, ...]
}
```

### 示例2：个人联系信息

```json
{
  "id": "chunk_002",
  "level1": "客户",
  "level2": "个人",
  "level3": "个人自然信息",
  "level4": "个人联系信息",
  "content": "手机、固定电话、电子邮箱地址、微信号等",
  "security_level": 3,
  "bm25_text": "个人联系信息 客户 个人 手机、固定电话、电子邮箱地址、微信号等",
  "embedding_text": "客户-个人-个人自然信息-个人联系信息。包含：手机、固定电话、电子邮箱地址、微信号等。安全级别3级。",
  "embedding_vector": [0.234, -0.567, 0.891, ...]
}
```

---

## 七、与完整版的对比

| 字段 | 简化版 | 完整版 | 说明 |
|------|--------|--------|------|
| level1-4 | ✅ | ✅ | 必需 |
| content | ✅ | ✅ | 必需 |
| security_level | ✅ | ✅ | 必需 |
| bm25_text | ✅ | ✅ | 优化BM25 |
| embedding_text | ✅ | ✅ | 生成向量 |
| embedding_vector | ✅ | ✅ | 必需 |
| level2-4_definition | ❌ | ✅ | 简化版去除 |

**简化点**：
- 去除了definition字段（定义说明）
- embedding_text不包含定义，只包含层级路径和content

**影响**：
- 准确率略降（约3-5%）
- 但实现更简单，存储更小

---

## 八、总结

### 核心设计

1. **粒度**：按四级子类切分
2. **bm25_text**：content + 层级关键词（level1, level2, level4）
3. **embedding_text**：层级路径 + content
4. **向量**：对embedding_text生成

### 构建公式

```python
bm25_text = f"{level4} {level1} {level2} {content}"

embedding_text = f"{level1}-{level2}-{level3}-{level4}。包含：{content}。安全级别{security_level}级。"

embedding_vector = model.encode(embedding_text)
```

### 预期效果

- Chunk数量：100-200个
- 向量维度：1024维
- BM25准确率：75-80%
- 向量准确率：78-83%
- 混合准确率：80-85%
