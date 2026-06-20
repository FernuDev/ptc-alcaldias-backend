"""Prueba de aceptación de la Fase 4: RBAC heredado propagado a los módulos.

Verifica que cambiar de usuario (distinto nodo) cambia lo que cada módulo
muestra, resuelto en servidor. Requiere FEATURE_ORGTREE_RBAC=true.
    python scripts/test_fase4.py
"""

import json
import urllib.error
import urllib.request
import sys

BASE = "http://localhost:8000/api/v1"
PASS, FAIL = "\033[92m✓\033[0m", "\033[91m✗\033[0m"
results: list[bool] = []

EMAILS = {
    "mc-admin": "fernando.mercado@mcontreras.gob.mx",
    "mc-dir-limpia": "jorge.vargas@mcontreras.gob.mx",
    "mc-dir-agua": "patricia.galvan@mcontreras.gob.mx",
    "mc-dir-obras": "adriana.belmont@mcontreras.gob.mx",
}


def _req(method, path, token=None, body=None):
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


def login(uid):
    s, d = _req("POST", "/auth/login", body={"email": EMAILS[uid], "password": f"{uid}.2026"})
    if s != 200:
        raise SystemExit(f"login {uid} -> {s} {d}")
    return d["access_token"]


def check(desc, cond, detail=""):
    results.append(cond)
    print(f"  {PASS if cond else FAIL} {desc}" + (f"  ({detail})" if detail and not cond else ""))


def cuadrillas(tok):
    _, d = _req("GET", "/cuadrillas", tok)
    return {c["nombre"] for c in d}


def main():
    print("\n── Fase 4 · RBAC heredado en módulos ──\n")
    admin = login("mc-admin")
    limpia = login("mc-dir-limpia")
    agua = login("mc-dir-agua")
    obras = login("mc-dir-obras")

    print("[Monitor] /cuadrillas scopeado por sub-árbol")
    ca = cuadrillas(admin)
    check("admin ve las 8 cuadrillas", len(ca) == 8, str(len(ca)))

    cl = cuadrillas(limpia)
    check("dir Servicios Urbanos ve 5 cuadrillas (sus JUDs)", len(cl) == 5, str(sorted(cl)))
    check("NO ve cuadrillas de Obras (Bacheo)",
          not any("Bacheo" in n for n in cl), str(sorted(cl)))

    cg = cuadrillas(agua)
    check("JUD Agua ve solo 1 cuadrilla (Agua y drenaje)",
          len(cg) == 1 and any("Agua y drenaje" in n for n in cg), str(sorted(cg)))

    co = cuadrillas(obras)
    check("dir Obras ve 2 cuadrillas (Bacheo + Mantenimiento)",
          len(co) == 2 and all("Agua" not in n for n in co), str(sorted(co)))

    check("agua ⊄ obras (no se solapan: distinto nodo, distinta vista)",
          cg.isdisjoint(co), f"{cg} ∩ {co}")

    print("\n[Scorecards] desempeño scopeado; global solo Alcalde/A&F")
    s, da = _req("GET", "/scorecards/cuadrillas", admin)
    check("admin scope=global", s == 200 and da["scope"]["nivel"] == "global",
          str(da.get("scope")))
    s, dg = _req("GET", "/scorecards/cuadrillas", agua)
    n_agua = len(dg.get("cuadrillas", [])) if s == 200 else -1
    check("JUD Agua ve scorecards de su sub-árbol (1)", n_agua == 1, f"status={s} n={n_agua}")
    check("JUD Agua scope != global", s == 200 and dg["scope"]["nivel"] != "global",
          str(dg.get("scope")))

    print("\n[Reportes] alcance por categorías del sub-árbol")
    _, ra = _req("GET", "/reportes?page=1&page_size=1", admin)
    _, rg = _req("GET", "/reportes?page=1&page_size=1", agua)
    ta = ra.get("total", 0)
    tg = rg.get("total", 0)
    check("admin ve >= reportes que el JUD Agua", ta >= tg, f"admin={ta} agua={tg}")
    check("JUD Agua ve un subconjunto (no todo el tenant)", tg < ta or ta == 0,
          f"admin={ta} agua={tg}")

    ok = sum(results)
    print(f"\n── {ok}/{len(results)} verificaciones OK ──")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
