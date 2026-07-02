import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session


def get_conn():
    return get_active_session()


def _build_sql(sql: str, params: tuple):
    """
    Replace %s placeholders with ?.
    Substitute None params as SQL NULL directly (Snowpark passes None as 'None' string).
    Returns (final_sql, non_none_params_list).
    """
    base = sql.replace("%s", "?")
    if not params:
        return base, []

    parts = base.split("?")
    result = parts[0]
    kept = []
    for i, val in enumerate(params):
        if val is None:
            result += "NULL"
        else:
            result += "?"
            kept.append(val)
        result += parts[i + 1]
    return result, kept


@st.cache_data(ttl=60, show_spinner=False)
def query(_conn, sql: str, params: tuple = None) -> pd.DataFrame:
    """Run a cached SELECT query."""
    final_sql, kept = _build_sql(sql, params or ())
    if kept:
        return _conn.sql(final_sql, params=kept).to_pandas()
    return _conn.sql(final_sql).to_pandas()


def execute(_conn, sql: str, params: tuple = None) -> None:
    """Run a non-cached DML statement (INSERT/UPDATE)."""
    final_sql, kept = _build_sql(sql, params or ())
    if kept:
        _conn.sql(final_sql, params=kept).collect()
    else:
        _conn.sql(final_sql).collect()


def execute_many(_conn, sql: str, rows: list) -> None:
    """Bulk insert — runs each row individually via execute."""
    for row in rows:
        execute(_conn, sql, tuple(row))


def clear_cache():
    query.clear()
