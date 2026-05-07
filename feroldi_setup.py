#!/usr/bin/env python3
"""
FEROLDI SETUP — v X0.56
Sistema Feroldi · @patonet
======================================
Script de configuración (ejecutar UNA VEZ por versión).
Sube los archivos X0.56 al repo patonet/informes.

CAMBIOS X0.56:
  [NUEVO] Requiere secret AV_API_KEY en GitHub Actions
  [NUEVO] feroldi_recolectar usa Alpha Vantage en lugar de StockAnalysis
  Ver CHANGELOG.txt para lista completa

SETUP PREVIO (una sola vez):
  1. GitHub Secrets: Settings → Secrets → Actions → New:
       GH_TOKEN   = tu_token_github
       AV_API_KEY = tu_key_alphavantage (9M0ZO9N2SCMOPD27 o similar)
  2. Mac Terminal:
       echo 'export GH_TOKEN="tu_token"'    >> ~/.zshrc
       echo 'export AV_API_KEY="tu_key_av"' >> ~/.zshrc
       source ~/.zshrc

USO:
  python3 feroldi_setup_X0.56.py
"""

import requests
import base64
import os
import sys
from pathlib import Path

VERSION = "X0.56"
TOKEN   = os.environ.get("GH_TOKEN", "")
REPO    = "patonet/informes"
API     = "https://api.github.com"
HDRS    = {
    "Authorization": f"token {TOKEN}",
    "Accept":        "application/vnd.github.v3+json"
}

ARCHIVOS = {
    # ── Python → raíz del repo (sin versión — Kika corre sin saber versión) ─
    "feroldi_recolectar_X0.56.py": "feroldi_recolectar.py",
    "feroldi_push_X0.56.py":       "feroldi_push.py",
    "feroldi_sankey_X0.56.py":     "feroldi_sankey.py",
    "feroldi_merge_X0.56.py":      "feroldi_merge.py",
    "feroldi_setup_X0.56.py":      "feroldi_setup.py",

    # ── GitHub Actions ───────────────────────────────────────────────────────
    "feroldi_X0.56.yml":           ".github/workflows/feroldi.yml",

    # ── Prompts activos CON versión en nombre (se referencian por URL) ──────
    "prompt_nucleo_X0.56.txt":     "prompts/prompt_nucleo_X0.56.txt",
    "prompt_light_X0.56.txt":      "prompts/prompt_light_X0.56.txt",
    "prompt_heavy_X0.56.txt":      "prompts/prompt_heavy_X0.56.txt",
    "prompt_maestro_X0.56.txt":    "prompts/prompt_maestro_X0.56.txt",

    # ── Prompts archivados ───────────────────────────────────────────────────
    "prompt_generador_light_X0.56.txt":   "prompts/archive/prompt_generador_light_X0.56.txt",
    "prompt_generador_heavy_X0.56.txt":   "prompts/archive/prompt_generador_heavy_X0.56.txt",
    "prompt_generador_sankey_X0.56.txt":  "prompts/archive/prompt_generador_sankey_X0.56.txt",

    # ── Docs ─────────────────────────────────────────────────────────────────
    "CHANGELOG.txt": "CHANGELOG.txt",
}

def get_sha(ruta):
    r = requests.get(f"{API}/repos/{REPO}/contents/{ruta}", headers=HDRS)
    return r.json().get("sha") if r.status_code == 200 else None

def subir(local, repo_path):
    p = Path(local)
    if not p.exists():
        print(f"  ⚠ No encontrado: {local}")
        return False
    b64 = base64.b64encode(p.read_bytes()).decode()
    sha = get_sha(repo_path)
    payload = {
        "message": f"feat: Sistema Feroldi {VERSION} — {Path(repo_path).name}",
        "content": b64
    }
    if sha: payload["sha"] = sha
    r = requests.put(f"{API}/repos/{REPO}/contents/{repo_path}", headers=HDRS, json=payload)
    if r.status_code in (200, 201):
        accion = "actualizado" if sha else "creado"
        print(f"  ✅ {accion}: {repo_path}")
        return True
    else:
        print(f"  ❌ Error {r.status_code} en {repo_path}: {r.json().get('message','?')}")
        return False

def main():
    print(f"\n{'='*60}")
    print(f"  FEROLDI SETUP — v {VERSION} · @patonet")
    print(f"  {len(ARCHIVOS)} archivos → patonet/informes")
    print(f"{'='*60}\n")

    if not TOKEN:
        print("❌ GH_TOKEN no configurado.")
        print("   export GH_TOKEN='tu_token'")
        sys.exit(1)

    r = requests.get(f"{API}/user", headers=HDRS)
    if r.status_code != 200:
        print(f"❌ Token inválido ({r.status_code})")
        sys.exit(1)
    print(f"  ✅ Token OK — {r.json().get('login')}\n")

    # Verificar AV_API_KEY configurado
    av_key = os.environ.get("AV_API_KEY","")
    if av_key:
        print(f"  ✅ AV_API_KEY configurado ({av_key[:4]}****)\n")
    else:
        print(f"  ⚠ AV_API_KEY no configurado localmente")
        print(f"    Recordá agregar el secret en GitHub Actions también\n")

    ok = 0
    for local, repo_path in ARCHIVOS.items():
        if subir(local, repo_path): ok += 1

    print(f"\n{'='*60}")
    print(f"  {ok}/{len(ARCHIVOS)} archivos subidos")
    print(f"\n  ℹ️  Recordá configurar en GitHub:")
    print(f"     Settings → Secrets → Actions → New secret:")
    print(f"       AV_API_KEY = tu_key_alphavantage")
    print(f"\n  Python en repo (Kika corre sin versión):")
    print(f"    feroldi_recolectar.py · feroldi_push.py")
    print(f"    feroldi_sankey.py · feroldi_merge.py")
    print(f"\n  Prompts:")
    print(f"    https://patonet.github.io/informes/prompts/")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
