# Business Case Template

| **Use Case Name:** | Staff Expense Claims |
|---|---|

---

## User Story

As a **Staff Member**, I want to **submit and track expense claims digitally**, so that **I can get reimbursed faster with less manual paperwork**.

---

## Solution Summary

A self-service web app where staff submit expense claims with receipt uploads, managers approve or reject submissions, and finance teams track reimbursement status — all stored and processed in Snowflake.

---

## Outcomes

- Faster reimbursement turnaround for staff
- Reduced manual paperwork and email chains
- Improved visibility for finance teams on outstanding claims
- Audit trail for all submissions and approvals

## Risks / Delivery Blockers

- Receipt upload file size and format constraints
- Approval workflow complexity across multiple managers
- Integration with existing payroll or ERP systems

---

## MVP Solution Design

- Build expense submission form with category, amount, date, and receipt upload
- Build manager approval/rejection workflow with email notifications
- Finance dashboard showing pending, approved, and paid claims
- Store all data in Snowflake tables with full audit history
- Automate as much as possible to reduce manual entry
