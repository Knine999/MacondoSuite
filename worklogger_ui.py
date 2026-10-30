"""
WorkLogger - interfaz (la pantalla para registrar horas en JaaS).

Reemplaza la herramienta de consola por una pantalla con el estilo Macondo.
Igual que el Bug Logger, se expone como render() para poder usarla sola
(worklogger_app.py) o como una pestaña (macondo_suite_app.py). La conexion
(token de JaaS) la resuelve macondo_login antes de llamar a render().

El flujo tiene dos etapas, en st.session_state["wl_stage"]:
  setup -> elegir proyecto, cargar versiones por API, elegir version y rango de fechas
  log   -> registrar el tiempo por dia y por actividad, revisar y enviar

Decision de diseno del registro (etapa log):
  Todos los dias y sus actividades van dentro de UN FORMULARIO (st.form). Dentro
  de un formulario, escribir en los campos NO recarga la pagina: Streamlit solo
  corre el script cuando pulsas el boton del formulario. Asi escribes todas las
  horas de la semana de corrido, sin que nada salte, se cierre ni te devuelva el
  scroll arriba. Al pulsar "Guardar y revisar" se calcula el resumen; despues,
  un boton aparte envia a JaaS. (Antes, cada hora recargaba la pagina y el scroll
  saltaba a la primera fecha: por eso se sentia que "se saltaba".)

Los IDs de los tickets se traen frescos desde JaaS cada vez que cargas una
version, asi que siempre registras contra las actividades actuales.
"""

from datetime import date

import streamlit as st

import worklogger_core as wl


# ---------------------------------------------------------------------------
# estado
# ---------------------------------------------------------------------------

def _init_state():
    defaults = {
        "wl_stage": "setup",
        "wl_project": wl.DEFAULT_PROJECT,
        "wl_project_resolved": wl.DEFAULT_PROJECT,  # el proyecto ya normalizado (MAYUS) que se consulto
        "wl_versions": None,     # lista de versiones detectadas, o None si aun no se cargaron
        "wl_all_issues": None,   # tickets crudos de JaaS (para recortar actividades por version)
        "wl_version_index": 0,
        "wl_activities": {},     # {actividad: ticket_key} de la version elegida
        "wl_workdays": [],       # lista de date (dias habiles del rango)
        "wl_results": None,      # resultados del ultimo envio, o None
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _input_key(day, activity):
    """
    Clave estable del input de tiempo de una actividad en un dia concreto.
    Como todos los inputs se dibujan siempre, Streamlit conserva su valor solo:
    leemos el tiempo directamente de cada input, sin almacen aparte.
    """
    return f"wl_in::{day.isoformat()}::{activity}"


# ---------------------------------------------------------------------------
# etapa: configuracion (proyecto, version y fechas)
# ---------------------------------------------------------------------------

def _load_versions():
    """Trae los tickets del proyecto desde JaaS y detecta las versiones disponibles."""
    # Leemos lo que el usuario escribio en el input y lo normalizamos (MAYUS) en una
    # variable aparte. OJO: no se puede reasignar st.session_state["wl_project"] aqui,
    # porque Streamlit prohibe modificar la clave de un widget despues de crearlo.
    project = (st.session_state.get("wl_project") or wl.DEFAULT_PROJECT).strip().upper() or wl.DEFAULT_PROJECT
    with st.spinner(f"Trayendo versiones de {project} desde JaaS..."):
        all_issues = wl.fetch_all_issues(st.session_state.jaas_token, project)
        versions = wl.find_available_versions(all_issues)
    st.session_state.wl_all_issues = all_issues
    st.session_state.wl_versions = versions
    st.session_state.wl_project_resolved = project  # para mostrarlo luego sin tocar el widget


def _stage_setup():
    st.caption(f"conectado como {st.session_state.user_display_name}")
    st.subheader("Versión y fechas")

    # --- proyecto ---
    col_p, col_btn = st.columns([2, 1])
    col_p.text_input(
        "Proyecto de registro de tiempo",
        key="wl_project",
        help="FCQV para skate. Otros equipos ponen aqui su propio proyecto.",
    )
    with col_btn:
        st.markdown("<div style='height:1.8em'></div>", unsafe_allow_html=True)  # alinea el boton con el input
        if st.button("Cargar versiones", type="primary", key="wl_btn_load"):
            _load_versions()
            st.rerun()

    versions = st.session_state.wl_versions
    if versions is None:
        st.info("Pon el proyecto y pulsa **Cargar versiones** para traer los tickets actuales desde JaaS.")
        return

    if not versions:
        st.error(
            f"No encontre versiones de 'Time Tracking' en {st.session_state.wl_project_resolved}. "
            "Revisa que el proyecto sea correcto y que tengas acceso a esos tickets."
        )
        return

    # --- version ---
    labels = [f"v{v['label']}  ({v['key']})" for v in versions[:10]]  # las 10 mas recientes
    chosen_label = st.selectbox("Versión", labels, key="wl_version_label")
    st.session_state.wl_version_index = labels.index(chosen_label)

    # --- rango de fechas ---
    today = date.today()
    col_a, col_b = st.columns(2)
    start = col_a.date_input("Desde", value=today, key="wl_start")
    end = col_b.date_input("Hasta", value=today, key="wl_end")

    if start > end:
        st.warning("La fecha 'Desde' es posterior a 'Hasta'.")
        return

    workdays = wl.get_workdays(start, end)
    if not workdays:
        st.warning("No hay dias habiles (lunes a viernes) en ese rango.")
        return
    st.caption(f"{len(workdays)} dia(s) habil(es): " + ", ".join(d.strftime("%a %d/%m") for d in workdays))

    if st.button("Preparar días", type="primary", key="wl_btn_prepare"):
        activities = wl.activities_for_version(
            st.session_state.wl_all_issues, versions, st.session_state.wl_version_index
        )
        if not activities:
            st.error("Esa version no tiene actividades para registrar.")
            return
        st.session_state.wl_activities = activities
        st.session_state.wl_workdays = workdays
        st.session_state.wl_results = None
        # Limpiamos cualquier hora de un periodo anterior.
        for key in [k for k in st.session_state if str(k).startswith("wl_in::")]:
            del st.session_state[key]
        st.session_state.wl_stage = "log"
        st.rerun()


# ---------------------------------------------------------------------------
# etapa: registro de horas (todos los dias visibles a la vez)
# ---------------------------------------------------------------------------

def _render_day_inputs():
    """Dibuja, dentro del formulario, cada dia con sus actividades y un input de tiempo."""
    for day in st.session_state.wl_workdays:
        st.divider()
        # Total del dia segun lo guardado en el ultimo 'Guardar y revisar'.
        day_minutes = _day_minutes_from_state(day)
        titulo = f"**{day.strftime('%A %d/%m/%Y')}**  —  "
        if day_minutes == wl.WORKDAY_MINUTES:
            titulo += f"✅ {wl.format_minutes(day_minutes)} / 8h"
        elif day_minutes:
            titulo += f"{wl.format_minutes(day_minutes)} / 8h"
        else:
            titulo += "sin registrar"
        st.markdown(titulo)

        for activity in st.session_state.wl_activities:
            col_name, col_time = st.columns([3, 1])
            col_name.markdown(activity)
            col_time.text_input(
                "tiempo",
                key=_input_key(day, activity),
                label_visibility="collapsed",
                placeholder="2h",
            )


def _day_minutes_from_state(day):
    """Suma los minutos escritos para un dia, leyendo el valor actual de cada input."""
    total = 0
    for activity in st.session_state.wl_activities:
        _, minutes = wl.parse_time(st.session_state.get(_input_key(day, activity), ""))
        total += minutes
    return total


def _collect_entries_from_state():
    """Arma la lista de registros con tiempo leyendo el valor actual de cada input."""
    entries = []
    for day in st.session_state.wl_workdays:
        for activity, ticket_key in st.session_state.wl_activities.items():
            time_str, minutes = wl.parse_time(st.session_state.get(_input_key(day, activity), ""))
            if minutes > 0:
                entries.append({
                    "day": day, "activity": activity, "ticket": ticket_key,
                    "time": time_str, "minutes": minutes,
                })
    return entries


def _submit_entries(entries):
    """Envia cada worklog a JaaS y guarda los resultados para mostrarlos."""
    results = []
    progress = st.progress(0.0)
    for i, entry in enumerate(entries, 1):
        ok, error = wl.submit_worklog(
            st.session_state.jaas_token,
            entry["ticket"],
            entry["time"],
            entry["day"],
            entry["activity"],  # el comentario del worklog es el nombre de la actividad
        )
        results.append({**entry, "ok": ok, "error": error})
        progress.progress(i / len(entries))
    progress.empty()
    st.session_state.wl_results = results


def _stage_log():
    activities = st.session_state.wl_activities
    workdays = st.session_state.wl_workdays

    # --- barra superior ---
    top_a, top_b = st.columns([3, 1.4])
    top_a.caption(f"conectado como {st.session_state.user_display_name}")
    if top_b.button("Cambiar versión / fechas", key="wl_btn_back"):
        st.session_state.wl_stage = "setup"
        st.rerun()

    version = st.session_state.wl_versions[st.session_state.wl_version_index]
    st.markdown(f"### {st.session_state.wl_project_resolved} · v{version['label']}")
    st.caption(
        f"{len(activities)} actividad(es) · {len(workdays)} dia(s). "
        "Escribe el tiempo por actividad (2h · 1h 30m · 45m · 1.5h) y pulsa **Guardar y revisar**. "
        "Mientras escribes dentro del formulario nada se recarga ni salta."
    )

    # --- formulario: todos los dias juntos, sin recargas al escribir ---
    with st.form("wl_log_form"):
        _render_day_inputs()
        st.divider()
        st.form_submit_button("Guardar y revisar", type="primary")

    # --- resumen + envio (fuera del formulario) ---
    entries = _collect_entries_from_state()
    st.subheader("Resumen")
    if not entries:
        st.info("Escribe las horas arriba y pulsa **Guardar y revisar** para ver el resumen.")
        return

    grand_total = sum(e["minutes"] for e in entries)
    current_day = None
    for entry in entries:
        if entry["day"] != current_day:
            current_day = entry["day"]
            day_total = sum(e["minutes"] for e in entries if e["day"] == current_day)
            st.markdown(f"**{current_day.strftime('%A %d/%m')}** — {wl.format_minutes(day_total)}")
        st.caption(f"　{entry['ticket']} · {entry['activity']} → {entry['time']}")
    st.markdown(f"**Total general: {wl.format_minutes(grand_total)} en {len(entries)} registro(s)**")

    if st.button("Enviar worklogs a JaaS", type="primary", key="wl_btn_submit"):
        _submit_entries(entries)
        st.rerun()


# ---------------------------------------------------------------------------
# resultados del envio
# ---------------------------------------------------------------------------

def _show_results():
    results = st.session_state.wl_results
    ok_count = sum(1 for r in results if r["ok"])
    fail_count = len(results) - ok_count

    if fail_count == 0:
        st.success(f"Listo: {ok_count} worklog(s) registrados correctamente.")
    else:
        st.warning(f"{ok_count} registrados, {fail_count} fallaron. Revisa los que fallaron abajo.")

    for r in results:
        line = f"{r['day'].strftime('%d/%m')} · {r['activity']} → {r['time']}"
        if r["ok"]:
            st.caption(f"✅ {line}")
        else:
            st.caption(f"❌ {line} — {r['error']}")

    col1, col2 = st.columns(2)
    if col1.button("Registrar otro periodo", key="wl_btn_new_period"):
        st.session_state.wl_results = None
        st.session_state.wl_stage = "setup"
        st.rerun()
    if col2.button("Volver al registro", key="wl_btn_back_to_log"):
        st.session_state.wl_results = None
        st.rerun()


# ---------------------------------------------------------------------------
# punto de entrada
# ---------------------------------------------------------------------------

def render():
    """Dibuja el WorkLogger. Da por hecho que ya hay sesion (ver macondo_login)."""
    _init_state()

    # Si acabamos de enviar, mostramos los resultados por encima de todo.
    if st.session_state.wl_results is not None:
        _show_results()
        return

    if st.session_state.wl_stage == "setup":
        _stage_setup()
    else:
        _stage_log()
