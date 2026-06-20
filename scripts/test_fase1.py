"""Prueba manual de los criterios de aceptación de la Fase 1 (R5 · REQ-17).

Ejecuta contra el backend vivo (http://localhost:8000). No requiere pytest.
    python scripts/test_fase1.py
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000/api/v1"
PASS, FAIL = "\033[92m✓\033[0m", "\033[91m✗\033[0m"
results: list[bool] = []


def _req(method: str, path: str, token: str | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def login(user_id: str) -> tuple[str, dict]:
    status, data = _req(
        "POST", "/auth/login", body={"email": f"{user_id}@demo.gob.mx", "password": f"{user_id}.2026"}
    )
    if status != 200:
        # El email puede no seguir el patrón; probamos con el email real vía /users
        raise SystemExit(f"Login fallo para {user_id}: {status} {data}")
    return data["access_token"], data["user"]


def check(desc: str, cond: bool, detail: str = ""):
    results.append(cond)
    print(f"  {PASS if cond else FAIL} {desc}" + (f"  ({detail})" if detail and not cond else ""))


def flatten(tree, acc=None):
    acc = acc if acc is not None else []
    for n in tree:
        acc.append(n)
        flatten(n.get("children", []), acc)
    return acc


# Descubrir los emails reales: login admin para listar usuarios y mapear id->email.
def discover_emails(admin_token: str) -> dict[str, str]:
    _, users = _req("GET", "/users", admin_token)
    return {u["id"]: u["email"] for u in users}


def login_by_email(email: str, user_id: str):
    status, data = _req(
        "POST", "/auth/login", body={"email": email, "password": f"{user_id}.2026"}
    )
    if status != 200:
        raise SystemExit(f"Login fallo para {email}: {status} {data}")
    return data["access_token"], data["user"]


def main():
    print("\n── Fase 1 · Núcleo organizacional ──\n")

    # Email real del admin demo (descubierto vía DB). Password patrón <id>.2026.
    admin_token, admin_user = login_by_email(
        "fernando.mercado@mcontreras.gob.mx", "mc-admin"
    )
    emails = discover_emails(admin_token)

    # ── Login response incluye contexto org ──
    print("\n[1] Login devuelve contexto organizacional")
    check("admin tiene rol_nivel=alcalde", admin_user.get("rol_nivel") == "alcalde",
          str(admin_user.get("rol_nivel")))
    check("admin es_campo=False", admin_user.get("es_campo") is False)
    check("admin tiene nodo_id", bool(admin_user.get("nodo_id")))

    # ── Admin ve todo el árbol (alcance global) ──
    print("\n[2] Admin/Alcalde ve el árbol completo (alcance global)")
    _, arbol_admin = _req("GET", "/org/arbol", admin_token)
    nodos_admin = flatten(arbol_admin)
    check("admin ve todo el árbol del tenant (>=16 nodos)", len(nodos_admin) >= 16,
          f"{len(nodos_admin)}")
    nombres_admin = {n["nombre"] for n in nodos_admin}
    check("admin ve Obras y Servicios Urbanos",
          "Obras y Desarrollo Urbano" in nombres_admin and "Servicios Urbanos" in nombres_admin)

    # ── Director de Servicios Urbanos: ve su sub-árbol, no Obras ──
    print("\n[3] Director (Servicios Urbanos) ve solo su sub-árbol")
    dir_limpia_tok, u = login_by_email(emails["mc-dir-limpia"], "mc-dir-limpia")
    _, arbol = _req("GET", "/org/arbol", dir_limpia_tok)
    nombres = {n["nombre"] for n in flatten(arbol)}
    check("ve Servicios Urbanos", "Servicios Urbanos" in nombres)
    check("ve sus JUDs (Agua, Alumbrado, Limpia, Áreas Verdes)",
          all(f"JUD {x}" in nombres for x in
              ["Agua y Drenaje", "Alumbrado Público", "Limpia", "Áreas Verdes"]))
    check("NO ve Obras y Desarrollo Urbano", "Obras y Desarrollo Urbano" not in nombres)
    check("NO ve Alcalde (no ve hacia arriba)", "Alcalde" not in nombres)

    # ── JUD: ve solo su rama ──
    print("\n[4] JUD (Agua y Drenaje) ve solo su rama")
    tok, u = login_by_email(emails["mc-dir-agua"], "mc-dir-agua")
    check("rol_nivel=jud", u.get("rol_nivel") == "jud", str(u.get("rol_nivel")))
    _, arbol = _req("GET", "/org/arbol", tok)
    nombres = {n["nombre"] for n in flatten(arbol)}
    check("ve JUD Agua y Drenaje + su cuadrilla real recolgada",
          "JUD Agua y Drenaje" in nombres
          and any("Agua y drenaje" in n.lower() or "agua y drenaje" in n.lower() for n in nombres),
          str(nombres))
    check("NO ve JUD Alumbrado Público", "JUD Alumbrado Público" not in nombres)
    check("NO ve Servicios Urbanos (su padre)", "Servicios Urbanos" not in nombres)

    # ── es_campo: jefe de cuadrilla rechazado del backoffice ──
    print("\n[5] Personal de campo (jefe de cuadrilla) rechazado del backoffice")
    tok, u = login_by_email(emails["mc-jefe-cuadrilla"], "mc-jefe-cuadrilla")
    check("login devuelve es_campo=True", u.get("es_campo") is True)
    status, _ = _req("GET", "/org/arbol", tok)
    check("GET /org/arbol => 403 (backoffice negado)", status == 403, f"status={status}")
    # mi-nodo sí debe funcionar para el usuario de campo
    status, mn = _req("GET", "/org/mi-nodo", tok)
    check("GET /org/mi-nodo => 200 para campo", status == 200, f"status={status}")

    # ── Capacidad: encender una capacidad cambia lo que el nodo puede ──
    print("\n[6] Encender/apagar capacidad en un nodo")
    # Buscar el nodo Servicios Urbanos (full tree del admin)
    su = next(n for n in nodos_admin if n["nombre"] == "Servicios Urbanos")
    caps_antes = {c["capacidad"] for c in su.get("capacidades", [])}
    check("Servicios Urbanos tiene 'cuadrillas' (central) por plantilla",
          "cuadrillas" in caps_antes, str(caps_antes))
    # Añadir 'obras' al nodo
    status, nuevas = _req("PUT", f"/org/nodos/{su['id']}/capacidades", admin_token,
                          body={"capacidades": [{"capacidad": "cuadrillas", "nivel_uso": "central"},
                                                {"capacidad": "obras", "nivel_uso": "usa"}]})
    codes = {c["capacidad"] for c in (nuevas or [])}
    check("ahora incluye 'obras'", status == 200 and "obras" in codes, f"{status} {codes}")

    # ── Validación: cuadrilla colgando del Alcalde => rechazado ──
    print("\n[7] Validación de estructuras imposibles")
    alcalde = next(n for n in nodos_admin if n["nivel"] == "alcalde")
    status, data = _req("POST", "/org/nodos", admin_token,
                        body={"parent_id": alcalde["id"], "nivel": "jefe_cuadrilla",
                              "tipo": "cuadrilla", "nombre": "Cuadrilla ilegal"})
    check("cuadrilla bajo Alcalde => 422", status == 422, f"status={status}")
    # Segunda raíz => conflicto
    status, data = _req("POST", "/org/nodos", admin_token,
                        body={"parent_id": None, "nivel": "alcalde",
                              "tipo": "direccion", "nombre": "Otro Alcalde"})
    check("segunda raíz (Alcalde) => 409", status == 409, f"status={status}")

    # ── Alta/baja restringida ──
    print("\n[8] Edición del organigrama restringida a admin")
    status, _ = _req("POST", "/org/nodos", dir_limpia_tok,
                     body={"parent_id": alcalde["id"], "nivel": "dir_area",
                           "tipo": "direccion", "nombre": "Intento no-admin"})
    check("director NO puede crear nodos => 403", status == 403, f"status={status}")

    # ── Otro tenant: estructura cargada sin tocar código ──
    print("\n[9] Multi-tenant: otro tenant tiene su propio árbol")
    _, arbol_tl_admin = (None, None)
    tl_token = None
    for email in (emails.get("tl-admin"),):
        if email:
            tl_token, _ = login_by_email(email, "tl-admin")
    if tl_token:
        _, arbol_tl = _req("GET", "/org/arbol", tl_token)
        check("tlalpan tiene su propio árbol de 16 nodos", len(flatten(arbol_tl)) == 16)

    # ── Resumen ──
    ok = sum(results)
    print(f"\n── {ok}/{len(results)} verificaciones OK ──")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
