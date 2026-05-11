#!/usr/bin/env python3
"""
FEROLDI BATCH CORRIDA — pipeline completo, sin AV, sin intervención.
Genera Sankeys en ~/Downloads/CORRIDA_N_FEROLDI/ y un reporte final.
El número de corrida se autoincrementa buscando el primer directorio libre.

RESOLUCIÓN DE TICKERS
  Los tickers se ingresan como símbolo puro sin sufijo de exchange.
  La función resolve_yf_ticker() detecta automáticamente el exchange correcto:
    - Números de 4 dígitos         → .HK  (Hong Kong)
    - Números 5-6 dígitos (0/2/3)  → .SZ  (Shenzhen)
    - Números 5-6 dígitos (6/9)    → .SS  (Shanghai)
    - Country code explícito       → sufijo mapeado
    - US / ADRs                    → sin sufijo

SKIP AUTOMÁTICO
  Si el ticker ya tiene un HTML en alguna CORRIDA anterior, se omite.

USO: python3 feroldi_batch_corrida.py
"""
import subprocess, os, json, time, glob, shutil
from datetime import datetime
import yfinance as yf

TODAY     = datetime.now().strftime("%d-%m-%Y")
TODAY_FMT = datetime.now().strftime("%d%m%Y")
DOWNLOADS = os.path.expanduser("~/Downloads")
WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
PROD_DIR  = os.path.expanduser("~")

# ── NÚMERO DE CORRIDA (auto-incremental) ─────────────────────────────────────
def next_corrida_number():
    n = 1
    while os.path.exists(os.path.join(DOWNLOADS, f"CORRIDA_{n}_FEROLDI")):
        n += 1
    return n

CORRIDA_N = next_corrida_number()
OUT_DIR   = os.path.join(DOWNLOADS, f"CORRIDA_{CORRIDA_N}_FEROLDI")
LOG_FILE  = os.path.join(OUT_DIR, "reporte.txt")
os.makedirs(OUT_DIR, exist_ok=True)

# ── RESOLUCIÓN DE EXCHANGE ────────────────────────────────────────────────────
# Sufijo yfinance por código de país/exchange
_COUNTRY_SUFFIX = {
    "MX": ".MX",  # Bolsa Mexicana de Valores
    "ES": ".MC",  # Bolsa de Madrid (IBEX)
    "HK": ".HK",  # Hong Kong Stock Exchange
    "SG": ".SI",  # Singapore Exchange (SGX)
    "FR": ".PA",  # Euronext París
    "SH": ".SS",  # Shanghai Stock Exchange
    "SZ": ".SZ",  # Shenzhen Stock Exchange
    "CA": ".TO",  # Toronto Stock Exchange
    "DE": ".DE",  # XETRA Frankfurt
    "AU": ".AX",  # ASX Australia
    "BR": ".SA",  # B3 Brasil
    # "US" / "AR" / "" → sin sufijo (NYSE / NASDAQ / OTC ADR)
}

def resolve_yf_ticker(symbol, country=""):
    """
    Convierte símbolo puro al formato yfinance correcto.
    El usuario nunca necesita escribir el sufijo de exchange manualmente.
    """
    # Si ya tiene punto explícito, respetar tal cual
    if "." in symbol:
        return symbol

    # Auto-detección por patrón numérico (China A-Shares y Hong Kong)
    if symbol.isdigit():
        n = len(symbol)
        if n == 4:
            return symbol + ".HK"          # HKEX: 4 dígitos
        elif n in (5, 6) and symbol[0] in "023":
            return symbol + ".SZ"          # Shenzhen: empieza con 0, 2 ó 3
        elif n in (5, 6) and symbol[0] in "69":
            return symbol + ".SS"          # Shanghai: empieza con 6 ó 9

    # Por código de país explícito
    if country in _COUNTRY_SUFFIX:
        return symbol + _COUNTRY_SUFFIX[country]

    # Default: NYSE / NASDAQ / OTC ADR — sin sufijo
    return symbol


# ── TICKERS — símbolo puro + código de país ───────────────────────────────────
# El usuario puede agregar tickers escribiendo solo el símbolo puro.
# Para exchanges locales no-US, indicar el country code correspondiente.
#
# Country codes:
#   ""  / "US" → NYSE / NASDAQ / OTC ADR (sin sufijo)
#   "AR"        → ADR argentino en NYSE (sin sufijo)
#   "MX"        → BMV México (.MX)
#   "ES"        → Bolsa Madrid (.MC)
#   "CA"        → TSX Toronto (.TO)
#   "DE"        → XETRA Frankfurt (.DE)
#   "FR"        → Euronext París (.PA)
#   "HK"        → Hong Kong Exchange (.HK)
#   "SG"        → Singapore Exchange (.SI)
#   "SH"        → Shanghai SSE (.SS)  — o auto-detectado por patrón numérico
#   "SZ"        → Shenzhen SZSE (.SZ) — o auto-detectado por patrón numérico

TICKERS = [
    # ── Argentina — NYSE ADRs ──────────────────────────────────────────────────
    ("BMA",     ""),   # Banco Macro
    ("CEPU",    ""),   # Central Puerto
    ("TEO",     ""),   # Telecom Argentina  (local: TECO2)
    ("LOMA",    ""),   # Loma Negra
    ("CRESY",   ""),   # Cresud (OTC ADR; ticker local: CRES)

    # ── México — NYSE ADRs + BMV locales ──────────────────────────────────────
    ("KOF",     ""),   # Coca-Cola FEMSA (NYSE)       (local: KOFUBL)
    # ("GRUMAB","MX"), # Grupo Bimbo — solo BMV, sin 20-F en EDGAR → sin datos de segmentos
    ("ASR",     ""),   # Grupo Aeroportuario Sureste (NYSE)
    ("PAC",     ""),   # Grupo Aeroportuario Pacífico (NYSE)
    # ("ELEKTRA","MX"), # Grupo Elektra — solo BMV, sin 20-F en EDGAR → sin datos de segmentos

    # ── España — NYSE/OTC ADRs + Bolsa Madrid ─────────────────────────────────
    ("BBVA",    ""),   # BBVA (NYSE ADR)
    ("TEFOF",   ""),   # Telefónica (OTC ADR; TEF se delistó de NYSE en 2019)
    ("IBDRY",   ""),   # Iberdrola (OTC ADR)
    ("GRFS",    ""),   # Grifols (NASDAQ ADR)         (local: GRF)
    ("CABK",    "ES"), # CaixaBank (solo Bolsa Madrid)

    # ── Canadá — NYSE cross-listed ─────────────────────────────────────────────
    ("BN",      ""),   # Brookfield Corp (NYSE)
    ("AEM",     ""),   # Agnico Eagle (NYSE)
    ("CM",      ""),   # CIBC (NYSE)
    ("BNS",     ""),   # Bank of Nova Scotia (NYSE)
    ("CNQ",     ""),   # Canadian Natural Resources (NYSE)

    # ── Alemania — OTC ADRs NYSE ──────────────────────────────────────────────
    ("IFNNY",   ""),   # Infineon (OTC)               (local: IFX)
    ("MURGY",   ""),   # Munich Re (OTC)              (local: MUV2)
    ("RNMBY",   ""),   # Rheinmetall (OTC)            (local: RHM)
    ("DHLGY",   ""),   # DHL Group (OTC ADR; DPSGY era el ticker antiguo, local: DHL.DE)
    ("DB",      ""),   # Deutsche Bank (NYSE)         (local: DBK)

    # ── Francia — OTC ADRs NYSE ───────────────────────────────────────────────
    ("SNY",     ""),   # Sanofi (NASDAQ)              (local: SASY)
    ("TTE",     ""),   # TotalEnergies (NYSE)
    ("LRLCY",   ""),   # L'Oréal (OTC)                (local: OR)
    ("LVMUY",   ""),   # LVMH (OTC)                   (local: MC)
    ("PPRUY",   ""),   # Kering (OTC)                 (local: KER)

    # ── China A-Shares — SIN 20-F en EDGAR, sin datos de segmentos disponibles ─
    # Las siguientes empresas cotizan solo en SSE/SZSE y no presentan informes
    # anuales con la SEC. El pipeline no puede obtener sus segmentos de ingresos.
    # ("601899",  ""),  # Zijin Mining (SSE) — sin EDGAR
    # ("600673",  ""),  # Chengdu Expressway (SSE) — sin EDGAR
    # ("002050",  ""),  # Zhejiang Sanhua (SZSE) — sin EDGAR
    # ("002475",  ""),  # Luxshare Precision (SZSE) — sin EDGAR
    # ("000938",  ""),  # Ziguang Guowei (SZSE) — sin EDGAR

    # ── Hong Kong — auto-detectados por patrón numérico ───────────────────────
    ("1398",    ""),   # ICBC (HKEX) — sí presenta 20-F en EDGAR
    ("2378",    ""),   # Phoenix New Media (HKEX) — sí presenta 20-F
    ("0805",    ""),   # Value Partners (HKEX) — sí presenta 20-F
    ("0883",    ""),   # CNOOC (HKEX) — sí presenta 20-F
    ("2318",    ""),   # Ping An Insurance (HKEX) — sí presenta 20-F

    # ── Singapur — SIN 20-F en EDGAR ──────────────────────────────────────────
    # Las siguientes empresas cotizan en SGX y no presentan informes con la SEC.
    # ("S68",   "SG"), # Singapore Exchange — sin EDGAR
    # ("Z74",   "SG"), # Singapore Telecom — sin EDGAR
    # ("V03",   "SG"), # Venture Corp — sin EDGAR
    # ("A17U",  "SG"), # CapitaLand Ascendas REIT — sin EDGAR
    # ("C38U",  "SG"), # CapitaLand Integrated Commercial Trust — sin EDGAR
]


# ── SKIP AUTOMÁTICO ───────────────────────────────────────────────────────────
def already_done(symbol):
    """
    Devuelve True si el ticker ya tiene un Sankey HTML en alguna corrida anterior.
    Evita reprocesar tickers ya completados.
    """
    pattern = os.path.join(DOWNLOADS, "CORRIDA_*_FEROLDI", f"Diagrama_Sankey_{symbol}_*.html")
    return bool(glob.glob(pattern))


# ── PRECIO VÍA YFINANCE ───────────────────────────────────────────────────────
def get_price(yf_ticker):
    """
    Obtiene precio actual vía yfinance.
    Recibe el ticker ya resuelto (con sufijo correcto).
    Intenta con el ticker resuelto primero; luego fallbacks comunes.
    """
    base = yf_ticker.split(".")[0] if "." in yf_ticker else yf_ticker
    candidates = [yf_ticker]
    for sfx in ["", ".BA", ".HK", ".TO", ".L", ".DE",
                 ".MC", ".PA", ".SI", ".MX", ".SS", ".SZ"]:
        t = base + sfx
        if t not in candidates:
            candidates.append(t)
    for t in candidates:
        try:
            info = yf.Ticker(t).info or {}
            p = (info.get("regularMarketPrice") or
                 info.get("currentPrice") or
                 info.get("previousClose"))
            if p:
                return round(float(p), 2)
        except Exception:
            continue
    return None


# ── BÚSQUEDA DE ARCHIVOS ─────────────────────────────────────────────────────
def find_json(symbol):
    """Busca el JSON más reciente del ticker en workspace y Downloads."""
    pattern = f"datos_{symbol}_{TODAY_FMT}.json"
    for base in [WORKSPACE, DOWNLOADS]:
        path = os.path.join(base, pattern)
        if os.path.exists(path):
            return path
    return None


def find_html(symbol):
    """
    Busca el HTML Sankey del ticker creado HOY en Downloads.
    Prueba ambos formatos de fecha: "09-05-2026" y "09052026".
    Fallback: el más reciente del ticker en los últimos 15 minutos.
    """
    now = datetime.now()
    pattern_dash   = os.path.join(DOWNLOADS, f"Diagrama_Sankey_{symbol}_*{TODAY}*.html")
    pattern_nodash = os.path.join(DOWNLOADS, f"Diagrama_Sankey_{symbol}_*{TODAY_FMT}*.html")
    for pattern in [pattern_dash, pattern_nodash]:
        matches = glob.glob(pattern)
        if matches:
            return max(matches, key=os.path.getmtime)
    # Fallback: creado en los últimos 15 minutos
    pattern_any = os.path.join(DOWNLOADS, f"Diagrama_Sankey_{symbol}_*.html")
    matches = [f for f in glob.glob(pattern_any)
               if (now.timestamp() - os.path.getmtime(f)) < 900]
    if matches:
        return max(matches, key=os.path.getmtime)
    return None


# ── PIPELINE POR TICKER ───────────────────────────────────────────────────────
def run_pipeline(symbol, precio):
    """Corre recolectar → normalizar → sankey para un ticker."""
    # 1. RECOLECTAR (--no-av para evitar rate limits en batch)
    r = subprocess.run(
        ["python3", os.path.join(PROD_DIR, "feroldi_recolectar.py"),
         symbol, str(precio), "--no-av"],
        capture_output=True, text=True, timeout=180
    )
    if r.returncode != 0:
        return False, "recolectar", (r.stderr or r.stdout)[-800:]

    # 2. Encontrar JSON generado
    json_path = find_json(symbol)
    if not json_path:
        return False, "json_not_found", f"datos_{symbol}_{TODAY_FMT}.json no encontrado"

    # 3. NORMALIZAR
    norm_script = os.path.join(PROD_DIR, "feroldi_normalizar.py")
    if not os.path.exists(norm_script):
        norm_script = os.path.join(WORKSPACE, "feroldi_normalizar.py")
    r = subprocess.run(
        ["python3", norm_script, json_path],
        capture_output=True, text=True, timeout=60
    )
    if r.returncode != 0:
        return False, "normalizar", (r.stderr or r.stdout)[-800:]

    # 4. SANKEY
    sankey_script = os.path.join(PROD_DIR, "feroldi_sankey.py")
    if not os.path.exists(sankey_script):
        sankey_script = os.path.join(WORKSPACE, "feroldi_sankey.py")
    r = subprocess.run(
        ["python3", sankey_script, json_path, str(precio)],
        capture_output=True, text=True, timeout=60
    )
    stdout = r.stdout or ""
    if r.returncode != 0:
        return False, "sankey", (r.stderr or stdout)[-800:]
    # Sankey puede imprimir error de datos pero salir con código 0
    if "✅ SANKEY GENERADO" not in stdout:
        return False, "sankey_no_data", stdout[-300:]

    # 5. Obtener path del HTML desde stdout ("Archivo: /path/...")
    html_path = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Archivo:"):
            html_path = stripped.replace("Archivo:", "").strip()
            break

    if html_path and os.path.exists(html_path):
        dest = os.path.join(OUT_DIR, os.path.basename(html_path))
        shutil.move(html_path, dest)
        return True, "ok", dest

    # Fallback: buscar por glob en Downloads
    html = find_html(symbol)
    if html and os.path.exists(html):
        dest = os.path.join(OUT_DIR, os.path.basename(html))
        shutil.move(html, dest)
        return True, "ok", dest

    return True, "ok_no_html", f"HTML no encontrado (stdout: {stdout[:100]})"


# ── MAIN ─────────────────────────────────────────────────────────────────────
results = []
skipped = []
print(f"\n{'='*65}")
print(f"  FEROLDI BATCH CORRIDA {CORRIDA_N} — {len(TICKERS)} tickers — {TODAY}")
print(f"  Output: {OUT_DIR}")
print(f"  Modo: --no-av (sin Alpha Vantage) | Skip: tickers ya procesados")
print(f"{'='*65}\n")

for i, (symbol, country) in enumerate(TICKERS):
    yf_symbol = resolve_yf_ticker(symbol, country)
    prefix = f"[{i+1:02d}/{len(TICKERS)}] {symbol}"
    if yf_symbol != symbol:
        prefix += f" ({yf_symbol})"

    # Skip si ya fue procesado en una corrida anterior
    if already_done(symbol):
        print(f"{prefix}... ⏭  ya procesado")
        skipped.append(symbol)
        results.append({"ticker": symbol, "yf_ticker": yf_symbol,
                        "status": "SKIP", "reason": "ya procesado"})
        continue

    print(f"{prefix}...", end=" ", flush=True)
    precio = get_price(yf_symbol)
    if not precio:
        print("❌ sin precio")
        results.append({"ticker": symbol, "yf_ticker": yf_symbol,
                        "status": "ERROR", "step": "precio",
                        "error": "sin precio yfinance"})
        continue

    print(f"${precio}", end=" → ", flush=True)
    try:
        ok, step, info = run_pipeline(symbol, precio)
        if ok:
            label = f"→ {os.path.basename(info)}" if info and info != "ok_no_html" else ""
            print(f"✅  {label}")
            results.append({"ticker": symbol, "yf_ticker": yf_symbol,
                            "precio": precio, "status": "OK", "html": info})
        else:
            print(f"❌ ({step})")
            results.append({"ticker": symbol, "yf_ticker": yf_symbol,
                            "precio": precio, "status": "ERROR",
                            "step": step, "error": info})
    except subprocess.TimeoutExpired:
        print("⏱ timeout")
        results.append({"ticker": symbol, "yf_ticker": yf_symbol,
                        "precio": precio, "status": "TIMEOUT"})
    except Exception as e:
        print(f"💥 {e}")
        results.append({"ticker": symbol, "yf_ticker": yf_symbol,
                        "precio": precio, "status": "CRASH", "error": str(e)})

    time.sleep(1)  # pausa mínima entre tickers

# ── REPORTE ───────────────────────────────────────────────────────────────────
ok_list   = [r for r in results if r["status"] == "OK"]
skip_list = [r for r in results if r["status"] == "SKIP"]
err_list  = [r for r in results if r["status"] not in ("OK", "SKIP")]

err_by_step = {}
for r in err_list:
    step = r.get("step", r["status"])
    err_by_step.setdefault(step, []).append(r["ticker"])

lines = [
    f"FEROLDI BATCH CORRIDA {CORRIDA_N} — {TODAY}",
    f"recolectar v X0.76  |  modo: --no-av  |  resolución automática de exchange",
    f"{'='*55}",
    f"Total: {len(TICKERS)} | OK: {len(ok_list)} | Omitidos: {len(skip_list)} | Errores: {len(err_list)}",
    "",
    "✅ EXITOSOS:",
    *[f"  {r['ticker']:12} ({r.get('yf_ticker', r['ticker']):14}) ${r.get('precio','?')}"
      for r in ok_list],
    "",
    "⏭  OMITIDOS (ya procesados en corrida anterior):",
    *[f"  {s}" for s in skipped],
    "",
    "❌ ERRORES POR STEP:",
    *[f"  [{step}] {', '.join(tickers)}"
      for step, tickers in sorted(err_by_step.items())],
    "",
    "DETALLE ERRORES:",
    *[f"  {r['ticker']:12} [{r.get('step', r['status'])}] {str(r.get('error',''))[:120]}"
      for r in err_list],
]
report = "\n".join(lines)
print(f"\n{report}")

with open(LOG_FILE, "w") as f:
    f.write(report + "\n\n")
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\n📁 {OUT_DIR}")
print(f"📋 Reporte: {LOG_FILE}")
