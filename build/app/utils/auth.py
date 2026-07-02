import streamlit as st
import pandas as pd
from utils.db import query


ROLE_HIERARCHY = ["STAFF", "MANAGER", "FINANCE", "ADMIN"]


def get_employee(conn) -> dict | None:
    """Return the EMPLOYEES row for the current Snowflake user, or None if not registered."""
    if "employee" in st.session_state:
        return st.session_state.employee

    df = query(
        conn,
        """
        SELECT
            EMPLOYEE_ID, SNOWFLAKE_USER, FIRST_NAME, LAST_NAME,
            EMAIL, DEPARTMENT, MANAGER_ID, APP_ROLE, IS_ACTIVE
        FROM EXPENSE_APP.CONFIG.EMPLOYEES
        WHERE SNOWFLAKE_USER = CURRENT_USER()
          AND IS_ACTIVE = TRUE
        LIMIT 1
        """,
    )

    if df.empty:
        return None

    emp = df.iloc[0].to_dict()
    st.session_state.employee = emp
    return emp


def require_role(conn, allowed_roles: list[str]) -> dict:
    """
    Return the employee record if their role is in allowed_roles.
    Otherwise show an error and stop the page.
    """
    emp = get_employee(conn)
    if emp is None:
        st.error("Your Snowflake user is not registered in the expense system. Contact your administrator.")
        st.stop()

    if emp["APP_ROLE"] not in allowed_roles:
        st.error(f"Access denied. This page requires one of: {', '.join(allowed_roles)}")
        st.stop()

    return emp


def has_role(conn, allowed_roles: list[str]) -> bool:
    """Return True if the current user has one of the allowed roles."""
    emp = get_employee(conn)
    return emp is not None and emp["APP_ROLE"] in allowed_roles


def display_name(emp: dict) -> str:
    return f"{emp['FIRST_NAME']} {emp['LAST_NAME']}"
