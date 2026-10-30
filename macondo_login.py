"""
Pantalla de conexion compartida (login) para las tres apps.

Pide el token de JaaS y, solo cuando hace falta IA (el Bug Logger), la Groq API
Key. Los guarda cifrados en este equipo con keyring, verifica la conexion y deja
los datos de la sesion listos para el resto de la app.

login_gate(need_groq) dibuja la pantalla de conexion si todavia no hay sesion y
devuelve True cuando ya esta conectado, para que la app siga su curso:

    if not macondo_login.login_gate(need_groq=True):
        st.stop()
"""

import streamlit as st
from groq import Groq

import core  # nucleo compartido: token, Groq key y verificacion de conexion


def _connect(jaas_token, remember, need_groq, groq_key):
    """Verifica el token contra JaaS y, si es valido, guarda la sesion. Devuelve True/False."""
    if not jaas_token:
        st.error("Falta el JaaS PAT Token.")
        return False

    with st.spinner("Conectando a JaaS..."):
        ok, display_name, username = core.test_connection(jaas_token)

    if not ok:
        st.error("Token invalido. Revisa que lo copiaste completo y que no haya expirado.")
        return False

    if remember:
        core.save_jaas_token(jaas_token)

    # Datos que el resto de la app usa para hablar con JaaS y mostrar quien eres.
    st.session_state.jaas_token = jaas_token
    st.session_state.reporter = username
    st.session_state.user_display_name = display_name
    if need_groq:
        st.session_state.groq_client = Groq(api_key=groq_key)
    st.session_state.connected = True
    return True


def login_gate(need_groq):
    """
    Dibuja la conexion si no hay sesion. Devuelve True cuando ya esta conectado.
    'need_groq' es True para el Bug Logger (usa IA) y False para el WorkLogger.
    """
    # Si ya nos conectamos en esta sesion, no mostramos nada: seguimos de largo.
    if st.session_state.get("connected"):
        return True

    st.subheader("Conectar")

    saved_token = core.load_jaas_token()

    # --- Groq API Key (solo si la app usa IA) -----------------------------
    groq_key = core.get_groq_key() if need_groq else None
    if need_groq and not groq_key:
        st.info("Primera vez en este equipo: pega tu Groq API Key una sola vez, queda guardada cifrada.")
        groq_key_input = st.text_input("Groq API Key", type="password", key="groq_key_input")
        if st.button("Guardar Groq API Key", key="btn_save_groq"):
            if groq_key_input:
                core.save_groq_key(groq_key_input)
                st.rerun()
            else:
                st.error("Pega una key antes de guardar.")

    # --- Token de JaaS ----------------------------------------------------
    if saved_token:
        st.success("Token de JaaS guardado en este equipo — no hace falta pegarlo de nuevo.")
        if st.button("Olvidar token", key="btn_forget"):
            core.delete_jaas_token()
            st.rerun()
        jaas_token = saved_token
        remember = False  # ya esta guardado, no hay nada que volver a guardar
    else:
        jaas_token = st.text_input("JaaS PAT Token", type="password", key="jaas_token_input")
        remember = st.checkbox(
            "Recordar en este equipo (cifrado, Windows Credential Manager)", value=True
        )

    # El boton Conectar se bloquea si falta la Groq key en una app que la necesita.
    disabled = need_groq and not groq_key
    if st.button("Conectar", type="primary", disabled=disabled, key="btn_connect"):
        if _connect(jaas_token, remember, need_groq, groq_key):
            st.rerun()

    return st.session_state.get("connected", False)
