"""
Macondo WorkLogger (independiente) - solo el registro de horas en JaaS.

Punto de entrada de la app. Junta tres piezas:
  - el tema Macondo (macondo_theme)
  - la conexion a JaaS (macondo_login) -- sin Groq, porque el WorkLogger no usa IA
  - la pantalla del WorkLogger (worklogger_ui)

Para correrla en modo desarrollo:  python -m streamlit run worklogger_app.py
"""

import streamlit as st

import macondo_theme
import macondo_login
import worklogger_ui

macondo_theme.apply("Macondo WorkLogger")
macondo_theme.header("Macondo WorkLogger")

# El WorkLogger no usa IA: solo necesita el token de JaaS.
if not macondo_login.login_gate(need_groq=False):
    st.stop()

worklogger_ui.render()
