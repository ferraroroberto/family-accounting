"""Cached helpers for Streamlit."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.config_manager import default_config_path, load_config


@st.cache_data(show_spinner=False)
def cached_config(path_str: str) -> dict:
    return load_config(Path(path_str))


def get_config() -> dict:
    return cached_config(str(default_config_path()))


def clear_data_caches() -> None:
    st.cache_data.clear()
