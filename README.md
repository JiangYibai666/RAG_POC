# A2A-AML-POC:基于 A2A 协议的反洗钱多智能体协作系统


## 00 设计方案

### 0.1 业务背景

本 POC 基于 LLM 与 RAG 技术,通过**多智能体协作**模式,让具备不同领域能力的 Agent 通过 A2A(Agent-to-Agent)协议互相协商,完成复杂的洗钱模式识别。

### 0.2 用例描述

**输入**:用户/系统提交的可疑交易记录,例如:
> "用户 U002 以 $1,000,000 出售 Tesla Model X"

**输出**:结构化风险报告,包含:
- 风险等级(LOW / MEDIUM / HIGH / CRITICAL)
- 异常类型(价格异常 / 结构化分拆 / 关联交易等)
- 完整证据链(每一步推理依据 + 调用了哪个 Agent)
- 建议处置动作(放行 / 冻结 / 上报 SAR)

---

## 01 技术栈选型

### 1.1 核心依赖

| 类别 | 技术 | 用途 | 选型理由 |
|---|---|---|---|
| **运行时** | Python 3.11+ | 主语言 | LangChain/LangGraph 生态 |
| **A2A 协议** | `a2a-sdk`(或 FastAPI 自研最小子集) | Agent 间通信 | 官方 SDK,标准化 |
| **Agent 编排** | `langgraph` | 单 Agent 内部推理图 | 状态机模型契合多步推理 |
| **LLM 抽象** | `langchain-core` | Tool / Message 抽象 | 与 LangGraph 无缝集成 |
| **LLM 提供商** | `anthropic`(Claude) | 推理模型 | 对应 PDF 笔记中"用 Claude" |
| **HTTP 服务** | `fastapi` + `uvicorn` | 每个 Agent 独立 HTTP 服务 | 异步高性能,SSE 原生支持 |
| **HTTP 客户端** | `httpx` | A2A 调用客户端 | 异步 + SSE 客户端支持 |
| **持久化** | `sqlite3`(stdlib) | Task / Message 历史 | 零依赖 |
| **RAG 检索** | `numpy` + Voyage/OpenAI Embedding | 极简向量检索 | POC 期避免向量数据库 |
| **CLI 美化** | `rich` | 流式可视化展示 | 演示效果加分项 |
| **配置管理** | `python-dotenv` | 环境变量 | 标准做法 |
| **数据校验** | `pydantic` v2 | A2A 数据结构 | 类型安全 + JSON 序列化 |
---

## 02 智能体角色设计

本系统包含 **3 个 Agent**,每个 Agent 都是独立的 HTTP 服务,暴露标准 A2A 接口。

### 2.1 整体架构图

```
                    ┌─────────────────────────────┐
                    │   User (CLI / API Client)   │
                    └──────────────┬──────────────┘
                                   │ A2A Protocol
                                   │ (HTTP + SSE)
                                   ▼
              ┌────────────────────────────────────────┐
              │         HostAgent  (Port 10000)        │
              │  ────────────────────────────────────  │
              │  • 用户入口 / 意图解析                  │
              │  • LangGraph: 多轮调查协商             │
              │  • 综合证据生成最终报告                 │
              └─────┬────────────────────────────┬─────┘
                    │ A2A                    A2A │
                    ▼                            ▼
        ┌───────────────────────┐    ┌──────────────────────────┐
        │ MarketAgent           │    │ TransactionAgent         │
        │ (Port 10001)          │    │ (Port 10002)             │
        │ ────────────────────  │    │ ────────────────────────│
        │ • 商品价格知识库      │    │ • 交易流水查询           │
        │ • RAG 检索            │    │ • 关联账户分析           │
        │ • 价格异常判定         │    │ • 结构化分拆检测         │
        └───────────────────────┘    └──────────────────────────┘
                    │                            │
                    ▼                            ▼
        ┌──────────────────────┐    ┌──────────────────────────┐
        │ market_knowledge     │    │ transactions.json        │
        │ + embeddings (numpy) │    │ (mock 交易流水)          │
        └──────────────────────┘    └──────────────────────────┘
```

### 2.2 HostAgent — 协调与决策

**端口**:10000

**职责**:作为用户入口,负责整个调查流程的编排。是唯一直接面向用户的 Agent。

**LangGraph 节点设计**:

```
parse_intent ──▶ plan_investigation ──▶ dispatch_to_agent ──▶ evaluate_response
                                              ▲                       │
                                              │  需要更多证据         │
                                              └───────────────────────┤
                                                                      │ 证据充分
                                                                      ▼
                                                              generate_report ──▶ END
```

| 节点 | 职责 |
|---|---|
| `parse_intent` | 解析用户输入,提取关键实体(用户ID、商品、金额、时间) |
| `plan_investigation` | LLM 看 AgentCards,生成初始调查计划 |
| `dispatch_to_agent` | 通过 `a2a.client` 调用具体 Agent(SSE 流式订阅) |
| `evaluate_response` | 收到 Agent 答复后判断:够不够? 还需要问谁? |
| `generate_report` | 综合所有证据,生成结构化风险报告 |


### 2.3 MarketAgent — 市场情报

**端口**:10001

**职责**:基于知识库回答商品/资产的合理价格区间,判断给定交易价格的异常程度。

**AgentCard skills**:

| Skill ID | 名称 | 描述 |
|---|---|---|
| `price_lookup` | 市场价格查询 | 返回某资产的合理价格区间 |
| `price_anomaly_check` | 价格异常检测 | 给定资产+成交价,返回偏离 σ 数 |

**内部 LangGraph**:

```
receive_query ──▶ rag_retrieve ──▶ llm_analyze ──▶ structure_output ──▶ END
```

- `rag_retrieve`:从 `market_knowledge.jsonl` 中检索 Top-K 相关条目(numpy 余弦相似度)
- `llm_analyze`:LLM 结合检索结果做异常判定
- `structure_output`:以 `DataPart` 格式返回结构化结果

**输出示例**:
```json
{
  "asset": "Tesla Model X 2024",
  "fair_range": {"min": 79990, "max": 119990},
  "historical_mean": 95000,
  "historical_stddev": 12000,
  "queried_price": 1000000,
  "deviation_sigma": 75.4,
  "verdict": "EXTREMELY_ANOMALOUS"
}
```

### 2.4 TransactionAgent — 交易行为分析

**端口**:10002

**职责**:基于交易流水,分析用户行为模式、关联账户、结构化分拆等可疑信号。

**AgentCard skills**:

| Skill ID | 名称 | 描述 |
|---|---|---|
| `user_history` | 用户交易历史 | 返回用户近期交易摘要 |
| `related_party_analysis` | 关联方分析 | 识别可疑的关联账户和交易对手 |
| `structuring_detection` | 结构化分拆检测 | 检测规避上报阈值的拆分行为 |

**内部 LangGraph**:

```
receive_query ──▶ classify_intent ──▶ query_db ──▶ pattern_analysis ──▶ structure_output ──▶ END
```

- `classify_intent`:判断用户问的是哪种 skill
- `query_db`:从 `transactions.json` 检索相关交易
- `pattern_analysis`:LLM + 启发式规则识别异常模式

**输出示例**(结构化分拆):
```json
{
  "user_id": "U003",
  "pattern_detected": "STRUCTURING",
  "evidence": {
    "transaction_count": 12,
    "amount_range": [9400, 9800],
    "threshold": 10000,
    "time_window": "7 days"
  },
  "verdict": "HIGH_RISK_STRUCTURING"
}
```

### 2.5 协作模式

每个 Agent **互不知道彼此的实现细节**,只通过 A2A 协议交换以下三类内容:

1. **`Message`**:自然语言或结构化数据的交换
2. **`Artifact`**:Agent 的最终结构化输出
3. **`TaskStatus`**:任务执行状态(`working` / `input-required` / `completed` 等)

---

## 03 目录结构

```
a2a-aml-poc/
├── main.py                          # 启动入口:并发拉起 3 个 Agent + CLI
├── pyproject.toml                   # uv/poetry 依赖管理
├── .env.example                     # 环境变量模板
├── README.md                        # 本文档
│
├── a2a/                             # A2A 协议层(可独立抽出复用)
│   ├── __init__.py
│   ├── types.py                     # Task/Message/AgentCard/Artifact + TaskState 枚举
│   ├── server.py                    # FastAPI 基类: /tasks/send, /tasks/sendSubscribe
│   ├── client.py                    # httpx 异步客户端,封装 A2A 调用 + SSE 订阅
│   └── registry.py                  # AGENT_ENDPOINTS 硬编码字典
│
├── agents/
│   ├── host_agent/                  # 端口 10000,用户入口
│   │   ├── __init__.py
│   │   ├── server.py                # 起 FastAPI,挂载 a2a.server
│   │   ├── graph.py                 # LangGraph 协商逻辑
│   │   ├── prompts.py               # 系统提示词
│   │   └── card.json                # AgentCard
│   │
│   ├── market_agent/                # 端口 10001
│   │   ├── server.py
│   │   ├── graph.py
│   │   ├── rag.py                   # numpy 余弦相似度 RAG
│   │   ├── prompts.py
│   │   └── card.json
│   │
│   └── transaction_agent/           # 端口 10002
│       ├── server.py
│       ├── graph.py
│       ├── prompts.py
│       └── card.json
│
├── tools/                           # LangChain Tool,被 Agent 内部调用
│   ├── market_search.py             # 检索 market_knowledge 向量库
│   ├── transaction_query.py         # 查 transactions.json
│   └── pattern_detector.py          # 启发式规则引擎
│
├── storage/
│   ├── task_store.py                # SQLite 封装(Task/Message 历史)
│   └── schema.sql                   # 建表 SQL
│
├── mock_data/
│   ├── market_knowledge.jsonl       # 商品价格知识(供 RAG)
│   ├── market_embeddings.npy        # 预计算的 embedding 矩阵
│   ├── transactions.json            # 交易流水
│   └── test_cases.json              # 演示测试用例
│
├── scripts/
│   ├── generate_mock_data.py        # 用 Claude 生成 mock 数据
│   └── build_embeddings.py          # 一次性构建市场知识库 embeddings
│
├── cli/
│   └── chat.py                      # rich + readline 流式展示
│
└── tests/
    ├── test_a2a_protocol.py         # A2A 协议层单元测试
    └── test_demo_scenarios.py       # 端到端测试(跑 test_cases.json)
```

### 3.1 关键文件职责说明

| 文件 | 职责 | 重要性 |
|---|---|---|
| `a2a/types.py` | 整个系统的数据契约,所有 Agent 共享 | ⭐⭐⭐⭐⭐ |
| `a2a/server.py` | A2A HTTP 服务基类,所有 Agent 复用 | ⭐⭐⭐⭐⭐ |
| `agents/host_agent/graph.py` | 多轮协商核心逻辑,POC 价值的体现 | ⭐⭐⭐⭐⭐ |
| `scripts/generate_mock_data.py` | 数据生成,所有功能的前置依赖 | ⭐⭐⭐⭐ |
| `cli/chat.py` | 演示效果决定 POC 成败 | ⭐⭐⭐⭐ |
| `tests/test_demo_scenarios.py` | 演示前防翻车 | ⭐⭐⭐ |

### 3.2 与原方案的关键变更

| 原方案 | 修正后 | 原因 |
|---|---|---|
| `a2a/router.py`(进程内消息路由) | `a2a/server.py + client.py`(HTTP/SSE) | A2A 协议本质是跨进程标准 |
| `agents/orchestrator.py` | `agents/host_agent/`(完整子包) | Host 也是 Agent,需暴露 AgentCard 和端口 |
| `db/`(PostgreSQL + SQLAlchemy) | `storage/task_store.py`(SQLite) | POC 不需要 Postgres |
| `docker-compose.yml` | 移除 | POC 直接 `python main.py` 启动 |
| 缺 CLI 模块 | `cli/chat.py` | 演示需要 |
| 缺测试 | `tests/` | 防演示翻车 |
| 缺 embedding 构建脚本 | `scripts/build_embeddings.py` | RAG 需要预计算 |

---

## 04 数据存储设计


### 4.2 SQLite Schema 设计

`storage/schema.sql`:

```sql
-- ─────────────────────────────────────────────────────────
-- A2A Task 表:每次 Agent 间调用对应一条 Task 记录
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    task_id        TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,                -- 同一调查的所有 Task 共享
    source_agent   TEXT NOT NULL,                -- 谁发起的
    target_agent   TEXT NOT NULL,                -- 谁执行的
    state          TEXT NOT NULL,                -- TaskState 枚举值
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_session ON tasks(session_id);
CREATE INDEX idx_tasks_state ON tasks(state);

-- ─────────────────────────────────────────────────────────
-- Message 表:Task 内的消息流(可还原完整对话)
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    message_id     TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL,
    role           TEXT NOT NULL,                -- 'user' | 'agent'
    parts_json     TEXT NOT NULL,                -- Part[] 序列化
    timestamp      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX idx_messages_task ON messages(task_id);

-- ─────────────────────────────────────────────────────────
-- Artifact 表:Agent 产出的最终结构化结果
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id    TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL,
    name           TEXT NOT NULL,
    parts_json     TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

-- ─────────────────────────────────────────────────────────
-- 调查会话表:用户每次发起调查对应一个 session
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    user_query     TEXT NOT NULL,                -- 用户原始输入
    final_report   TEXT,                         -- HostAgent 最终报告 JSON
    risk_level     TEXT,                         -- LOW/MEDIUM/HIGH/CRITICAL
    started_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at   TIMESTAMP
);
```

### 4.3 数据生命周期

```
用户输入
    │
    ▼
┌─────────────────────────────┐
│ 创建 session(sessions 表)  │
└──────────────┬──────────────┘
               │
               ▼
   ┌──────────────────────────┐
   │ HostAgent 调用 X Agent    │ ──▶ 创建 task (tasks 表)
   │  ─────────────────────── │
   │ 多轮 SSE 消息往来         │ ──▶ 写入 messages 表
   │  ─────────────────────── │
   │ X Agent 返回 Artifact     │ ──▶ 写入 artifacts 表
   └──────────────────────────┘
               │
               │ (可能多次循环)
               ▼
┌─────────────────────────────┐
│ 生成最终报告(更新 sessions) │
└─────────────────────────────┘
```

### 4.4 mock_data 文件设计

| 文件 | 格式 | 规模 | 用途 |
|---|---|---|---|
| `market_knowledge.jsonl` | 每行一个 JSON | 50-100 条 | RAG 检索源 |
| `market_embeddings.npy` | numpy 二进制 | (N, 1024) | 预计算 embedding |
| `transactions.json` | JSON 数组 | 200-500 笔 | TransactionAgent 数据源 |
| `test_cases.json` | JSON 数组 | 5-10 个 | 演示用例 |

`market_knowledge.jsonl` 单条样例:
```json
{
  "asset_id": "tesla_model_x_2024",
  "asset_name": "Tesla Model X 2024",
  "category": "luxury_vehicle",
  "price_range": {"min": 79990, "max": 119990, "currency": "USD"},
  "historical_mean": 95000,
  "historical_stddev": 12000,
  "description": "2024 款 Tesla Model X,纯电动豪华 SUV,标配双电机..."
}
```

`transactions.json` 单条样例:
```json
{
  "tx_id": "tx_00042",
  "timestamp": "2025-04-15T09:23:11Z",
  "user_id": "U002",
  "counterparty_id": "C9821",
  "asset_id": "tesla_model_x_2024",
  "amount_usd": 1000000,
  "type": "sale",
  "counterparty_account_age_days": 3
}
```

---

## 05 完整交互流程

以 **Demo Case 2(Tesla $1M 异常交易)** 为例,展示从用户输入到最终报告的完整流程。

### 5.1 时序图

```
User           CLI         HostAgent      MarketAgent    TransactionAgent    SQLite
 │              │              │               │                │               │
 │  输入查询    │              │               │                │               │
 │─────────────▶│              │               │                │               │
 │              │              │               │                │               │
 │              │ POST /tasks/sendSubscribe    │                │               │
 │              │─────────────▶│               │                │               │
 │              │              │ 创建 session  │                │               │
 │              │              │──────────────────────────────────────────────▶│
 │              │              │               │                │               │
 │              │              │ ① parse_intent│                │               │
 │              │              │ "U002, Tesla, $1M"             │               │
 │              │              │               │                │               │
 │              │ SSE: state=working           │                │               │
 │              │◀─────────────│               │                │               │
 │              │              │               │                │               │
 │              │              │ ② plan_investigation           │               │
 │              │              │ LLM 决定:先查市场价           │               │
 │              │              │               │                │               │
 │              │              │ POST /tasks/send (price check) │               │
 │              │              │──────────────▶│                │               │
 │              │              │               │ RAG 检索       │               │
 │              │              │               │ LLM 分析       │               │
 │              │              │               │                │               │
 │              │              │  Artifact: 7.5σ 异常           │               │
 │              │              │◀──────────────│                │               │
 │              │              │               │                │               │
 │              │ SSE: market verdict received │                │               │
 │              │◀─────────────│               │                │               │
 │              │              │               │                │               │
 │              │              │ ③ evaluate    │                │               │
 │              │              │ LLM 决定:价格异常 → 查行为   │               │
 │              │              │               │                │               │
 │              │              │ POST /tasks/send (user history)│               │
 │              │              │───────────────────────────────▶│               │
 │              │              │               │                │ 查 tx        │
 │              │              │               │                │ 模式分析     │
 │              │              │  Artifact: 3 笔关联高价交易    │               │
 │              │              │◀───────────────────────────────│               │
 │              │              │               │                │               │
 │              │ SSE: tx pattern received     │                │               │
 │              │◀─────────────│               │                │               │
 │              │              │               │                │               │
 │              │              │ ④ evaluate    │                │               │
 │              │              │ LLM 决定:再查对手方           │               │
 │              │              │               │                │               │
 │              │              │ POST /tasks/send (counterparty)│               │
 │              │              │───────────────────────────────▶│               │
 │              │              │  Artifact: 全是新开账户        │               │
 │              │              │◀───────────────────────────────│               │
 │              │              │               │                │               │
 │              │              │ ⑤ generate_report             │               │
 │              │              │ 综合证据 → CRITICAL            │               │
 │              │              │               │                │               │
 │              │              │ 写入 sessions 最终报告         │               │
 │              │              │──────────────────────────────────────────────▶│
 │              │              │               │                │               │
 │              │ SSE: state=completed + Artifact               │               │
 │              │◀─────────────│               │                │               │
 │              │              │               │                │               │
 │   最终报告   │              │               │                │               │
 │◀─────────────│              │               │                │               │
```

### 5.2 关键步骤详解

#### 步骤 ①:意图解析

**输入**:`"用户 U002 以 $1,000,000 出售 Tesla Model X"`

**HostAgent 解析输出**(结构化):
```json
{
  "user_id": "U002",
  "asset": "Tesla Model X",
  "transaction_amount": 1000000,
  "transaction_type": "sale",
  "investigation_goal": "判定该交易是否涉嫌洗钱"
}
```

#### 步骤 ②:规划首次调查

HostAgent 的 LLM 看到所有 AgentCard 后,**自主决策**首先调用谁。Prompt 关键片段:

```
你有以下 Agent 可调用:
- MarketAgent: 价格查询、价格异常检测
- TransactionAgent: 用户历史、关联方分析、结构化检测

当前调查任务:判定 U002 以 $1M 出售 Tesla Model X 是否涉嫌洗钱。

请决定:第一步应该调用哪个 Agent? 提什么问题?
```

LLM 输出:
```json
{
  "next_agent": "MarketAgent",
  "skill": "price_anomaly_check",
  "query": "Tesla Model X 2024 当前成交价 $1,000,000,异常程度?"
}
```

#### 步骤 ③ / ④:循环评估

每次收到 Agent 答复后,HostAgent 的 `evaluate_response` 节点都会让 LLM 判断:
- 当前证据是否足以下结论?
- 如果不够,下一步问谁、问什么?

这个**条件回路**是整个 POC 最有展示价值的部分——它证明 Agent 之间是真的在"对话",而非走预设流程。

#### 步骤 ⑤:综合报告

**最终输出**:
```json
{
  "session_id": "sess_a1b2c3",
  "risk_level": "CRITICAL",
  "anomaly_types": ["PRICE_MANIPULATION", "RELATED_PARTY_TRANSACTION"],
  "evidence_chain": [
    {
      "step": 1,
      "agent": "MarketAgent",
      "finding": "成交价 $1M 偏离市场均值 7.5σ"
    },
    {
      "step": 2,
      "agent": "TransactionAgent",
      "finding": "U002 过去 30 天有 3 笔类似 Tesla 高价交易"
    },
    {
      "step": 3,
      "agent": "TransactionAgent",
      "finding": "3 笔交易对手方均为 7 天内新开账户"
    }
  ],
  "recommended_action": "FREEZE_AND_REPORT_SAR",
  "confidence": 0.94
}
```

### 5.3 CLI 实时展示效果

```
┌─ AML Investigation ──────────────────────────────────────┐
│ Query: 用户 U002 以 $1,000,000 出售 Tesla Model X         │
└──────────────────────────────────────────────────────────┘

🔍 [HostAgent] 解析意图... ✓
   └─ Target: U002 / Tesla Model X / $1M

📋 [HostAgent] 规划调查... ✓
   └─ Plan: Market check → Behavior analysis

📡 [HostAgent → MarketAgent] 价格异常检测...
   ├─ RAG 检索市场知识库 (50 条) ... ✓
   ├─ LLM 推理 ... ✓
   └─ 📊 结果: $1M 偏离均值 7.5σ → EXTREMELY_ANOMALOUS

🤔 [HostAgent] 评估证据 → 价格异常,需深挖用户行为

📡 [HostAgent → TransactionAgent] 用户行为分析...
   ├─ 查询交易流水 ... ✓
   ├─ 模式分析 ... ✓
   └─ 📊 结果: 发现 3 笔关联 Tesla 高价交易

🤔 [HostAgent] 评估证据 → 还需查对手方背景

📡 [HostAgent → TransactionAgent] 关联方分析...
   └─ 📊 结果: 3 个对手方均为 7 天内新开账户

📝 [HostAgent] 生成最终报告...

┌─ Final Report ───────────────────────────────────────────┐
│ Risk Level: 🔴 CRITICAL                                  │
│ Confidence: 94%                                          │
│ Action: FREEZE_AND_REPORT_SAR                            │
│ Evidence: 3 items (查看详情)                             │
└──────────────────────────────────────────────────────────┘

⏱ Total time: 8.3s | A2A calls: 3 | Tokens: 12,450
```

---

## 06 快速开始

### 6.1 环境准备

```bash
# 1. 克隆并进入项目
cd a2a-aml-poc

# 2. 安装依赖(推荐 uv)
uv sync
# 或使用 pip
pip install -e .

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env,填入 ANTHROPIC_API_KEY
```

### 6.2 初始化数据

```bash
# 1. 生成 mock 数据(用 Claude 一次性生成)
python scripts/generate_mock_data.py

# 2. 构建市场知识库 embeddings
python scripts/build_embeddings.py

# 3. 初始化 SQLite
python -c "from storage.task_store import init_db; init_db()"
```

### 6.3 启动系统

```bash
# 一键启动:并发拉起 3 个 Agent + CLI
python main.py
```

预期输出:
```
✓ HostAgent listening on http://localhost:10000
✓ MarketAgent listening on http://localhost:10001
✓ TransactionAgent listening on http://localhost:10002
✓ All AgentCards loaded
✓ SQLite initialized at ./aml.db

Ready. Type your query below (or 'exit' to quit):
> _
```

### 6.4 运行测试

```bash
# 单元测试
pytest tests/test_a2a_protocol.py

# 端到端 demo case 测试
pytest tests/test_demo_scenarios.py -v
```

---

## 07 演示用例

POC 准备 3 个精心设计的 demo case,从浅到深展示系统能力。

### 7.1 Case 1:正常交易(展示"不误报")

**输入**:`"用户 U001 以 $95,000 出售 Tesla Model X"`

**预期流程**:
- HostAgent → MarketAgent:价格判断
- MarketAgent:$95K 在 $80K-$120K 区间内,正常
- HostAgent:单轮判断足够,无需深挖
- **报告**:`LOW risk`

**演示价值**:证明系统不会过度调查,只在必要时调用更多 Agent。

### 7.2 Case 2:明显价格异常(主推 demo)

**输入**:`"用户 U002 以 $1,000,000 出售 Tesla Model X"`

**预期流程**:见 [5.1 时序图](#51-时序图)

**演示价值**:
- 4 次 A2A 调用
- 2 个 Agent 协作
- 3 轮自主决策协商
- 完整证据链生成

### 7.3 Case 3:隐蔽分拆交易(展示反向调用顺序)

**输入**:`"审查用户 U003 最近活动"`

**预期流程**:
- HostAgent → TransactionAgent:行为模式扫描
- TransactionAgent:发现 12 笔 $9,500 转账(规避 $10K 阈值)
- HostAgent → MarketAgent:这些交易涉及的商品价格是否合理?
- MarketAgent:无对应商品流水,纯资金转移
- **报告**:`HIGH risk` (structuring + 无真实商业实质)

**演示价值**:证明 Host 是真的在"思考"——这个 case 调用顺序与 Case 2 相反,说明流程不是写死的。

---

## 附录 A:扩展路线图(POC 之后)

| 阶段 | 内容 | 工作量 |
|---|---|---|
| **POC**(本项目) | 3 Agent + 单机 + Mock 数据 | 1-2 周 |
| **MVP** | 接入真实数据源,SQLite → PostgreSQL | 2-4 周 |
| **生产化** | 容器化部署,加入认证、限流、审计 | 4-8 周 |
| **能力扩展** | 加入 ComplianceAgent(法规库)、ReportingAgent(自动生成 SAR) | 持续 |

## 附录 B:参考资料

- [Google A2A Protocol Specification](https://google.github.io/A2A/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Anthropic Claude API](https://docs.claude.com/)

---

**文档版本**:v1.0  
**最后更新**:2026-05-07  
**作者**:[Your Name]
