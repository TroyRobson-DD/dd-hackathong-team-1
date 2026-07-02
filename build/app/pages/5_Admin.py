import streamlit as st
from utils.db import get_conn, query, execute, clear_cache
from utils.auth import require_role
from utils.formatting import fmt_currency, fmt_date

st.set_page_config(page_title="Admin", page_icon="⚙️", layout="wide")

conn = get_conn()
emp = require_role(conn, ["ADMIN"])

st.title("⚙️ Admin")
st.divider()

tab_cats, tab_emps, tab_audit = st.tabs(["📂 Expense Categories", "👥 Employees", "🔍 Audit Log"])

# ── Tab 1: Expense Categories ─────────────────────────────────────────────────
with tab_cats:
    st.subheader("Expense Categories")

    cats_df = query(conn, """
        SELECT CATEGORY_ID, CATEGORY_NAME, DESCRIPTION, DAILY_LIMIT, REQUIRES_RECEIPT, IS_ACTIVE
        FROM EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES
        ORDER BY CATEGORY_NAME
    """)
    st.dataframe(
        cats_df.rename(columns={
            "CATEGORY_ID": "ID", "CATEGORY_NAME": "Name", "DESCRIPTION": "Description",
            "DAILY_LIMIT": "Daily Limit (AUD)", "REQUIRES_RECEIPT": "Needs Receipt", "IS_ACTIVE": "Active",
        }),
        use_container_width=True,
    )

    st.subheader("Edit Category")
    cat_names = cats_df["CATEGORY_NAME"].tolist()
    sel_cat   = st.selectbox("Select category to edit", cat_names)
    sel_row   = cats_df[cats_df["CATEGORY_NAME"] == sel_cat].iloc[0]

    ec1, ec2, ec3 = st.columns(3)
    new_limit   = ec1.number_input("Daily Limit (AUD, blank = no limit)",
                                    value=float(sel_row["DAILY_LIMIT"]) if sel_row["DAILY_LIMIT"] else 0.0,
                                    min_value=0.0, step=5.0, format="%.2f")
    new_receipt = ec2.checkbox("Requires Receipt", value=bool(sel_row["REQUIRES_RECEIPT"]))
    new_active  = ec3.checkbox("Active",           value=bool(sel_row["IS_ACTIVE"]))

    if st.button("💾 Save Category", key="save_cat"):
        execute(conn, """
            UPDATE EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES
            SET DAILY_LIMIT = %s, REQUIRES_RECEIPT = %s, IS_ACTIVE = %s
            WHERE CATEGORY_ID = %s
        """, (new_limit if new_limit > 0 else None, new_receipt, new_active, int(sel_row["CATEGORY_ID"])))
        clear_cache()
        st.success(f"Category '{sel_cat}' updated.")
        st.experimental_rerun()

    st.subheader("Add New Category")
    nc1, nc2 = st.columns(2)
    new_name  = nc1.text_input("Category Name *")
    new_desc  = nc2.text_input("Description")
    na1, na2, na3 = st.columns(3)
    new_nlimit   = na1.number_input("Daily Limit (0 = none)", min_value=0.0, step=5.0, format="%.2f", key="new_limit")
    new_nreceipt = na2.checkbox("Requires Receipt", value=True, key="new_receipt")

    if st.button("➕ Add Category"):
        if not new_name.strip():
            st.error("Category name is required.")
        else:
            execute(conn, """
                INSERT INTO EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES
                    (CATEGORY_NAME, DESCRIPTION, DAILY_LIMIT, REQUIRES_RECEIPT)
                VALUES (%s,%s,%s,%s)
            """, (new_name.strip(), new_desc.strip() or None,
                  new_nlimit if new_nlimit > 0 else None, new_nreceipt))
            clear_cache()
            st.success(f"Category '{new_name}' added.")
            st.experimental_rerun()


# ── Tab 2: Employees ──────────────────────────────────────────────────────────
with tab_emps:
    st.subheader("Registered Employees")

    emps_df = query(conn, """
        SELECT e.EMPLOYEE_ID, e.SNOWFLAKE_USER, e.FIRST_NAME, e.LAST_NAME,
               e.EMAIL, e.DEPARTMENT, e.APP_ROLE, e.IS_ACTIVE,
               m.FIRST_NAME||' '||m.LAST_NAME AS MANAGER_NAME
        FROM EXPENSE_APP.CONFIG.EMPLOYEES e
        LEFT JOIN EXPENSE_APP.CONFIG.EMPLOYEES m ON e.MANAGER_ID = m.EMPLOYEE_ID
        ORDER BY e.LAST_NAME, e.FIRST_NAME
    """)
    st.dataframe(
        emps_df[["SNOWFLAKE_USER","FIRST_NAME","LAST_NAME","EMAIL","DEPARTMENT","APP_ROLE","IS_ACTIVE","MANAGER_NAME"]].rename(columns={
            "SNOWFLAKE_USER": "Snowflake User", "FIRST_NAME": "First", "LAST_NAME": "Last",
            "EMAIL": "Email", "DEPARTMENT": "Dept", "APP_ROLE": "Role",
            "IS_ACTIVE": "Active", "MANAGER_NAME": "Manager",
        }),
        use_container_width=True,
    )

    st.subheader("Add Employee")
    ae1, ae2 = st.columns(2)
    e_user  = ae1.text_input("Snowflake Username *", placeholder="e.g. JSMITH")
    e_email = ae2.text_input("Email *")
    ae3, ae4 = st.columns(2)
    e_first = ae3.text_input("First Name *")
    e_last  = ae4.text_input("Last Name *")
    ae5, ae6, ae7 = st.columns(3)
    e_dept  = ae5.text_input("Department")
    e_role  = ae6.selectbox("App Role", ["STAFF", "MANAGER", "FINANCE", "ADMIN"])

    mgr_options = ["(None)"] + [f"{r['FIRST_NAME']} {r['LAST_NAME']} ({r['SNOWFLAKE_USER']})" for _, r in emps_df.iterrows()]
    e_mgr_sel   = ae7.selectbox("Manager", mgr_options)
    e_mgr_id    = None
    if e_mgr_sel != "(None)":
        mgr_user = e_mgr_sel.split("(")[-1].rstrip(")")
        mgr_row  = emps_df[emps_df["SNOWFLAKE_USER"] == mgr_user]
        if not mgr_row.empty:
            e_mgr_id = int(mgr_row.iloc[0]["EMPLOYEE_ID"])

    if st.button("➕ Add Employee"):
        if not all([e_user.strip(), e_email.strip(), e_first.strip(), e_last.strip()]):
            st.error("Snowflake Username, Email, First Name, and Last Name are required.")
        else:
            execute(conn, """
                INSERT INTO EXPENSE_APP.CONFIG.EMPLOYEES
                    (SNOWFLAKE_USER, FIRST_NAME, LAST_NAME, EMAIL, DEPARTMENT, MANAGER_ID, APP_ROLE)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                e_user.strip().upper(), e_first.strip(), e_last.strip(),
                e_email.strip(), e_dept.strip() or None, e_mgr_id, e_role,
            ))
            clear_cache()
            st.success(f"Employee {e_first} {e_last} added.")
            st.experimental_rerun()

    st.subheader("Edit Employee Role / Manager")
    sel_emp_name = st.selectbox(
        "Select employee",
        [f"{r['FIRST_NAME']} {r['LAST_NAME']} ({r['SNOWFLAKE_USER']})" for _, r in emps_df.iterrows()],
        key="edit_emp_sel",
    )
    sel_emp_user = sel_emp_name.split("(")[-1].rstrip(")")
    sel_emp_row  = emps_df[emps_df["SNOWFLAKE_USER"] == sel_emp_user].iloc[0]
    sel_emp_id   = int(sel_emp_row["EMPLOYEE_ID"])

    ee1, ee2, ee3 = st.columns(3)
    upd_role    = ee1.selectbox("Role", ["STAFF","MANAGER","FINANCE","ADMIN"],
                                index=["STAFF","MANAGER","FINANCE","ADMIN"].index(sel_emp_row["APP_ROLE"]),
                                key="upd_role")
    upd_active  = ee2.checkbox("Active", value=bool(sel_emp_row["IS_ACTIVE"]), key="upd_active")
    upd_mgr_sel = ee3.selectbox("Manager", mgr_options,
                                index=0 if not sel_emp_row["MANAGER_NAME"] else
                                next((i for i, o in enumerate(mgr_options) if sel_emp_row["MANAGER_NAME"].split()[0] in o), 0),
                                key="upd_mgr")
    upd_mgr_id = None
    if upd_mgr_sel != "(None)":
        upd_mgr_user = upd_mgr_sel.split("(")[-1].rstrip(")")
        upd_mgr_row  = emps_df[emps_df["SNOWFLAKE_USER"] == upd_mgr_user]
        if not upd_mgr_row.empty:
            upd_mgr_id = int(upd_mgr_row.iloc[0]["EMPLOYEE_ID"])

    if st.button("💾 Save Employee", key="save_emp"):
        execute(conn, """
            UPDATE EXPENSE_APP.CONFIG.EMPLOYEES
            SET APP_ROLE = %s, IS_ACTIVE = %s, MANAGER_ID = %s, UPDATED_AT = CURRENT_TIMESTAMP()
            WHERE EMPLOYEE_ID = %s
        """, (upd_role, upd_active, upd_mgr_id, sel_emp_id))
        clear_cache()
        st.success("Employee updated.")
        st.experimental_rerun()


# ── Tab 3: Audit Log ──────────────────────────────────────────────────────────
with tab_audit:
    st.subheader("Claim Status History")

    audit_df = query(conn, """
        SELECT h.CHANGED_AT, h.CLAIM_ID, c.CLAIM_REFERENCE, c.TITLE,
               h.OLD_STATUS, h.NEW_STATUS, h.CHANGED_BY_USER, h.CHANGED_BY_ROLE, h.CHANGE_SOURCE
        FROM EXPENSE_APP.AUDIT.CLAIM_STATUS_HISTORY h
        JOIN EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c ON h.CLAIM_ID = c.CLAIM_ID
        ORDER BY h.CHANGED_AT DESC
        LIMIT 200
    """)

    if audit_df.empty:
        st.info("No audit history yet.")
    else:
        st.dataframe(
            audit_df.rename(columns={
                "CHANGED_AT": "Timestamp", "CLAIM_ID": "Claim ID",
                "CLAIM_REFERENCE": "Reference", "TITLE": "Title",
                "OLD_STATUS": "From", "NEW_STATUS": "To",
                "CHANGED_BY_USER": "User", "CHANGED_BY_ROLE": "Role",
                "CHANGE_SOURCE": "Source",
            }),
            use_container_width=True,
        )
        csv = audit_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export Audit Log", data=csv, file_name="audit_log.csv", mime="text/csv")
