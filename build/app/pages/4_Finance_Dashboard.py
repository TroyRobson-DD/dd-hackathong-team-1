import streamlit as st
import altair as alt
import pandas as pd
from utils.db import get_conn, query, execute, clear_cache
from utils.auth import require_role
from utils.formatting import fmt_currency, fmt_date, status_badge

st.set_page_config(page_title="Finance Dashboard", page_icon="📊", layout="wide")

conn = get_conn()
emp = require_role(conn, ["FINANCE", "ADMIN"])

st.title("📊 Finance Dashboard")
st.divider()

# ── KPI metrics ────────────────────────────────────────────────────────────────
kpi_df = query(conn, """
    SELECT
        COUNT_IF(STATUS IN ('SUBMITTED','UNDER_REVIEW'))            AS pending_count,
        COALESCE(SUM(CASE WHEN STATUS IN ('SUBMITTED','UNDER_REVIEW') THEN TOTAL_AMOUNT END),0) AS pending_amt,
        COUNT_IF(STATUS = 'APPROVED')                               AS approved_count,
        COALESCE(SUM(CASE WHEN STATUS='APPROVED' THEN TOTAL_AMOUNT END),0) AS approved_amt,
        COUNT_IF(STATUS='PAID' AND YEAR(PAID_DATE)=YEAR(CURRENT_DATE()) AND MONTH(PAID_DATE)=MONTH(CURRENT_DATE())) AS paid_month_count,
        COALESCE(SUM(CASE WHEN STATUS='PAID' AND YEAR(PAID_DATE)=YEAR(CURRENT_DATE()) AND MONTH(PAID_DATE)=MONTH(CURRENT_DATE()) THEN TOTAL_AMOUNT END),0) AS paid_month_amt,
        COALESCE(SUM(CASE WHEN STATUS='PAID' AND YEAR(PAID_DATE)=YEAR(CURRENT_DATE()) THEN TOTAL_AMOUNT END),0) AS paid_ytd_amt
    FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS
""")

k = kpi_df.iloc[0]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Pending Approval",       f"{int(k['PENDING_COUNT'])} claims",    fmt_currency(k["PENDING_AMT"]))
k2.metric("Approved (Unpaid)",      f"{int(k['APPROVED_COUNT'])} claims",   fmt_currency(k["APPROVED_AMT"]))
k3.metric("Paid This Month",        f"{int(k['PAID_MONTH_COUNT'])} claims",  fmt_currency(k["PAID_MONTH_AMT"]))
k4.metric("Paid YTD",               fmt_currency(k["PAID_YTD_AMT"]))

st.divider()

# ── Filters ────────────────────────────────────────────────────────────────────
fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
status_filter = fc1.multiselect(
    "Status", ["SUBMITTED","UNDER_REVIEW","APPROVED","REJECTED","PAID","CANCELLED","DRAFT"],
    default=["SUBMITTED","UNDER_REVIEW","APPROVED","PAID"],
)
dept_df      = query(conn, "SELECT DISTINCT DEPARTMENT FROM EXPENSE_APP.CONFIG.EMPLOYEES WHERE DEPARTMENT IS NOT NULL ORDER BY 1")
dept_options = ["All"] + dept_df["DEPARTMENT"].tolist()
dept_filter  = fc2.selectbox("Department", dept_options)
date_from    = fc3.date_input("From", value=None, key="ffrom")
date_to      = fc4.date_input("To",   value=None, key="fto")

# ── Main claims query ──────────────────────────────────────────────────────────
where_parts = []
params = []
if status_filter:
    placeholders = ",".join(["%s"] * len(status_filter))
    where_parts.append(f"c.STATUS IN ({placeholders})")
    params.extend(status_filter)
if dept_filter != "All":
    where_parts.append("e.DEPARTMENT = %s")
    params.append(dept_filter)
if date_from:
    where_parts.append("c.CREATED_AT >= %s")
    params.append(str(date_from))
if date_to:
    where_parts.append("c.CREATED_AT <= DATEADD('day',1,%s)")
    params.append(str(date_to))

where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

claims_df = query(conn, f"""
    SELECT c.CLAIM_ID, c.CLAIM_REFERENCE, e.FIRST_NAME||' '||e.LAST_NAME AS EMPLOYEE,
           e.DEPARTMENT, c.TITLE, c.STATUS, c.TOTAL_AMOUNT, c.CURRENCY,
           c.SUBMISSION_DATE, c.PAID_DATE, c.PAYMENT_REF, c.COST_CENTRE, c.PROJECT_CODE
    FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c
    JOIN EXPENSE_APP.CONFIG.EMPLOYEES e ON c.EMPLOYEE_ID = e.EMPLOYEE_ID
    {where_sql}
    ORDER BY c.SUBMISSION_DATE DESC NULLS LAST
""", params=tuple(params) if params else None)

st.caption(f"{len(claims_df)} claim(s) found")

if not claims_df.empty:
    # ── Mark as Paid ──────────────────────────────────────────────────────────
    approved_only = claims_df[claims_df["STATUS"] == "APPROVED"]
    if not approved_only.empty:
        with st.expander(f"💳 Mark as Paid ({len(approved_only)} approved claim(s))"):
            st.dataframe(
                approved_only[["CLAIM_REFERENCE","EMPLOYEE","TITLE","TOTAL_AMOUNT"]].rename(columns={
                    "CLAIM_REFERENCE": "Ref", "EMPLOYEE": "Employee",
                    "TITLE": "Title", "TOTAL_AMOUNT": "Amount",
                }),
                use_container_width=True,
            )
            pay_refs = {
                str(row["CLAIM_ID"]): st.text_input(
                    f"Payment Ref — {row['CLAIM_REFERENCE']}",
                    key=f"payref_{row['CLAIM_ID']}",
                    placeholder="e.g. PAY-2024-001",
                )
                for _, row in approved_only.iterrows()
            }
            if st.button("✅ Mark Selected as Paid", type="primary"):
                paid_count = 0
                for _, row in approved_only.iterrows():
                    ref = pay_refs.get(str(int(row["CLAIM_ID"])), "").strip()
                    if ref:
                        execute(conn, """
                            UPDATE EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS
                            SET STATUS = 'PAID', PAID_DATE = CURRENT_DATE(),
                                PAYMENT_REF = %s, UPDATED_AT = CURRENT_TIMESTAMP()
                            WHERE CLAIM_ID = %s
                        """, (ref, int(row["CLAIM_ID"])))
                        execute(conn, """
                            INSERT INTO EXPENSE_APP.AUDIT.CLAIM_STATUS_HISTORY
                                (CLAIM_ID, OLD_STATUS, NEW_STATUS, CHANGE_SOURCE)
                            VALUES (%s,'APPROVED','PAID','APP')
                        """, (int(row["CLAIM_ID"]),))
                        paid_count += 1
                clear_cache()
                st.success(f"{paid_count} claim(s) marked as paid.")
                st.experimental_rerun()

    # ── Claims table ──────────────────────────────────────────────────────────
    st.subheader("Claims")
    display_df = claims_df[["CLAIM_REFERENCE","EMPLOYEE","DEPARTMENT","TITLE","STATUS","TOTAL_AMOUNT","SUBMISSION_DATE","PAID_DATE","PAYMENT_REF"]].rename(columns={
        "CLAIM_REFERENCE": "Ref", "EMPLOYEE": "Employee", "DEPARTMENT": "Dept",
        "TITLE": "Title", "STATUS": "Status", "TOTAL_AMOUNT": "Amount (AUD)",
        "SUBMISSION_DATE": "Submitted", "PAID_DATE": "Paid", "PAYMENT_REF": "Pay Ref",
    })
    st.dataframe(display_df, use_container_width=True)

    # CSV export
    csv = display_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Export CSV", data=csv, file_name="expense_claims.csv", mime="text/csv")

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    st.subheader("Analytics")
    ch1, ch2 = st.columns(2)

    with ch1:
        dept_chart_df = query(conn, """
            SELECT e.DEPARTMENT, SUM(c.TOTAL_AMOUNT) AS TOTAL
            FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c
            JOIN EXPENSE_APP.CONFIG.EMPLOYEES e ON c.EMPLOYEE_ID = e.EMPLOYEE_ID
            WHERE c.STATUS NOT IN ('DRAFT','CANCELLED')
              AND e.DEPARTMENT IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC LIMIT 10
        """)
        if not dept_chart_df.empty:
            chart = alt.Chart(dept_chart_df).mark_bar().encode(
                x=alt.X("TOTAL:Q", title="Total AUD"),
                y=alt.Y("DEPARTMENT:N", sort="-x", title="Department"),
                color=alt.value("#29B5E8"),
                tooltip=["DEPARTMENT", alt.Tooltip("TOTAL:Q", format=",.2f")],
            ).properties(title="Spend by Department", height=280)
            st.altair_chart(chart, use_container_width=True)

    with ch2:
        monthly_df = query(conn, """
            SELECT DATE_TRUNC('month', SUBMISSION_DATE) AS MONTH,
                   SUM(TOTAL_AMOUNT) AS TOTAL
            FROM EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS
            WHERE STATUS NOT IN ('DRAFT','CANCELLED')
              AND SUBMISSION_DATE >= DATEADD('month',-11,DATE_TRUNC('month',CURRENT_DATE()))
            GROUP BY 1 ORDER BY 1
        """)
        if not monthly_df.empty:
            monthly_df["MONTH"] = pd.to_datetime(monthly_df["MONTH"])
            chart2 = alt.Chart(monthly_df).mark_line(point=True).encode(
                x=alt.X("MONTH:T", title="Month"),
                y=alt.Y("TOTAL:Q", title="Total AUD"),
                color=alt.value("#29B5E8"),
                tooltip=["MONTH:T", alt.Tooltip("TOTAL:Q", format=",.2f")],
            ).properties(title="Monthly Claim Totals (12 months)", height=280)
            st.altair_chart(chart2, use_container_width=True)

    # Category pie
    cat_df = query(conn, """
        SELECT cat.CATEGORY_NAME, SUM(i.AMOUNT) AS TOTAL
        FROM EXPENSE_APP.CLAIMS.EXPENSE_ITEMS i
        JOIN EXPENSE_APP.CONFIG.EXPENSE_CATEGORIES cat ON i.CATEGORY_ID = cat.CATEGORY_ID
        JOIN EXPENSE_APP.CLAIMS.EXPENSE_CLAIMS c ON i.CLAIM_ID = c.CLAIM_ID
        WHERE c.STATUS NOT IN ('DRAFT','CANCELLED')
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8
    """)
    if not cat_df.empty:
        pie = alt.Chart(cat_df).mark_arc(innerRadius=50).encode(
            theta=alt.Theta("TOTAL:Q"),
            color=alt.Color("CATEGORY_NAME:N", legend=alt.Legend(title="Category")),
            tooltip=["CATEGORY_NAME", alt.Tooltip("TOTAL:Q", format=",.2f")],
        ).properties(title="Spend by Category", height=300)
        st.altair_chart(pie, use_container_width=True)
