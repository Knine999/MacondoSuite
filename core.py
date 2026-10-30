import os
import re
import json
import difflib
import requests
import keyring
from concurrent.futures import ThreadPoolExecutor
from groq import Groq

JAAS_URL      = "https://api.jaas.ea.com"
GROQ_MODEL    = "openai/gpt-oss-120b"
LEARNING_FILE_TEMPLATE = "buglogger_examples_{project}.json"
# Los ejemplos aprendidos viven en una carpeta fija del usuario, no junto al .exe:
# asi sobreviven a actualizaciones de la app y se pueden respaldar.
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "MacondoLogger")
MAX_EXAMPLES  = 3
KEYRING_SERVICE = "sk8-buglogger"
SHARED_GROQ_KEY = os.environ.get("SK8_BUGLOGGER_GROQ_KEY", "")

# solo se usa si JaaS no deja listar los proyectos del usuario
FALLBACK_PROJECTS = {"SK8": "skate.", "PL1": "PlaygroundBugLogger"}

BRANCHES = [
    "dingo-staging-blue",
    "dingo-staging-blue-retail",
    "dingo-staging-red",
    "dingo-staging-red-retail",
    "dingo-staging-green",
    "dingo-main",
    "dingo-dev",
    "dingo-release",
]

BUG_TYPES = ["In-Game", "UI", "Server"]

# nombre logico -> nombre exacto del campo tal como aparece en Jira (field.name en editmeta)
FIELD_NAMES = {
    "pillar":        "Pillar",
    "game_spine":    "Game Spine",
    "platform":      "Platform",
    "repro_rate":    "Repro Rate",
    "player_impact": "Player Impact",
    "severity":      "Severity",
    "player_path":   "Player Path",
    "activity":      "Activity",
    "changelist":    "Changelist Found",
    "branch":        "Branch",
    "bug_type":      "Bug Type",
}


# ---------------------------------------------------------------------------
# credenciales: guardadas cifradas via Windows Credential Manager (keyring),
# nunca en texto plano en disco. Una por usuario del sistema operativo.
# ---------------------------------------------------------------------------

def save_jaas_token(token):
    keyring.set_password(KEYRING_SERVICE, "jaas_token", token)


def load_jaas_token():
    try:
        return keyring.get_password(KEYRING_SERVICE, "jaas_token")
    except Exception:
        return None


def delete_jaas_token():
    try:
        keyring.delete_password(KEYRING_SERVICE, "jaas_token")
    except Exception:
        pass


def get_groq_key():
    """
    La Groq key no identifica a nadie (solo genera texto), asi que no hace
    falta que cada persona tenga la suya, pero cada PC necesita configurarla
    una vez. Prioridad:
      1. Guardada en keyring (la app la pide una sola vez en el primer login)
      2. Variable de entorno SK8_BUGLOGGER_GROQ_KEY, por si alguien prefiere
         setearla asi en vez de guardarla desde la UI
    Devuelve "" si no hay ninguna configurada.
    """
    try:
        saved = keyring.get_password(KEYRING_SERVICE, "groq_key")
        if saved:
            return saved
    except Exception:
        pass
    return SHARED_GROQ_KEY


def save_groq_key(key):
    keyring.set_password(KEYRING_SERVICE, "groq_key", key)


# ---------------------------------------------------------------------------
# conexion, proyectos del usuario y campos habilitados por proyecto
# ---------------------------------------------------------------------------

STANDARD_FIELDS = {"summary", "description", "reporter", "priority", "versions", "project", "issuetype", "attachment"}


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_connection(token):
    res = requests.get(f"{JAAS_URL}/rest/api/2/myself", headers=_headers(token), timeout=30)
    if res.status_code == 200:
        data = res.json()
        return True, data.get("displayName", ""), data.get("name", "")
    return False, "", ""


def _has_create_permission(token, project_key):
    """True/False si JaaS responde, None si no se pudo verificar."""
    try:
        res = requests.get(
            f"{JAAS_URL}/rest/api/2/mypermissions",
            headers=_headers(token),
            params={"projectKey": project_key, "permissions": "CREATE_ISSUES"},
            timeout=20,
        )
    except requests.RequestException:
        return None
    if res.status_code != 200:
        return None
    perm = res.json().get("permissions", {}).get("CREATE_ISSUES", {})
    return bool(perm.get("havePermission"))


def _recent_project_keys(token):
    """Proyectos donde el usuario reporto bugs hace poco, el mas reciente primero."""
    try:
        res = requests.get(
            f"{JAAS_URL}/rest/api/2/search",
            headers=_headers(token),
            params={"jql": "reporter = currentUser() ORDER BY created DESC", "fields": "project", "maxResults": 100},
            timeout=30,
        )
    except requests.RequestException:
        return []
    if res.status_code != 200:
        return []
    keys = []
    for issue in res.json().get("issues", []):
        key = issue.get("fields", {}).get("project", {}).get("key")
        if key and key not in keys:
            keys.append(key)
    return keys


def list_user_projects(token, username, workers=10):
    """
    Proyectos donde el usuario puede crear bugs.
      1. /project: todos los proyectos que puede ver.
      2. mypermissions (CREATE_ISSUES) por proyecto, en paralelo: se queda con los que puede usar.
      3. Marca 'recent' (donde reporto hace poco) y 'is_lead' (es el lead del proyecto).
    Devuelve (lista, verificado). Si ninguna verificacion de permisos funciona,
    devuelve todos los visibles con verificado=False para que la UI avise.
    """
    res = requests.get(f"{JAAS_URL}/rest/api/2/project", headers=_headers(token), params={"expand": "lead"}, timeout=60)
    if res.status_code != 200:
        raise RuntimeError(f"no pude listar los proyectos ({res.status_code})")
    visible = res.json()

    recent = _recent_project_keys(token)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        permissions = list(pool.map(lambda p: _has_create_permission(token, p["key"]), visible))

    verified = any(p is not None for p in permissions)
    me = (username or "").lower()
    projects = []
    for project, can_create in zip(visible, permissions):
        if verified and not can_create:
            continue
        lead = project.get("lead") or {}
        lead_ids = {str(lead.get("name", "")).lower(), str(lead.get("key", "")).lower()}
        projects.append({
            "key": project["key"],
            "name": project.get("name", ""),
            "can_create": can_create,
            "is_lead": bool(me) and me in lead_ids,
            "recent": project["key"] in recent,
        })

    def order(p):
        rank = recent.index(p["key"]) if p["recent"] else 10_000
        return (not p["recent"], rank, not p["is_lead"], p["name"].lower())

    return sorted(projects, key=order), verified


# --- lectura de campos ------------------------------------------------------

def _get_paged(token, path, page_size=200):
    """Junta todas las paginas de un endpoint paginado de Jira (campo 'values')."""
    items, start = [], 0
    while True:
        res = requests.get(
            f"{JAAS_URL}{path}",
            headers=_headers(token),
            params={"startAt": start, "maxResults": page_size},
            timeout=30,
        )
        if res.status_code != 200:
            return items or None
        data = res.json()
        if isinstance(data, list):
            return data
        page = data.get("values")
        if page is None:
            return data.get("fields") or data.get("issueTypes")  # forma alternativa, sin paginar
        items.extend(page)
        total = data.get("total")
        if data.get("isLast", True) or not page or (total is not None and len(items) >= total):
            return items
        start += len(page)


def _index_fields(raw):
    """Los campos pueden venir como lista o como dict; se normaliza a {fieldId: campo}."""
    if isinstance(raw, dict):
        out = {}
        for field_id, field in raw.items():
            field = dict(field)
            field.setdefault("fieldId", field_id)
            out[field_id] = field
        return out
    return {f["fieldId"]: f for f in (raw or []) if f.get("fieldId")}


def _options(field):
    return {
        (v.get("value") or v.get("name")): v["id"]
        for v in field.get("allowedValues", [])
        if v.get("id") and (v.get("value") or v.get("name"))
    }


def _catalogs_and_ids(fields):
    """Resuelve los campos conocidos POR NOMBRE, porque el customfield_id cambia entre proyectos."""
    by_name = {f.get("name", "").strip().lower(): (fid, f) for fid, f in fields.items()}
    catalogs, field_ids = {}, {}
    for logical, jira_name in FIELD_NAMES.items():
        entry = by_name.get(jira_name.lower())
        if entry:
            field_ids[logical] = entry[0]
            catalogs[logical] = _options(entry[1])
        else:
            field_ids[logical] = None
            catalogs[logical] = {}
    catalogs["priority"] = _options(fields.get("priority", {}))
    catalogs["version"] = _options(fields.get("versions", {}))
    return catalogs, field_ids


def _field_kind(field):
    """Tipo de control que la app sabe dibujar para un campo. None si no lo soporta."""
    schema = field.get("schema", {})
    kind, items = schema.get("type"), schema.get("items")
    has_options = bool(field.get("allowedValues"))
    if kind == "string":
        return "text"
    if kind == "number":
        return "number"
    if kind == "date":
        return "date"
    if kind == "option" and has_options:
        return "select"
    if kind == "array" and items == "option" and has_options:
        return "multiselect"
    if kind == "array" and items == "string":
        return "labels"
    return None


def _extra_fields(fields, known_ids):
    """Campos habilitados que no son los conocidos ni los estandar."""
    extras, unsupported = [], []
    for field_id, field in fields.items():
        if field_id in STANDARD_FIELDS or field_id in known_ids:
            continue
        kind = _field_kind(field)
        item = {
            "id": field_id,
            "name": field.get("name", field_id),
            "required": bool(field.get("required")) and not field.get("hasDefaultValue"),
            "kind": kind,
            "options": _options(field) if kind in ("select", "multiselect") else {},
        }
        (extras if kind else unsupported).append(item)
    return extras, unsupported


def _build_meta(project, source, fields, issuetype_id, issuetype_name, ref_ticket=None):
    catalogs, field_ids = _catalogs_and_ids(fields)
    known_ids = {fid for fid in field_ids.values() if fid}
    extras, unsupported = _extra_fields(fields, known_ids)
    return {
        "project": project,
        "source": source,  # "createmeta" (pantalla de creacion real) o "editmeta" (ticket de referencia)
        "ref_ticket": ref_ticket,
        "issuetype_id": issuetype_id,
        "issuetype_name": issuetype_name,
        "catalogs": catalogs,
        "field_ids": field_ids,
        "extra_fields": extras,
        "unsupported_fields": unsupported,
        "required_ids": {fid for fid, f in fields.items() if f.get("required") and not f.get("hasDefaultValue")},
        "enabled_ids": set(fields) if source == "createmeta" else None,
        "field_names": {fid: f.get("name", fid) for fid, f in fields.items()},
    }


def fetch_create_meta(token, project):
    """
    Campos habilitados en la pantalla de CREACION del proyecto, para el tipo Bug.
    Usa los endpoints de Jira DC 8.4+:
      /issue/createmeta/{proyecto}/issuetypes
      /issue/createmeta/{proyecto}/issuetypes/{id}
    Devuelve None si no estan disponibles o si el usuario no tiene permiso de crear ahi.
    """
    types = _get_paged(token, f"/rest/api/2/issue/createmeta/{project}/issuetypes")
    if not types:
        return None
    if isinstance(types, dict):
        types = list(types.values())
    candidates = [t for t in types if not t.get("subtask")]
    bug = next((t for t in candidates if t.get("name", "").strip().lower() == "bug"), None)
    issuetype = bug or (candidates[0] if candidates else None)
    if not issuetype:
        return None

    raw_fields = _get_paged(token, f"/rest/api/2/issue/createmeta/{project}/issuetypes/{issuetype['id']}")
    if not raw_fields:
        return None

    meta = _build_meta(project, "createmeta", _index_fields(raw_fields), issuetype["id"], issuetype.get("name"))
    meta["issuetype_is_bug"] = bug is not None
    return meta


def find_reference_ticket(token, reporter_username, project):
    """Ticket reciente del proyecto para leer editmeta: primero uno del usuario, si no, cualquiera."""
    for jql in (
        f'project = {project} AND reporter = "{reporter_username}" ORDER BY created DESC',
        f"project = {project} ORDER BY created DESC",
    ):
        res = requests.get(
            f"{JAAS_URL}/rest/api/2/search",
            headers=_headers(token),
            params={"jql": jql, "maxResults": 1, "fields": "key"},
            timeout=30,
        )
        if res.status_code == 200 and res.json().get("issues"):
            return res.json()["issues"][0]["key"]
    return None


def fetch_edit_meta(token, project, issue_key):
    """Plan B: campos de un ticket existente. Puede incluir campos que no estan en la pantalla de creacion."""
    res = requests.get(
        f"{JAAS_URL}/rest/api/2/issue/{issue_key}?expand=editmeta",
        headers=_headers(token),
        timeout=30,
    )
    if res.status_code != 200:
        return None
    issue = res.json()
    fields = _index_fields(issue.get("editmeta", {}).get("fields", {}))
    issuetype = issue.get("fields", {}).get("issuetype", {})
    return _build_meta(project, "editmeta", fields, issuetype.get("id"), issuetype.get("name"), ref_ticket=issue_key)


def load_project_meta(token, reporter_username, project):
    """
    Punto de entrada unico al elegir un proyecto:
      1. pantalla de creacion real (createmeta)
      2. si no esta disponible, editmeta de un ticket de referencia
    Devuelve el dict meta, o None si no se pudo leer ninguna de las dos.
    """
    try:
        meta = fetch_create_meta(token, project)
    except requests.RequestException:
        meta = None
    if not meta:
        try:
            ref = find_reference_ticket(token, reporter_username, project)
            meta = fetch_edit_meta(token, project, ref) if ref else None
        except requests.RequestException:
            meta = None
    if meta:
        meta["style"] = fetch_project_style(token, project, meta.get("issuetype_name") or "Bug")
    return meta


def fetch_project_style(token, project, issuetype_name="Bug", limit=20):
    """
    Estilo real del proyecto: summaries y descriptions de bugs recientes.
    Primero los del propio usuario; si no tiene, los de cualquiera en el proyecto.
    Nunca falla: si JaaS no responde, devuelve listas vacias.
    """
    style = {"summaries": [], "descriptions": [], "source": None}
    for who, jql in (
        ("tuyos", f'project = "{project}" AND issuetype = "{issuetype_name}" AND reporter = currentUser() ORDER BY created DESC'),
        ("del proyecto", f'project = "{project}" AND issuetype = "{issuetype_name}" ORDER BY created DESC'),
    ):
        try:
            res = requests.get(
                f"{JAAS_URL}/rest/api/2/search",
                headers=_headers(token),
                params={"jql": jql, "maxResults": limit, "fields": "summary,description"},
                timeout=30,
            )
        except requests.RequestException:
            continue
        if res.status_code != 200:
            continue
        for issue in res.json().get("issues", []):
            fields = issue.get("fields", {})
            summary = (fields.get("summary") or "").strip()
            description = (fields.get("description") or "").strip()
            if summary and len(style["summaries"]) < 6:
                style["summaries"].append(summary)
            # solo descripciones con estructura (varias lineas), no tickets de una frase
            if len(description) >= 150 and description.count("\n") >= 3 and len(style["descriptions"]) < MAX_EXAMPLES:
                style["descriptions"].append(description[:2500])
        if style["descriptions"]:
            style["source"] = who
            break
    return style


# ---------------------------------------------------------------------------
# machine learning local: ejemplos aprendidos de correcciones
# ---------------------------------------------------------------------------

def _examples_path(project):
    return os.path.join(DATA_DIR, LEARNING_FILE_TEMPLATE.format(project=project))


def load_examples(project):
    path = _examples_path(project)
    if not os.path.exists(path):
        legacy = LEARNING_FILE_TEMPLATE.format(project=project)  # versiones viejas lo guardaban junto a la app
        path = legacy if os.path.exists(legacy) else None
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_example(project, raw_bug, pillar, feature, description, summary=None):
    examples = load_examples(project)
    examples.append({
        "raw_bug": raw_bug,
        "pillar": pillar,
        "feature": feature,
        "summary": summary,
        "description": description,
    })
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_examples_path(project), "w", encoding="utf-8") as f:
        json.dump(examples, f, indent=2, ensure_ascii=False)


def recent_examples_block(project):
    examples = load_examples(project)[-MAX_EXAMPLES:]
    if not examples:
        return ""
    block = ""
    for i, ex in enumerate(examples, 1):
        block += f"\n=== CORRECTED EXAMPLE {i} (Pillar: {ex.get('pillar') or 'N/A'}, Feature: {ex.get('feature')}) ===\n"
        block += ex["description"] + "\n"
    return block


def project_style_block(style):
    descriptions = (style or {}).get("descriptions") or []
    if not descriptions:
        return ""
    block = "\n=== REAL TICKETS FROM THIS PROJECT (match their structure, section names and markup) ===\n"
    for i, description in enumerate(descriptions, 1):
        block += f"\n--- PROJECT EXAMPLE {i} ---\n{description}\n"
    return block


def learning_status(project, style):
    """Para mostrar en la UI de donde esta aprendiendo la app en este proyecto."""
    return {
        "corrections": len(load_examples(project)),
        "real_tickets": len((style or {}).get("descriptions") or []),
        "real_source": (style or {}).get("source"),
    }


# ---------------------------------------------------------------------------
# metricas de uso: de aqui sale la accuracy REAL del ML, medida con el uso.
#
# Por cada bug se guardan cuatro numeros por proyecto:
#   generated      -> cuantas veces se genero un borrador con IA
#   sent           -> cuantos se enviaron a JaaS
#   corrected      -> cuantos se editaron antes de enviar
#   similarity_sum -> suma del parecido (0..1) entre el borrador y lo enviado
#
# accuracy = enviados SIN reescribir / enviados. Es el % que de verdad importa:
# cuanto menos hay que corregir, mas acierta el modelo con el estilo del proyecto.
# ---------------------------------------------------------------------------

STATS_FILE_TEMPLATE = "buglogger_stats_{project}.json"
_STATS_DEFAULT = {"generated": 0, "sent": 0, "corrected": 0, "similarity_sum": 0.0}


def _stats_path(project):
    return os.path.join(DATA_DIR, STATS_FILE_TEMPLATE.format(project=project))


def load_stats(project):
    path = _stats_path(project)
    stats = dict(_STATS_DEFAULT)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            for key in stats:
                stats[key] = saved.get(key, stats[key])
        except (OSError, ValueError):
            pass
    return stats


def _save_stats(project, stats):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_stats_path(project), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)


def record_generation(project):
    """Se llama cada vez que la IA genera un borrador."""
    stats = load_stats(project)
    stats["generated"] += 1
    _save_stats(project, stats)


def record_submission(project, was_corrected, generated_text, final_text):
    """Se llama al enviar un ticket. Guarda si se corrigio y cuanto cambio el texto."""
    stats = load_stats(project)
    stats["sent"] += 1
    if was_corrected:
        stats["corrected"] += 1
    # 1.0 = identico al borrador, 0.0 = totalmente reescrito
    ratio = difflib.SequenceMatcher(None, generated_text or "", final_text or "").ratio()
    stats["similarity_sum"] += ratio
    _save_stats(project, stats)


def accuracy_report(project):
    """
    Resumen listo para mostrar o para el brochure:
      accuracy_pct     -> % de enviados sin reescribir
      avg_similarity_pct -> % de parecido promedio entre borrador y enviado
    Devuelve None en los porcentajes cuando todavia no hay envios.
    """
    stats = load_stats(project)
    sent = stats["sent"]
    unedited = sent - stats["corrected"]
    return {
        "generated": stats["generated"],
        "sent": sent,
        "unedited": unedited,
        "corrected": stats["corrected"],
        "accuracy_pct": (unedited / sent * 100) if sent else None,
        "avg_similarity_pct": (stats["similarity_sum"] / sent * 100) if sent else None,
    }


# ---------------------------------------------------------------------------
# groq
# ---------------------------------------------------------------------------

def ask_groq(client, system_prompt, user_prompt):
    res = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0.2,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    return res.choices[0].message.content.strip()


DESCRIPTION_RULES = (
    "You are a QA engineer at EA writing bug reports in Jira.\n"
    "Match the structure, section names, markup, tone and length of the example(s) given to you below. "
    "If the examples come from this project's real tickets or corrections, their structure wins over the "
    "default structure listed here.\n\n"
    "=== DEFAULT STRUCTURE (use it only where the examples don't say otherwise) ===\n"
    "- Description paragraph: 2-3 sentences max. What is wrong, where, and the consequence.\n"
    "- Repro Steps: 5-8 steps. Start with Boot. End with 'Notice that [what is wrong]'.\n"
    "- Player Impact: 1-2 sentences, focus on player experience.\n"
    "- Note: include Pillar Team and Feature exactly as given, only when they are provided. "
    "Add Expected/Actual only when there are specific values. Add Prerequisite only if mentioned. "
    "Add a likely cause line only if it's obvious from the description.\n"
    "- Jira wiki markup: # for steps, * for note bullets.\n\n"
    "=== ALWAYS ===\n"
    "- Do not invent details that aren't in the bug description (no item names, values, CLs or steps the user did not give).\n"
    "- Do not copy facts from the examples: they show format only.\n"
    "- No headers before the description paragraph.\n"
    "- Return only the description text."
)

# Ejemplos de estilo para el equipo skate. Sirven de base cuando un proyecto
# todavia no tiene sus propios ejemplos aprendidos (ver recent_examples_block).
# Mencionan cosas propias del juego (San Van, Skate Pass) a proposito, como
# muestra real de nivel de detalle -- no se deben usar para otro juego una vez
# que ese proyecto ya tenga ejemplos propios guardados.
SK8_STYLE_EXAMPLES = (
    "\n=== EXAMPLE 1 ===\n"
    "The challenge OTL S04-OwnTheLot-001 does not display the pre-challenge countdown timer when played in Co-op. "
    "Before the challenge begins, the expected countdown is absent, causing the challenge to start without providing "
    "players with the proper visual indication and preparation time.\n\n"
    "*Repro Rate:*\n5/5 (Always)\n\n"
    "*Repro Steps:*\n"
    "# Boot the title: - CL 28452329 (Staging Blue Retail)\n"
    "# Purchase the Skate Pass to gain access to San Van Open Stadium\n"
    "# Create or join a Co-op session\n"
    "# Enter San Van Open Stadium\n"
    "# Navigate to OTL S04-OwnTheLot-001 \"X Marks the Lot\"\n"
    "# Start the challenge in Co-op mode\n"
    "# Observe the UI before the challenge begins\n"
    "# Notice that the pre-challenge countdown timer is not displayed\n\n"
    "*Player Impact:*\n"
    "Players do not receive the expected visual cue before the challenge starts, reducing coordination "
    "and negatively impacting the Co-op gameplay experience.\n\n"
    "*Note:*\n"
    "* Pillar Team: Events\n"
    "* Feature: Challenges\n"
    "* Prerequisite: Purchase the Skate Pass to access San Van Open Stadium\n"
    "* Expected behavior: A countdown timer should be displayed before the challenge starts in Co-op mode\n"
    "* Actual behavior: No pre-challenge countdown timer appears\n"
    "* Likely issue with Co-op HUD synchronization or challenge initialization logic.\n\n"
    "=== EXAMPLE 2 ===\n"
    "The Zone Entrance progress indicator is displaying an incorrect total count. "
    "The UI currently shows 1/11, while the expected value should be 1/7. "
    "This results in inaccurate progression information being presented to the player.\n\n"
    "*Repro Rate:*\n5/5 (Always)\n\n"
    "*Repro Steps:*\n"
    "# Boot the title: - CL 28371079 (Staging Blue)\n"
    "# Enter the Stadium area\n"
    "# Navigate to or trigger the Zone Entrance objective/progression UI\n"
    "# Observe the displayed progress counter\n"
    "# Notice that the UI shows 1/11\n"
    "# Verify that the correct count should be 1/7\n\n"
    "*Player Impact:*\n"
    "Players receive incorrect progression information, which may cause confusion regarding "
    "objective completion and overall zone progress.\n\n"
    "*Note:*\n"
    "* Pillar Team: Stadium\n"
    "* Feature: Zone Progression/UI\n"
    "* Expected display: 1/7\n"
    "* Actual display: 1/11\n"
    "* Likely incorrect objective count or UI data configuration.\n\n"
    "=== EXAMPLE 3 ===\n"
    "The player can unexpectedly be dropped beneath the world geometry, causing the character to fall below "
    "the playable area. Once below the world, the player is unable to interact with the environment as intended "
    "and may become stuck in an invalid gameplay state.\n\n"
    "*Repro Rate:*\n1/5 (Observed Once)\n\n"
    "*Repro Steps:*\n"
    "# Boot the title: - CL 28371079 (Staging Blue)\n"
    "# Navigate to the affected location\n"
    "# Perform the actions shown in the attached video/logs\n"
    "# Observe the player position relative to the world geometry\n"
    "# Notice that the player is dropped below the world and begins falling underneath the map\n\n"
    "*Player Impact:*\n"
    "Players can become trapped outside the playable area, potentially requiring a respawn, "
    "fast travel, or game restart to recover.\n\n"
    "*Note:*\n"
    "* Pillar Team: Worlds\n"
    "* Feature: Layout\n"
    "* Issue results in the player leaving the intended playable space\n"
    "* Likely related to missing collision, streaming issue, or invalid player spawn/teleport location.\n"
)


SK8_SUMMARY_EXAMPLES = [
    'Pre-challenge countdown timer is missing in Co-op for OTL S04-OwnTheLot-001 "X Marks the Lot"',
    'Handplants are counted multiple times in OTL S04-OwnTheLot-001 "X Marks the Lot"',
    '"Let The Games Begin!" news item is not displayed first in the News feed order',
    "Zone Entrance counter displays incorrect value (1/11 instead of 1/7)",
    "Player can fall below the world geometry",
]


def generate_summary(client, pillar, game_spine, raw_bug, project=None, style=None):
    corrected = [ex["summary"] for ex in load_examples(project)[-MAX_EXAMPLES:] if ex.get("summary")] if project else []
    real = (style or {}).get("summaries") or []
    examples = corrected + real or SK8_SUMMARY_EXAMPLES
    system = (
        "You are a QA engineer writing Jira ticket summaries.\n"
        "Given a bug description, write a short specific one-line summary of the issue. "
        "If the examples start with a 'Pillar - Area -' style prefix, leave that prefix out: write only the bug part.\n\n"
        "Real summaries from this project, for wording and level of detail:\n"
        + "".join(f"- {e}\n" for e in examples[:8])
        + "\nBe specific, include item names and values when mentioned. One line, no quotes around it. "
        "Return only that line."
    )
    bug_line = ask_groq(client, system, f"Bug: {raw_bug}")
    bug_line = re.sub(r'[\x00-\x1f\x7f]', ' ', bug_line).strip().strip('"')
    return " - ".join([p for p in (pillar, game_spine) if p] + [bug_line])


def generate_description(client, project, raw_bug, cl, branch, pillar, feature, repro_rate, player_impact, severity, style=None):
    lines = [f"Bug: {raw_bug}"]
    for label, value in (
        ("CL", cl), ("Branch", branch), ("Pillar Team", pillar), ("Feature", feature),
        ("Repro Rate", repro_rate), ("Player Impact level", player_impact), ("Severity", severity),
    ):
        if value:
            lines.append(f"{label}: {value}")

    # Prioridad de aprendizaje por proyecto:
    #   1. correcciones del propio tester en este proyecto (lo mas fiel)
    #   2. tickets reales recientes del proyecto en JaaS (estructura de esa franquicia)
    #   3. solo si no hay nada de lo anterior: estilo base de SK8
    own = recent_examples_block(project)
    real = project_style_block(style)
    system = DESCRIPTION_RULES + (own + real if (own or real) else SK8_STYLE_EXAMPLES)
    return ask_groq(client, system, "\n".join(lines))


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------

def match(value, options):
    if not value or not options:
        return None
    value_lower = value.lower()
    for key in options:
        if key.lower() == value_lower:
            return key
    for key in options:
        if value_lower in key.lower() or key.lower() in value_lower:
            return key
    return list(options.keys())[0] if options else None


def _empty(value):
    return value is None or value == "" or value == []


def _format_extra(kind, value, options):
    if kind in ("text", "date"):
        return str(value)
    if kind == "number":
        return float(value)
    if kind == "select":
        return {"id": options[value]}
    if kind == "multiselect":
        return [{"id": options[v]} for v in value]
    if kind == "labels":
        return [x for x in re.split(r"[,\s]+", str(value)) if x]
    return None


def _error_map(res):
    try:
        return res.json().get("errors") or {}
    except ValueError:
        return {}


def explain_error(res, meta):
    """Convierte el error de JaaS en lineas legibles, con el nombre del campo."""
    try:
        data = res.json()
    except ValueError:
        return res.text
    lines = list(data.get("errorMessages", []))
    names = meta.get("field_names", {})
    for field_id, message in (data.get("errors") or {}).items():
        label = names.get(field_id)
        lines.append(f"{label} ({field_id}): {message}" if label else f"{field_id}: {message}")
    return "\n".join(lines) or res.text


def submit_ticket(token, ticket, meta):
    """
    Crea el bug en UNA sola llamada, mandando solo los campos que el proyecto
    tiene habilitados (incluidos los obligatorios). El reporter no se manda:
    JaaS usa al dueno del token.
    Si JaaS rechaza campos OPCIONALES, se quitan y se reintenta una vez; quedan como warnings.
    Devuelve (respuesta_de_jaas, warnings).
    """
    enabled = meta.get("enabled_ids")
    catalogs, field_ids = meta["catalogs"], meta["field_ids"]
    warnings = []

    def allowed(field_id):
        return bool(field_id) and (enabled is None or field_id in enabled)

    fields = {
        "project": {"key": meta["project"]},
        "issuetype": {"id": meta["issuetype_id"]} if meta.get("issuetype_id") else {"name": "Bug"},
        "summary": ticket["summary"],
        "description": ticket["description"],
    }

    version_id = catalogs["version"].get(ticket.get("version") or "")
    if allowed("versions") and version_id:
        fields["versions"] = [{"id": version_id}]

    if allowed("priority") and ticket.get("priority"):
        priority_id = catalogs["priority"].get(match(ticket["priority"], catalogs["priority"]))
        if priority_id:
            fields["priority"] = {"id": priority_id}

    for logical in ("pillar", "game_spine", "repro_rate", "player_impact", "severity", "player_path", "activity"):
        field_id, value = field_ids.get(logical), ticket.get(logical)
        if allowed(field_id) and value:
            option_id = catalogs[logical].get(match(value, catalogs[logical]))
            if option_id:
                fields[field_id] = {"id": option_id}

    field_id = field_ids.get("platform")
    if allowed(field_id) and ticket.get("platform"):
        platform_id = catalogs["platform"].get(match(ticket["platform"], catalogs["platform"]))
        if platform_id:
            fields[field_id] = [{"id": platform_id}]

    if allowed(field_ids.get("branch")) and ticket.get("branch"):
        fields[field_ids["branch"]] = [ticket["branch"]]

    if allowed(field_ids.get("bug_type")) and ticket.get("bug_type"):
        fields[field_ids["bug_type"]] = [ticket["bug_type"]]

    if allowed(field_ids.get("changelist")) and ticket.get("cl"):
        try:
            fields[field_ids["changelist"]] = float(ticket["cl"])
        except ValueError:
            warnings.append("Changelist Found: el CL no es un numero, no se envio ese campo.")

    for extra in meta.get("extra_fields", []):
        value = (ticket.get("extras") or {}).get(extra["id"])
        if allowed(extra["id"]) and not _empty(value):
            fields[extra["id"]] = _format_extra(extra["kind"], value, extra["options"])

    headers = {**_headers(token), "Content-Type": "application/json"}
    url = f"{JAAS_URL}/rest/api/2/issue"
    res = requests.post(url, headers=headers, json={"fields": fields})

    if res.status_code == 400:
        errors = _error_map(res)
        keep = set(meta.get("required_ids", ())) | {"summary", "description", "project", "issuetype"}
        droppable = [fid for fid in errors if fid in fields and fid not in keep]
        if droppable:
            for field_id in droppable:
                label = meta.get("field_names", {}).get(field_id, field_id)
                warnings.append(f"{label}: {errors[field_id]}")
                fields.pop(field_id)
            res = requests.post(url, headers=headers, json={"fields": fields})

    return res, warnings


def attach_files(token, issue_key, files):
    """
    Sube archivos a un ticket ya creado.
    files: lista de tuplas (filename, bytes, content_type)
    Devuelve lista de (filename, ok:bool, error_msg:str|None)
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Atlassian-Token": "no-check",  # requerido por Jira para subir attachments
    }
    results = []
    for filename, filebytes, content_type in files:
        res = requests.post(
            f"{JAAS_URL}/rest/api/2/issue/{issue_key}/attachments",
            headers=headers,
            files={"file": (filename, filebytes, content_type or "application/octet-stream")},
        )
        if res.status_code in (200, 201):
            results.append((filename, True, None))
        else:
            results.append((filename, False, res.text))
    return results
