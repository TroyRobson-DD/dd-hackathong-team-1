# Streamlit App — Staff Expense Claims

## Overview

Multi-page Streamlit-in-Snowflake app. All data in `EXPENSE_APP` (already built). Uses `st.connection("snowflake")` with embedded identity — no secrets needed in SiS. Only pre-installed packages used (streamlit, pandas, altair) so no `pyproject.toml` and no EAI required.

## File Structure

```
build/app/
├── streamlit_app.py          ← entry point + role routing
├── pages/
│   ├── 1_Submit_Claim.py
│   ├── 2_My_Claims.py
│   ├── 3_Approval_Queue.py
│   ├── 4_Finance_Dashboard.py
│   └── 5_Admin.py
├── utils/
│   ├── auth.py               ← CURRENT_USER() → employee + role
│   ├── db.py                 ← connection helper + query wrapper
│   └── formatting.py         ← currency, dates, status badges
└── snowflake.yml
```

## Task 1 — Utils

**`utils/db.py`**
- `get_conn()` → `st.connection("snowflake")`
- `query(sql, params)` → `pd.DataFrame` via `conn.query()`

**`utils/auth.py`**
- `get_employee(conn)` → row from `CONFIG.EMPLOYEES` where `SNOWFLAKE_USER = CURRENT_USER()`
- Returns `None` if user not registered (shows setup message)
- Role stored in `st.session_state.employee`

**`utils/formatting.py`**
- `fmt_currency(amount)` → `"$1,234.50"`
- `status_badge(status)` → coloured markdown span
- `fmt_date(d)` → `"2 Jul 2024"`

---

## Task 2 — Entry Point (`streamlit_app.py`)

- Load employee record; if missing, show "Contact admin to register" message and stop
- Store in `st.session_state`
- Sidebar: user name + role chip + page links filtered by role
  - STAFF sees: Submit Claim, My Claims
  - MANAGER adds: Approval Queue
  - FINANCE adds: Finance Dashboard
  - ADMIN adds: Admin
- Home page: welcome card + summary counts (total claims, pending approval, total paid YTD)

---

## Task 3 — Page 1: Submit Claim

**Access:** All roles

**Flow:**
1. Claim header: Title, Period Start/End, Cost Centre, Project Code, Description
2. Line items section — `st.session_state` list, Add Item / Remove buttons
   - Each item: Date, Category (selectbox), Description, Supplier, Amount, GST, Notes
   - Receipt uploader per item (PDF/PNG/JPG, 10 MB max) — if category `REQUIRES_RECEIPT`
3. Running total displayed
4. **Save Draft** → INSERT into `EXPENSE_CLAIMS` (STATUS=DRAFT) + `EXPENSE_ITEMS`
5. **Submit** → same INSERT then UPDATE STATUS→SUBMITTED + set SUBMISSION_DATE + INSERT into `AUDIT.CLAIM_STATUS_HISTORY` + INSERT `NOTIFICATIONS` row for manager
6. Receipts uploaded to `@RECEIPT_STAGE/<year>/<claim_id>/<item_id>_<filename>` using `conn.cursor().execute("PUT ...")`

---

## Task 4 — Page 2: My Claims

**Access:** All roles (row-filtered by view)

- Query `V_MY_CLAIMS` with optional STATUS filter chips and date range
- Table with status badges, amounts, item count
- Click row → expander showing full claim detail + line items table
- **Cancel** button visible for DRAFT claims → UPDATE STATUS=CANCELLED + audit row

---

## Task 5 — Page 3: Approval Queue

**Access:** MANAGER, FINANCE, ADMIN

- Query `V_PENDING_APPROVALS`
- Each claim in an `st.expander` showing: submitter, dates, line items table, receipt links
- **Approve** button → `st.popover` with optional comments → UPDATE EXPENSE_CLAIMS STATUS=APPROVED + INSERT APPROVALS + INSERT audit + INSERT NOTIFICATIONS
- **Reject** button → `st.popover` with mandatory reason → same pattern with STATUS=REJECTED + set REJECTION_REASON

---

## Task 6 — Page 4: Finance Dashboard

**Access:** FINANCE, ADMIN

**KPI row (st.metric):**
- Total pending (SUBMITTED + UNDER_REVIEW) — count + amount
- Total approved awaiting payment — count + amount
- Total paid this month

**Claims table:**
- Filters: STATUS multiselect, Department, date range
- Sortable table
- **Mark as Paid** → select rows → enter Payment Reference → bulk UPDATE + audit + notifications

**Charts (Altair):**
- Bar: spend by department
- Line: monthly claim totals (last 12 months)
- Pie: top categories by amount

**Export:** `st.download_button` → CSV of filtered results

---

## Task 7 — Page 5: Admin

**Access:** ADMIN only

Three tabs:

1. **Categories** — editable table of `EXPENSE_CATEGORIES` (toggle active, edit daily limit)
2. **Employees** — add employee form + list with role/manager assignment
3. **Audit Log** — paginated view of `AUDIT.CLAIM_STATUS_HISTORY` with filters

---

## Task 8 — snowflake.yml + Deploy

- Query `DEFAULT_STREAMLIT_COMPUTE_POOL` parameter
- No `pyproject.toml` (pre-installed packages only) → no EAI needed
- `artifacts` lists all `.py` files in `app/` and `pages/` and `utils/`
- Deploy with `snow streamlit deploy --replace`
