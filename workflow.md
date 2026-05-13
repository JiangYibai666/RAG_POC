# 整体工作流架构

```
┌────────────────────────────────────────────────────────────────────────┐
│                         python3 main.py                                │
└────────────────┬─────────────────────────────────────────────────────┘
                 │
                 ├─ 步骤 0：系统初始化
                 │   ├─ init_db() → SQLite schema 建表
                 │   ├─ mp.Process × 3 → 并发启动 3 个 Agent 服务
                 │   │   ├─ HostAgent (port 10000)
                 │   │   ├─ MarketAgent (port 10001)
                 │   │   └─ TransactionAgent (port 10002)
                 │   └─ CLI 启动 → 进入交互提示符 `>`
                 │
                 └─ 步骤 1：用户输入 → CLI 接收（cli/chat.py）
                     │
                     ├─ 用户输入："User U002 sold a Tesla Model X for $1,000,000"
                     │
                     └─ CLI 转发 → HostAgent (HTTP POST /tasks/sendSubscribe)
```

---

## 第 I 阶段：HostAgent 协调流程

位置：[agents/host_agent/graph.py](agents/host_agent/graph.py) 的 `run_host_investigation()`

```
HostAgent 收到用户查询
    │
    ├─ 步骤 1.1：解析意图（parse_intent）
    │   ├─ 正则提取 user_id （U002）
    │   ├─ 正则提取 asset（Tesla Model X）
    │   ├─ 正则提取 transaction_amount（1,000,000）
    │   └─ 输出：parsed = { user_id, asset, transaction_amount, ... }
    │
    ├─ 步骤 1.2：创建 session（数据库持久化）
    │   └─ create_session(session_id, original_query) → SQLite
    │
    ├─ 步骤 1.3：并发调用两个子 Agent（via A2AClient HTTP）
    │   │
    │   ├─ 并行路 A：MarketAgent（价格异常侦测）
    │   │   └─ POST /tasks/send → MarketAgent
    │   │       └─ [执行第 II 阶段：RAG + Z-score]
    │   │
    │   └─ 并行路 B：TransactionAgent（行为异常侦测）
    │       └─ POST /tasks/send → TransactionAgent
    │           └─ [执行第 III 阶段：新账户 + 结构化检测]
    │
    ├─ 步骤 1.4：收集两路结果
    │   ├─ market_data = { asset, fair_range, historical_mean, deviation_sigma, verdict, ... }
    │   └─ tx_data = { user_id, new_account_counterparties, structuring verdict, ... }
    │
    └─ 步骤 1.5：综合裁定（_risk_from_evidence）
        └─ 规则树：sigma >= 10? → CRITICAL
                   sigma >= 5 AND (新账户 OR 结构化)? → CRITICAL
                   sigma >= 3? → HIGH
                   sigma >= 2? → MEDIUM
                   else → LOW
        └─ 输出：final_risk_level（例如 CRITICAL）
        └─ 保存到 SQLite sessions.final_report + sessions.risk_level
```

---

## 第 II 阶段：MarketAgent + RAG 检索详解

位置：[agents/market_agent/graph.py](agents/market_agent/graph.py) + [agents/market_agent/rag.py](agents/market_agent/rag.py)

### RAG 的四步工作机制：

#### 步骤 2.1：向量化查询文本
```python
# [agents/market_agent/rag.py] _simple_embed()
text = "User U002 sold a Tesla Model X for $1,000,000"
│
├─ 分词（lower().split()）
│  → ["user", "u002", "sold", "a", "tesla", "model", "x", "for", "$1", "000", "000"]
│
└─ Hash Bag-of-Words 向量化（dim=128）
   ├─ 为每个 token 计算 idx = hash(token) % 128
   ├─ vec[idx] += 1.0  （多个 token 映射相同位置会累加）
   └─ 向量归一化 → query_vector（128 维）
```

#### 步骤 2.2：加载市场知识库 + 预计算向量
```python
# [agents/market_agent/rag.py] _load_kb() + _load_embeddings()

从 mockdata/market_knowledge.jsonl 读入 5 条市场记录：
   record[0] = { asset_id: "tesla_model_x_2024",
                 asset_name: "Tesla Model X 2024",
                 description: "All-electric luxury SUV.",
                 historical_mean: 95000,
                 historical_stddev: 12000,
                 ... }
   record[1] = { ... Tesla Model S ... }
   record[2] = { ... Porsche 911 ... }
   ...

检查 market_embeddings.npy 是否存在且行数匹配：
   ├─ 若匹配：直接加载缓存的 (5, 128) numpy 矩阵
   └─ 若不匹配：当场重新生成向量
       ├─ 对每条 record：text = asset_name + " " + description
       ├─ 调用 _simple_embed(text, dim=128)
       └─ vstack → (5, 128) 矩阵保存回 .npy
```

#### 步骤 2.3：计算相似度（双层评分）
```python
# [agents/market_agent/rag.py] retrieve_market_entries()

cosine_scores = embeddings @ query_vector
   → [0.72, 0.81, 0.45, 0.38, 0.29]  （5 条记录的余弦相似度）

query_tokens = { "user", "u002", "sold", "tesla", "model", "x", ... }

FOR each record:
   name_overlap = 该 record 的 asset_name 有多少 token 出现在 query 里
       record[0]: Tesla Model X 2024
           → { "tesla", "model", "x", "2024" } ∩ query_tokens
           → overlap = 3/4 = 0.75  【强匹配】
       
       record[1]: Tesla Model S 2024
           → { "tesla", "model", "s", "2024" } ∩ query_tokens
           → overlap = 2/4 = 0.5   【弱匹配】
       
       record[2]: Porsche 911 Turbo
           → { "porsche", "911", "turbo" } ∩ query_tokens
           → overlap = 0/3 = 0.0   【无匹配】

mixed_score = (name_overlap, cosine_similarity)  【元组排序：先比较名称，再比较相似度】

排序结果：
   record[0]: (0.75, 0.72) ← 强名称匹配 + 高相似度 → 排名第一
   record[1]: (0.5, 0.81)  ← 弱名称匹配（即使相似度稍高也排在后）
   record[2]: (0.0, 0.45)  ← 无名称匹配
```

#### 步骤 2.4：应用 RAG 策略
```python
best_name_score = 0.75  (record[0] 的最高分)

策略：
  IF best_name_score >= 0.5:  【强匹配情况】
      return [records[0]]  【只返回 1 条，避免价格均值被稀释】
      
  ELIF best_name_score == 0.0:  【完全无名称匹配】
      按纯相似度 top_k 返回
      
  ELSE:  【弱匹配情况】
      按混合评分 top_k 返回（通常 1~3 条）
```

结果：**强名称匹配只返回 record[0]（Tesla Model X）**

---

## 第 III 阶段：MarketAgent Z-score 计算

位置：[agents/market_agent/graph.py](agents/market_agent/graph.py)

```python
# 现在 entries = [record[0]] （RAG 检索到的 1 条市场记录）

# 从唯一的一条记录提取统计数据
historical_mean = 95000
historical_stddev = 12000

# 从查询中提取交易价格
query_price = _extract_price(query_text)  → 1000000

# 计算 Z-score
mu = mean([95000]) = 95000
sigma = mean([12000]) = 12000
deviation_sigma = |1000000 - 95000| / 12000 = 75.42

# Z-score 判级
if deviation_sigma >= 5:  ✓ 75.42 >= 5
    verdict = "EXTREMELY_ANOMALOUS"

# 返回 market_data 给 HostAgent
{
  "asset": "Tesla Model X 2024",
  "fair_range": {"min": 79990, "max": 119990},
  "historical_mean": 95000,
  "historical_stddev": 12000,
  "queried_price": 1000000,
  "deviation_sigma": 75.42,
  "verdict": "EXTREMELY_ANOMALOUS"
}
```

---

## 第 IV 阶段：TransactionAgent 行为检测

位置：[agents/transaction_agent/graph.py](agents/transaction_agent/graph.py) + [tools/pattern_detector.py](tools/pattern_detector.py)

```python
# TransactionAgent 接收："Analyze user U002 for suspicious patterns"

user_id = "U002"
txs = find_user_transactions("U002")  # 从 transactions.json 读取该用户的全部交易

# 检测 A：新账户对手方（<= 7 天）
new_account_counterparties = len([
    t for t in txs if t["counterparty_account_age_days"] <= 7
])
# U002 有 3 笔交易对手账户年龄是 3/2/6 天
# → new_account_counterparties = 3

# 检测 B：结构化拆单（7 天内 >= 5 笔 < $10K）
structuring = detect_structuring(txs)
# ├─ 时间窗口：最近 7 天
# ├─ 过滤金额 < $10,000 的交易
# ├─ 若满足 >= 5 笔 → HIGH_RISK_STRUCTURING
# └─ 否则 → NO_STRUCTURING_SIGNAL

# TransactionAgent 综合定级
if new_account_counterparties > 0 or is_structuring:
    verdict = "HIGH_RISK"
# → 返回给 HostAgent
```

---

## 第 V 阶段：HostAgent 最终综合裁定

位置：[agents/host_agent/graph.py](agents/host_agent/graph.py) 的 `_risk_from_evidence()`

```python
market = { deviation_sigma: 75.42, verdict: "EXTREMELY_ANOMALOUS", ... }
tx = { new_account_counterparties: 3, structuring: {...}, ... }

# 规则树判断
if sigma >= 10:  # 75.42 >= 10？✓
    risk_level = "CRITICAL"  ✓ 立即返回，无需其他条件

# 最终结论：CRITICAL
```

---

## 第 VI 阶段：结果输出和持久化

```python
final_report = {
    "session_id": "sess_xxx",
    "risk_level": "CRITICAL",
    "confidence": 0.92,
    "anomaly_types": ["PRICE_ANOMALY", "RELATED_PARTY_TRANSACTION"],
    "evidence_chain": [
        { "step": 1, "agent": "MarketAgent", "finding": "Price sigma deviation: 75.42" },
        { "step": 2, "agent": "TransactionAgent", "finding": "New counterparties within 7 days: 3" }
    ],
    "recommended_action": "FREEZE_AND_REPORT_SAR",
    "market_analysis": { ... },
    "transaction_analysis": { ... }
}

# 持久化
finalize_session(session_id, final_report, "CRITICAL")  → SQLite

# CLI 展示（cli/chat.py）
print("\n[Final Report]")
print(json.dumps(final_report, indent=2))
print("\n[Summary]")
print("The risk level for this investigation is CRITICAL. ...")

# 回到 CLI 提示符等待下一条查询
print("\n> ")
```

---

## RAG 的核心特点总结

| 特性 | 实现 |
|---|---|
| **向量算法** | Hash Bag-of-Words（128 维） |
| **检索策略** | 名称重叠（主）+ 余弦相似度（辅） |
| **强匹配处理** | 一旦名称相似度 >= 0.5，只返回 1 条，避免动均值 |
| **缓存机制** | 预计算 .npy，启动时校验行数是否匹配知识库 |
| **可复现性** | 若 embedding 缓存丢失，重新生成结果完全相同 |
