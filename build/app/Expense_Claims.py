import streamlit as st
from utils.db import get_conn, query
from utils.auth import get_employee, display_name
from utils.formatting import role_chip, status_badge, fmt_currency

st.set_page_config(
    page_title="Expense Claims",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

conn = get_conn()
emp = get_employee(conn)

# ── Logo helper ───────────────────────────────────────────────────────────────
def _logo():
    try:
        import os
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        with open(logo_path, "rb") as f:
            return f.read()
    except Exception:
        return None

logo_bytes = _logo()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    if logo_bytes:
        st.image(logo_bytes, use_column_width=True)
    else:
        st.title("🧾 Expense Claims")
    st.divider()

    if emp:
        st.markdown(
            f"**{display_name(emp)}**  \n{emp['EMAIL']}  \n{role_chip(emp['APP_ROLE'])}",
            unsafe_allow_html=True,
        )
        if emp.get("DEPARTMENT"):
            st.caption(emp["DEPARTMENT"])
    else:
        st.warning("User not registered")

    st.divider()
    st.caption("Use the pages listed above to navigate.")

# ── Unregistered user ─────────────────────────────────────────────────────────
if not emp:
    st.error("Your Snowflake user is not registered in the expense system.")
    st.info("Ask your administrator to add you in the **Admin → Employees** tab.")
    st.stop()

# ── Home dashboard ────────────────────────────────────────────────────────────
if logo_bytes:
    lcol, _ = st.columns([1, 3])
    with lcol:
        st.image(logo_bytes, use_column_width=True)

st.title(f"Welcome, {emp['FIRST_NAME']} 👋")
st.caption("Staff Expense Claims Portal")
st.divider()

# Summary counts scoped to current user's role
eid = int(emp["EMPLOYEE_ID"])

my_counts = query(
    conn,
    """
    SELECT
        COUNT_IF(STATUS = 'DRAFT')                          AS drafts,
        COUNT_IF(STATUS = 'SUBMITTED')                      AS submitted,
        COUNT_IF(STATUS IN ('SUBMITTED','UNDER_REVIEW'))    AS pending_approval,
        COUNT_IF(STATUS = 'APPROVED')                       AS approved,
        COUNT_IF(STATUS = 'PAID')                           AS paid,
        COALESCE(SUM(CASE WHEN STATUS='PAID' THEN TOTAL_AMOUNT END), 0) AS paid_ytd
    FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS
    WHERE EMPLOYEE_ID = %s
      AND (STATUS != 'PAID' OR YEAR(PAID_DATE) = YEAR(CURRENT_DATE()))
    """,
    params=(eid,),
)

row = my_counts.fillna(0).iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Draft Claims",       int(row["DRAFTS"]))
c2.metric("Pending Approval",   int(row["PENDING_APPROVAL"]))
c3.metric("Approved (unpaid)",  int(row["APPROVED"]))
c4.metric("Paid YTD",           fmt_currency(row["PAID_YTD"]))

st.divider()

# Manager / finance extra panel
if emp["APP_ROLE"] in ("MANAGER", "FINANCE", "ADMIN"):
    st.subheader("Team Overview")
    if emp["APP_ROLE"] == "MANAGER":
        team_df = query(
            conn,
            """
            SELECT c.CLAIM_REFERENCE, e.FIRST_NAME||' '||e.LAST_NAME AS EMPLOYEE,
                   c.TITLE, c.STATUS, c.TOTAL_AMOUNT, c.SUBMISSION_DATE
            FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c
            JOIN EXPENSE_APP.CONFIG.EMPLOYEES e ON c.EMPLOYEE_ID = e.EMPLOYEE_ID
            WHERE c.STATUS IN ('SUBMITTED','UNDER_REVIEW')
              AND c.MANAGER_ID = %s
            ORDER BY c.SUBMISSION_DATE
            LIMIT 10
            """,
            params=(eid,),
        )
    else:
        team_df = query(
            conn,
            """
            SELECT c.CLAIM_REFERENCE, e.FIRST_NAME||' '||e.LAST_NAME AS EMPLOYEE,
                   c.TITLE, c.STATUS, c.TOTAL_AMOUNT, c.SUBMISSION_DATE
            FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c
            JOIN EXPENSE_APP.CONFIG.EMPLOYEES e ON c.EMPLOYEE_ID = e.EMPLOYEE_ID
            WHERE c.STATUS IN ('SUBMITTED','UNDER_REVIEW','APPROVED')
            ORDER BY c.SUBMISSION_DATE
            LIMIT 10
            """,
        )

    if team_df.empty:
        st.info("No claims awaiting action.")
    else:
        st.dataframe(team_df, use_container_width=True)

st.divider()
st.caption("Powered by Snowflake · Cortex Hackathon 2024")
