"""
WorkLogger - logica de fondo (sin interfaz, sin consola).

Aqui vive todo lo que habla con JaaS para el registro de horas:
  - traer los tickets de "Time Tracking" del proyecto, siempre frescos por API
  - detectar las versiones disponibles (los tickets "padre" de cada version)
  - sacar la lista de actividades de una version
  - calcular los dias habiles de un rango de fechas
  - interpretar tiempos escritos a mano ("2h", "1h 30m", "45m", "1.5h")
  - enviar cada worklog a su ticket

La autenticacion (token de JaaS, su guardado cifrado y la verificacion de
conexion) se reutiliza de core.py, el nucleo compartido con Macondo Logger,
para no repetir ese codigo en dos lugares.
"""

import re
import requests
from datetime import datetime, timedelta

import core  # nucleo compartido: token, conexion y URL base de JaaS

JAAS_URL = core.JAAS_URL

# Proyecto y filtro por defecto. El equipo de skate registra el tiempo en el
# proyecto FCQV, en tickets cuyo summary contiene "Time Tracking". Otros equipos
# pueden cambiar el proyecto desde la propia app sin tocar el codigo.
DEFAULT_PROJECT = "FCQV"
DEFAULT_SUMMARY_MATCH = "Time Tracking"

# Una jornada completa son 8 horas = 480 minutos. Se usa solo para mostrar
# cuanto falta para llenar el dia; no impide registrar mas ni menos.
WORKDAY_MINUTES = 480


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# traer los tickets del proyecto (siempre frescos desde JaaS)
# ---------------------------------------------------------------------------

def fetch_all_issues(token, project=DEFAULT_PROJECT, summary_match=DEFAULT_SUMMARY_MATCH):
    """
    Trae todos los tickets de registro de tiempo del proyecto, el mas nuevo primero.
    Pide de a 100 y sigue pidiendo hasta traerlos todos.
    Devuelve [] si JaaS no responde o si el token no tiene acceso.
    """
    jql = f'project={project} AND summary ~ "{summary_match}" ORDER BY created DESC'
    all_issues = []
    start_at = 0
    page_size = 100

    while True:
        params = {
            "jql": jql,
            "maxResults": page_size,
            "startAt": start_at,
            "fields": "summary,key,created",
        }
        try:
            res = requests.get(
                f"{JAAS_URL}/rest/api/2/search",
                headers=_headers(token),
                params=params,
                timeout=30,
            )
        except requests.RequestException:
            return []
        if res.status_code != 200:
            return []

        data = res.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)

        # Nos detenemos cuando ya trajimos todos o la pagina vino incompleta.
        if len(all_issues) >= data.get("total", 0) or len(issues) < page_size:
            break
        start_at += page_size

    return all_issues


# ---------------------------------------------------------------------------
# versiones y actividades
#
# En FCQV el registro de tiempo se organiza asi:
#   - Un ticket "padre" por version, con un summary tipo "Time Tracking 0.31.5"
#     (sin corchetes).
#   - Debajo, los tickets "hijos" de cada actividad, con summary entre corchetes,
#     tipo "[QA][Time Tracking] Regression - San Van".
# Como la lista viene ordenada del mas nuevo al mas viejo, las actividades de
# una version son las que quedan entre su ticket padre y el padre anterior.
# ---------------------------------------------------------------------------

def find_available_versions(all_issues):
    """
    Detecta los tickets 'padre' de cada version.
    Devuelve una lista del mas nuevo al mas viejo:
      [{"label": "0.31.5", "key": "FCQV-123", "index": 5}, ...]
    'index' es la posicion de ese ticket dentro de all_issues.
    """
    versions = []
    for i, issue in enumerate(all_issues):
        summary = issue["fields"]["summary"]
        # Un padre no tiene corchetes y menciona "Time Tracking <numero>".
        if "[" not in summary and re.search(r"Time Tracking [\d\.]+", summary):
            number = re.search(r"[\d]+\.[\d\.]+", summary)
            label = number.group(0) if number else summary
            versions.append({"label": label, "key": issue["key"], "index": i})
    return versions


def _clean_activity_label(summary):
    """Quita el prefijo '[...][Time Tracking] ' y deja solo el nombre de la actividad."""
    label = summary
    if "][Time Tracking] " in label:
        label = label.split("][Time Tracking] ")[-1]
    elif "[Time Tracking] " in label:
        label = label.replace("[Time Tracking] ", "")
    return label.strip()


def _extract_activities(issues):
    """Convierte una tanda de tickets hijos en {nombre_actividad: ticket_key}, sin repetidos."""
    activities = {}
    seen = set()
    for issue in issues:
        summary = issue["fields"]["summary"]
        if "[" not in summary:  # saltar cualquier padre que se haya colado
            continue
        label = _clean_activity_label(summary)
        if label and label not in seen:
            activities[label] = issue["key"]
            seen.add(label)
    return dict(sorted(activities.items()))


def activities_for_version(all_issues, versions, version_index):
    """
    Devuelve {actividad: ticket_key} para la version elegida.
    version_index es la posicion dentro de la lista 'versions' (0 = la mas nueva).
    """
    selected = versions[version_index]
    if version_index == 0:
        # Version mas nueva: sus actividades van desde el principio de la lista
        # (lo mas reciente) hasta justo antes de su ticket padre.
        start_idx, end_idx = 0, selected["index"]
    else:
        # Version mas vieja: entre el padre anterior (exclusive) y este padre.
        prev_parent = versions[version_index - 1]
        start_idx, end_idx = prev_parent["index"] + 1, selected["index"]
    return _extract_activities(all_issues[start_idx:end_idx])


# ---------------------------------------------------------------------------
# fechas y tiempos
# ---------------------------------------------------------------------------

def get_workdays(start_date, end_date):
    """Lista de dias habiles (lunes a viernes) entre dos fechas, inclusive."""
    days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:  # 0=lunes ... 4=viernes
            days.append(current)
        current += timedelta(days=1)
    return days


def parse_date(text):
    """Interpreta una fecha en varios formatos comunes. Devuelve date o None."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_time(text):
    """
    Interpreta un tiempo escrito a mano y devuelve (texto_normalizado, minutos).
    Acepta: "2h", "1h 30m", "45m", "1.5h". Vacio o cero -> (None, 0).
    El texto normalizado es el que JaaS espera en el worklog ("1h 30m").
    """
    text = (text or "").strip().lower()
    if not text or text in ("0", "skip", "s", "-"):
        return None, 0

    total_minutes = 0
    try:
        if "h" in text and "m" in text:
            hours_part = text.split("h")[0].strip()
            minutes_part = text.split("h")[1].replace("m", "").strip()
            total_minutes = int(hours_part) * 60 + int(minutes_part)
        elif "h" in text:
            total_minutes = int(float(text.replace("h", "").strip()) * 60)
        elif "m" in text:
            total_minutes = int(text.replace("m", "").strip())
        else:
            # Un numero suelto se interpreta como horas: "1.5" -> 90 min.
            total_minutes = int(float(text) * 60)
    except ValueError:
        return None, 0

    if total_minutes <= 0:
        return None, 0
    return format_minutes(total_minutes), total_minutes


def format_minutes(total_minutes):
    """Convierte minutos a un texto legible: 90 -> '1h 30m', 120 -> '2h', 45 -> '45m'."""
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0 and minutes > 0:
        return f"{hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h"
    return f"{minutes}m"


# ---------------------------------------------------------------------------
# enviar el registro de tiempo a JaaS
# ---------------------------------------------------------------------------

def submit_worklog(token, ticket_key, time_spent, log_date, comment):
    """
    Registra tiempo en un ticket. 'time_spent' es el texto normalizado ("1h 30m").
    La hora de inicio se fija a las 09:00 del dia indicado (JaaS exige una).
    Devuelve (ok, mensaje_de_error). ok=True si JaaS acepto el worklog.
    """
    headers = {**_headers(token), "Content-Type": "application/json"}
    started = f"{log_date.strftime('%Y-%m-%d')}T09:00:00.000+0000"
    payload = {"timeSpent": time_spent, "started": started, "comment": comment}
    try:
        res = requests.post(
            f"{JAAS_URL}/rest/api/2/issue/{ticket_key}/worklog",
            headers=headers,
            json=payload,
            timeout=30,
        )
    except requests.RequestException as error:
        return False, str(error)

    if res.status_code in (200, 201):
        return True, None
    return False, res.text
