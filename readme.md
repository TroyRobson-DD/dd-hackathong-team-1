# Staff Expense Claims — Hackathon Project

A Streamlit-in-Snowflake application allowing staff to submit expense claims, managers to approve or reject them, and finance teams to track reimbursement status.

## Folder Structure

```
├── readme.md               ← this file
├── agents.md               ← Cortex agent definitions
├── context/
│   ├── business_canvas.md  ← business case template
│   └── demo_narrative.md   ← demo script and talking points
├── solution/
│   └── solution_design.md  ← detailed technical specification
└── build/
    ├── expense_claims_ddl.sql  ← Snowflake DDL (tables, roles, views, procedures)
    └── app/                    ← Streamlit application source
```

## Quick Start

1. Run `build/expense_claims_ddl.sql` against your Snowflake account to create all objects.
2. Deploy the Streamlit app from `build/app/` using `snow streamlit deploy --replace`.
3. Assign roles (`EXPENSE_APP_STAFF`, `EXPENSE_APP_MANAGER`, `EXPENSE_APP_FINANCE`) to users.
