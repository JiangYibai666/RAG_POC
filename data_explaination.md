# 数据初始化与 mock_data / scripts 关系说明

---

## 一、初始化数据在做什么

快速开始里有两条初始化命令：

```bash
python scripts/generate_mock_data.py
python scripts/build_embeddings.py
```

### 第一步：`generate_mock_data.py`

这个脚本**完全在本地运行，不调用任何 LLM API**，它做三件事：

1. **生成市场知识库**（`mock_data/market_knowledge.jsonl`）  
   硬编码 5 种资产（Tesla Model S/X、Apple iPhone 15 Pro、Samsung Galaxy S24 Ultra、Sony PlayStation 5）的市场知识记录，包含资产名称、描述、关键词、典型价格区间等字段。

2. **生成交易记录**（`mock_data/transactions.json`）  
   使用固定随机种子 `Random(42)` 生成 **219 条随机合规交易**，并额外硬编码 **3 条专门的洗钱案例**（`tx_aml_0001/0002/0003`），合计 222 条交易。3 条 AML 案例均属于用户 U002，金额分别约为 $1,000,000 / $960,000 / $980,000，且 `counterparty_account_age_days` 极低（3 / 2 / 6 天），用于测试风险检测逻辑。

3. **生成测试用例**（`mock_data/test_cases.json`）  
   几条预设的标准测试输入，供手动或自动化测试使用。

### 第二步：`build_embeddings.py`

这个脚本读取第一步生成的 `market_knowledge.jsonl`，为每条记录计算向量，并输出向量矩阵文件（`mock_data/market_embeddings.npy`）。

向量算法是自研的 **128 维 hash-based bag-of-words**：

```python
def _embed(text: str, dim: int = 128) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    for token in text.lower().split():
        vec[hash(token) % dim] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec
```

不依赖任何外部 embedding API，完全离线。输出为 `(5, 128)` 的 float32 numpy 矩阵，持久化为 `.npy` 文件。

---

## 二、mock_data 和 scripts 的关系

两者是**生产者 → 数据仓库 → 消费者**的三层关系：

```
scripts/                         mock_data/
├── generate_mock_data.py  ──→   ├── market_knowledge.jsonl
│                                ├── transactions.json
│                                └── test_cases.json
└── build_embeddings.py    ──→       └── market_embeddings.npy
                                         ↑
                                   (读取 market_knowledge.jsonl 生成)
```

**`scripts/` 是生产者**，只需在初始化时运行一次，把数据写入 `mock_data/`。

**`mock_data/` 是静态数据仓库**，存放所有模拟业务数据，运行时不再修改。

**Agent / Tools 是消费者**，运行时直接读取 `mock_data/` 里的文件：

| 消费者 | 读取的文件 | 用途 |
|--------|-----------|------|
| `agents/market_agent/rag.py` | `market_knowledge.jsonl` + `market_embeddings.npy` | RAG 检索市场知识，混合名称重叠评分 + 余弦相似度 |
| `tools/transaction_query.py` | `transactions.json` | 按 user_id 过滤交易记录，供 TransactionAgent 做风险分析 |

### 补充说明

- `rag.py` 有缓存验证逻辑：启动时检查 `.npy` 行数是否与 `.jsonl` 记录数一致，不一致时自动重算，无需手动重跑 `build_embeddings.py`。
- `storage/task_store.py` 管理的 `aml.db`（SQLite）是**运行时产生的**，与 `mock_data/` 无关；它存储会话、任务、消息和 Artifact，由 `main.py` 启动时自动初始化（`init_db()`），无需手动执行。
- 如果修改了 `generate_mock_data.py` 中的市场知识内容，需要重新运行 `build_embeddings.py` 更新向量文件；如果只修改了交易记录，则不需要重跑 `build_embeddings.py`。
