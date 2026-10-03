import logging
import os

import streamlit as st


LOGGER = logging.getLogger("macrosnap.ui")


def developer_debug_enabled():
    return os.getenv("MACROSNAP_DEBUG", "").strip().lower() in {"1", "true", "yes"}


def safe_error(message, error=None):
    if error is not None:
        LOGGER.error("Handled UI error (%s).", type(error).__name__)
    st.error(message)
    if error is not None and developer_debug_enabled():
        st.exception(error)
