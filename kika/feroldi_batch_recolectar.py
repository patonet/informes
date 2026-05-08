#!/usr/bin/env python3
"""
FEROLDI BATCH RECOLECTAR — v X0.63
Sistema Feroldi · @patonet
======================================
Recolecta 50 tickers SIN Alpha Vantage.
Fuentes: EDGAR (edgartools) + yfinance únicamente.

Propósito: stress-test del pipeline de datos ANTES de construir
           Light, Heavy, Infografía y PDF. Si el alma está rota,
           todo lo que sigue se cae.

Detecta automáticamente por ticker:
  · Moneda mezclada (empresa reporta JPY/EUR, mercado en USD)
  · Empresa pre-revenue o quema extrema
  · Banco / aseguradora (sin estructura COGS clásica)
  · REIT (FFO ≠ FCF tradicional)
  · Filing 20-F / 40-F (empresa extranjera — EDGAR puede no leerlo bien)
  · Campos críticos nulos (cobertura de datos)
  · Valores NaN o infinitos

Output: ~/Downloads/batch_datos_DDMMYYYY.json
  Un solo JSON con 50 resultados + resumen analítico + errores.

USO:
  python3 feroldi_batch_recolectar.py               # los 50 tickers
  python3 feroldi_batch_recolectar.py --dry-run     # solo 5, prueba rápida
  python3 feroldi_batch_recolectar.py --sleep 5     # 5s entre tickers

INSTALAR (una sola vez):
  pip install edgartools yfinance
"""

import json
import sys
import os
import time
import math
import argparse
import traceback
from datetime import datetime

VERSION   = "X0.63"
TODAY     = datetime.now().strftime("%d-%m-%Y")
SLEEP_SEC = 3   # segundos entre tickers

# SEC requiere User-Agent identificado para todas las requests a EDGAR
try:
    from edgar import set_identity
    set_identity("patonet@example.com")
except ImportError:
    print("ERROR: edgartools no instalado. Ejecuta: pip install edgartools")
    sys.exit(1)

# OUTPUT_DIR: ~/Downloads en Mac, directorio actual si no existe (GitHub Actions)
_downloads = os.path.expanduser("~/Downloads")
OUTPUT_DIR = os.environ.get("FEROLDI_OUTPUT_DIR",
                            _downloads if os.path.isdir(_downloads) else os.getcwd())

# ── UNIVERSO DE TICKERS ────────────────────────────────────────────────────────
# Excluidos (ya analizados): GE, MCD, AAPL, AMZN, AUR, TM

TICKERS_SP500 = [
    "JPM",   # Banco — sin COGS, revenue = net interest income
    "WMT",   # FY termina enero — fy_year confuso
    "COST",  # FY termina agosto, margen bruto ~3%
    "XOM",   # Energy — capex masivo, FCF volátil
    "PLD",   # REIT — FFO ≠ FCF, deprec. distorsionada
    "BA",    # Negative equity, FCF negativo crónico
    "LLY",   # Revenue explotó 3x en 2 años — yoy extremo
    "NEE",   # Utilities — deuda enorme, capex = core del negocio
    "UNH",   # Health insurer — revenue = primas, no ventas
    "BLK",   # Asset manager — revenue = fees, sin COGS
]

TICKERS_NASDAQ = [
    "MSFT",  # Baseline sano — debería pasar todo
    "NVDA",  # Revenue x10 en 2 años — yoy extremo
    "META",  # Recompras masivas, SBC gigante
    "TSLA",  # PE alto, márgenes volátiles
    "NFLX",  # Recién empezó a generar FCF real
    "INTC",  # Pérdidas, capex destructivo
    "MRNA",  # Revenue colapsó de $18B → $3B post-COVID
    "ADBE",  # SBC ~20% del net income
    "PYPL",  # Fintech — estructura financiera diferente
    "CSCO",  # Sólido, goodwill inflado por acquisitions
]

TICKERS_ADR = [
    "ASML",  # Holanda, EUR, 20-F, semiconductor equipment
    "TSM",   # Taiwán, TWD, 20-F
    "BABA",  # China, CNY, 20-F, estructura VIE
    "NVO",   # Dinamarca, DKK, 20-F
    "SAP",   # Alemania, EUR, 20-F
    "SHEL",  # UK/NL, ya reporta en USD, 20-F
    "AZN",   # UK, ya reporta en USD, 20-F
    "RY",    # Canadá, CAD, 40-F, banco
    "SNY",   # Francia, EUR, 20-F
    "UL",    # UK, GBP, 20-F
]

TICKERS_R2000 = [
    "ARWR",  # Biotech pre-revenue, solo quema
    "RXRX",  # AI drug discovery, pre-revenue
    "JOBY",  # eVTOL, pre-revenue, activos mínimos
    "ENVX",  # Battery tech, revenue incipiente
    "HIMS",  # Telemedicine, crecimiento rápido
    "MRVI",  # Maravai LifeSciences, revenue colapsó post-COVID
    "RKT",   # Mortgage company, estructura financiera
    "CLOV",  # Health insurer pequeño, pérdidas
    "ASAN",  # Asana — SaaS, pérdidas, buena cobertura de datos
    "ACVA",  # Auto auctions platform
    "BOOT",  # Retail especializado, rentable
    "LCII",  # Manufactura RVs — cíclico
    "PRCT",  # Medical devices, break-even
    "SFIX",  # E-commerce, revenue cayendo
    "APLS",  # Pharma, recién tiene revenue
    "TASK",  # BPO/servicios, estable
    "SMPL",  # Consumer goods, profitable
    "CERT",  # Certara, pharma software
    "AGIO",  # Agios Pharma, oncología
    "TFIN",  # Triumph Financial, banco pequeño
]

ALL_TICKERS = TICKERS_SP500 + TICKERS_NASDAQ + TICKERS_ADR + TICKERS_R2000  # 50 total

# ── HELPERS ────────────────────────────────────────────────────────────────────
def _float(v):
    """Convierte a float, retorna None si es NaN/Inf/None/inválido."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return None


def fmt_b(v):
    if v is None:
        return "N/D"
    try:
        v = float(v)
        if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
        if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6:  return f"${v/1e6:.1f}M"
        return f"${v:,.0f}"
    except Exception:
        return "N/D"


def pick(*vals):
    """Primer valor no-None de la lista."""
    for v in vals:
        fv = _float(v)
        if fv is not None:
            return fv
    return None


# ── TIER 2: EDGAR ─────────────────────────────────────────────────────────────
def _extract_stmt(stmt, concept_map, result):
    """
    Extrae valores de un Statement edgartools usando to_dataframe() — API actual.
    Filtra filas sin dimensiones para obtener valores consolidados.
    Soporta columnas con y sin sufijo '(FY)'.
    """
    try:
        df = stmt.to_dataframe()
        if df is None or df.empty:
            return
        # Columnas de fecha: '2025-06-30' o '2025-06-30 (FY)'
        date_cols = [c for c in df.columns
                     if len(str(c)) >= 10 and str(c)[4] == '-' and str(c)[7] == '-']
        if not date_cols:
            return
        latest_col = sorted(date_cols)[-1]

        # Filtrar filas consolidadas: dimension==False (bool) = valor total sin desglose
        if "dimension" in df.columns:
            df = df[df["dimension"] == False]  # noqa: E712  (False es bool, no comparación)
        # Excluir filas abstractas (headers/subtotales sin valor propio)
        if "abstract" in df.columns:
            df = df[df["abstract"] == False]  # noqa: E712

        for concept_key, field in concept_map.items():
            if result.get(field):
                continue
            # Claves con '$' al final → regex de sufijo exacto (evita falsos positivos)
            use_regex = concept_key.endswith("$")
            mask = df["concept"].str.contains(concept_key, na=False, regex=use_regex)
            rows = df[mask]
            if rows.empty:
                continue
            # Iterar filas hasta encontrar un valor no-NaN (ignora headers subtotales)
            for _, row in rows.iterrows():
                v = _float(row[latest_col])
                if v is not None:
                    result[field] = v
                    break
    except Exception:
        pass


def get_edgar(ticker):
    """
    Extrae datos financieros de EDGAR.
    Intenta 10-K primero, luego 20-F, luego 40-F.
    Usa to_dataframe() — API actual de edgartools.
    Nunca lanza excepción — errores quedan en result["edgar_error"].
    """
    result = {"filing_type": None, "fy_year": None}
    try:
        from edgar import Company
        company = Company(ticker)

        filing      = None
        filing_type = None
        for form in ["10-K", "20-F", "40-F"]:
            try:
                f = company.get_filings(form=form).latest(1)
                if f:
                    filing      = f
                    filing_type = form
                    break
            except Exception:
                continue

        if not filing:
            result["edgar_error"] = "No filing (10-K / 20-F / 40-F)"
            return result

        result["filing_type"] = filing_type
        result["fy_year"]     = str(filing.filing_date)[:4]
        try:
            result["company_name"] = company.name
        except Exception:
            pass

        # --- obj() + to_dataframe() ---
        try:
            tenk = filing.obj()
            if tenk:
                _extract_stmt(tenk.income_statement, {
                    # Revenue — orden importa: más específico primero
                    "RevenueFromContractWithCustomerExcludingAssessedTax$": "revenue",
                    "_Revenues$":          "revenue",   # XOM, energía
                    "SalesRevenueNet$":    "revenue",
                    # Net income — anclado para NO capturar NoncontrollingInterest
                    "_NetIncomeLoss$":     "net_income",
                    "_NetIncome$":         "net_income",
                    # Operating income
                    "OperatingIncomeLoss$": "operating_income",
                    # SBC
                    "ShareBasedCompensation$": "sbc",
                }, result)

                _extract_stmt(tenk.balance_sheet, {
                    "CashAndCashEquivalentsAtCarryingValue$": "cash_real",
                    # Deuda: LongTermDebt exacto → Noncurrent → Current como fallback
                    "LongTermDebt$":                  "deuda_total",
                    "LongTermDebtNoncurrent$":        "deuda_total",
                    "LongTermDebtCurrent$":           "deuda_total",
                    "_Assets$":                       "total_assets",   # anclado: no AssetsCurrent
                    "Goodwill$":                      "goodwill",
                    "CommonStockSharesOutstanding$":  "shares",
                }, result)

                _extract_stmt(tenk.cash_flow_statement, {
                    # CFO anclado — no capturar Continuing/Discontinued variants
                    "_NetCashProvidedByUsedInOperatingActivities$": "cfo",
                    "PaymentsToAcquirePropertyPlantAndEquipment$":  "capex",
                    "PaymentsOfDividendsCommonStock$": "dividendos",
                    "PaymentsOfDividends$":            "dividendos",
                }, result)
        except Exception as e:
            result["edgar_obj_error"] = str(e)

        # FCF derivado
        if not result.get("fcf") and result.get("cfo") and result.get("capex"):
            result["fcf"] = result["cfo"] - abs(result["capex"])

    except Exception as e:
        result["edgar_error"] = str(e)

    return result


# ── TIER 1 (MERCADO): YFINANCE ────────────────────────────────────────────────
def get_yfinance(ticker):
    """
    Obtiene datos de mercado y ratios.
    En este script yfinance ES la fuente primaria de market data (no hay AV).
    Nunca lanza excepción.
    """
    result = {}
    try:
        import yfinance as yf
        result["yf_version"] = getattr(yf, "__version__", "?")
        t    = yf.Ticker(ticker)
        info = t.info or {}

        result["company_name"]    = info.get("longName") or info.get("shortName")
        result["sector"]          = info.get("sector")
        result["industry"]        = info.get("industry")
        result["exchange"]        = info.get("exchange")
        result["precio_actual"]   = _float(info.get("currentPrice")
                                          or info.get("regularMarketPrice"))
        result["market_cap"]      = _float(info.get("marketCap"))
        result["beta"]            = _float(info.get("beta"))
        result["pe_forward"]      = _float(info.get("forwardPE"))
        result["pe_ttm"]          = _float(info.get("trailingPE"))
        result["analyst_target"]  = _float(info.get("targetMeanPrice"))
        result["w52_high"]        = _float(info.get("fiftyTwoWeekHigh"))
        result["w52_low"]         = _float(info.get("fiftyTwoWeekLow"))
        result["margen_bruto"]    = _float(info.get("grossMargins"))
        result["margen_op"]       = _float(info.get("operatingMargins"))
        result["margen_neto"]     = _float(info.get("profitMargins"))
        result["shares"]          = _float(info.get("sharesOutstanding"))
        result["deuda_total"]     = _float(info.get("totalDebt"))
        result["cash_real"]       = _float(info.get("totalCash"))
        result["revenue_yf"]      = _float(info.get("totalRevenue"))  # cross-check
        result["analyst_consenso"]= info.get("recommendationKey")     # "buy"/"hold"/"sell"

    except Exception as e:
        result["yf_error"] = str(e)

    return result


# ── DETECTOR DE ANOMALÍAS ─────────────────────────────────────────────────────
def detect_anomalies(edgar, yf, canonical):
    """
    Detecta problemas estructurales que romperán Light / Heavy / Sankey / PDF.
    Retorna lista de códigos de warning — uno por problema detectado.
    """
    warnings = []

    revenue      = canonical.get("revenue")
    mkt_cap      = canonical.get("market_cap")
    margen_bruto = canonical.get("margen_bruto")
    filing_type  = edgar.get("filing_type")

    # ── Problemas de revenue ──────────────────────────────────────────────────
    if revenue is None:
        warnings.append("NO_REVENUE")
    elif abs(revenue) < 10_000_000:
        warnings.append("PRE_REVENUE")

    # ── Márgenes absurdos → moneda local sin convertir ────────────────────────
    if margen_bruto is not None and abs(margen_bruto) > 5.0:
        warnings.append("MARGIN_EXTREME")

    # ── Ratio revenue/mkt_cap extremo → sospecha de moneda ───────────────────
    if revenue and mkt_cap and mkt_cap > 0:
        if abs(revenue) / mkt_cap > 50:
            warnings.append("CURRENCY_MISMATCH_SUSPECTED")

    # ── Filing extranjero ─────────────────────────────────────────────────────
    if filing_type == "20-F":
        warnings.append("FOREIGN_FILER_20F")
    elif filing_type == "40-F":
        warnings.append("FOREIGN_FILER_40F")
    elif filing_type is None:
        warnings.append("NO_EDGAR_FILING")

    # ── EDGAR no entregó financials ───────────────────────────────────────────
    if "edgar_error" in edgar or not edgar.get("revenue"):
        warnings.append("EDGAR_NO_FINANCIALS")

    # ── FCF negativo (informativo — no es malo per se) ────────────────────────
    if canonical.get("fcf") is not None and canonical["fcf"] < 0:
        warnings.append("NEGATIVE_FCF")

    # ── yfinance no pudo dar márgenes ─────────────────────────────────────────
    if yf.get("margen_bruto") is None and yf.get("margen_op") is None:
        warnings.append("YF_NO_MARGINS")

    # ── Sospecha de banco/aseguradora (revenue > $1B pero sin márgenes) ───────
    if (revenue and abs(revenue) > 1e9 and
            margen_bruto is None and yf.get("margen_bruto") is None):
        warnings.append("FINANCIAL_SECTOR_SUSPECTED")

    # ── Cobertura crítica baja ────────────────────────────────────────────────
    critical_fields = ["revenue", "net_income", "cfo", "shares", "market_cap"]
    null_critical   = [f for f in critical_fields if not canonical.get(f)]
    if len(null_critical) >= 3:
        warnings.append(f"NULL_CRITICAL_{len(null_critical)}OF{len(critical_fields)}")

    # ── Error total ───────────────────────────────────────────────────────────
    if "edgar_error" in edgar and "yf_error" in yf:
        warnings.append("TOTAL_FAILURE")

    return warnings


# ── RECOLECTAR UN TICKER ──────────────────────────────────────────────────────
def recolectar_uno(ticker):
    """
    Recolecta datos para un solo ticker combinando EDGAR + yfinance.
    Nunca lanza excepción — errores quedan documentados en el resultado.
    """
    edgar = get_edgar(ticker)
    yf    = get_yfinance(ticker)

    # ── Ensamblar canonical (EDGAR > yfinance para financials) ────────────────
    revenue    = pick(edgar.get("revenue"),    yf.get("revenue_yf"))
    net_income = pick(edgar.get("net_income"))
    op_income  = pick(edgar.get("operating_income"))
    cfo        = pick(edgar.get("cfo"))
    capex_raw  = pick(edgar.get("capex"))
    capex      = abs(capex_raw) if capex_raw else None
    sbc        = pick(edgar.get("sbc"))
    dividendos = pick(edgar.get("dividendos"))
    fcf        = edgar.get("fcf") or ((cfo - capex) if cfo and capex else None)
    shares     = pick(edgar.get("shares"),    yf.get("shares"))
    deuda      = pick(edgar.get("deuda_total"), yf.get("deuda_total"))
    cash       = pick(edgar.get("cash_real"),  yf.get("cash_real"))
    goodwill   = pick(edgar.get("goodwill"))
    total_assets = pick(edgar.get("total_assets"))

    # market data viene de yfinance (no hay AV en este script)
    market_cap   = yf.get("market_cap")
    margen_bruto = yf.get("margen_bruto")
    margen_op    = yf.get("margen_op")
    margen_neto  = yf.get("margen_neto")

    canonical = {
        "revenue":          revenue,
        "net_income":       net_income,
        "operating_income": op_income,
        "cfo":              cfo,
        "capex":            capex,
        "fcf":              fcf,
        "sbc":              sbc,
        "dividendos":       dividendos,
        "deuda_total":      deuda,
        "cash_real":        cash,
        "goodwill":         goodwill,
        "total_assets":     total_assets,
        "shares":           shares,
        "market_cap":       market_cap,
        "precio_actual":    yf.get("precio_actual"),
        "margen_bruto":     margen_bruto,
        "margen_op":        margen_op,
        "margen_neto":      margen_neto,
    }

    warnings = detect_anomalies(edgar, yf, canonical)

    # ── Cobertura de datos ────────────────────────────────────────────────────
    null_fields   = [k for k, v in canonical.items() if v is None]
    total_fields  = len(canonical)
    coverage_pct  = int((total_fields - len(null_fields)) / total_fields * 100)

    # ── Status general ────────────────────────────────────────────────────────
    if "TOTAL_FAILURE" in warnings:
        status = "error"
    elif null_fields or warnings:
        status = "partial"
    else:
        status = "ok"

    # ── Armar errores si los hay ──────────────────────────────────────────────
    errors = {}
    if edgar.get("edgar_error"):
        errors["edgar"] = edgar["edgar_error"]
    if yf.get("yf_error"):
        errors["yfinance"] = yf["yf_error"]

    result = {
        "status":       status,
        "warnings":     warnings,
        "filing_type":  edgar.get("filing_type", "unknown"),
        "fy_year":      edgar.get("fy_year"),
        "company_name": yf.get("company_name") or edgar.get("company_name"),
        "sector":       yf.get("sector"),
        "industry":     yf.get("industry"),
        "coverage_pct": coverage_pct,
        "null_fields":  null_fields,
        "edgar": {
            "fy_year":          edgar.get("fy_year"),
            "revenue":          revenue,
            "net_income":       net_income,
            "operating_income": op_income,
            "cfo":              cfo,
            "capex":            capex,
            "fcf":              fcf,
            "sbc":              sbc,
            "dividendos":       dividendos,
            "deuda_total":      deuda,
            "cash_real":        cash,
            "total_assets":     total_assets,
            "goodwill":         goodwill,
            "shares":           shares,
        },
        "market": {
            "precio_actual":    yf.get("precio_actual"),
            "market_cap":       market_cap,
            "w52_high":         yf.get("w52_high"),
            "w52_low":          yf.get("w52_low"),
            "analyst_target":   yf.get("analyst_target"),
            "analyst_consenso": yf.get("analyst_consenso"),
            "pe_ttm":           yf.get("pe_ttm"),
        },
        "ratios": {
            "beta":        yf.get("beta"),
            "pe_forward":  yf.get("pe_forward"),
            "margen_bruto": margen_bruto,
            "margen_op":   margen_op,
            "margen_neto": margen_neto,
        },
    }
    if errors:
        result["errors"] = errors

    icon = "✅" if status == "ok" else ("⚠️ " if status == "partial" else "❌")
    warn_str = ", ".join(warnings) if warnings else "—"
    print(f"  {icon} cov={coverage_pct}%  rev={fmt_b(revenue)}  warns=[{warn_str}]")

    return result


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description=f"Feroldi Batch Recolectar v{VERSION} — stress-test 50 tickers"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo corre los primeros 5 tickers (prueba rápida)")
    parser.add_argument("--sleep", type=float, default=SLEEP_SEC,
                        help=f"Segundos entre tickers (default: {SLEEP_SEC})")
    args = parser.parse_args()

    tickers = ALL_TICKERS[:5] if args.dry_run else ALL_TICKERS

    print(f"\n{'='*62}")
    print(f"  FEROLDI BATCH RECOLECTAR v{VERSION}")
    print(f"  {TODAY}  ·  {len(tickers)} tickers")
    if args.dry_run:
        print(f"  ⚡ DRY-RUN — solo primeros 5 tickers")
    else:
        print(f"  ⏱  ~{int(len(tickers) * args.sleep / 60)} min estimados")
    print(f"  Fuentes: EDGAR (edgartools) + yfinance  [sin AV]")
    print(f"  Output:  {OUTPUT_DIR}")
    print(f"{'='*62}\n")

    batch = {
        "meta": {
            "batch_version":    VERSION,
            "fecha":            TODAY,
            "tickers_total":    len(tickers),
            "tickers_ok":       0,
            "tickers_partial":  0,
            "tickers_error":    0,
            "dry_run":          args.dry_run,
            "fuentes":          ["EDGAR (edgartools)", "yfinance"],
        },
        "tickers": {},
        "resumen": {},
    }

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:02d}/{len(tickers)}] {ticker}:", end="  ", flush=True)
        try:
            result = recolectar_uno(ticker)
            batch["tickers"][ticker] = result

            s = result["status"]
            if   s == "ok":      batch["meta"]["tickers_ok"]     += 1
            elif s == "partial": batch["meta"]["tickers_partial"] += 1
            else:                batch["meta"]["tickers_error"]   += 1

        except Exception as e:
            batch["tickers"][ticker] = {
                "status":   "error",
                "warnings": ["UNEXPECTED_ERROR"],
                "errors":   {"unexpected": str(e)},
            }
            batch["meta"]["tickers_error"] += 1
            print(f"  ❌ Error inesperado: {e}")

        if i < len(tickers):
            time.sleep(args.sleep)

    # ── RESUMEN ANALÍTICO ─────────────────────────────────────────────────────
    all_warnings  = {}
    coverage_map  = {}
    for t, r in batch["tickers"].items():
        for w in r.get("warnings", []):
            all_warnings.setdefault(w, []).append(t)
        coverage_map[t] = r.get("coverage_pct", 0)

    filing_types = {}
    for t, r in batch["tickers"].items():
        ft = r.get("filing_type", "unknown")
        filing_types.setdefault(ft, []).append(t)

    batch["resumen"] = {
        "warnings_por_tipo": {
            w: {"count": len(ts), "tickers": ts}
            for w, ts in sorted(all_warnings.items(), key=lambda x: -len(x[1]))
        },
        "filing_types": {
            ft: {"count": len(ts), "tickers": ts}
            for ft, ts in filing_types.items()
        },
        "cobertura_promedio_pct": (
            int(sum(coverage_map.values()) / len(coverage_map))
            if coverage_map else 0
        ),
        "tickers_cobertura_baja":  [t for t, c in coverage_map.items() if c < 50],
        "tickers_sin_warnings":    [t for t, r in batch["tickers"].items()
                                    if not r.get("warnings")],
        "tickers_total_failure":   [t for t, r in batch["tickers"].items()
                                    if r.get("status") == "error"],
    }

    # ── GUARDAR JSON ──────────────────────────────────────────────────────────
    suffix = "_DRYRUN" if args.dry_run else ""
    fname  = os.path.join(OUTPUT_DIR,
                          f"batch_datos{suffix}_{TODAY.replace('-','')}.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2, default=str)

    # ── REPORTE FINAL ─────────────────────────────────────────────────────────
    m = batch["meta"]
    r = batch["resumen"]
    print(f"\n{'='*62}")
    print(f"  ✅ BATCH COMPLETADO — v{VERSION}")
    print(f"  OK: {m['tickers_ok']}  "
          f"Parcial: {m['tickers_partial']}  "
          f"Error: {m['tickers_error']}")
    print(f"  Cobertura promedio: {r['cobertura_promedio_pct']}%")

    print(f"\n  WARNINGS detectados ({len(r['warnings_por_tipo'])} tipos):")
    for w, info in r["warnings_por_tipo"].items():
        tlist   = info["tickers"]
        preview = ", ".join(tlist[:6])
        more    = f" +{len(tlist)-6}más" if len(tlist) > 6 else ""
        print(f"    {w:<38} {info['count']:>2}  → {preview}{more}")

    print(f"\n  FILING TYPES:")
    for ft, info in r["filing_types"].items():
        print(f"    {ft or 'unknown':<10} {info['count']:>2}  → {', '.join(info['tickers'])}")

    if r["tickers_cobertura_baja"]:
        print(f"\n  ⚠ Cobertura <50%: {', '.join(r['tickers_cobertura_baja'])}")
    if r["tickers_total_failure"]:
        print(f"  ❌ Falló totalmente: {', '.join(r['tickers_total_failure'])}")
    if r["tickers_sin_warnings"]:
        print(f"  ✓ Sin warnings: {', '.join(r['tickers_sin_warnings'])}")

    print(f"\n  Archivo: {fname}")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    main()
