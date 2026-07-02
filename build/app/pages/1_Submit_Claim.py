import streamlit as st
import datetime
from utils.db import get_conn, query, execute, clear_cache
from utils.auth import require_role, display_name
from utils.formatting import fmt_currency

st.set_page_config(page_title="Submit Claim", page_icon="📝", layout="wide")

conn = get_conn()
emp = require_role(conn, ["STAFF", "MANAGER", "FINANCE", "ADMIN"])
eid = int(emp["EMPLOYEE_ID"])

st.title("📝 Submit Expense Claim")
st.divider()

# ── Load categories ────────────────────────────────────────────────────────────
cats_df = query(conn, """
    SELECT CATEGORY_ID, CATEGORY_NAME, DAILY_LIMIT, REQUIRES_RECEIPT
    FROM EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES
    WHERE IS_ACTIVE = TRUE ORDER BY CATEGORY_NAME
""")
cat_map = {row["CATEGORY_NAME"]: row for _, row in cats_df.iterrows()}
cat_names = list(cat_map.keys())

# ── Session state for line items ───────────────────────────────────────────────
if "line_items" not in st.session_state:
    st.session_state.line_items = [{}]

# ── Claim header form ──────────────────────────────────────────────────────────
st.subheader("Claim Details")
col1, col2 = st.columns(2)
with col1:
    title = st.text_input("Claim Title *", placeholder="e.g. Sydney Conference June 2024")
    period_start = st.date_input("Period Start *", value=datetime.date.today().replace(day=1))
    cost_centre = st.text_input("Cost Centre", placeholder="Optional")
with col2:
    description = st.text_area("Description", placeholder="Optional — purpose of this claim", height=68)
    period_end = st.date_input("Period End *", value=datetime.date.today())
    project_code = st.text_input("Project Code", placeholder="Optional")

st.divider()

# ── Line items ─────────────────────────────────────────────────────────────────
st.subheader("Expense Line Items")

items_data = []   # collect valid data for each row
upload_map = {}   # idx → uploaded file

for idx, _ in enumerate(st.session_state.line_items):
    st.markdown("---")
    with st.container():
        hcol1, hcol2 = st.columns([6, 1])
        hcol1.markdown(f"**Item {idx + 1}**")
        if hcol2.button("✕ Remove", key=f"remove_{idx}", disabled=len(st.session_state.line_items) == 1):
            st.session_state.line_items.pop(idx)
            st.experimental_rerun()

        r1c1, r1c2, r1c3 = st.columns([2, 3, 2])
        item_date = r1c1.date_input("Date *", value=datetime.date.today(), key=f"idate_{idx}")
        cat_name  = r1c2.selectbox("Category *", cat_names, key=f"icat_{idx}")
        amount    = r1c3.number_input("Amount (AUD) *", min_value=0.01, step=0.01, format="%.2f", key=f"iamt_{idx}")

        r2c1, r2c2, r2c3 = st.columns([3, 2, 2])
        item_desc = r2c1.text_input("Description *", key=f"idesc_{idx}")
        supplier  = r2c2.text_input("Supplier / Merchant", key=f"isup_{idx}")
        gst       = r2c3.number_input("GST Amount", min_value=0.0, step=0.01, format="%.2f", key=f"igst_{idx}")

        cat_row = cat_map[cat_name]
        needs_receipt = bool(cat_row["REQUIRES_RECEIPT"])
        receipt_label = f"Receipt Reference {'(required)' if needs_receipt else '(optional)'}"  
        receipt_ref = st.text_input(receipt_label, placeholder="e.g. INV-1234 or scan ref", key=f"ifile_{idx}")
        upload_map[idx] = receipt_ref or None

        notes = st.text_input("Notes", key=f"inotes_{idx}")

        items_data.append({
            "date": item_date,
            "cat_name": cat_name,
            "cat_id": int(cat_row["CATEGORY_ID"]),
            "requires_receipt": needs_receipt,
            "desc": item_desc,
            "supplier": supplier,
            "amount": amount,
            "gst": gst,
            "notes": notes,
        })

if st.button("➕ Add Another Item"):
    st.session_state.line_items.append({})
    st.experimental_rerun()

# Running total
total = sum(i["amount"] for i in items_data)
st.markdown(f"### Total: **{fmt_currency(total)}**")

st.divider()


# ── Validation ─────────────────────────────────────────────────────────────────
def validate(submit: bool) -> list[str]:
    errors = []
    if not title.strip():
        errors.append("Claim Title is required.")
    if period_end < period_start:
        errors.append("Period End must be on or after Period Start.")
    for i, item in enumerate(items_data):
        prefix = f"Item {i+1}"
        if not item["desc"].strip():
            errors.append(f"{prefix}: Description is required.")
        if item["amount"] <= 0:
            errors.append(f"{prefix}: Amount must be greater than 0.")
        if item["requires_receipt"] and submit and not upload_map.get(i):
            errors.append(f"{prefix}: Receipt reference is required for category '{item['cat_name']}'.")
    return errors


# ── Save / Submit ──────────────────────────────────────────────────────────────
def save_claim(status: str):
    errors = validate(submit=(status == "SUBMITTED"))
    if errors:
        for e in errors:
            st.error(e)
        return

    # Generate claim reference — use conn.sql directly to bypass cache
    ref_df = conn.sql("SELECT 'EXP-'||YEAR(CURRENT_DATE())||'-'||LPAD(EXPENSE_APP.CLAIMS.CLAIM_SEQ.NEXTVAL,5,'0') AS REF").to_pandas()
    claim_ref = ref_df.iloc[0]["REF"]

    # Get manager from employee record — guard against pandas NaN
    import pandas as pd
    _mgr = emp.get("MANAGER_ID")
    manager_id = None if (_mgr is None or (isinstance(_mgr, float) and pd.isna(_mgr))) else _mgr

    # Insert claim header
    execute(conn, """
        INSERT INTO EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS
            (CLAIM_REFERENCE, EMPLOYEE_ID, TITLE, DESCRIPTION,
             TOTAL_AMOUNT, CURRENCY, STATUS, SUBMISSION_DATE,
             PERIOD_START, PERIOD_END, COST_CENTRE, PROJECT_CODE, MANAGER_ID)
        VALUES (%s,%s,%s,%s,%s,'AUD',%s,%s,%s,%s,%s,%s,%s)
    """, (
        claim_ref, eid, title.strip(), description.strip(),
        total, status,
        datetime.date.today() if status == "SUBMITTED" else None,
        period_start, period_end,
        cost_centre.strip() or None, project_code.strip() or None,
        int(manager_id) if manager_id is not None else None,
    ))

    # Get new claim ID — bypass cache so we see the just-inserted row
    claim_df = conn.sql(f"SELECT CLAIM_ID FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS WHERE CLAIM_REFERENCE = '{claim_ref}'").to_pandas()
    claim_id = int(claim_df.iloc[0]["CLAIM_ID"])

    # Insert line items
    for i, item in enumerate(items_data):
        execute(conn, """
            INSERT INTO EXPENSE_APP.CLAIMS.EXPENSE_ITEMS
                (CLAIM_ID, CATEGORY_ID, ITEM_DATE, DESCRIPTION, SUPPLIER,
                 AMOUNT, CURRENCY, GST_AMOUNT, NOTES)
            VALUES (%s,%s,%s,%s,%s,%s,'AUD',%s,%s)
        """, (
            claim_id, item["cat_id"], item["date"], item["desc"].strip(),
            item["supplier"].strip() or None, item["amount"], item["gst"],
            item["notes"].strip() or None,
        ))

        # Store receipt reference if provided
        receipt_ref = upload_map.get(i)
        if receipt_ref:
            item_df = query(conn, "SELECT MAX(ITEM_ID) AS ID FROM EXPENSE_APP.CLAIMS.EXPENSE_ITEMS WHERE CLAIM_ID = %s", params=(claim_id,))
            item_id = int(item_df.iloc[0]["ID"])
            execute(conn, """
                UPDATE EXPENSE_APP.CLAIMS.EXPENSE_ITEMS
                SET RECEIPT_FILE_NAME = %s
                WHERE ITEM_ID = %s
            """, (receipt_ref, item_id))

    # Audit trail
    execute(conn, """
        INSERT INTO EXPENSE_APP.AUDIT.CLAIM_STATUS_HISTORY
            (CLAIM_ID, OLD_STATUS, NEW_STATUS, CHANGE_SOURCE)
        VALUES (%s, NULL, %s, 'APP')
    """, (claim_id, status))

    # Notification to manager on submit
    if status == "SUBMITTED" and manager_id:
        mgr_df = query(conn, "SELECT EMAIL, FIRST_NAME||' '||LAST_NAME AS NAME FROM EXPENSE_APP.CONFIG.EMPLOYEES WHERE EMPLOYEE_ID = %s", params=(int(manager_id),))
        if not mgr_df.empty:
            execute(conn, """
                INSERT INTO EXPENSE_APP.CLAIMS.NOTIFICATIONS
                    (CLAIM_ID, RECIPIENT_EMAIL, RECIPIENT_NAME, NOTIFICATION_TYPE, SUBJECT, BODY_TEXT)
                VALUES (%s,%s,%s,'APPROVAL_REQUIRED',%s,%s)
            """, (
                claim_id,
                mgr_df.iloc[0]["EMAIL"],
                mgr_df.iloc[0]["NAME"],
                f"Expense Claim Awaiting Approval: {claim_ref}",
                f"{display_name(emp)} has submitted expense claim {claim_ref} for {fmt_currency(total)} requiring your approval.",
            ))

    clear_cache()
    st.session_state.line_items = [{}]
    st.success(f"Claim **{claim_ref}** {'submitted' if status == 'SUBMITTED' else 'saved as draft'} successfully!")
    st.experimental_rerun()


col_save, col_submit = st.columns([1, 1])
with col_save:
    if st.button("💾 Save as Draft", use_container_width=True):
        save_claim("DRAFT")
with col_submit:
    if st.button("🚀 Submit Claim", type="primary", use_container_width=True):
        save_claim("SUBMITTED")
