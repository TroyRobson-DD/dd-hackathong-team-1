import streamlit as st
from utils.db import get_conn, query, execute, clear_cache
from utils.auth import require_role
from utils.formatting import status_badge, fmt_currency, fmt_date

st.set_page_config(page_title="My Claims", page_icon="📋", layout="wide")

conn = get_conn()
emp = require_role(conn, ["STAFF", "MANAGER", "FINANCE", "ADMIN"])
eid = int(emp["EMPLOYEE_ID"])

st.title("📋 My Claims")
st.divider()

# ── Filters ────────────────────────────────────────────────────────────────────
fc1, fc2, fc3 = st.columns([3, 2, 2])
status_opts = ["All", "DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "PAID", "CANCELLED"]
sel_status  = fc1.selectbox("Filter by Status", status_opts, index=0)
date_from   = fc2.date_input("From", value=None, key="myfrom")
date_to     = fc3.date_input("To",   value=None, key="myto")

# ── Build query ─────────────────────────────────────────────────────────────────
where_clauses = ["c.EMPLOYEE_ID = %s"]
params: list = [eid]

if sel_status != "All":
    where_clauses.append("c.STATUS = %s")
    params.append(sel_status)
if date_from:
    where_clauses.append("c.CREATED_AT >= %s")
    params.append(str(date_from))
if date_to:
    where_clauses.append("c.CREATED_AT <= DATEADD('day',1,%s)")
    params.append(str(date_to))

where_sql = " AND ".join(where_clauses)

claims_df = query(conn, f"""
    SELECT
        c.CLAIM_ID, c.CLAIM_REFERENCE, c.TITLE, c.STATUS,
        c.TOTAL_AMOUNT, c.CURRENCY, c.SUBMISSION_DATE,
        c.PERIOD_START, c.PERIOD_END, c.CREATED_AT,
        c.REJECTION_REASON,
        COUNT(i.ITEM_ID) AS ITEM_COUNT
    FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c
    LEFT JOIN EXPENSE_APP.CLAIMS.EXPENSE_ITEMS i ON c.CLAIM_ID = i.CLAIM_ID
    WHERE {where_sql}
    GROUP BY ALL
    ORDER BY c.CREATED_AT DESC
""", params=tuple(params))

if claims_df.empty:
    st.info("No claims found. Use **Submit Claim** to get started.")
    st.stop()

st.caption(f"{len(claims_df)} claim(s) found")

# ── Claims list ────────────────────────────────────────────────────────────────
for _, row in claims_df.iterrows():
    claim_id  = int(row["CLAIM_ID"])
    claim_ref = row["CLAIM_REFERENCE"]
    status    = row["STATUS"]

    header = (
        f"{claim_ref} &nbsp;·&nbsp; **{row['TITLE']}** &nbsp;·&nbsp; "
        f"{status_badge(status)} &nbsp;·&nbsp; {fmt_currency(row['TOTAL_AMOUNT'])} &nbsp;·&nbsp; "
        f"{int(row['ITEM_COUNT'])} item(s)"
    )

    with st.expander(f"{claim_ref} — {row['TITLE']} | {status} | {fmt_currency(row['TOTAL_AMOUNT'])}"):
        st.markdown(header, unsafe_allow_html=True)
        st.divider()

        dc1, dc2, dc3, dc4 = st.columns(4)
        dc1.metric("Total Amount",   fmt_currency(row["TOTAL_AMOUNT"]))
        dc2.metric("Period",         f"{fmt_date(row['PERIOD_START'])} → {fmt_date(row['PERIOD_END'])}")
        dc3.metric("Submitted",      fmt_date(row["SUBMISSION_DATE"]) if row["SUBMISSION_DATE"] else "Not yet")
        dc4.metric("Items",          int(row["ITEM_COUNT"]))

        if status == "REJECTED" and row["REJECTION_REASON"]:
            st.error(f"**Rejection reason:** {row['REJECTION_REASON']}")

        # Line items table
        items_df = query(conn, """
            SELECT i.ITEM_DATE, cat.CATEGORY_NAME, i.DESCRIPTION, i.SUPPLIER,
                   i.AMOUNT, i.GST_AMOUNT, i.RECEIPT_FILE_NAME, i.NOTES
            FROM EXPENSE_APP.CLAIMS.EXPENSE_ITEMS i
            JOIN EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES cat ON i.CATEGORY_ID = cat.CATEGORY_ID
            WHERE i.CLAIM_ID = %s
            ORDER BY i.ITEM_DATE
        """, params=(claim_id,))

        if not items_df.empty:
            st.subheader("Line Items")
            st.dataframe(
                items_df.rename(columns={
                    "ITEM_DATE": "Date", "CATEGORY_NAME": "Category",
                    "DESCRIPTION": "Description", "SUPPLIER": "Supplier",
                    "AMOUNT": "Amount", "GST_AMOUNT": "GST",
                    "RECEIPT_FILE_NAME": "Receipt", "NOTES": "Notes",
                }),
                use_container_width=True,
            )

        # Approval history
        hist_df = query(conn, """
            SELECT a.ACTIONED_AT, e.FIRST_NAME||' '||e.LAST_NAME AS APPROVER,
                   a.ACTION, a.COMMENTS
            FROM EXPENSE_APP.CLAIMS.APPROVALS a
            JOIN EXPENSE_APP.CONFIG.EMPLOYEES e ON a.APPROVER_ID = e.EMPLOYEE_ID
            WHERE a.CLAIM_ID = %s ORDER BY a.ACTIONED_AT DESC
        """, params=(claim_id,))

        if not hist_df.empty:
            st.subheader("Approval History")
            st.dataframe(hist_df.rename(columns={
                "ACTIONED_AT": "Date", "APPROVER": "Approver",
                "ACTION": "Action", "COMMENTS": "Comments",
            }), use_container_width=True)

        # Cancel button for DRAFT claims
        if status == "DRAFT":
            st.divider()
            if st.button("🗑️ Cancel Claim", key=f"cancel_{claim_id}", type="secondary"):
                execute(conn, """
                    UPDATE EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS
                    SET STATUS = 'CANCELLED', UPDATED_AT = CURRENT_TIMESTAMP()
                    WHERE CLAIM_ID = %s AND EMPLOYEE_ID = %s
                """, (claim_id, eid))
                execute(conn, """
                    INSERT INTO EXPENSE_APP.AUDIT.CLAIM_STATUS_HISTORY
                        (CLAIM_ID, OLD_STATUS, NEW_STATUS, CHANGE_SOURCE)
                    VALUES (%s,'DRAFT','CANCELLED','APP')
                """, (claim_id,))
                clear_cache()
                st.success(f"Claim {claim_ref} cancelled.")
                st.experimental_rerun()
