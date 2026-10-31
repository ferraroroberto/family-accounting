"""Streamlit-cached config helpers for the UI package."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app._tx_view import load_transactions_df
from src.config_manager import default_config_path, load_config
from src.database import connect, init_db


@st.cache_data(show_spinner=False)
def cached_config(path_str: str) -> dict:
    return load_config(Path(path_str))


def get_config() -> dict:
    return cached_config(str(default_config_path()))


def _db_stamp(db_path: Path) -> int:
    """Modification time of the database, so an out-of-app write (CLI import) busts the cache."""
    return db_path.stat().st_mtime_ns


@st.cache_data(show_spinner=False)
def _cached_transactions(db_path_str: str, _stamp: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = connect(Path(db_path_str))
    try:
        init_db(conn)
        standard = load_transactions_df(conn)
        raw = pd.read_sql_query(
            "SELECT * FROM transactions ORDER BY date DESC, id DESC", conn
        )
    finally:
        conn.close()
    return standard, raw


def cached_transactions_df(db_path: Path) -> pd.DataFrame:
    """Standard transaction columns, cached until the database file changes."""
    return _cached_transactions(str(db_path), _db_stamp(db_path))[0]


def cached_raw_transactions_df(db_path: Path) -> pd.DataFrame:
    """Every transactions column (newest first), cached until the database file changes."""
    return _cached_transactions(str(db_path), _db_stamp(db_path))[1]


def clear_data_caches() -> None:
    st.cache_data.clear()
