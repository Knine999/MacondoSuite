"""
Macondo Suite - Bug Logger y WorkLogger en una sola app, con pestañas.

Es la misma app del Bug Logger mas una pestaña para el WorkLogger. Una sola
conexion a JaaS (y Groq) sirve para las dos pestañas, porque comparten sesion.

Para correrla en modo desarrollo:  python -m streamlit run macondo_suite_app.py
"""

import streamlit as st

import macondo_theme
import macondo_login
import bug_logger_ui
import worklogger_ui

macondo_theme.apply("Macondo Suite")
macondo_theme.header("Macondo Suite")

# Hay una pestaña con IA (Bug Logger), asi que la conexion pide la Groq API Key.
# Esa misma sesion sirve tambien para el WorkLogger.
if not macondo_login.login_gate(need_groq=True):
    st.stop()

tab_bug, tab_work = st.tabs(["🐞 Bug Logger", "⏱️ WorkLogger"])
with tab_bug:
    bug_logger_ui.render()
with tab_work:
    worklogger_ui.render()
