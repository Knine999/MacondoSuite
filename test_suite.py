"""
Pruebas con simulacion (sin JaaS real).

Cubren:
  1. La logica del WorkLogger: deteccion de versiones, recorte de actividades por
     version, parseo de tiempos, dias habiles y formato de minutos.
  2. Que las tres apps arrancan hasta la pantalla de conexion sin errores.
  3. Que la pantalla de registro del WorkLogger se dibuja con datos simulados.

Correr:  python -m pytest test_suite.py -q     (o:  python test_suite.py)
"""

from datetime import date

import worklogger_core as wl


# ---------------------------------------------------------------------------
# 1. logica del WorkLogger
# ---------------------------------------------------------------------------

def _fake_issues():
    """Imita la lista que devuelve JaaS: hijos arriba (lo mas nuevo), padres intercalados."""
    def issue(key, summary):
        return {"key": key, "fields": {"summary": summary}}
    return [
        issue("FCQV-11", "[QA][Time Tracking] Regression - San Van"),  # 0  hijo v0.31.5
        issue("FCQV-12", "[QA][Time Tracking] Smoke - Boot"),          # 1  hijo v0.31.5
        issue("FCQV-10", "Time Tracking 0.31.5"),                       # 2  PADRE v0.31.5
        issue("FCQV-08", "[QA][Time Tracking] Old task"),               # 3  hijo v0.31.4
        issue("FCQV-07", "Time Tracking 0.31.4"),                       # 4  PADRE v0.31.4
    ]


def test_find_versions():
    versions = wl.find_available_versions(_fake_issues())
    assert [v["label"] for v in versions] == ["0.31.5", "0.31.4"]
    assert versions[0]["index"] == 2 and versions[1]["index"] == 4


def test_activities_latest_version():
    issues = _fake_issues()
    versions = wl.find_available_versions(issues)
    acts = wl.activities_for_version(issues, versions, 0)  # la mas nueva
    assert acts == {
        "Regression - San Van": "FCQV-11",
        "Smoke - Boot": "FCQV-12",
    }


def test_activities_older_version():
    issues = _fake_issues()
    versions = wl.find_available_versions(issues)
    acts = wl.activities_for_version(issues, versions, 1)  # la anterior
    assert acts == {"Old task": "FCQV-08"}


def test_parse_time():
    assert wl.parse_time("2h") == ("2h", 120)
    assert wl.parse_time("1h 30m") == ("1h 30m", 90)
    assert wl.parse_time("45m") == ("45m", 45)
    assert wl.parse_time("1.5h") == ("1h 30m", 90)
    assert wl.parse_time("") == (None, 0)
    assert wl.parse_time("0") == (None, 0)


def test_format_minutes():
    assert wl.format_minutes(90) == "1h 30m"
    assert wl.format_minutes(120) == "2h"
    assert wl.format_minutes(45) == "45m"


def test_workdays_skips_weekend():
    # Lunes 2026-10-05 a domingo 2026-10-11 -> 5 dias habiles.
    days = wl.get_workdays(date(2026, 10, 5), date(2026, 10, 11))
    assert len(days) == 5
    assert all(d.weekday() < 5 for d in days)


# ---------------------------------------------------------------------------
# 2 y 3. las apps arrancan (usando el AppTest de Streamlit)
# ---------------------------------------------------------------------------

def test_apps_reach_login():
    from streamlit.testing.v1 import AppTest
    for app_file in ("macondo_app.py", "worklogger_app.py", "macondo_suite_app.py"):
        at = AppTest.from_file(app_file, default_timeout=30).run()
        assert not at.exception, f"{app_file} lanzo una excepcion al arrancar"
        # Antes de conectar, siempre aparece el boton Conectar.
        labels = [b.label for b in at.button]
        assert "Conectar" in labels, f"{app_file} no mostro el boton Conectar"


def test_worklogger_load_versions_button():
    """Regresion: pulsar 'Cargar versiones' no debe chocar con el widget wl_project."""
    from streamlit.testing.v1 import AppTest
    import worklogger_core

    issues = _fake_issues()
    # Evitamos la red: fetch_all_issues devuelve datos simulados.
    worklogger_core.fetch_all_issues = lambda token, project=worklogger_core.DEFAULT_PROJECT: issues

    at = AppTest.from_file("worklogger_app.py", default_timeout=30)
    at.session_state["connected"] = True
    at.session_state["jaas_token"] = "fake"
    at.session_state["reporter"] = "ivanromero"
    at.session_state["user_display_name"] = "Ivan Romero"
    at.run()
    assert not at.exception

    # Click en "Cargar versiones" -> antes reventaba al reasignar wl_project.
    button = next(b for b in at.button if b.label == "Cargar versiones")
    button.click().run()
    assert not at.exception, "Cargar versiones lanzo una excepcion"
    assert at.session_state["wl_project_resolved"] == "FCQV"


def _log_stage_app():
    """Prepara un AppTest del WorkLogger ya en la etapa de registro, con datos simulados."""
    from streamlit.testing.v1 import AppTest
    import worklogger_core

    issues = _fake_issues()
    versions = worklogger_core.find_available_versions(issues)
    activities = worklogger_core.activities_for_version(issues, versions, 0)

    at = AppTest.from_file("worklogger_app.py", default_timeout=30)
    at.session_state["connected"] = True
    at.session_state["jaas_token"] = "fake"
    at.session_state["reporter"] = "ivanromero"
    at.session_state["user_display_name"] = "Ivan Romero"
    at.session_state["wl_stage"] = "log"
    at.session_state["wl_project"] = "FCQV"
    at.session_state["wl_project_resolved"] = "FCQV"
    at.session_state["wl_all_issues"] = issues
    at.session_state["wl_versions"] = versions
    at.session_state["wl_version_index"] = 0
    at.session_state["wl_activities"] = activities
    at.session_state["wl_workdays"] = [date(2026, 10, 5), date(2026, 10, 6)]
    at.session_state["wl_time"] = {}
    at.session_state["wl_results"] = None
    return at


def test_worklogger_log_screen_with_fake_data():
    """La pantalla de registro dibuja todos los dias dentro de un formulario."""
    at = _log_stage_app().run()
    assert not at.exception, "la pantalla de registro lanzo una excepcion"
    assert "Cambiar versión / fechas" in [b.label for b in at.button]
    # Sin selector de dia (antes saltaba). Todos los inputs visibles: 2 act x 2 dias = 4.
    assert len(at.selectbox) == 0
    assert len(at.text_input) == 4


def test_worklogger_time_persists_and_counts():
    """Regresion: una hora escrita se conserva (todos los inputs siempre dibujados)
    y el dia correcto la cuenta, sin saltar a otra fecha."""
    import worklogger_ui

    at = _log_stage_app()
    # Simulamos que ya se habia escrito 2h en una actividad del SEGUNDO dia.
    key = worklogger_ui._input_key(date(2026, 10, 6), "Regression - San Van")
    at.session_state[key] = "2h"
    at.run()
    assert not at.exception
    # El input conserva la hora.
    assert "2h" in [ti.value for ti in at.text_input]
    # Y aparece bajo el 06/10 en el resumen (el dia correcto, no otro).
    md = " ".join(m.value or "" for m in at.markdown)
    assert "2h" in md and "06/10" in md


if __name__ == "__main__":
    import sys
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"  OK  {test.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} pruebas OK")
    sys.exit(0 if passed == len(tests) else 1)
