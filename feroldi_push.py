#!/usr/bin/env python3
"""
FEROLDI PUSH — v X0.50
Sistema Feroldi · @patonet
======================================
Sube archivos generados por Claude al repo patonet/informes.
Detecta automáticamente el tipo de archivo y la carpeta destino.
Actualiza el dashboard index.html.

USO:
  python3 feroldi_push.py [archivo]         # sube un archivo específico
  python3 feroldi_push.py                   # detecta y sube todos en ~/Downloads

INSTALAR (una sola vez):
  pip3 install requests

TOKEN: configurar variable de entorno GH_TOKEN
  export GH_TOKEN="ghp_tu_token_aqui"
  O añadir a ~/.zshrc para que sea permanente
"""

import requests
import base64
import os
import json
import sys
import re
from pathlib import Path
from datetime import datetime

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN = os.environ.get("GH_TOKEN", "")   # Token desde variable de entorno
REPO  = "patonet/informes"
API   = "https://api.github.com"
HDRS  = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# Patrones de nombre → carpeta destino en GitHub
PATRONES = [
    # (regex_patron, carpeta_github, tipo)
    (r"^infografia_light_.+\.html$",      "equities/",          "Infografía Light"),
    (r"^infografia_.+\.html$",            "equities/",          "Infografía Heavy"),
    (r"^InformePDF_lite_.+\.pdf$",        "pdfs/equities/",     "PDF Lite"),
    (r"^InformePDF_.+\.pdf$",             "pdfs/equities/",     "PDF Heavy"),
    (r"^Diagrama_Sankey_.+\.html$",       "diagramas/equities/","Sankey"),
]

DASHBOARD_PATH = "index.html"

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def get_sha(ruta_repo):
    """Obtiene SHA del archivo si ya existe en el repo."""
    url = f"{API}/repos/{REPO}/contents/{ruta_repo}"
    r = requests.get(url, headers=HDRS)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def subir_archivo(ruta_local, ruta_repo, tipo):
    """Sube o actualiza un archivo en GitHub."""
    with open(ruta_local, "rb") as f:
        contenido_b64 = base64.b64encode(f.read()).decode()

    sha = get_sha(ruta_repo)
    payload = {
        "message": f"feat: {tipo} via feroldi_push v X0.50",
        "content": contenido_b64
    }
    if sha:
        payload["sha"] = sha

    url = f"{API}/repos/{REPO}/contents/{ruta_repo}"
    r = requests.put(url, headers=HDRS, json=payload)

    if r.status_code in (200, 201):
        nombre = Path(ruta_local).name
        url_pages = f"https://patonet.github.io/informes/{ruta_repo}"
        print(f"  ✅ {tipo}: {nombre}")
        print(f"     → {url_pages}")
        return url_pages
    else:
        msg = r.json().get("message", "error desconocido")
        print(f"  ❌ Error {r.status_code}: {msg}")
        return None


def detectar_tipo(nombre_archivo):
    """Determina la carpeta destino y tipo según el nombre del archivo."""
    for patron, carpeta, tipo in PATRONES:
        if re.match(patron, nombre_archivo):
            return carpeta + nombre_archivo, tipo
    return None, None


def extraer_meta_del_nombre(nombre_archivo):
    """Extrae ticker, precio y fecha del nombre del archivo."""
    # Patrón: infografia_TICKER_PRECIO_DD-MM-AAAA.html
    match = re.search(r"_([A-Z]+)_([\d.]+)_(\d{2}-\d{2}-\d{4})", nombre_archivo)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, None


def actualizar_dashboard(urls_generadas):
    """Actualiza index.html con los nuevos archivos."""
    if not urls_generadas:
        return

    print("\n  📊 Actualizando dashboard...")

    # Obtener index.html actual
    r = requests.get(f"{API}/repos/{REPO}/contents/{DASHBOARD_PATH}", headers=HDRS)
    if r.status_code != 200:
        print(f"  ⚠ No se pudo obtener index.html: {r.status_code}")
        return

    data = r.json()
    sha = data.get("sha")
    contenido = base64.b64decode(data.get("content", "")).decode("utf-8")

    # Encontrar el ticker de los archivos subidos
    ticker = None
    for url in urls_generadas.values():
        match = re.search(r"/([A-Z]+)_[\d.]+_\d{2}-\d{2}-\d{4}", url or "")
        if match:
            ticker = match.group(1)
            break

    if not ticker:
        print("  ⚠ No se pudo determinar ticker para actualizar dashboard")
        return

    # Construir entry para REPORTS
    today = datetime.now().strftime("%d-%m-%Y")
    new_entry = f"""    {{
      ticker: "{ticker}",
      name: "{ticker}",
      desc: "Análisis Feroldi · {today}",
      type: "equity",
      verdict: "neutral",
      price: 0,
      upside: 0,
      target: 0,
      date: "{today}",
      url: "{urls_generadas.get('infografia_heavy', '')}",
      pdfUrl: "{urls_generadas.get('pdf_heavy', '')}",
      urlLight: "{urls_generadas.get('infografia_light', '')}",
      pdfLightUrl: "{urls_generadas.get('pdf_lite', '')}",
      sankeyUrl: "{urls_generadas.get('sankey', '')}"
    }},"""

    # Insertar al inicio del array REPORTS
    if "const REPORTS = [" in contenido:
        contenido_nuevo = contenido.replace(
            "const REPORTS = [",
            f"const REPORTS = [\n{new_entry}"
        )

        nuevo_b64 = base64.b64encode(contenido_nuevo.encode()).decode()
        payload = {
            "message": f"feat: dashboard actualizado con {ticker}",
            "content": nuevo_b64,
            "sha": sha
        }
        r2 = requests.put(
            f"{API}/repos/{REPO}/contents/{DASHBOARD_PATH}",
            headers=HDRS,
            json=payload
        )
        if r2.status_code in (200, 201):
            print(f"  ✅ Dashboard actualizado con {ticker}")
        else:
            print(f"  ⚠ No se pudo actualizar dashboard: {r2.json().get('message')}")
    else:
        print("  ⚠ No se encontró const REPORTS = [ en index.html")


def verificar_token():
    """Verifica que el token sea válido."""
    if not TOKEN:
        print("\n❌ TOKEN no configurado.")
        print("   Ejecuta: export GH_TOKEN='tu_token_aqui'")
        print("   O añade a ~/.zshrc: export GH_TOKEN='tu_token_aqui'")
        return False

    r = requests.get(f"{API}/user", headers=HDRS)
    if r.status_code == 200:
        usuario = r.json().get("login")
        rate = r.headers.get("X-RateLimit-Remaining", "?")
        print(f"  ✅ Token válido — usuario: {usuario} · Rate limit: {rate}/5000")
        return True
    else:
        print(f"  ❌ Token inválido (HTTP {r.status_code})")
        return False


# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"  FEROLDI PUSH — v X0.50 · @patonet")
    print(f"{'='*55}\n")

    if not verificar_token():
        sys.exit(1)

    # Determinar archivos a subir
    if len(sys.argv) > 1:
        # Archivo específico pasado como argumento
        archivos = [Path(sys.argv[1])]
    else:
        # Auto-detectar en directorio actual y ~/Downloads
        directorios = [Path("."), Path.home() / "Downloads"]
        archivos = []
        for d in directorios:
            if d.exists():
                for f in d.iterdir():
                    if f.is_file():
                        _, tipo = detectar_tipo(f.name)
                        if tipo:
                            archivos.append(f)

    if not archivos:
        print("⚠️  No se encontraron archivos para subir.")
        print("   Busqué archivos con estos prefijos:")
        for _, _, tipo in PATRONES:
            print(f"   • {tipo}")
        print(f"\n   En: directorio actual y ~/Downloads")
        sys.exit(0)

    print(f"📁 {len(archivos)} archivo(s) encontrado(s):\n")

    urls_generadas = {}
    tipo_map = {
        "Infografía Heavy": "infografia_heavy",
        "Infografía Light": "infografia_light",
        "PDF Heavy":        "pdf_heavy",
        "PDF Lite":         "pdf_lite",
        "Sankey":           "sankey"
    }

    for ruta_local in archivos:
        ruta_repo, tipo = detectar_tipo(ruta_local.name)
        if not ruta_repo:
            print(f"  ⚠ Ignorado (tipo no reconocido): {ruta_local.name}")
            continue

        url = subir_archivo(str(ruta_local), ruta_repo, tipo)
        if url and tipo in tipo_map:
            urls_generadas[tipo_map[tipo]] = url

    # Actualizar dashboard
    if urls_generadas:
        actualizar_dashboard(urls_generadas)

    # Resumen
    print(f"\n{'='*55}")
    print(f"  ✅ {len(urls_generadas)}/{len(archivos)} archivo(s) subido(s)")
    print(f"\n  🔗 Links (activos en ~2 min por caché CDN de GitHub Pages):")
    for tipo_key, url in urls_generadas.items():
        print(f"  {url}")
    print(f"  Dashboard: https://patonet.github.io/informes/")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
