"""
Bug Logger - interfaz (la pantalla para loguear bugs en JaaS con ayuda de IA).

Esta es la misma herramienta de siempre, pero empaquetada como una funcion
render() en vez de un script suelto. Asi se puede usar de dos maneras:
  - sola, en macondo_app.py (solo el Bug Logger)
  - como una pestaña, en macondo_suite_app.py (junto al WorkLogger)

La conexion (token de JaaS + Groq key) la resuelve macondo_login ANTES de
llamar a render(), asi que aqui ya damos por hecho que hay sesion.

El flujo interno tiene cuatro etapas, guardadas en st.session_state["bl_stage"]:
  project  -> elegir el proyecto donde se va a crear el bug
  form     -> llenar los campos que ese proyecto tiene habilitados
  preview  -> revisar y editar el summary/description antes de enviar
  done     -> ticket creado, con adjuntos y avisos
"""

import streamlit as st

import core


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _is_empty(value):
    return value is None or value == "" or value == []


def _project_label(project):
    """Etiqueta del proyecto en la lista, marcando los recientes y los que lideras."""
    tags = [tag for tag, on in (("reciente", project["recent"]), ("lead", project["is_lead"])) if on]
    return f"{project['key']} — {project['name']}" + (f"   [{', '.join(tags)}]" if tags else "")


def _load_projects():
    """Lista los proyectos donde puedes crear bugs. Si JaaS no lo permite, usa la lista de respaldo."""
    try:
        projects, verified = core.list_user_projects(
            st.session_state.jaas_token, st.session_state.reporter
        )
    except Exception:
        projects = [
            {"key": k, "name": n, "can_create": None, "is_lead": False, "recent": False}
            for k, n in core.FALLBACK_PROJECTS.items()
        ]
        verified = False
    st.session_state.bl_projects = projects
    st.session_state.bl_projects_verified = verified


def _open_project(project_key):
    """Lee los campos habilitados del proyecto y pasa al formulario. True si pudo abrirlo."""
    with st.spinner(f"Leyendo los campos habilitados de {project_key}..."):
        meta = core.load_project_meta(
            st.session_state.jaas_token, st.session_state.reporter, project_key
        )
    if meta is None:
        st.error(
            f"No pude leer los campos de {project_key}. Puede que no tengas permiso para crear bugs ahi, "
            "que no tenga un tipo 'Bug', o que no exista ningun ticket para tomar como referencia."
        )
        return False
    st.session_state.bl_meta = meta
    st.session_state.bl_stage = "form"
    return True


def _init_state():
    """Valores por defecto de la sesion del Bug Logger. Carga los proyectos la primera vez."""
    defaults = {
        "bl_stage": "project",
        "bl_meta": None,
        "bl_ticket": None,
        "bl_was_corrected": False,
        "bl_projects": None,
        "bl_projects_verified": True,
        "bl_pending_files": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    if st.session_state.bl_projects is None:
        with st.spinner("Buscando tus proyectos..."):
            _load_projects()


# ---------------------------------------------------------------------------
# etapa: elegir proyecto
# ---------------------------------------------------------------------------

def _stage_project():
    st.subheader("Elige el proyecto")

    if not st.session_state.bl_projects_verified:
        st.warning(
            "No pude verificar en cuales proyectos tienes permiso para crear bugs, asi que aparecen todos los que "
            "JaaS me deja ver (o la lista de respaldo). Si eliges uno donde no puedes crear, te lo aviso al abrirlo."
        )

    text_filter = st.text_input("Filtrar por clave o nombre", key="bl_project_filter").strip().lower()
    visible = [
        p for p in st.session_state.bl_projects
        if text_filter in f"{p['key']} {p['name']}".lower()
    ]
    st.caption(
        f"{len(visible)} de {len(st.session_state.bl_projects)} proyectos · "
        "los recientes y los que lideras van primero"
    )

    if visible:
        keys_by_label = {_project_label(p): p["key"] for p in visible}
        choice = keys_by_label[st.selectbox("Proyecto", list(keys_by_label), key="bl_project_choice")]
    else:
        choice = None
        st.info("Ningun proyecto coincide con el filtro.")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Usar este proyecto", type="primary", disabled=not choice, key="bl_btn_use_project"):
            if _open_project(choice):
                st.rerun()
    with col_b:
        if st.button("Actualizar lista", key="bl_btn_reload_projects"):
            with st.spinner("Buscando tus proyectos..."):
                _load_projects()
            st.rerun()

    with st.expander("¿No ves tu proyecto? Escribe la clave"):
        manual = st.text_input("Clave del proyecto (ej. SK8, ABC, XYZ)", key="bl_manual_project").strip().upper()
        if st.button("Abrir por clave", disabled=not manual, key="bl_btn_manual_project"):
            if _open_project(manual):
                st.rerun()


# ---------------------------------------------------------------------------
# etapa: formulario (campos habilitados del proyecto)
# ---------------------------------------------------------------------------

def _stage_form():
    meta = st.session_state.bl_meta
    project = meta["project"]
    catalogs = meta["catalogs"]
    field_ids = meta["field_ids"]
    required = meta["required_ids"]
    enabled = meta["enabled_ids"]

    def on_screen(field_id):
        """True si el campo esta en la pantalla de creacion (o no sabemos y lo dejamos pasar)."""
        return bool(field_id) and (enabled is None or field_id in enabled)

    def star(field_id):
        """Marca ' *' los campos obligatorios."""
        return " *" if field_id in required else ""

    # --- barra superior: proyecto y refrescos ---
    top_a, top_b, top_c = st.columns([3, 1.4, 1.6])
    top_a.caption(f"conectado como {st.session_state.user_display_name}")
    if top_b.button("Cambiar proyecto", key="bl_btn_change_project"):
        st.session_state.bl_stage = "project"
        st.rerun()
    if top_c.button("🔄 Refrescar campos", key="bl_btn_refresh"):
        with st.spinner("Actualizando..."):
            fresh = core.load_project_meta(st.session_state.jaas_token, st.session_state.reporter, project)
        if fresh:
            st.session_state.bl_meta = fresh
            st.rerun()
        st.error("No pude actualizar los campos.")

    st.markdown(f"### {project}")
    if meta["source"] == "createmeta":
        st.caption(
            f"Campos leidos de la pantalla de creacion del proyecto (tipo {meta['issuetype_name']}). "
            "Los marcados con * son obligatorios."
        )
        if not meta.get("issuetype_is_bug", True):
            st.warning(f"Este proyecto no tiene un tipo 'Bug'. Se usa '{meta['issuetype_name']}'.")
    else:
        st.warning(
            f"No pude leer la pantalla de creacion de {project}; use el ticket {meta['ref_ticket']} como referencia. "
            "Pueden aparecer campos que el proyecto no permite al crear: si JaaS los rechaza, se omiten y te aviso."
        )

    # --- de donde esta aprendiendo el estilo en este proyecto ---
    learning = core.learning_status(project, meta.get("style"))
    if learning["corrections"] or learning["real_tickets"]:
        parts = []
        if learning["corrections"]:
            parts.append(f"{learning['corrections']} correccion(es) tuyas")
        if learning["real_tickets"]:
            parts.append(f"{learning['real_tickets']} bug(s) reales {learning['real_source']}")
        st.caption("🦋 Aprendiendo el estilo de " + project + " de: " + " + ".join(parts))
    else:
        st.caption(
            "🦋 Todavia no hay bugs de referencia en " + project +
            ": se usa un estilo base hasta que corrijas los primeros."
        )

    # Accuracy real del ML en este proyecto, medida con el uso.
    acc = core.accuracy_report(project)
    if acc["sent"]:
        st.caption(
            f"📊 Accuracy en {project}: {acc['accuracy_pct']:.0f}% "
            f"({acc['unedited']} de {acc['sent']} enviados sin reescribir) · "
            f"parecido promedio al borrador: {acc['avg_similarity_pct']:.0f}%"
        )

    blocking = [f["name"] for f in meta["unsupported_fields"] if f["required"]]
    if blocking:
        st.error(
            "Este proyecto exige campos que la app todavia no sabe llenar: " + ", ".join(blocking) +
            ". Es probable que JaaS rechace el ticket."
        )

    def known_select(box, logical, label):
        """Dibuja un selectbox para uno de los campos conocidos, si el proyecto lo tiene."""
        field_id = field_ids.get(logical)
        options = sorted(catalogs[logical])
        if not field_id or not options:
            return None
        return box.selectbox(label + star(field_id), options, key=f"bl_{project}_{logical}")

    # --- build info ---
    st.subheader("Build info")
    col1, col2 = st.columns(2)
    cl = col1.text_input("CL number" + star(field_ids.get("changelist")), key=f"bl_{project}_cl")
    branch = col1.selectbox("Branch", core.BRANCHES, key=f"bl_{project}_branch") if field_ids.get("branch") else None
    if on_screen("versions") and catalogs["version"]:
        version = col2.selectbox("Version" + star("versions"), sorted(catalogs["version"]), key=f"bl_{project}_version")
    else:
        version = None
    bug_type = col2.selectbox("Bug type", core.BUG_TYPES, key=f"bl_{project}_bug_type") if field_ids.get("bug_type") else None

    # --- campos conocidos ---
    st.subheader("Campos")
    col1, col2 = st.columns(2)
    pillar = known_select(col1, "pillar", "Pillar team")
    feature = col1.text_input("Feature", key=f"bl_{project}_feature", placeholder="ej. Challenges, News System")
    game_spine = known_select(col1, "game_spine", "Game spine")
    platform = known_select(col1, "platform", "Platform")
    repro_rate = known_select(col2, "repro_rate", "Repro rate")
    player_impact = known_select(col2, "player_impact", "Player impact")
    severity = known_select(col2, "severity", "Severity")
    player_path = known_select(col2, "player_path", "Player path")

    col1, col2 = st.columns(2)
    activity = known_select(col1, "activity", "Activity")
    if on_screen("priority") and catalogs["priority"]:
        priority = col2.selectbox(
            "Priority (opcional)", ["(sin especificar)"] + sorted(catalogs["priority"]), key=f"bl_{project}_priority"
        )
        priority = None if priority == "(sin especificar)" else priority
    else:
        priority = None

    # --- campos extra que trae el proyecto y la app sabe dibujar ---
    def render_extra(extra, box):
        label = extra["name"] + (" *" if extra["required"] else "")
        key = f"bl_{project}_x_{extra['id']}"
        kind = extra["kind"]
        if kind == "text":
            return box.text_input(label, key=key)
        if kind == "number":
            return box.number_input(label, value=None, key=key)
        if kind == "date":
            picked = box.date_input(label, value=None, key=key)
            return picked.isoformat() if picked else None
        if kind == "select":
            picked = box.selectbox(label, [""] + sorted(extra["options"]), key=key)
            return picked or None
        if kind == "multiselect":
            return box.multiselect(label, sorted(extra["options"]), key=key)
        if kind == "labels":
            return box.text_input(label, key=key, help="Separadas por coma")
        return None

    extras_values = {}
    required_extras = [e for e in meta["extra_fields"] if e["required"]]
    optional_extras = [e for e in meta["extra_fields"] if not e["required"]]
    if required_extras:
        st.subheader(f"Campos obligatorios de {project}")
        for extra in required_extras:
            extras_values[extra["id"]] = render_extra(extra, st)
    if optional_extras:
        with st.expander(f"Otros campos habilitados en {project} ({len(optional_extras)})"):
            for extra in optional_extras:
                extras_values[extra["id"]] = render_extra(extra, st)

    missing = [e["name"] for e in required_extras if _is_empty(extras_values.get(e["id"]))]
    if field_ids.get("changelist") in required and not cl.strip():
        missing.append("CL number")

    # --- descripcion libre del bug + adjuntos ---
    st.subheader("Describe el bug")
    raw_bug = st.text_area(
        "Bug", height=120, key="bl_raw_bug",
        placeholder="Que esta pasando, donde, y que esperabas en cambio",
    )

    st.markdown("**Adjuntos** (opcional — logs, videos, imagenes)")
    uploaded = st.file_uploader(
        "Arrastra archivos o hace click para elegir",
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="bl_file_uploader",
    )
    pasted = st.file_uploader(
        "O pega un screenshot (Ctrl+V) — click aca primero y despues pega",
        accept_multiple_files=True,
        type=["png", "jpg", "jpeg"],
        key="bl_paste_uploader",
    )
    st.caption("Para pegar un screenshot: copialo (PrtScn o herramienta de recorte), click en el cuadro de arriba, y Ctrl+V.")

    all_files = list(uploaded or []) + list(pasted or [])
    if all_files:
        st.caption(f"{len(all_files)} archivo(s) listos para adjuntar al ticket: " + ", ".join(f.name for f in all_files))

    if missing:
        st.caption("Faltan campos obligatorios: " + ", ".join(missing))

    # --- generar con IA ---
    can_generate = bool(raw_bug and feature and not missing)
    if st.button("Generar con IA", type="primary", disabled=not can_generate, key="bl_btn_generate"):
        with st.spinner("Escribiendo summary y description..."):
            style = meta.get("style")
            summary = core.generate_summary(
                st.session_state.groq_client, pillar, game_spine, raw_bug, project, style
            )
            description = core.generate_description(
                st.session_state.groq_client, project, raw_bug, cl, branch,
                pillar, feature, repro_rate, player_impact, severity, style,
            )

        core.record_generation(project)  # métricas: un borrador generado

        st.session_state.bl_pending_files = [(f.name, f.getvalue(), f.type) for f in all_files]
        st.session_state.bl_ticket = {
            "cl": cl, "branch": branch, "version": version, "bug_type": bug_type,
            "pillar": pillar, "feature": feature, "game_spine": game_spine,
            "platform": platform, "repro_rate": repro_rate, "player_impact": player_impact,
            "severity": severity, "player_path": player_path, "activity": activity,
            "priority": priority, "raw_bug": raw_bug,
            "extras": {fid: v for fid, v in extras_values.items() if not _is_empty(v)},
            "summary": summary, "description": description,
            # Guardamos el borrador original para comparar con lo enviado (accuracy):
            "generated_summary": summary, "generated_description": description,
        }
        st.session_state.bl_was_corrected = False
        st.session_state.bl_stage = "preview"
        st.rerun()


# ---------------------------------------------------------------------------
# etapa: preview editable
# ---------------------------------------------------------------------------

def _stage_preview():
    ticket = st.session_state.bl_ticket
    meta = st.session_state.bl_meta
    project = meta["project"]

    if project == "SK8":
        st.warning("Enviando a **SK8** (proyecto real) — revisa bien antes de confirmar.")
    else:
        st.info(f"Enviando a **{project}**")

    st.subheader("Preview")
    edited_summary = st.text_input("Summary", value=ticket["summary"], key="bl_edit_summary")
    edited_description = st.text_area("Description", value=ticket["description"], height=350, key="bl_edit_description")

    # Si tocaste el texto, lo guardamos como ejemplo al enviar (asi aprende tu estilo).
    if edited_summary != ticket["summary"] or edited_description != ticket["description"]:
        st.session_state.bl_was_corrected = True

    with st.expander("Campos"):
        cols = st.columns(2)
        shown = [
            ("Pillar", ticket["pillar"]), ("Feature", ticket["feature"]),
            ("Game spine", ticket["game_spine"]), ("Platform", ticket["platform"]),
            ("Repro rate", ticket["repro_rate"]), ("Player impact", ticket["player_impact"]),
            ("Severity", ticket["severity"]), ("Player path", ticket["player_path"]),
            ("Activity", ticket["activity"]), ("Priority", ticket["priority"]),
            ("Version", ticket["version"]), ("CL", ticket["cl"]),
            ("Branch", ticket["branch"]), ("Bug type", ticket["bug_type"]),
        ]
        shown += [(meta["field_names"].get(fid, fid), value) for fid, value in ticket["extras"].items()]
        for i, (label, value) in enumerate(item for item in shown if item[1]):
            cols[i % 2].markdown(f"**{label}:** {value}")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("↩️ Empezar de nuevo", key="bl_btn_restart"):
            st.session_state.bl_stage = "form"
            st.session_state.bl_ticket = None
            st.rerun()

    with col2:
        if st.button("✅ Confirmar y enviar", type="primary", key="bl_btn_submit"):
            ticket["summary"] = edited_summary
            ticket["description"] = edited_description

            with st.spinner("Enviando a JaaS..."):
                res, warnings = core.submit_ticket(st.session_state.jaas_token, ticket, meta)

            if res.status_code == 201:
                key = res.json().get("key")
                st.session_state.bl_last_key = key
                st.session_state.bl_last_warnings = warnings

                pending_files = st.session_state.get("bl_pending_files", [])
                st.session_state.bl_attach_results = (
                    core.attach_files(st.session_state.jaas_token, key, pending_files) if pending_files else []
                )

                # Solo guardamos como ejemplo cuando corregiste algo: eso es lo que ensena.
                if st.session_state.bl_was_corrected:
                    core.save_example(
                        project, ticket["raw_bug"], ticket["pillar"], ticket["feature"], edited_description,
                        summary=edited_summary,
                    )

                # Métricas: registramos el envío y cuánto cambió respecto al borrador.
                core.record_submission(
                    project, st.session_state.bl_was_corrected,
                    ticket.get("generated_description", ""), edited_description,
                )

                st.session_state.bl_stage = "done"
                st.rerun()
            else:
                st.error("Fallo el envio:")
                st.code(core.explain_error(res, meta))

    with col3:
        st.caption("Los cambios en Summary/Description se guardan como ejemplo para mejorar futuras generaciones.")


# ---------------------------------------------------------------------------
# etapa: listo
# ---------------------------------------------------------------------------

def _stage_done():
    key = st.session_state.bl_last_key
    st.success(f"**{key}** creado")
    st.markdown(f"[Abrir en JaaS](https://jaas.ea.com/browse/{key})")

    warnings = st.session_state.get("bl_last_warnings", [])
    if warnings:
        with st.expander(f"⚠️ {len(warnings)} campo(s) no se pudieron aplicar", expanded=True):
            st.caption("El ticket se creo igual, sin estos campos:")
            for warning in warnings:
                st.text(warning)

    attach_results = st.session_state.get("bl_attach_results", [])
    if attach_results:
        ok_count = sum(1 for _, ok, _ in attach_results if ok)
        fail_count = len(attach_results) - ok_count
        if fail_count == 0:
            st.caption(f"📎 {ok_count} adjunto(s) subido(s) correctamente.")
        else:
            with st.expander(f"📎 {ok_count} adjunto(s) OK, {fail_count} fallaron", expanded=True):
                for filename, ok, error in attach_results:
                    st.caption(f"✅ {filename}" if ok else f"❌ {filename}: {error}")

    col1, col2 = st.columns(2)
    if col1.button("Loguear otro bug", key="bl_btn_another"):
        st.session_state.bl_stage = "form"
        st.session_state.bl_ticket = None
        st.session_state.bl_pending_files = []
        st.rerun()
    if col2.button("Cambiar proyecto", key="bl_btn_done_change_project"):
        st.session_state.bl_stage = "project"
        st.session_state.bl_ticket = None
        st.session_state.bl_pending_files = []
        st.rerun()


# ---------------------------------------------------------------------------
# punto de entrada: dibuja la etapa actual
# ---------------------------------------------------------------------------

def render():
    """Dibuja el Bug Logger. Da por hecho que ya hay sesion (ver macondo_login)."""
    _init_state()
    stage = st.session_state.bl_stage
    if stage == "project":
        _stage_project()
    elif stage == "form":
        _stage_form()
    elif stage == "preview":
        _stage_preview()
    elif stage == "done":
        _stage_done()
