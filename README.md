# A2A-AML-POC: Anti-Money Laundering Multi-Agent Collaboration System Based on A2A Protocol


## 00 Solution Design

### 0.1 Business Background

This POC is built on LLM and RAG technologies. Through a **multi-agent collaboration** pattern, agents with different domain capabilities coordinate via the A2A (Agent-to-Agent) protocol to complete complex money-laundering pattern detection.

### 0.2 Use Case Description

**Input**: suspicious transaction records submitted by users/systems, for example:
> "User U002 sold a Tesla Model X for $1,000,000"

**Output**: a structured risk report including:
- Risk level (LOW / MEDIUM / HIGH / CRITICAL)
- Anomaly type (price anomaly / structuring / related-party transaction, etc.)
- Complete evidence chain (reasoning basis for each step + which agent was called)
- Recommended action (approve / freeze / report SAR)

---

## 01 Tech Stack Selection

### 1.1 Core Dependencies

| Category | Technology | Purpose | Why Chosen |
|---|---|---|---|
| **Runtime** | Python 3.11+ | Primary language | LangChain/LangGraph ecosystem |
| **A2A Protocol** | `a2a-sdk` (or minimal in-house FastAPI subset) | Inter-agent communication | Official SDK, standardized |
| **Agent Orchestration** | `langgraph` | Intra-agent reasoning graph | State-machine model fits multi-step reasoning |
| **LLM Abstraction** | `langchain-core` | Tool / Message abstraction | Seamless integration with LangGraph |
| **LLM Provider** | `anthropic` (Claude) | Reasoning model | Matches the PDF notes: "use Claude" |
| **HTTP Service** | `fastapi` + `uvicorn` | Independent HTTP service per agent | High-performance async, native SSE support |
| **HTTP Client** | `httpx` | A2A client calls | Async + SSE client support |
| **Persistence** | `sqlite3` (stdlib) | Task / Message history | Zero dependency |
| **RAG Retrieval** | `numpy` + Voyage/OpenAI Embedding | Minimal vector retrieval | Avoid vector DB in POC stage |
| **CLI UX** | `rich` | Streaming visualization | Improves demo quality |
| **Config Management** | `python-dotenv` | Environment variables | Standard practice |
| **Data Validation** | `pydantic` v2 | A2A data structures | Type safety + JSON serialization |
---

## 02 Agent Role Design

This system includes **3 agents**, each running as an independent HTTP service and exposing standard A2A endpoints.

### 2.1 Overall Architecture

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
              │  • User entry / intent parsing         │
              │  • LangGraph: multi-round investigation│
              │  • Final report generation from evidence |
              └─────┬────────────────────────────┬─────┘
                    │ A2A                    A2A │
                    ▼                            ▼
        ┌───────────────────────┐    ┌──────────────────────────┐
        │ MarketAgent           │    │ TransactionAgent         │
        │ (Port 10001)          │    │ (Port 10002)             │
        │ ────────────────────  │    │ ────────────────────────│
        │ • Asset pricing KB    │    │ • Transaction lookup     │
        │ • RAG retrieval       │    │ • Related account analysis |
        │ • Price anomaly check │    │ • Structuring detection  │
        └───────────────────────┘    └──────────────────────────┘
                    │                            │
                    ▼                            ▼
        ┌──────────────────────┐    ┌──────────────────────────┐
        │ market_knowledge     │    │ transactions.json        │
        │ + embeddings (numpy) │    │ (mock transaction logs)  │
        └──────────────────────┘    └──────────────────────────┘
```

### 2.2 HostAgent - Coordination and Decisioning

**Port**: 10000

**Responsibility**: Acts as the user entry point and orchestrates the entire investigation workflow. It is the only agent directly facing the user.

**LangGraph node design**:

```
parse_intent ──▶ plan_investigation ──▶ dispatch_to_agent ──▶ evaluate_response
                                              ▲                       │
                                              │  Need more evidence   │
                                              └───────────────────────┤
                                                                      │ Evidence sufficient
                                                                      ▼
                                                              generate_report ──▶ END
```

| Node | Responsibility |
|---|---|
| `parse_intent` | Parse user input and extract key entities (user ID, asset, amount, time) |
| `plan_investigation` | LLM reads AgentCards and generates an initial investigation plan |
| `dispatch_to_agent` | Call specific agents via `a2a.client` (SSE streaming subscription) |
| `evaluate_response` | After receiving a response, decide: enough evidence? who to ask next? |
| `generate_report` | Synthesize all evidence into a structured risk report |


### 2.3 MarketAgent - Market Intelligence

**Port**: 10001

**Responsibility**: Uses a knowledge base to return reasonable price ranges for assets and evaluate anomaly severity of the transaction price.

**AgentCard skills**:

| Skill ID | Name | Description |
|---|---|---|
| `price_lookup` | Market price query | Return a reasonable price range for an asset |
| `price_anomaly_check` | Price anomaly detection | Given asset + transaction price, return sigma deviation |

**Internal LangGraph**:

```
receive_query ──▶ rag_retrieve ──▶ llm_analyze ──▶ structure_output ──▶ END
```

- `rag_retrieve`: Retrieve Top-K relevant entries from `market_knowledge.jsonl` (numpy cosine similarity)
- `llm_analyze`: LLM performs anomaly judgment using retrieved context
- `structure_output`: Return structured result in `DataPart` format

**Output example**:
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

### 2.4 TransactionAgent - Transaction Behavior Analysis

**Port**: 10002

**Responsibility**: Analyzes transaction logs for suspicious signals such as behavior patterns, related accounts, and structuring.

**AgentCard skills**:

| Skill ID | Name | Description |
|---|---|---|
| `user_history` | User transaction history | Return a summary of recent transactions for a user |
| `related_party_analysis` | Related-party analysis | Identify suspicious related accounts and counterparties |
| `structuring_detection` | Structuring detection | Detect split transactions used to evade reporting thresholds |

**Internal LangGraph**:

```
receive_query ──▶ classify_intent ──▶ query_db ──▶ pattern_analysis ──▶ structure_output ──▶ END
```

- `classify_intent`: Decide which skill is being requested
- `query_db`: Retrieve related records from `transactions.json`
- `pattern_analysis`: LLM + heuristic rules identify anomaly patterns

**Output example** (structuring):
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

### 2.5 Collaboration Model

Each agent **does not know the implementation details of the others**. They exchange only the following three categories through A2A:

1. **`Message`**: natural language or structured data exchange
2. **`Artifact`**: final structured output produced by an agent
3. **`TaskStatus`**: task execution status (`working` / `input-required` / `completed`, etc.)

---

## 03 Directory Structure

```
a2a-aml-poc/
├── main.py                          # Startup entry: launch 3 agents + CLI concurrently
├── pyproject.toml                   # uv/poetry dependency management
├── .env                             # Local environment variables (optional)
├── README.md                        # This document
│
├── a2a/                             # A2A protocol layer (can be extracted for reuse)
│   ├── __init__.py
│   ├── types.py                     # Task/Message/AgentCard/Artifact + TaskState enum
│   ├── server.py                    # FastAPI base: /tasks/send, /tasks/sendSubscribe
│   ├── client.py                    # Async httpx client, A2A calls + SSE subscription wrapper
│   └── registry.py                  # Hardcoded AGENT_ENDPOINTS dictionary
│
├── agents/
│   ├── host_agent/                  # Port 10000, user entry point
│   │   ├── __init__.py
│   │   ├── server.py                # Start FastAPI and mount a2a.server
│   │   ├── graph.py                 # LangGraph coordination logic
│   │   ├── prompts.py               # System prompts
│   │   └── card.json                # AgentCard
│   │
│   ├── market_agent/                # Port 10001
│   │   ├── server.py
│   │   ├── graph.py
│   │   ├── rag.py                   # Numpy cosine similarity RAG
│   │   ├── prompts.py
│   │   └── card.json
│   │
│   └── transaction_agent/           # Port 10002
│       ├── server.py
│       ├── graph.py
│       ├── prompts.py
│       └── card.json
│
├── tools/                           # LangChain tools used internally by agents
│   ├── market_search.py             # Retrieve market_knowledge vector store
│   ├── transaction_query.py         # Query transactions.json
│   └── pattern_detector.py          # Heuristic rule engine
│
├── storage/
│   ├── task_store.py                # SQLite wrapper (Task/Message history)
│   └── schema.sql                   # Table creation SQL
│
├── mock_data/
│   ├── market_knowledge.jsonl       # Asset pricing knowledge (for RAG)
│   ├── market_embeddings.npy        # Precomputed embedding matrix
│   ├── transactions.json            # Transaction logs
│   └── test_cases.json              # Demo test cases
│
├── scripts/
│   ├── generate_mock_data.py        # Generate mock data locally
│   └── build_embeddings.py          # One-time market KB embedding builder
│
├── cli/
│   └── chat.py                      # Streaming display with rich + readline
```

### 3.1 Key File Responsibilities

| File | Responsibility | Importance |
|---|---|---|
| `a2a/types.py` | Data contract shared across the whole system by all agents |
| `a2a/server.py` | Reusable A2A HTTP service base for all agents |
| `agents/host_agent/graph.py` | Core multi-round coordination logic, key POC value |
| `scripts/generate_mock_data.py` | Data generation, prerequisite for all features |
| `cli/chat.py` | Demo UX quality, critical for POC perception |

---

## 04 Data Storage Design


### 4.2 SQLite Schema Design

`storage/schema.sql`:

```sql
-- ─────────────────────────────────────────────────────────
-- A2A Task table: each inter-agent call corresponds to one Task
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    task_id        TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,                -- All tasks in the same investigation share this
    source_agent   TEXT NOT NULL,                -- Caller
    target_agent   TEXT NOT NULL,                -- Executor
    state          TEXT NOT NULL,                -- TaskState enum value
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_session ON tasks(session_id);
CREATE INDEX idx_tasks_state ON tasks(state);

-- ─────────────────────────────────────────────────────────
-- Message table: message stream within a Task (full conversation replay)
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    message_id     TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL,
    role           TEXT NOT NULL,                -- 'user' | 'agent'
    parts_json     TEXT NOT NULL,                -- Serialized Part[]
    timestamp      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX idx_messages_task ON messages(task_id);

-- ─────────────────────────────────────────────────────────
-- Artifact table: final structured output produced by an agent
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
-- Investigation session table: each user investigation maps to one session
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    user_query     TEXT NOT NULL,                -- Original user input
    final_report   TEXT,                         -- HostAgent final report JSON
    risk_level     TEXT,                         -- LOW/MEDIUM/HIGH/CRITICAL
    started_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at   TIMESTAMP
);
```

### 4.3 Data Lifecycle

```
User input
    │
    ▼
┌─────────────────────────────┐
│ Create session (sessions)   │
└──────────────┬──────────────┘
               │
               ▼
   ┌──────────────────────────┐
   │ HostAgent calls X Agent  │ ──▶ Create task (tasks)
   │  ─────────────────────── │
   │ Multi-round SSE exchange │ ──▶ Write messages
   │  ─────────────────────── │
   │ X Agent returns Artifact │ ──▶ Write artifacts
   └──────────────────────────┘
               │
               │ (may loop multiple times)
               ▼
┌─────────────────────────────┐
│ Generate final report       │
│ (update sessions)           │
└─────────────────────────────┘
```

### 4.4 mock_data File Design

| File | Format | Scale | Purpose |
|---|---|---|---|
| `market_knowledge.jsonl` | One JSON per line | 50-100 entries | RAG retrieval source |
| `market_embeddings.npy` | Numpy binary | (N, 1024) | Precomputed embeddings |
| `transactions.json` | JSON array | 200-500 records | TransactionAgent data source |
| `test_cases.json` | JSON array | 5-10 cases | Demo scenarios |

Single-record example from `market_knowledge.jsonl`:
```json
{
  "asset_id": "tesla_model_x_2024",
  "asset_name": "Tesla Model X 2024",
  "category": "luxury_vehicle",
  "price_range": {"min": 79990, "max": 119990, "currency": "USD"},
  "historical_mean": 95000,
  "historical_stddev": 12000,
  "description": "Tesla Model X 2024, all-electric luxury SUV, dual-motor standard configuration..."
}
```

Single-record example from `transactions.json`:
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

## 05 End-to-End Interaction Flow

Using **Demo Case 2 (Tesla $1M anomalous transaction)** as an example, this section shows the full path from user input to final report.

### 5.1 Sequence Diagram

```
User           CLI         HostAgent      MarketAgent    TransactionAgent    SQLite
 │              │              │               │                │               │
 │  Input query │              │               │                │               │
 │─────────────▶│              │               │                │               │
 │              │              │               │                │               │
 │              │ POST /tasks/sendSubscribe    │                │               │
 │              │─────────────▶│               │                │               │
 │              │              │ Create session│                │               │
 │              │              │──────────────────────────────────────────────▶│
 │              │              │               │                │               │
 │              │              │ ① parse_intent│                │               │
 │              │              │ "U002, Tesla, $1M"             │               │
 │              │              │               │                │               │
 │              │ SSE: state=working           │                │               │
 │              │◀─────────────│               │                │               │
 │              │              │               │                │               │
 │              │              │ ② plan_investigation           │               │
 │              │              │ LLM decides: check market first│               │
 │              │              │               │                │               │
 │              │              │ POST /tasks/send (price check) │               │
 │              │              │──────────────▶│                │               │
 │              │              │               │ RAG retrieval  │               │
 │              │              │               │ LLM analysis   │               │
 │              │              │               │                │               │
 │              │              │  Artifact: 7.5σ anomaly        │               │
 │              │              │◀──────────────│                │               │
 │              │              │               │                │               │
 │              │ SSE: market verdict received │                │               │
 │              │◀─────────────│               │                │               │
 │              │              │               │                │               │
 │              │              │ ③ evaluate    │                │               │
 │              │              │ LLM decides: price abnormal -> investigate behavior │
 │              │              │               │                │               │
 │              │              │ POST /tasks/send (user history)│               │
 │              │              │───────────────────────────────▶│               │
 │              │              │               │                │ Query tx      │
 │              │              │               │                │ Pattern analysis │
 │              │              │  Artifact: 3 related high-price trades │       │
 │              │              │◀───────────────────────────────│               │
 │              │              │               │                │               │
 │              │ SSE: tx pattern received     │                │               │
 │              │◀─────────────│               │                │               │
 │              │              │               │                │               │
 │              │              │ ④ evaluate    │                │               │
 │              │              │ LLM decides: check counterparties next │        │
 │              │              │               │                │               │
 │              │              │ POST /tasks/send (counterparty)│               │
 │              │              │───────────────────────────────▶│               │
 │              │              │  Artifact: all newly created accounts │         │
 │              │              │◀───────────────────────────────│               │
 │              │              │               │                │               │
 │              │              │ ⑤ generate_report             │               │
 │              │              │ Synthesize evidence -> CRITICAL│               │
 │              │              │               │                │               │
 │              │              │ Write final report to sessions │               │
 │              │              │──────────────────────────────────────────────▶│
 │              │              │               │                │               │
 │              │ SSE: state=completed + Artifact               │               │
 │              │◀─────────────│               │                │               │
 │              │              │               │                │               │
 │  Final report│              │               │                │               │
 │◀─────────────│              │               │                │               │
```

### 5.2 Key Step Details

#### Step ①: Intent Parsing

**Input**: `"User U002 sold a Tesla Model X for $1,000,000"`

**HostAgent parsed output** (structured):
```json
{
  "user_id": "U002",
  "asset": "Tesla Model X",
  "transaction_amount": 1000000,
  "transaction_type": "sale",
  "investigation_goal": "Determine whether this transaction may involve money laundering"
}
```

#### Step ②: Plan the First Investigation Action

After seeing all AgentCards, the HostAgent's LLM **autonomously decides** which agent to call first. Key prompt excerpt:

```
Available agents:
- MarketAgent: price lookup, price anomaly detection
- TransactionAgent: user history, related-party analysis, structuring detection

Current investigation task: determine whether U002 selling a Tesla Model X for $1M may involve money laundering.

Decide: which agent should be called first, and what question should be asked?
```

LLM output:
```json
{
  "next_agent": "MarketAgent",
  "skill": "price_anomaly_check",
  "query": "Current transaction price for Tesla Model X 2024 is $1,000,000. How abnormal is it?"
}
```

#### Step ③ / ④: Iterative Evaluation Loop

After each agent response, the HostAgent's `evaluate_response` node asks the LLM to judge:
- Is the current evidence sufficient for a conclusion?
- If not, who should be asked next and what should be asked?

This **conditional loop** is one of the most demonstrable values of the POC: it proves agents are actually "conversing" rather than following a fixed hardcoded flow.

#### Step ⑤: Final Synthesis Report

**Final output**:
```json
{
  "session_id": "sess_a1b2c3",
  "risk_level": "CRITICAL",
  "anomaly_types": ["PRICE_MANIPULATION", "RELATED_PARTY_TRANSACTION"],
  "evidence_chain": [
    {
      "step": 1,
      "agent": "MarketAgent",
      "finding": "Transaction price $1M deviates from market mean by 7.5σ"
    },
    {
      "step": 2,
      "agent": "TransactionAgent",
      "finding": "U002 made 3 similar high-price Tesla trades in the past 30 days"
    },
    {
      "step": 3,
      "agent": "TransactionAgent",
      "finding": "All 3 counterparties are accounts opened within 7 days"
    }
  ],
  "recommended_action": "FREEZE_AND_REPORT_SAR",
  "confidence": 0.94
}
```

### 5.3 CLI Real-Time Display Example

```
┌─ AML Investigation ──────────────────────────────────────┐
│ Query: User U002 sold a Tesla Model X for $1,000,000    │
└──────────────────────────────────────────────────────────┘

[HostAgent] Parsing intent... ✓
   └─ Target: U002 / Tesla Model X / $1M

[HostAgent] Planning investigation... ✓
   └─ Plan: Market check -> Behavior analysis

[HostAgent -> MarketAgent] Running price anomaly check...
   ├─ RAG retrieval from market knowledge base (50 entries) ... ✓
   ├─ LLM reasoning ... ✓
   └─ Result: $1M deviates from mean by 7.5σ -> EXTREMELY_ANOMALOUS

[HostAgent] Evaluating evidence -> Price anomaly confirmed, deeper behavior analysis needed

[HostAgent -> TransactionAgent] Running user behavior analysis...
   ├─ Querying transaction logs ... ✓
   ├─ Pattern analysis ... ✓
   └─ Result: 3 related high-price Tesla transactions detected

[HostAgent] Evaluating evidence -> Counterparty background check still needed

[HostAgent -> TransactionAgent] Running related-party analysis...
   └─ Result: all 3 counterparties are newly opened accounts within 7 days

[HostAgent] Generating final report...

┌─ Final Report ───────────────────────────────────────────┐
│ Risk Level: CRITICAL                                    │
│ Confidence: 94%                                         │
│ Action: FREEZE_AND_REPORT_SAR                           │
│ Evidence: 3 items (view details)                        │
└──────────────────────────────────────────────────────────┘

Total time: 8.3s | A2A calls: 3 | Tokens: 12,450
```

---

## 06 Quick Start

### 6.1 Create and Activate a Virtual Environment

```bash
# 1. Enter the project root
cd RAG_POC

# 2. Create and activate a venv with Python 3.11+
python3.11 -m venv venv
source venv/bin/activate
```

### 6.2 Install Dependencies

```bash
pip install -r requirements.txt
```

### 6.3 Configure Environment Variables

Create or edit `.env`:

```env
# Optional: override default agent endpoints
HOST_AGENT_URL=http://127.0.0.1:10000
MARKET_AGENT_URL=http://127.0.0.1:10001
TRANSACTION_AGENT_URL=http://127.0.0.1:10002

# Optional: customize SQLite file path
AML_DB_PATH=./aml.db
```

Note: This project uses SQLite by default, so no Docker/database startup step is required in this repo.

### 6.4 Initialize Data

```bash
# 1. Generate mock data (local script generation)
python3 scripts/generate_mock_data.py

# 2. Build market knowledge base embeddings
python3 scripts/build_embeddings.py

# 3. Initialize SQLite
python3 -c "from storage.task_store import init_db; init_db()"
```

### 6.5 Start the System

```bash
# One-command startup: launch 3 agents + CLI concurrently
python3 main.py
```

Expected output:
```
✓ HostAgent listening on http://localhost:10000
✓ MarketAgent listening on http://localhost:10001
✓ TransactionAgent listening on http://localhost:10002
✓ SQLite initialized at ./aml.db

╭──────────────── A2A-AML-POC ────────────────╮
│ AML Investigation CLI (type 'exit' to quit) │
╰─────────────────────────────────────────────╯
> _
```

