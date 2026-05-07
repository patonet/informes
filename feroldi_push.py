#!/usr/bin/env python3
"""
FEROLDI PUSH — v X0.56
Sistema Feroldi · @patonet
======================================
Busca automáticamente en ~/Downloads/:
  - ZIPs con archivos Feroldi → descomprime y procesa
  - Archivos sueltos .html/.pdf con nombre Feroldi → procesa directo

Lógica anti-duplicados: si el archivo ya existe en GitHub → skip.
Organiza copia local en ~/feroldi_informes/TICKER/FECHA/
Actualiza dashboard index.html
Pregunta si borrar los archivos procesados de Downloads.

USO:
  python3 feroldi_push.py

TOKEN: variable de entorno GH_TOKEN
  export GH_TOKEN="ghp_tu_token_aqui"
  O añadir a ~/.zshrc para que sea permanente
"""

import requests
import base64
import os
import re
import sys
import zipfile
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN     = os.environ.get("GH_TOKEN", "")
REPO      = "patonet/informes"
API       = "https://api.github.com"
HDRS      = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}
DOWNLOADS = Path.home() / "Downloads"
INFORMES  = Path.home() / "feroldi_informes"
DASHBOARD = "index.html"

# Patrones nombre → (carpeta GitHub, tipo, clave)
PATRONES = [
    (r"^infografia_light_([A-Z0-9.]+)_([\d.]+)_(\d{2}-\d{2}-\d{4}).*\.html$",  "equities/",           "Infografía Light", "infografia_light"),
    (r"^infografia_([A-Z0-9.]+)_([\d.]+)_(\d{2}-\d{2}-\d{4}).*\.html$",        "equities/",           "Infografía Heavy", "infografia_heavy"),
    (r"^InformePDF_lite_([A-Z0-9.]+)_([\d.]+)_(\d{2}-\d{2}-\d{4}).*\.pdf$",    "pdfs/equities/",      "PDF Lite",         "pdf_lite"),
    (r"^InformePDF_([A-Z0-9.]+)_([\d.]+)_(\d{2}-\d{2}-\d{4}).*\.pdf$",         "pdfs/equities/",      "PDF Heavy",        "pdf_heavy"),
    (r"^Diagrama_Sankey_([A-Z0-9.]+)_([\d.]+)_(\d{2}-\d{2}-\d{4}).*\.html$",   "diagramas/equities/", "Sankey",           "sankey"),
]

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def detectar(nombre):
    """Retorna (ruta_repo, tipo, clave, ticker, precio, fecha) o None.
    BUG-1 FIX: re.IGNORECASE → detecta Infografia_ e infografia_ por igual.
    BUG-2 FIX: ticker en uppercase siempre.
    """
    for patron, carpeta, tipo, clave in PATRONES:
        m = re.match(patron, nombre, re.IGNORECASE)
        if m:
            ticker = m.group(1).upper()
            precio, fecha = m.group(2), m.group(3)
            return carpeta + nombre, tipo, clave, ticker, precio, fecha
    return None

def get_sha(ruta_repo):
    r = requests.get(f"{API}/repos/{REPO}/contents/{ruta_repo}", headers=HDRS)
    return r.json().get("sha") if r.status_code == 200 else None

def subir_bytes(contenido_bytes, ruta_repo, tipo, nombre):
    """Sube archivo. Retorna URL si subió, 'skip' si ya existe, None si error."""
    sha = get_sha(ruta_repo)
    if sha:
        print(f"  ⏭  Skip (ya existe en GitHub): {nombre}")
        return "skip"

    contenido_b64 = base64.b64encode(contenido_bytes).decode()
    payload = {
        "message": f"feat: {tipo} via feroldi_push v X0.56",
        "content": contenido_b64
    }
    r = requests.put(f"{API}/repos/{REPO}/contents/{ruta_repo}", headers=HDRS, json=payload)

    if r.status_code in (200, 201):
        url = f"https://patonet.github.io/informes/{ruta_repo}"
        print(f"  ✅ {tipo}: {nombre}")
        print(f"     → {url}")
        return url
    else:
        print(f"  ❌ Error {r.status_code}: {r.json().get('message','?')} ({nombre})")
        return None

def guardar_local(contenido_bytes, ticker, fecha, nombre):
    """Guarda copia organizada en ~/feroldi_informes/TICKER/FECHA/"""
    carpeta = INFORMES / ticker / fecha
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / nombre
    destino.write_bytes(contenido_bytes)
    return destino

def actualizar_dashboard(ticker, fecha, urls):
    """Inserta entrada al inicio de const REPORTS en index.html."""
    r = requests.get(f"{API}/repos/{REPO}/contents/{DASHBOARD}", headers=HDRS)
    if r.status_code != 200:
        print(f"  ⚠ No se pudo obtener index.html ({r.status_code})")
        return

    data = r.json()
    sha  = data.get("sha")
    html = base64.b64decode(data.get("content", "")).decode("utf-8")

    if "const REPORTS = [" not in html:
        print("  ⚠ No se encontró const REPORTS = [ en index.html")
        return

    entry = f"""    {{
      ticker: "{ticker}",
      name: "{ticker}",
      desc: "Análisis Feroldi · {fecha}",
      type: "equity",
      verdict: "neutral",
      price: 0, upside: 0, target: 0,
      date: "{fecha}",
      url: "{urls.get('infografia_heavy', '')}",
      pdfUrl: "{urls.get('pdf_heavy', '')}",
      urlLight: "{urls.get('infografia_light', '')}",
      pdfLightUrl: "{urls.get('pdf_lite', '')}",
      sankeyUrl: "{urls.get('sankey', '')}"
    }},"""

    nuevo_html = html.replace("const REPORTS = [", f"const REPORTS = [\n{entry}")
    nuevo_b64  = base64.b64encode(nuevo_html.encode()).decode()
    payload    = {
        "message": f"feat: dashboard — {ticker} {fecha}",
        "content": nuevo_b64,
        "sha": sha
    }
    r2 = requests.put(f"{API}/repos/{REPO}/contents/{DASHBOARD}", headers=HDRS, json=payload)
    if r2.status_code in (200, 201):
        print(f"  ✅ Dashboard actualizado — {ticker} {fecha}")
    else:
        print(f"  ⚠ Dashboard no actualizado: {r2.json().get('message','?')}")

# ─── RECOLECCIÓN ───────────────────────────────────────────────────────────────
def recolectar():
    """
    Busca en ~/Downloads/:
      1. ZIPs que contengan archivos Feroldi → extrae en memoria
      2. Archivos sueltos .html/.pdf con nombre Feroldi
    Retorna lista de (nombre, contenido_bytes, fuente_path)
    """
    candidatos  = []
    nombres_zip = set()

    # 1. ZIPs
    for zip_path in sorted(DOWNLOADS.glob("*.zip")):
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                encontrados = []
                for entry in zf.namelist():
                    nombre_base = Path(entry).name
                    if nombre_base and detectar(nombre_base):
                        encontrados.append((nombre_base, zf.read(entry)))
                        nombres_zip.add(nombre_base)
                if encontrados:
                    print(f"  📦 ZIP: {zip_path.name} → {len(encontrados)} archivo(s) Feroldi")
                    for nb, contenido in encontrados:
                        candidatos.append((nb, contenido, zip_path))
        except Exception as e:
            print(f"  ⚠ No se pudo leer {zip_path.name}: {e}")

    # 2. Archivos sueltos (no duplicar lo que ya vino de ZIP)
    for ext in ("*.html", "*.pdf"):
        for archivo in sorted(DOWNLOADS.glob(ext)):
            if archivo.name not in nombres_zip and detectar(archivo.name):
                candidatos.append((archivo.name, archivo.read_bytes(), archivo))

    return candidatos

# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"  FEROLDI PUSH — v X0.56 · @patonet")
    print(f"{'='*55}\n")

    if not TOKEN:
        print("❌ GH_TOKEN no configurado.")
        print("   Ejecuta: export GH_TOKEN='tu_token'")
        sys.exit(1)

    r = requests.get(f"{API}/user", headers=HDRS)
    if r.status_code != 200:
        print(f"❌ Token inválido (HTTP {r.status_code})")
        sys.exit(1)
    usuario = r.json().get("login")
    rate    = r.headers.get("X-RateLimit-Remaining", "?")
    print(f"  ✅ Token válido — {usuario} · Rate: {rate}/5000\n")

    print(f"  🔍 Buscando en {DOWNLOADS}...\n")
    candidatos = recolectar()

    if not candidatos:
        print("  ⚠ No se encontraron archivos Feroldi en ~/Downloads/")
        print("  Nombres esperados:")
        print("    infografia_light_TICKER_PRECIO_DD-MM-AAAA.html")
        print("    infografia_TICKER_PRECIO_DD-MM-AAAA.html")
        print("    InformePDF_lite_TICKER_PRECIO_DD-MM-AAAA.pdf")
        print("    InformePDF_TICKER_PRECIO_DD-MM-AAAA.pdf")
        print("    Diagrama_Sankey_TICKER_PRECIO_DD-MM-AAAA.html")
        print("  O un ZIP que los contenga.")
        sys.exit(0)

    print(f"  📁 {len(candidatos)} archivo(s) encontrado(s)\n")

    # Procesar cada archivo
    urls_por_ticker   = {}  # {ticker: {clave: url}}
    fechas_por_ticker = {}
    procesados        = []  # (nombre, fuente_path) — para preguntar borrar
    fuentes_zip       = set()

    for nombre, contenido, fuente in candidatos:
        resultado = detectar(nombre)
        if not resultado:
            continue
        ruta_repo, tipo, clave, ticker, precio, fecha = resultado

        url = subir_bytes(contenido, ruta_repo, tipo, nombre)

        # Guardar local siempre (nuevo o skip)
        dest = guardar_local(contenido, ticker, fecha, nombre)
        print(f"     💾 Local: {dest}")

        if url and url != "skip":
            if ticker not in urls_por_ticker:
                urls_por_ticker[ticker]   = {}
                fechas_por_ticker[ticker] = fecha
            urls_por_ticker[ticker][clave] = url
            procesados.append((nombre, fuente))

        elif url == "skip":
            procesados.append((nombre, fuente))

        if isinstance(fuente, Path) and fuente.suffix == ".zip":
            fuentes_zip.add(fuente)

    # Actualizar dashboard
    for ticker, urls in urls_por_ticker.items():
        print(f"\n  📊 Actualizando dashboard — {ticker}...")
        actualizar_dashboard(ticker, fechas_por_ticker[ticker], urls)

    # BUG-3 FIX: contador claro
    n_nuevos = sum(1 for n, _ in procesados
                   if any(urls_por_ticker.get(detectar(n)[3], {}).values()
                          if detectar(n) else []))
    n_skip   = sum(1 for n, _ in procesados
                   if detectar(n) and not urls_por_ticker.get(detectar(n)[3]))
    print(f"\n{'='*55}")
    print(f"  📁 {len(candidatos)} detectado(s) · ✅ {len(urls_por_ticker)} ticker(s)")
    print(f"  💾 Copias locales: ~/feroldi_informes/")
    if urls_por_ticker:
        print(f"  🔗 Dashboard: https://patonet.github.io/informes/")
    print(f"{'='*55}\n")

    # Preguntar borrar de Downloads
    archivos_borrar = list(fuentes_zip)
    for nombre, fuente in procesados:
        if isinstance(fuente, Path) and fuente.suffix != ".zip" and fuente not in archivos_borrar:
            archivos_borrar.append(fuente)

    if archivos_borrar:
        print("  🗑  ¿Borrar de ~/Downloads/ los archivos procesados?")
        for f in archivos_borrar:
            print(f"     • {f.name}")
        resp = input("\n  Borrar? [s/N]: ").strip().lower()
        if resp == "s":
            for f in archivos_borrar:
                try:
                    f.unlink()
                    print(f"  🗑  Borrado: {f.name}")
                except Exception as e:
                    print(f"  ⚠ No se pudo borrar {f.name}: {e}")
        else:
            print("  ✓ Archivos conservados en Downloads")

    print()

if __name__ == "__main__":
    main()
