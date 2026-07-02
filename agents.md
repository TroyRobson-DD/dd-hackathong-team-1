# Cortex Agent Definitions

Agents to be configured for the Staff Expense Claims application.

---

## Agent 1 — Expense Policy Assistant

**Purpose:** Answer staff questions about expense policy, category limits, and submission rules.

**Type:** Cortex Agent (RAG over policy documents)

**Data Sources:**
- Expense category table (`CONFIG.EXPENSE_CATEGORIES`) — limits per category
- Policy document (to be uploaded to a Snowflake stage and indexed via Cortex Search)

**Example queries:**
- "What is the daily meal allowance?"
- "Do I need a receipt for office supplies under $50?"
- "How do I submit a claim for a conference registration?"

---

## Agent 2 — Finance Analyst Assistant

**Purpose:** Allow finance team members to query claims data using natural language.

**Type:** Cortex Analyst (semantic model over claims tables)

**Semantic Model Tables:**
- `CLAIMS.EXPENSE_CLAIMS`
- `CLAIMS.EXPENSE_ITEMS`
- `CONFIG.EMPLOYEES`
- `CONFIG.EXPENSE_CATEGORIES`

**Example queries:**
- "Show me total spend by department this quarter"
- "Which employees have claims pending approval for more than 7 days?"
- "What are the top 5 expense categories by total amount this year?"

---

## Agent 3 — Claim Anomaly Detector (Future Phase)

**Purpose:** Flag unusual or potentially duplicate expense submissions.

**Type:** Cortex ML + Alert

**Signals:**
- Duplicate amounts from same supplier within 7 days
- Claims significantly above category average
- Weekend submissions for business-only categories
