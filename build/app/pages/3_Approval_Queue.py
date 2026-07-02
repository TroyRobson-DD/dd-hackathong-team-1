import streamlit as st
from utils.db import get_conn, query, execute, clear_cache
from utils.auth import require_role, display_name
from utils.formatting import status_badge, fmt_currency, fmt_date

st.set_page_config(page_title="Approval Queue", page_icon="✅", layout="wide")

conn = get_conn()
emp = require_role(conn, ["MANAGER", "FINANCE", "ADMIN"])
eid = int(emp["EMPLOYEE_ID"])
role = emp["APP_ROLE"]

st.title("✅ Approval Queue")
st.divider()

# ── Load pending claims ────────────────────────────────────────────────────────
if role == "MANAGER":
    # Managers only see their direct reports
    pending_df = query(conn, """
        SELECT c.CLAIM_ID, c.CLAIM_REFERENCE, c.TITLE, c.STATUS,
               c.TOTAL_AMOUNT, c.CURRENCY, c.SUBMISSION_DATE,
               e.FIRST_NAME||' '||e.LAST_NAME AS EMPLOYEE_NAME,
               e.DEPARTMENT, e.EMAIL AS EMPLOYEE_EMAIL
        FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c
        JOIN EXPENSE_APP.CONFIG.EMPLOYEES e ON c.EMPLOYEE_ID = e.EMPLOYEE_ID
        WHERE c.STATUS IN ('SUBMITTED','UNDER_REVIEW')
          AND c.MANAGER_ID = %s
        ORDER BY c.SUBMISSION_DATE
    """, params=(eid,))
else:
    # Finance / Admin see all pending
    pending_df = query(conn, """
        SELECT c.CLAIM_ID, c.CLAIM_REFERENCE, c.TITLE, c.STATUS,
               c.TOTAL_AMOUNT, c.CURRENCY, c.SUBMISSION_DATE,
               e.FIRST_NAME||' '||e.LAST_NAME AS EMPLOYEE_NAME,
               e.DEPARTMENT, e.EMAIL AS EMPLOYEE_EMAIL
        FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c
        JOIN EXPENSE_APP.CONFIG.EMPLOYEES e ON c.EMPLOYEE_ID = e.EMPLOYEE_ID
        WHERE c.STATUS IN ('SUBMITTED','UNDER_REVIEW')
        ORDER BY c.SUBMISSION_DATE
    """)

if pending_df.empty:
    st.success("No claims pending approval. All caught up!")
    st.stop()

st.caption(f"{len(pending_df)} claim(s) awaiting action")

# ── Claims list ────────────────────────────────────────────────────────────────
for _, row in pending_df.iterrows():
    claim_id  = int(row["CLAIM_ID"])
    claim_ref = row["CLAIM_REFERENCE"]
    status    = row["STATUS"]

    with st.expander(
        f"{claim_ref} — {row['EMPLOYEE_NAME']} | {row['TITLE']} | "
        f"{fmt_currency(row['TOTAL_AMOUNT'])} | {fmt_date(row['SUBMISSION_DATE'])}"
    ):
        # Summary row
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Employee",      row["EMPLOYEE_NAME"])
        sc2.metric("Amount",        fmt_currency(row["TOTAL_AMOUNT"]))
        sc3.metric("Submitted",     fmt_date(row["SUBMISSION_DATE"]))
        sc4.markdown(f"**Status**  \n{status_badge(status)}", unsafe_allow_html=True)

        if row.get("DEPARTMENT"):
            st.caption(f"Department: {row['DEPARTMENT']}")

        # Line items
        items_df = query(conn, """
            SELECT i.ITEM_DATE, cat.CATEGORY_NAME, i.DESCRIPTION, i.SUPPLIER,
                   i.AMOUNT, i.GST_AMOUNT, i.RECEIPT_FILE_NAME, i.RECEIPT_STAGE_PATH, i.NOTES
            FROM EXPENSE_APP.CLAIMS.EXPENSE_ITEMS i
            JOIN EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES cat ON i.CATEGORY_ID = cat.CATEGORY_ID
            WHERE i.CLAIM_ID = %s ORDER BY i.ITEM_DATE
        """, params=(claim_id,))

        st.subheader("Line Items")
        if not items_df.empty:
            display_df = items_df[["ITEM_DATE","CATEGORY_NAME","DESCRIPTION","SUPPLIER","AMOUNT","GST_AMOUNT","RECEIPT_FILE_NAME","NOTES"]].rename(columns={
                "ITEM_DATE": "Date", "CATEGORY_NAME": "Category",
                "DESCRIPTION": "Description", "SUPPLIER": "Supplier",
                "AMOUNT": "Amount (AUD)", "GST_AMOUNT": "GST",
                "RECEIPT_FILE_NAME": "Receipt", "NOTES": "Notes",
            })
            st.dataframe(display_df, use_container_width=True)

            # Receipt download links
            receipts = items_df[items_df["RECEIPT_STAGE_PATH"].notna()]
            if not receipts.empty:
                st.caption("Receipts attached: " + ", ".join(receipts["RECEIPT_FILE_NAME"].tolist()))

        st.divider()

        # ── Approve / Reject actions ──────────────────────────────────────────
        acol1, acol2 = st.columns(2)

        with acol1:
            with st.form(key=f"approve_form_{claim_id}"):
                st.markdown(f"**Approve** {claim_ref} ({fmt_currency(row['TOTAL_AMOUNT'])})?")
                approve_comment = st.text_area("Comments (optional)")
                if st.form_submit_button("✅ Confirm Approval", type="primary", use_container_width=True):
                    execute(conn, """
                        UPDATE EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS
                        SET STATUS = 'APPROVED', UPDATED_AT = CURRENT_TIMESTAMP()
                        WHERE CLAIM_ID = %s
                    """, (claim_id,))
                    execute(conn, """
                        INSERT INTO EXPENSE_APP.CLAIMS.APPROVALS
                            (CLAIM_ID, APPROVER_ID, ACTION, COMMENTS, PREVIOUS_STATUS, NEW_STATUS)
                        VALUES (%s,%s,'APPROVED',%s,%s,'APPROVED')
                    """, (claim_id, eid, approve_comment.strip() or None, status))
                    execute(conn, """
                        INSERT INTO EXPENSE_APP.AUDIT.CLAIM_STATUS_HISTORY
                            (CLAIM_ID, OLD_STATUS, NEW_STATUS, CHANGE_SOURCE)
                        VALUES (%s,%s,'APPROVED','APP')
                    """, (claim_id, status))
                    emp_email = row["EMPLOYEE_EMAIL"]
                    execute(conn, """
                        INSERT INTO EXPENSE_APP.CLAIMS.NOTIFICATIONS
                            (CLAIM_ID, RECIPIENT_EMAIL, RECIPIENT_NAME, NOTIFICATION_TYPE, SUBJECT, BODY_TEXT)
                        VALUES (%s,%s,%s,'CLAIM_APPROVED',%s,%s)
                    """, (
                        claim_id, emp_email, row["EMPLOYEE_NAME"],
                        f"Expense Claim Approved: {claim_ref}",
                        f"Your expense claim {claim_ref} for {fmt_currency(row['TOTAL_AMOUNT'])} has been approved by {display_name(emp)}.",
                    ))
                    clear_cache()
                    st.success(f"Claim {claim_ref} approved.")
                    st.experimental_rerun()

        with acol2:
            with st.form(key=f"reject_form_{claim_id}"):
                st.markdown(f"**Reject** {claim_ref}?")
                reject_reason = st.text_area("Reason for rejection *")
                if st.form_submit_button("❌ Confirm Rejection", type="primary", use_container_width=True):
                    if not reject_reason.strip():
                        st.error("A rejection reason is required.")
                    else:
                        execute(conn, """
                            UPDATE EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS
                            SET STATUS = 'REJECTED',
                                REJECTION_REASON = %s,
                                UPDATED_AT = CURRENT_TIMESTAMP()
                            WHERE CLAIM_ID = %s
                        """, (reject_reason.strip(), claim_id))
                        execute(conn, """
                            INSERT INTO EXPENSE_APP.CLAIMS.APPROVALS
                                (CLAIM_ID, APPROVER_ID, ACTION, COMMENTS, PREVIOUS_STATUS, NEW_STATUS)
                            VALUES (%s,%s,'REJECTED',%s,%s,'REJECTED')
                        """, (claim_id, eid, reject_reason.strip(), status))
                        execute(conn, """
                            INSERT INTO EXPENSE_APP.AUDIT.CLAIM_STATUS_HISTORY
                                (CLAIM_ID, OLD_STATUS, NEW_STATUS, CHANGE_SOURCE)
                            VALUES (%s,%s,'REJECTED','APP')
                        """, (claim_id, status))
                        emp_email = row["EMPLOYEE_EMAIL"]
                        execute(conn, """
                            INSERT INTO EXPENSE_APP.CLAIMS.NOTIFICATIONS
                                (CLAIM_ID, RECIPIENT_EMAIL, RECIPIENT_NAME, NOTIFICATION_TYPE, SUBJECT, BODY_TEXT)
                            VALUES (%s,%s,%s,'CLAIM_REJECTED',%s,%s)
                        """, (
                            claim_id, emp_email, row["EMPLOYEE_NAME"],
                            f"Expense Claim Rejected: {claim_ref}",
                            f"Your expense claim {claim_ref} was rejected. Reason: {reject_reason.strip()}",
                        ))
                        clear_cache()
                        st.success(f"Claim {claim_ref} rejected.")
                        st.experimental_rerun()
