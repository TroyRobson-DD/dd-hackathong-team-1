# Demo Narrative — Staff Expense Claims

## Elevator Pitch (30 seconds)

> "Every company deals with expense claims — but most still run them through email chains and spreadsheets. We built a Snowflake-native app where staff submit claims in seconds, managers approve with one click, and finance has a live dashboard showing exactly what's owed and what's been paid. Everything lives in Snowflake — zero external systems."

---

## Demo Flow (5 minutes)

### Scene 1 — Staff Submits a Claim (1 min)

**Persona:** Sarah, a sales rep returning from a customer visit.

1. Log in as `EXPENSE_APP_STAFF` role.
2. Navigate to **Submit Claim**.
3. Enter claim title: "Customer Visit — Melbourne, June 2024".
4. Add two line items:
   - Flights: $420.00 — upload a sample PDF receipt.
   - Meals: $68.50 — upload a sample JPG receipt.
5. Click **Submit** — claim moves to `SUBMITTED` status.
6. *Talking point: receipts stored directly in Snowflake stage — no third-party file storage needed.*

---

### Scene 2 — Manager Approves (1 min)

**Persona:** James, Sarah's direct manager.

1. Log in as `EXPENSE_APP_MANAGER` role.
2. Navigate to **Approval Queue** — Sarah's claim appears immediately.
3. Click to expand — view line items and receipts inline.
4. Click **Approve** with a comment: "Approved. Matches trip itinerary."
5. Claim moves to `APPROVED` — Sarah receives a notification.
6. *Talking point: full audit trail — every action is logged with timestamp and role.*

---

### Scene 3 — Finance Dashboard (1.5 min)

**Persona:** Lisa, a finance officer.

1. Log in as `EXPENSE_APP_FINANCE` role.
2. Navigate to **Finance Dashboard**.
3. Show KPI tiles: total pending, total approved awaiting payment, total paid this month.
4. Filter by department — show Engineering claims.
5. Select Sarah's approved claim — click **Mark as Paid**, enter payment reference.
6. Show spend-by-category chart.
7. *Talking point: no more Excel exports — live data, always up to date.*

---

### Scene 4 — Cortex Agent Q&A (1 min)

1. Open the Expense Policy Assistant.
2. Ask: *"What is the meal allowance per day?"*
3. Ask: *"Show me total spend by department this quarter."*
4. *Talking point: AI built in — staff get instant answers, finance gets instant insights.*

---

## Key Differentiators

| Feature | Traditional Approach | Our App |
|---|---|---|
| Submission | Email + spreadsheet | Self-service Streamlit form |
| Receipts | Email attachments | Snowflake internal stage |
| Approval | Reply-all email chains | One-click in-app workflow |
| Audit trail | None / manual log | Immutable Snowflake audit table |
| Finance reporting | Monthly Excel export | Live dashboard |
| AI | None | Cortex Agent for policy Q&A + analytics |

---

## Anticipated Questions

**Q: How does role security work?**
A: Roles are enforced at the Snowflake layer — views filter by `CURRENT_USER()`, so staff can only ever see their own claims, regardless of how they query the data.

**Q: What happens to receipts?**
A: Uploaded to a Snowflake internal stage, scoped by claim ID. Finance and managers can view them inline in the app.

**Q: Can this scale to a large organisation?**
A: Yes — all compute and storage is Snowflake-native. The app scales with your warehouse size.
