# Staff Expense Claims — Implementation Specification

## Overview

A Streamlit-in-Snowflake multi-page application allowing staff to submit expense claims, managers to approve or reject them, and finance teams to track reimbursement. All data is stored in Snowflake. Receipt files are stored in a Snowflake internal stage.

---

## 1. Snowflake Database & Schema

```sql
CREATE DATABASE IF NOT EXISTS EXPENSE_APP;
CREATE SCHEMA IF NOT EXISTS EXPENSE_APP.CLAIMS;
CREATE SCHEMA IF NOT EXISTS EXPENSE_APP.CONFIG;
CREATE SCHEMA IF NOT EXISTS EXPENSE_APP.AUDIT;
```

---

## 2. Roles & Access Control

### Role Hierarchy

```
ACCOUNTADMIN
  └── EXPENSE_APP_ADMIN
        ├── EXPENSE_APP_FINANCE
        │     └── EXPENSE_APP_MANAGER
        │           └── EXPENSE_APP_STAFF
        └── (direct admin access)
```

### Role Definitions

| Role | Description |
|---|---|
| `EXPENSE_APP_STAFF` | Submit new claims, view own claims only |
| `EXPENSE_APP_MANAGER` | All staff permissions + approve/reject team claims |
| `EXPENSE_APP_FINANCE` | Read all claims, mark as paid, run reports |
| `EXPENSE_APP_ADMIN` | Full access — manage categories, users, system config |

### Role Creation SQL

```sql
CREATE ROLE IF NOT EXISTS EXPENSE_APP_ADMIN;
CREATE ROLE IF NOT EXISTS EXPENSE_APP_FINANCE;
CREATE ROLE IF NOT EXISTS EXPENSE_APP_MANAGER;
CREATE ROLE IF NOT EXISTS EXPENSE_APP_STAFF;

-- Hierarchy grants
GRANT ROLE EXPENSE_APP_STAFF   TO ROLE EXPENSE_APP_MANAGER;
GRANT ROLE EXPENSE_APP_MANAGER TO ROLE EXPENSE_APP_FINANCE;
GRANT ROLE EXPENSE_APP_FINANCE TO ROLE EXPENSE_APP_ADMIN;
```

### Object Privileges

```sql
-- STAFF: submit and view own claims
GRANT USAGE ON DATABASE EXPENSE_APP TO ROLE EXPENSE_APP_STAFF;
GRANT USAGE ON SCHEMA EXPENSE_APP.CLAIMS TO ROLE EXPENSE_APP_STAFF;
GRANT SELECT, INSERT ON TABLE EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS  TO ROLE EXPENSE_APP_STAFF;
GRANT SELECT, INSERT ON TABLE EXPENSE_APP.CLAIMS.EXPENSE_ITEMS   TO ROLE EXPENSE_APP_STAFF;
GRANT SELECT ON TABLE EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES      TO ROLE EXPENSE_APP_STAFF;
GRANT SELECT ON TABLE EXPENSE_APP.CONFIG.EMPLOYEES               TO ROLE EXPENSE_APP_STAFF;
GRANT READ, WRITE ON STAGE EXPENSE_APP.CLAIMS.RECEIPT_STAGE      TO ROLE EXPENSE_APP_STAFF;

-- MANAGER: approve/reject + view team claims
GRANT UPDATE ON TABLE EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS   TO ROLE EXPENSE_APP_MANAGER;
GRANT SELECT, INSERT ON TABLE EXPENSE_APP.CLAIMS.APPROVALS TO ROLE EXPENSE_APP_MANAGER;

-- FINANCE: view all + mark paid + reports
GRANT SELECT ON ALL TABLES IN SCHEMA EXPENSE_APP.CLAIMS  TO ROLE EXPENSE_APP_FINANCE;
GRANT UPDATE ON TABLE EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS  TO ROLE EXPENSE_APP_FINANCE;
GRANT SELECT ON ALL TABLES IN SCHEMA EXPENSE_APP.AUDIT   TO ROLE EXPENSE_APP_FINANCE;

-- ADMIN: full DDL + config management
GRANT ALL PRIVILEGES ON DATABASE EXPENSE_APP             TO ROLE EXPENSE_APP_ADMIN;
GRANT ALL PRIVILEGES ON ALL SCHEMAS IN DATABASE EXPENSE_APP TO ROLE EXPENSE_APP_ADMIN;
GRANT ALL PRIVILEGES ON ALL TABLES IN DATABASE EXPENSE_APP  TO ROLE EXPENSE_APP_ADMIN;
```

---

## 3. Tables

### 3.1 `CONFIG.EMPLOYEES`

Stores all app users. Populated from HR system or manually by admin.

```sql
CREATE TABLE EXPENSE_APP.CONFIG.EMPLOYEES (
    EMPLOYEE_ID       NUMBER(10)       NOT NULL AUTOINCREMENT PRIMARY KEY,
    SNOWFLAKE_USER    VARCHAR(100)     NOT NULL UNIQUE,   -- matches CURRENT_USER()
    FIRST_NAME        VARCHAR(100)     NOT NULL,
    LAST_NAME         VARCHAR(100)     NOT NULL,
    EMAIL             VARCHAR(255)     NOT NULL UNIQUE,
    DEPARTMENT        VARCHAR(100),
    MANAGER_ID        NUMBER(10)       REFERENCES EXPENSE_APP.CONFIG.EMPLOYEES(EMPLOYEE_ID),
    APP_ROLE          VARCHAR(50)      NOT NULL DEFAULT 'STAFF',  -- STAFF | MANAGER | FINANCE | ADMIN
    IS_ACTIVE         BOOLEAN          NOT NULL DEFAULT TRUE,
    CREATED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
```

### 3.2 `CONFIG.EXPENSE_CATEGORIES`

Lookup table for claim categories. Managed by admin.

```sql
CREATE TABLE EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES (
    CATEGORY_ID       NUMBER(5)        NOT NULL AUTOINCREMENT PRIMARY KEY,
    CATEGORY_NAME     VARCHAR(100)     NOT NULL UNIQUE,  -- e.g. Travel, Meals, Software
    DESCRIPTION       VARCHAR(500),
    DAILY_LIMIT       NUMBER(10, 2),   -- NULL = no limit
    REQUIRES_RECEIPT  BOOLEAN          NOT NULL DEFAULT TRUE,
    IS_ACTIVE         BOOLEAN          NOT NULL DEFAULT TRUE,
    CREATED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
```

**Seed data:**

| CATEGORY_NAME | DAILY_LIMIT | REQUIRES_RECEIPT |
|---|---|---|
| Travel — Flights | NULL | TRUE |
| Travel — Accommodation | NULL | TRUE |
| Travel — Ground Transport | 150.00 | TRUE |
| Meals & Entertainment | 75.00 | TRUE |
| Software & Subscriptions | NULL | TRUE |
| Office Supplies | 50.00 | FALSE |
| Training & Conferences | NULL | TRUE |
| Telecommunications | 100.00 | FALSE |
| Other | NULL | TRUE |

### 3.3 `CLAIMS.EXPENSE_CLAIMS`

Header-level record for each claim submission.

```sql
CREATE TABLE EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS (
    CLAIM_ID          NUMBER(15)       NOT NULL AUTOINCREMENT PRIMARY KEY,
    CLAIM_REFERENCE   VARCHAR(20)      NOT NULL UNIQUE,  -- e.g. EXP-2024-00001
    EMPLOYEE_ID       NUMBER(10)       NOT NULL REFERENCES EXPENSE_APP.CONFIG.EMPLOYEES(EMPLOYEE_ID),
    TITLE             VARCHAR(255)     NOT NULL,         -- e.g. "Sydney Conference June 2024"
    DESCRIPTION       VARCHAR(2000),
    TOTAL_AMOUNT      NUMBER(12, 2)    NOT NULL DEFAULT 0,
    CURRENCY          VARCHAR(3)       NOT NULL DEFAULT 'AUD',
    STATUS            VARCHAR(20)      NOT NULL DEFAULT 'DRAFT',
        -- DRAFT | SUBMITTED | UNDER_REVIEW | APPROVED | REJECTED | PAID | CANCELLED
    SUBMISSION_DATE   DATE,            -- set when STATUS → SUBMITTED
    PERIOD_START      DATE             NOT NULL,
    PERIOD_END        DATE             NOT NULL,
    COST_CENTRE       VARCHAR(50),
    PROJECT_CODE      VARCHAR(50),
    MANAGER_ID        NUMBER(10)       REFERENCES EXPENSE_APP.CONFIG.EMPLOYEES(EMPLOYEE_ID),
    REJECTION_REASON  VARCHAR(2000),   -- populated on REJECTED
    PAID_DATE         DATE,            -- set when STATUS → PAID
    PAYMENT_REF       VARCHAR(100),    -- payroll/ERP reference
    CREATED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
```

**Status flow:**

```
DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED → PAID
                                 ↘ REJECTED
DRAFT → CANCELLED
```

### 3.4 `CLAIMS.EXPENSE_ITEMS`

Individual line items within a claim. A claim has one or more items.

```sql
CREATE TABLE EXPENSE_APP.CLAIMS.EXPENSE_ITEMS (
    ITEM_ID           NUMBER(15)       NOT NULL AUTOINCREMENT PRIMARY KEY,
    CLAIM_ID          NUMBER(15)       NOT NULL REFERENCES EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS(CLAIM_ID),
    CATEGORY_ID       NUMBER(5)        NOT NULL REFERENCES EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES(CATEGORY_ID),
    ITEM_DATE         DATE             NOT NULL,
    DESCRIPTION       VARCHAR(500)     NOT NULL,
    SUPPLIER          VARCHAR(255),    -- vendor / merchant name
    AMOUNT            NUMBER(12, 2)    NOT NULL,
    CURRENCY          VARCHAR(3)       NOT NULL DEFAULT 'AUD',
    GST_AMOUNT        NUMBER(12, 2)    NOT NULL DEFAULT 0,
    RECEIPT_FILE_NAME VARCHAR(255),    -- filename as stored in stage
    RECEIPT_STAGE_PATH VARCHAR(500),   -- full stage path e.g. @RECEIPT_STAGE/2024/001/receipt.pdf
    IS_PERSONAL       BOOLEAN          NOT NULL DEFAULT FALSE,  -- flag if disputed as personal
    NOTES             VARCHAR(1000),
    CREATED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
```

### 3.5 `CLAIMS.APPROVALS`

Approval/rejection action log. Each decision by a manager is recorded as a row.

```sql
CREATE TABLE EXPENSE_APP.CLAIMS.APPROVALS (
    APPROVAL_ID       NUMBER(15)       NOT NULL AUTOINCREMENT PRIMARY KEY,
    CLAIM_ID          NUMBER(15)       NOT NULL REFERENCES EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS(CLAIM_ID),
    APPROVER_ID       NUMBER(10)       NOT NULL REFERENCES EXPENSE_APP.CONFIG.EMPLOYEES(EMPLOYEE_ID),
    ACTION            VARCHAR(20)      NOT NULL,  -- APPROVED | REJECTED | RETURNED | ESCALATED
    COMMENTS          VARCHAR(2000),
    ACTIONED_AT       TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PREVIOUS_STATUS   VARCHAR(20)      NOT NULL,
    NEW_STATUS        VARCHAR(20)      NOT NULL
);
```

### 3.6 `AUDIT.CLAIM_STATUS_HISTORY`

Immutable audit trail of every status change on every claim.

```sql
CREATE TABLE EXPENSE_APP.AUDIT.CLAIM_STATUS_HISTORY (
    HISTORY_ID        NUMBER(15)       NOT NULL AUTOINCREMENT PRIMARY KEY,
    CLAIM_ID          NUMBER(15)       NOT NULL,
    OLD_STATUS        VARCHAR(20),
    NEW_STATUS        VARCHAR(20)      NOT NULL,
    CHANGED_BY_USER   VARCHAR(100)     NOT NULL DEFAULT CURRENT_USER(),
    CHANGED_BY_ROLE   VARCHAR(100)     NOT NULL DEFAULT CURRENT_ROLE(),
    CHANGED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CHANGE_SOURCE     VARCHAR(50)      NOT NULL DEFAULT 'APP',  -- APP | API | MANUAL
    METADATA          VARIANT          -- optional JSON payload for additional context
);
```

### 3.7 `AUDIT.APP_EVENTS`

Application-level event log for debugging and compliance.

```sql
CREATE TABLE EXPENSE_APP.AUDIT.APP_EVENTS (
    EVENT_ID          NUMBER(15)       NOT NULL AUTOINCREMENT PRIMARY KEY,
    EVENT_TYPE        VARCHAR(100)     NOT NULL,  -- CLAIM_SUBMITTED | RECEIPT_UPLOADED | etc.
    USER_NAME         VARCHAR(100)     NOT NULL DEFAULT CURRENT_USER(),
    CLAIM_ID          NUMBER(15),
    ITEM_ID           NUMBER(15),
    DESCRIPTION       VARCHAR(2000),
    EVENT_DATA        VARIANT,                    -- JSON payload
    CREATED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
```

### 3.8 `CLAIMS.NOTIFICATIONS`

Notification queue. Processed by a Snowflake Task to send emails.

```sql
CREATE TABLE EXPENSE_APP.CLAIMS.NOTIFICATIONS (
    NOTIFICATION_ID   NUMBER(15)       NOT NULL AUTOINCREMENT PRIMARY KEY,
    CLAIM_ID          NUMBER(15)       NOT NULL REFERENCES EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS(CLAIM_ID),
    RECIPIENT_EMAIL   VARCHAR(255)     NOT NULL,
    RECIPIENT_NAME    VARCHAR(200)     NOT NULL,
    NOTIFICATION_TYPE VARCHAR(50)      NOT NULL,
        -- CLAIM_SUBMITTED | CLAIM_APPROVED | CLAIM_REJECTED | CLAIM_PAID | APPROVAL_REQUIRED
    SUBJECT           VARCHAR(255)     NOT NULL,
    BODY_TEXT         VARCHAR(5000)    NOT NULL,
    STATUS            VARCHAR(20)      NOT NULL DEFAULT 'PENDING',  -- PENDING | SENT | FAILED
    SEND_ATTEMPTS     NUMBER(3)        NOT NULL DEFAULT 0,
    LAST_ATTEMPT_AT   TIMESTAMP_NTZ,
    SENT_AT           TIMESTAMP_NTZ,
    ERROR_MESSAGE     VARCHAR(1000),
    CREATED_AT        TIMESTAMP_NTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
```

---

## 4. Snowflake Stage (Receipt Storage)

```sql
CREATE STAGE EXPENSE_APP.CLAIMS.RECEIPT_STAGE
    DIRECTORY = (ENABLE = TRUE)
    COMMENT = 'Internal stage for expense claim receipt uploads';
```

**File path convention:**
```
@RECEIPT_STAGE/<YEAR>/<CLAIM_ID>/<ITEM_ID>_<ORIGINAL_FILENAME>
-- e.g. @RECEIPT_STAGE/2024/1042/3_united_airlines_invoice.pdf
```

**Accepted formats:** PDF, PNG, JPG, JPEG  
**Max file size:** 10 MB per receipt

---

## 5. Claim Reference Number Generation

```sql
CREATE SEQUENCE EXPENSE_APP.CLAIMS.CLAIM_SEQ START = 1 INCREMENT = 1;

-- Reference format: EXP-YYYY-#####
-- Generated in app as: 'EXP-' || YEAR(CURRENT_DATE()) || '-' || LPAD(NEXTVAL(CLAIM_SEQ), 5, '0')
```

---

## 6. Key Views

### `CLAIMS.V_MY_CLAIMS` — staff sees own claims only

```sql
CREATE OR REPLACE VIEW EXPENSE_APP.CLAIMS.V_MY_CLAIMS AS
SELECT
    c.CLAIM_ID,
    c.CLAIM_REFERENCE,
    c.TITLE,
    c.STATUS,
    c.TOTAL_AMOUNT,
    c.CURRENCY,
    c.SUBMISSION_DATE,
    c.PERIOD_START,
    c.PERIOD_END,
    c.CREATED_AT,
    c.UPDATED_AT,
    COUNT(i.ITEM_ID) AS ITEM_COUNT
FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c
LEFT JOIN EXPENSE_APP.CLAIMS.EXPENSE_ITEMS i ON c.CLAIM_ID = i.CLAIM_ID
WHERE c.EMPLOYEE_ID = (
    SELECT EMPLOYEE_ID FROM EXPENSE_APP.CONFIG.EMPLOYEES
    WHERE SNOWFLAKE_USER = CURRENT_USER()
)
GROUP BY ALL;
```

### `CLAIMS.V_PENDING_APPROVALS` — manager sees submitted claims for their team

```sql
CREATE OR REPLACE VIEW EXPENSE_APP.CLAIMS.V_PENDING_APPROVALS AS
SELECT
    c.CLAIM_ID,
    c.CLAIM_REFERENCE,
    c.TITLE,
    c.STATUS,
    c.TOTAL_AMOUNT,
    c.CURRENCY,
    c.SUBMISSION_DATE,
    e.FIRST_NAME || ' ' || e.LAST_NAME AS EMPLOYEE_NAME,
    e.DEPARTMENT
FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c
JOIN EXPENSE_APP.CONFIG.EMPLOYEES e ON c.EMPLOYEE_ID = e.EMPLOYEE_ID
WHERE c.STATUS IN ('SUBMITTED', 'UNDER_REVIEW')
  AND c.MANAGER_ID = (
      SELECT EMPLOYEE_ID FROM EXPENSE_APP.CONFIG.EMPLOYEES
      WHERE SNOWFLAKE_USER = CURRENT_USER()
  );
```

---

## 7. Stored Procedures

### `SUBMIT_CLAIM(CLAIM_ID NUMBER)`

Validates and transitions a DRAFT claim to SUBMITTED. Triggers notification.

```sql
CREATE OR REPLACE PROCEDURE EXPENSE_APP.CLAIMS.SUBMIT_CLAIM(CLAIM_ID NUMBER)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
    -- Validate claim belongs to current user and is in DRAFT
    -- Validate at least one expense item exists
    -- Validate total_amount > 0
    -- Update status to SUBMITTED, set SUBMISSION_DATE = CURRENT_DATE()
    -- Insert into AUDIT.CLAIM_STATUS_HISTORY
    -- Insert APPROVAL_REQUIRED notification for manager
    RETURN 'SUCCESS';
END;
$$;
```

### `APPROVE_CLAIM(CLAIM_ID NUMBER, COMMENTS VARCHAR)`

Manager approves a claim.

### `REJECT_CLAIM(CLAIM_ID NUMBER, REASON VARCHAR)`

Manager rejects a claim with a mandatory reason.

### `MARK_PAID(CLAIM_ID NUMBER, PAYMENT_REF VARCHAR)`

Finance marks an approved claim as paid.

---

## 8. Snowflake Task — Notification Sender

Runs every 5 minutes, processes PENDING notifications.

```sql
CREATE TASK EXPENSE_APP.CLAIMS.SEND_NOTIFICATIONS
    WAREHOUSE = COMPUTE_WH
    SCHEDULE  = '5 MINUTE'
AS
    CALL EXPENSE_APP.CLAIMS.PROCESS_PENDING_NOTIFICATIONS();
```

---

## 9. Streamlit App — Page Structure

```
streamlit_app.py          ← entry point, login detection, role routing
pages/
  1_Submit_Claim.py       ← staff: new claim form + line items + receipt upload
  2_My_Claims.py          ← staff: list and track own claims
  3_Approval_Queue.py     ← managers: pending claims, approve/reject actions
  4_Finance_Dashboard.py  ← finance: all claims, filters, mark paid, CSV export
  5_Admin.py              ← admin: manage categories, employees, system config
utils/
  auth.py                 ← resolve current user, role, employee record
  db.py                   ← Snowflake connection helper, parameterized query wrapper
  notifications.py        ← insert notification rows
  formatting.py           ← currency, date, status badge formatting
```

---

## 10. Page Specifications

### Page 1 — Submit Claim

**Accessible by:** STAFF, MANAGER, FINANCE, ADMIN

**Fields:**

| Field | Type | Validation |
|---|---|---|
| Title | Text input | Required, max 255 chars |
| Period Start | Date picker | Required, not future |
| Period End | Date picker | Required ≥ Period Start |
| Cost Centre | Text input | Optional |
| Project Code | Text input | Optional |
| Description | Text area | Optional, max 2000 chars |

**Line Items (repeatable):**

| Field | Type | Validation |
|---|---|---|
| Date | Date picker | Required, within period |
| Category | Selectbox (from EXPENSE_CATEGORIES) | Required |
| Description | Text input | Required |
| Supplier | Text input | Optional |
| Amount (AUD) | Number input | Required, > 0 |
| GST Amount | Number input | Optional, ≥ 0 |
| Receipt Upload | File uploader (PDF/PNG/JPG) | Required if category REQUIRES_RECEIPT |
| Notes | Text area | Optional |

**Actions:** Save as Draft / Submit

---

### Page 2 — My Claims

**Accessible by:** All roles (scoped to own claims)

- Table of all claims with status badges
- Filter by status and date range
- Click to expand claim details and line items
- Cancel button available for DRAFT claims
- Download claim as PDF (future phase)

---

### Page 3 — Approval Queue

**Accessible by:** MANAGER, FINANCE, ADMIN

- List of SUBMITTED / UNDER_REVIEW claims for the manager's direct reports
- Click claim to expand full detail including receipts
- Approve button → modal for optional comments → calls `APPROVE_CLAIM`
- Reject button → modal with mandatory reason text → calls `REJECT_CLAIM`
- History tab showing past decisions

---

### Page 4 — Finance Dashboard

**Accessible by:** FINANCE, ADMIN

**Summary KPIs:**
- Total pending amount (SUBMITTED + UNDER_REVIEW)
- Total approved, awaiting payment
- Total paid this month / YTD

**Claims table with filters:**
- Status, Department, Employee, Date Range, Cost Centre

**Actions:**
- Mark as Paid (bulk or individual) → enter Payment Reference
- Export to CSV

**Charts:**
- Claims by department (bar)
- Monthly spend trend (line)
- Claims by category (pie)

---

### Page 5 — Admin

**Accessible by:** ADMIN only

- Manage expense categories (add, edit, deactivate)
- Manage employees (add, assign manager, change role)
- View audit log (CLAIM_STATUS_HISTORY, APP_EVENTS)
- System configuration (currency, notification settings)

---

## 11. Security Considerations

- Row-level security enforced via views (`V_MY_CLAIMS`, `V_PENDING_APPROVALS`) filtered by `CURRENT_USER()`
- All DML routed through stored procedures — app roles do not have direct UPDATE on the claims table except through procedure execution
- Receipt files scoped per claim in stage path — staff can write to their own paths only
- Audit tables are INSERT-only for app roles (no UPDATE or DELETE)
- Secrets stored in Snowflake secrets object or `.streamlit/secrets.toml` locally — never committed to source control
- `REJECTION_REASON` and approval comments are mandatory and logged to the audit table

---

## 12. Out of Scope (Post-MVP)

- Multi-currency conversion (FX rates)
- OCR receipt parsing (Cortex Document AI)
- Mobile-optimised UI
- Integration with payroll / ERP systems
- Delegated approvals (manager absence)
- PDF export of individual claims
- SSO / SAML group-based role assignment
