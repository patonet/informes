#!/usr/bin/env python3
"""
FEROLDI RECOLECTAR — v X0.82
Sistema Feroldi · @patonet
  Sistema: X0.82 (release actual)
  Archivo: X0.82 (última modificación en este release)

CAMBIOS X0.77 vs X0.76:
  [FIX 1]   Option C: resolución de tickers numéricos (HKEX/China) — X0.77
            · _is_numeric_ticker(): detecta tickers puramente numéricos (1398, 0805)
            · _resolve_edgar_company(): para numéricos, obtiene nombre real vía
              yfinance y busca en EDGAR por nombre (edgar_find) en lugar de usar
              Company(ticker) que interpreta el número como CIK → datos falsos
            · Si no hay match EDGAR: CIK=N/D, nombre de yfinance, return temprano
            · get_edgar_edgartools() reemplaza Company(ticker.upper()) directo
              por _resolve_edgar_company() con lógica de early return para numéricos
  [FIX 2]   40-F support en extract_segments_edgartools() — X0.77
            · Agrega fallback a form="40-F" (amendments=False y con amendments)
              para filers canadienses: BN, BNS, CM, CNQ, AEM y otros
            · También usa _resolve_edgar_company() en lugar de Company(ticker)
              directo, evitando CIK falso para tickers numéricos en esta función
  [FIX 3]   Sanity check "Entity NNN" en get_edgar_edgartools() — X0.77
            · Detecta nombres genéricos tipo "Entity 805" que señalan CIK erróneo
            · Log de advertencia: no bloquea el pipeline, solo advierte
            · result["cik_sanity_warning"] = True para rastreo downstream
  [FIX 4]   already_done() sin glob de dos niveles — en feroldi_batch_corrida.py
            · glob con wildcard en subdirectorios falla silenciosamente bajo
              macOS TCC restriction en contexto de subprocess
            · Reemplazado por os.listdir() explícito sobre DOWNLOADS buscando
              directorios CORRIDA_*_FEROLDI, luego listdir() dentro de cada uno

CAMBIOS X0.75 vs X0.74:
  [NUEVO]   Guard None en cashflow_statement() y balance_sheet() (X0.75)
            · VALE y otros 20-F IFRS retornan None en cashflow_statement()
            · Sin este fix, la excepción interrumpía el pipeline ANTES de
              llegar a extract_segments_edgartools() → segmentos = null
            · Ahora raw_cf=[] y raw_bs=[] cuando el statement no existe,
              el pipeline continúa y los segmentos se extraen correctamente
            · Impacto: VALE pasa de 0 segmentos a 6 correctos

CAMBIOS X0.74 vs X0.73:
  [NUEVO]   amendments=False en get_filings() — SHOP usaba 10-K/A (amended) que
            carecía de XBRL dimensional. Ahora preferimos el 10-K original.
  [NUEVO]   ifrs-full_ProductsAndServicesAxis en AXIS_PRIORITY — VALE y otros
            filers IFRS reportan por producto en este eje (antes no estaba listado).
  [NUEVO]   Coverage cap 3.0x para ifrs-full_SegmentsAxis — bancos IFRS (HSBC)
            reportan revenue bruto por segmento que supera el Net Interest Income.
  [NUEVO]   ifrs-full_RevenueAndOperatingIncome como concepto de revenue
            (HSBC reporta segmentos en este concepto, no en ifrs-full_Revenue).
  [NUEVO]   Limpieza " [member]" de nombres IFRS (NVS: "Entresto [member]" → "Entresto").
  [NUEVO]   "Reportable segments [member]" → genérico (NU single-segment fallback).
  [NUEVO]   _detect_edgar_currency mejorado: detecta ARS vía BS cuando income
            stmt solo tiene EPS. Fix bug para LOMA (ARS reportado como USD en yfinance).
  [NUEVO]   Heurística revenue/mktcap>50 → detect moneda local (LOMA fix).
======================================
Recolecta datos financieros con jerarquía de fuentes:
  TIER 1 — Alpha Vantage  (ratios, métricas, earnings, analistas)
  TIER 2 — EDGAR edgartools (SBC, goodwill, deuda, cash, segmentos XBRL)
  TIER 3 — TradingView    (performance histórica)
  TIER 4 — yfinance        (auditoría silenciosa siempre activa)

CAMBIOS X0.72 vs X0.68:
  [NUEVO]   FX conversion en segmentos (X0.72) — sin este fix valores en JPY/TWD
            · edgar.segmentos[].revenue ahora se convierte × fx_rate igual que
              los campos escalares (revenue, fcf, etc.)
            · Sin X0.72: TSM/TM mostraban segmentos en miles de millones de JPY
              en el Sankey en vez de USD
  [NUEVO]   Fix 20-F en extract_segments_edgartools() (X0.71) — root cause real
            · TM/NVO/SAP/TSM presentan 20-F ante la SEC, no 10-K
            · get_filings(form="10-K") retornaba None → segmentos siempre null
            · Ahora fallback a 20-F si no hay 10-K
            · Soluciona: Toyota mostraba 1 segmento (consolidado) en lugar de
              sus segmentos reales (Automotive, Financial Services, etc.)
  [NUEVO]   Ejes IFRS en AXIS_PRIORITY y REVENUE_CONCEPTS_SEG (X0.70)
            · ifrs-full_SegmentsAxis, ifrs-full_ProductsAndServicesAxis
            · ifrs-full_Revenue, ifrs-full_RevenueFromContractsWithCustomers

CAMBIOS X0.68 vs X0.61:
  [NUEVO]   FX dinámico en pipeline individual — porta arquitectura de X0.67
            · Detecta moneda de reporte XBRL desde datos edgartools (campo unit)
            · Si EDGAR reporta en moneda local (TWD, EUR, etc.), convierte a USD
            · Tasa en tiempo real via yfinance → fallback tabla hardcoded
            · fx_info en meta del JSON de salida (par, rate, date, 🟢/🟡 tag)
            · Cache de sesión _FX_CACHE para evitar llamadas duplicadas
            · Soluciona: sin X0.68, un TSM con AV caído y EDGAR en TWD
              producía revenue ~32x inflado en el Sankey sin advertencia

CAMBIOS X0.61 vs X0.58:
  [NUEVO]   TIER 4 = yfinance — auditoría silenciosa siempre activa
            · Compara TODOS los campos contra EDGAR+AV
            · Categorías por campo: match / disagree / filled / null
            · Solo se USAN fills (campos que eran null en TIER 1+2+3)
            · audit completo en meta.tier4_audit del JSON de salida
            · Log persistente ~/Downloads/tier4_audit_log.jsonl (una línea por corrida)
  [NUEVO]   Flag --no-yfinance para deshabilitar TIER 4

USO:
  export AV_API_KEY="tu_key"  (o AV_API_KEY_2, AV_API_KEY_3, AV_API_KEY_4 para fallback)
  python3 feroldi_recolectar.py FSLY 31.60
  python3 feroldi_recolectar.py FSLY 31.60 --no-yfinance

INSTALAR (una sola vez):
  pip3 install aiohttp requests edgartools yfinance
"""

import asyncio
import aiohttp
import argparse
import json
import re
import sys
import os
from datetime import datetime
from itertools import combinations
import traceback

from edgar import Company, set_identity

# ─── CONFIG ────────────────────────────────────────────────────────────────────
VERSION   = "X0.83"
UA        = "patonet@example.com"
set_identity(UA)

# Flag global — se setea en main() via --no-av para saltar Alpha Vantage en batch runs
_USE_AV = True

# Multi-key AV fallback (F2)
AV_KEYS = [
    os.environ.get("AV_API_KEY_1", os.environ.get("AV_API_KEY", "")),
    os.environ.get("AV_API_KEY_2", ""),
    os.environ.get("AV_API_KEY_3", ""),
    os.environ.get("AV_API_KEY_4", ""),
]
AV_KEYS = [k for k in AV_KEYS if k]
AV_BASE   = "https://www.alphavantage.co/query"
AV_SLEEP  = 12          # segundos entre calls AV
TV_HEADERS = {
    "Origin":       "https://www.tradingview.com",
    "Referer":      "https://www.tradingview.com/",
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0"
}
TODAY = datetime.now().strftime("%d-%m-%Y")
ND    = "N/D"

# ─── FX DINÁMICO — tasas en tiempo real vía yfinance (X0.68) ──────────────────
# Fallback de emergencia si yfinance no puede obtener la tasa
FX_FALLBACK_DATE = "2026-05-08"
FX_FALLBACK = {
    "TWD": 1/32.0,    # Taiwan Dollar
    "DKK": 1/6.85,    # Danish Krone
    "EUR": 1.08,      # Euro
    "GBP": 1.26,      # British Pound
    "CAD": 0.73,      # Canadian Dollar
    "CNY": 1/7.25,    # Chinese Yuan
    "HKD": 1/7.78,    # Hong Kong Dollar
    "JPY": 1/149.0,   # Japanese Yen
    "CHF": 1.11,      # Swiss Franc
    "SEK": 1/10.5,    # Swedish Krona
    "NOK": 1/10.8,    # Norwegian Krone
    "AUD": 0.65,      # Australian Dollar
    "INR": 1/83.5,    # Indian Rupee
    "KRW": 1/1330.0,  # South Korean Won
    "BRL": 1/5.10,    # Brazilian Real
    "ARS": 1/1400.0,  # Peso argentino (referencia — muy volátil, preferir live)
    "MXN": 1/17.5,    # Peso mexicano
    "CLP": 1/950.0,   # Peso chileno
    "COP": 1/4200.0,  # Peso colombiano
}

_FX_CACHE = {}   # cache de sesión: currency → (rate, pair, date)

# Sufijos de exchange para resolver tickers no-US (TSX, LSE, ASX, etc.)
_YF_EXCHANGE_SUFFIXES = [
    ".TO", ".V",   # Canadá (TSX, TSXV)
    ".L",          # Londres
    ".AX",         # Australia
    ".DE",         # Alemania (XETRA)
    ".PA",         # París
    ".MI",         # Milán
    ".AS",         # Ámsterdam
    ".MC",         # Madrid
    ".HK",         # Hong Kong
    ".T",          # Tokio
    ".KS",         # Corea del Sur
    ".NS", ".BO",  # India (NSE, BSE)
]

# Tipos de activo NO permitidos en el análisis Feroldi (solo EQUITY)
_INVALID_QUOTE_TYPES = {
    "ETF":            "ETF — Feroldi no analiza fondos indexados",
    "MUTUALFUND":     "Fondo de inversión — Feroldi no analiza fondos",
    "CRYPTOCURRENCY": "Criptomoneda — Feroldi solo analiza empresas cotizadas",
    "CURRENCY":       "Forex/divisa — Feroldi solo analiza empresas cotizadas",
    "INDEX":          "Índice bursátil — Feroldi solo analiza empresas cotizadas",
    "FUTURE":         "Futuro/derivado — Feroldi solo analiza empresas cotizadas",
    "OPTION":         "Opción financiera — Feroldi solo analiza empresas cotizadas",
}


def _validate_ticker_type(ticker: str) -> None:
    """
    Pre-flight: verifica que el ticker sea una empresa cotizada (EQUITY).
    Corre SIEMPRE, incluso con --no-yfinance (es un control de entrada, no un tier).
    Si el activo es inválido o el ticker no existe → sys.exit(1) con mensaje claro.
    Si yfinance no está disponible o hay error de red → continúa con advertencia.
    """
    import sys
    try:
        import yfinance as yf
    except ImportError:
        print("  ⚠ yfinance no disponible — validación de tipo de activo omitida")
        return

    print("🔍 Pre-flight: validando tipo de activo...")
    attempts = [ticker] + [ticker + s for s in _YF_EXCHANGE_SUFFIXES]
    found_info = None

    for t in attempts:
        try:
            info = yf.Ticker(t).info or {}
            # Un dict válido tiene al menos quoteType o shortName
            if info.get("quoteType") or info.get("shortName") or info.get("longName"):
                found_info = info
                break
        except Exception:
            continue

    # ── 1. Ticker no encontrado ───────────────────────────────────────────────
    if not found_info:
        msg = (
            f"❌ TICKER NO ENCONTRADO: '{ticker}'\n"
            f"   yfinance no retornó datos para este símbolo.\n"
            f"   Verificá que el ticker sea correcto (ej: AAPL, NKE, 0700.HK)."
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

    # ── 2. Tipo de activo no válido ───────────────────────────────────────────
    quote_type = (found_info.get("quoteType") or "").upper()
    if quote_type in _INVALID_QUOTE_TYPES:
        name = found_info.get("shortName") or found_info.get("longName") or ticker
        label = _INVALID_QUOTE_TYPES[quote_type]
        msg = (
            f"❌ ACTIVO NO VÁLIDO: {ticker} — \"{name}\"\n"
            f"   Tipo detectado: {label}.\n"
            f"   Feroldi solo analiza acciones individuales (EQUITY).\n"
            f"   Si querés analizar una empresa del índice, ingresá su ticker directo."
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

    # ── 3. quoteType vacío sin precio → ticker fantasma ───────────────────────
    if not quote_type and not found_info.get("regularMarketPrice"):
        msg = (
            f"❌ TICKER SIN DATOS DE MERCADO: '{ticker}'\n"
            f"   El símbolo existe pero no tiene precio de mercado activo.\n"
            f"   Puede estar delisted, pendiente de IPO, o ser un ticker inválido."
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

    # ── OK ────────────────────────────────────────────────────────────────────
    name = found_info.get("shortName") or found_info.get("longName") or ticker
    qt_display = quote_type or "EQUITY"
    print(f"  ✅ Activo válido: {ticker} — \"{name}\" [{qt_display}]\n")


def _resolve_yf_ticker(ticker):
    """
    Resuelve el ticker correcto para yfinance.
    Prueba bare ticker primero (US); si no tiene revenue, prueba sufijos
    de exchange en orden hasta encontrar uno con datos.
    Retorna (yf_ticker, currency_str).
    """
    try:
        import yfinance as yf
    except ImportError:
        return ticker, "USD"

    attempts = [ticker] + [ticker + s for s in _YF_EXCHANGE_SUFFIXES]
    for t in attempts:
        try:
            info = yf.Ticker(t).info or {}
            if info.get("totalRevenue"):
                currency = (info.get("currency") or "USD").upper()
                if t != ticker:
                    print(f"  🌐 yfinance: ticker resuelto {ticker} → {t} ({currency})")
                return t, currency
        except Exception:
            continue
    return ticker, "USD"


def get_fx_rate(currency):
    """
    Retorna (rate_usd, pair_str, date_str) para 1 unidad de la moneda dada.
    Intenta yfinance en tiempo real → fallback tabla hardcoded → (None, None, None).
    Cachea por sesión para evitar llamadas duplicadas.
    """
    if currency == "USD":
        return 1.0, "USD", datetime.now().strftime("%Y-%m-%d")
    if currency in _FX_CACHE:
        return _FX_CACHE[currency]
    pair = f"{currency}USD=X"
    try:
        import yfinance as yf
        t    = yf.Ticker(pair)
        info = t.info or {}
        rate = _float(info.get("regularMarketPrice") or info.get("price"))
        if rate and rate > 0:
            today  = datetime.now().strftime("%Y-%m-%d")
            result = (rate, pair, today)
            _FX_CACHE[currency] = result
            return result
    except Exception:
        pass
    rate_fb = FX_FALLBACK.get(currency)
    if rate_fb:
        result = (rate_fb, f"{currency}USD=FALLBACK", FX_FALLBACK_DATE)
        _FX_CACHE[currency] = result
        return result
    return None, None, None

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def fmt_b(v):
    if v is None: return ND
    try:
        v = float(v)
        if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
        elif abs(v) >= 1e6: return f"${v/1e6:.1f}M"
        else:               return f"${v:,.0f}"
    except: return ND

def _float(v):
    if v is None or v in ("None", "-", "", "N/A"): return None
    try:
        f = float(v)
        return None if f != f else f
    except: return None

def _int(v):
    if v is None or v in ("None", "-", "", "N/A"): return None
    try: return int(float(v))
    except: return None

def pick(*vals):
    for v in vals:
        if v is not None and v != ND: return v
    return None

def _extract_concept(raw, concept_name):
    """Extrae el valor FY más reciente de un concepto desde raw data XBRL.
    Maneja periodos 'duration' (income/cash flow) e 'instant' (balance sheet)."""
    for item in raw:
        if (item['concept'] == concept_name
                and not item.get('is_dimension')
                and item.get('has_values')):
            vals = item['values']
            fy_vals = {k: v for k, v in vals.items()
                       if 'duration' in k or 'instant' in k}
            if fy_vals:
                latest_key = max(fy_vals.keys())
                return fy_vals[latest_key]
    return None

def _extract_concept_label(raw, concept_name):
    """Extrae (valor, label) del concepto más reciente.
    Maneja periodos 'duration' e 'instant'."""
    for item in raw:
        if (item['concept'] == concept_name
                and not item.get('is_dimension')
                and item.get('has_values')):
            vals = item['values']
            fy_vals = {k: v for k, v in vals.items()
                       if 'duration' in k or 'instant' in k}
            if fy_vals:
                latest_key = max(fy_vals.keys())
                return fy_vals[latest_key], item.get('label', concept_name)
    return None, None


# ─── TIER 1: ALPHA VANTAGE ─────────────────────────────────────────────────────
async def get_alphavantage(ticker):
    """
    Obtiene ratios, métricas y EPS desde Alpha Vantage.
    Multi-key fallback automático (F2).
    Secuencial por rate limit (5 calls/min en free tier).
    """
    if not _USE_AV:
        print("  ⚠ Alpha Vantage deshabilitado (--no-av)")
        return {}, {}
    if not AV_KEYS:
        print("  ⚠ No hay AV_API_KEY configurada — saltando Alpha Vantage")
        print("    Configura: export AV_API_KEY='***'")
        return {}, {}

    async def av_call(function, api_key):
        params = {"function": function, "symbol": ticker, "apikey": api_key}
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as s:
                async with s.get(AV_BASE, params=params,
                                 timeout=aiohttp.ClientTimeout(total=20)) as r:
                    data = await r.json(content_type=None)
            if "Information" in data or "Note" in data:
                msg = data.get("Information") or data.get("Note", "")
                return {"_rate_limit": True, "_error": msg[:90]}
            if "Error Message" in data:
                return {"_error": data['Error Message'][:80]}
            return data
        except Exception as e:
            return {"_error": str(e)}

    # ── CALL 1: OVERVIEW ─────────────────────────────────────────────────────
    ov = None
    used_keys_ov = []
    print(f"  📡 AV OVERVIEW...")
    for key_idx, api_key in enumerate(AV_KEYS):
        result = await av_call("OVERVIEW", api_key)
        if isinstance(result, dict) and result.get("_rate_limit"):
            print(f"  ⚠ AV rate limit key[{key_idx+1}], probando siguiente...")
            used_keys_ov.append((key_idx, "rate_limit"))
            continue
        if isinstance(result, dict) and result.get("_error"):
            print(f"  ⚠ AV error key[{key_idx+1}]: {result['_error']}")
            used_keys_ov.append((key_idx, "error"))
            continue
        if result and "Symbol" in result:
            ov = result
            used_keys_ov.append((key_idx, "ok"))
            break
        used_keys_ov.append((key_idx, "no_data"))

    await asyncio.sleep(AV_SLEEP)

    # ── CALL 2: EARNINGS ─────────────────────────────────────────────────────
    earn = None
    used_keys_earn = []
    print(f"  📡 AV EARNINGS...")
    for key_idx, api_key in enumerate(AV_KEYS):
        result = await av_call("EARNINGS", api_key)
        if isinstance(result, dict) and result.get("_rate_limit"):
            print(f"  ⚠ AV rate limit key[{key_idx+1}], probando siguiente...")
            used_keys_earn.append((key_idx, "rate_limit"))
            continue
        if isinstance(result, dict) and result.get("_error"):
            used_keys_earn.append((key_idx, "error"))
            continue
        if result and "annualEarnings" in result:
            earn = result
            used_keys_earn.append((key_idx, "ok"))
            break
        used_keys_earn.append((key_idx, "no_data"))

    # ── PROCESAR OVERVIEW ─────────────────────────────────────────────────────
    result_ov = {}
    if ov and "Symbol" in ov:
        gp_ttm  = _float(ov.get("GrossProfitTTM")) or 0
        rev_ttm = _float(ov.get("RevenueTTM")) or 1
        gm_calc = (gp_ttm / rev_ttm) if rev_ttm else None

        result_ov = {
            "market_cap":        _float(ov.get("MarketCapitalization")),
            "w52_high":          _float(ov.get("52WeekHigh")),
            "w52_low":           _float(ov.get("52WeekLow")),
            "shares_av":         _int(ov.get("SharesOutstanding")),
            "percent_insiders":  _float(ov.get("PercentInsiders")),
            "pe_ttm":            _float(ov.get("PERatio")),
            "pe_forward":        _float(ov.get("ForwardPE")),
            "peg":               _float(ov.get("PEGRatio")),
            "ev_ebitda":         _float(ov.get("EVToEBITDA")),
            "ev_revenue":        _float(ov.get("EVToRevenue")),
            "pb":                _float(ov.get("PriceToBookRatio")),
            "p_sales":           _float(ov.get("PriceToSalesRatioTTM")),
            "eps_ttm":           _float(ov.get("DilutedEPSTTM")),
            "margen_bruto":      gm_calc,
            "margen_op":         _float(ov.get("OperatingMarginTTM")),
            "margen_neto":       _float(ov.get("ProfitMargin")),
            "roe":               _float(ov.get("ReturnOnEquityTTM")),
            "roa":               _float(ov.get("ReturnOnAssetsTTM")),
            "beta":              _float(ov.get("Beta")),
            "dividend_yield":    _float(ov.get("DividendYield")),
            "revenue_yoy_q":     _float(ov.get("QuarterlyRevenueGrowthYOY")),
            "earnings_yoy_q":    _float(ov.get("QuarterlyEarningsGrowthYOY")),
            "analyst_target":       _float(ov.get("AnalystTargetPrice")),
            "analyst_strong_buy":   _int(ov.get("AnalystRatingStrongBuy")),
            "analyst_buy":          _int(ov.get("AnalystRatingBuy")),
            "analyst_hold":         _int(ov.get("AnalystRatingHold")),
            "analyst_sell":         _int(ov.get("AnalystRatingSell")),
            "analyst_strong_sell":  _int(ov.get("AnalystRatingStrongSell")),
            "exchange":         ov.get("Exchange"),
            "sector":           ov.get("Sector"),
            "industry":         ov.get("Industry"),
            "latest_quarter":   ov.get("LatestQuarter"),
            "ebitda_ttm":       _float(ov.get("EBITDA")),
        }
        ok_count = sum(1 for v in result_ov.values() if v is not None)
        print(f"  ✓ AV OVERVIEW — {ok_count}/{len(result_ov)} campos resueltos")
    else:
        print(f"  ⚠ AV OVERVIEW: sin datos para {ticker}")

    # ── PROCESAR EARNINGS ────────────────────────────────────────────────────
    result_earn = {"annual_eps": [], "quarterly_eps": []}
    if earn:
        for ae in earn.get("annualEarnings", []):
            fy = ae.get("fiscalYearEnding", ae.get("fiscalDateEnding", ""))
            eps = _float(ae.get("reportedEPS"))
            if fy and eps is not None:
                result_earn["annual_eps"].append({"fy": fy[:4], "eps": round(eps, 4)})
        for qe in earn.get("quarterlyEarnings", []):
            fecha = qe.get("fiscalDateEnding", "")
            reported = _float(qe.get("reportedEPS"))
            estimated = _float(qe.get("estimatedEPS"))
            surprise = _float(qe.get("surprise"))
            report_date = qe.get("reportDate", "")
            entry = {"fecha": fecha}
            if reported is not None:
                entry["reported"] = round(reported, 4)
            if estimated is not None:
                entry["estimated"] = round(estimated, 4)
            if surprise is not None:
                entry["surprise_pct"] = round(surprise, 4)
            if report_date:
                entry["report_date"] = report_date
            if len(entry) > 1:
                result_earn["quarterly_eps"].append(entry)
        print(f"  ✓ AV EARNINGS — {len(result_earn['annual_eps'])} años · {len(result_earn['quarterly_eps'])} trimestres")
    else:
        print(f"  ⚠ AV EARNINGS: sin datos para {ticker}")

    return result_ov, result_earn


# ─── TIER 2: EDGAR via edgartools ──────────────────────────────────────────────

# ─── OPTION C: resolución de tickers numéricos (HK, China) ─────────────────────
def _is_numeric_ticker(ticker):
    """Detecta tickers puramente numéricos (HKEX: 1398, 0805, etc.)."""
    return ticker.replace(".", "").isdigit()


def _resolve_edgar_company(ticker):
    """
    Resuelve el Company de edgartools para cualquier ticker.
    Para tickers numéricos (HK): evita el falso CIK — busca por nombre real.
    Retorna (company_or_None, resolved_by_name: bool).
    """
    if not _is_numeric_ticker(ticker):
        try:
            return Company(ticker.upper()), False
        except Exception:
            return None, False

    # Ticker numérico → evitar Company(ticker) que usaría el número como CIK
    # Paso 1: obtener nombre real via yfinance
    real_name = None
    try:
        import yfinance as yf
        for suffix in ["", ".HK", ".SS", ".SZ"]:
            try:
                info = yf.Ticker(ticker + suffix).info or {}
                real_name = info.get("longName") or info.get("shortName")
                if real_name:
                    print(f"  🔍 Ticker numérico {ticker}: yfinance name = '{real_name}'")
                    break
            except Exception:
                continue
    except ImportError:
        pass

    if not real_name:
        print(f"  ⚠ Ticker numérico {ticker}: sin nombre en yfinance — CIK=N/D")
        return None, False

    # Paso 2: buscar en EDGAR por nombre con validación estricta de similitud
    # Score mínimo 80 + difflib para evitar falsos positivos (ICBC→CM score=60,
    # Ping An→Reinsurance Group score=70 → ambos rechazados correctamente).
    try:
        from edgar import find as edgar_find
        from difflib import SequenceMatcher
        results = edgar_find(real_name)
        df = getattr(results, "results", None)
        if df is not None and not df.empty:
            top = df.iloc[0]
            top_score = float(top.get("score", 0))
            top_name  = str(top.get("company", ""))
            # Similitud de cadena entre el nombre buscado y el encontrado
            _sim = SequenceMatcher(None,
                                   real_name.lower().strip(),
                                   top_name.lower().strip()).ratio()
            if top_score >= 80 and _sim >= 0.50:
                best_cik = str(top["cik"])
                company  = Company(best_cik)
                print(f"  ✅ Ticker numérico {ticker} → EDGAR CIK={best_cik} "
                      f"({company.name}) [score={top_score:.0f}, sim={_sim:.2f}]")
                return company, True
            else:
                print(f"  ⚠ EDGAR match rechazado: '{top_name}' "
                      f"[score={top_score:.0f}<80 o sim={_sim:.2f}<0.50]")
    except Exception as e:
        print(f"  ⚠ EDGAR name search falló para '{real_name}': {e}")

    # Paso 3: sin match EDGAR → no usar Company(ticker) para evitar datos falsos
    print(f"  ⚠ Ticker numérico {ticker} ('{real_name}'): sin CIK en EDGAR — CIK=N/D")
    return None, False


def _extract_income_stmt_segs(ticker, total_revenue):
    """
    Fallback para empresas que reportan revenue por tipo de servicio/producto
    como conceptos propietarios en el income statement (ej. MCD usa mcd_* concepts)
    en lugar de ejes XBRL dimensionales estándar.

    Solo aplica cuando no hay ProductOrServiceAxis dimensional data.
    Requiere ≥2 segmentos que sumen ≈ total_revenue (±10%).
    """
    if not total_revenue:
        return None
    try:
        company = Company(ticker.upper())
        fin = company.get_financials()
        if not fin:
            return None
        raw = fin.income_statement().get_raw_data()
    except Exception:
        return None

    SKIP_CONCEPTS = {
        "us-gaap_Revenues",
        "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax",
        "us-gaap_SalesRevenueNet",
    }
    REVENUE_KEYWORDS = ["revenue", "sales", "fees", "royalt", "service", "product"]
    EXCLUDE_KEYWORDS = ["cost", "expense", "occupancy", "deprec", "amort", "impair",
                        "interest", "tax", "income", "loss", "profit", "margin"]

    candidates = []
    for item in raw:
        if item.get("is_dimension"):
            continue
        concept = item.get("concept", "")
        if concept in SKIP_CONCEPTS:
            continue
        concept_lower = concept.lower()
        if not any(kw in concept_lower for kw in REVENUE_KEYWORDS):
            continue
        if any(kw in concept_lower for kw in EXCLUDE_KEYWORDS):
            continue
        vals = item.get("values", {})
        fy_vals = {k: v for k, v in vals.items() if "duration" in k}
        if not fy_vals:
            continue
        val = fy_vals[max(fy_vals.keys())]
        if val <= 0:
            continue
        label = item.get("label") or concept.split("_", 1)[-1]
        candidates.append({"nombre": label, "revenue": int(val)})

    if len(candidates) < 2:
        return None

    total = sum(c["revenue"] for c in candidates)
    if not (total_revenue * 0.88 <= total <= total_revenue * 1.12):
        return None

    candidates.sort(key=lambda x: x["revenue"], reverse=True)
    return candidates


def extract_segments_edgartools(ticker, total_revenue=None):
    """
    Extrae segmentos de revenue desde XBRL dimensional via edgartools.
    X0.58: devuelve datos CRUDOS de todos los ejes disponibles.
    La limpieza (parent detection, agrupación, geo vs producto)
    es responsabilidad de feroldi_normalizar.py.

    Retorna: dict con {axis_name: [{nombre, revenue}, ...]} o None
    El primer eje que tenga datos con cobertura razonable se usa como primario.
    """
    try:
        # X0.77: _resolve_edgar_company evita CIK falso para tickers numéricos (HK)
        company, _ = _resolve_edgar_company(ticker)
        if company is None:
            return None  # Ticker numérico sin CIK EDGAR real → sin segmentos XBRL

        # X0.74: amendments=False — el 10-K/A (amended filing) puede carecer de
        # XBRL dimensional completo. Preferir siempre el 10-K original.
        # X0.77: Se prueba cada forma de filing Y su XBRL antes de pasar al siguiente.
        # BN (Brookfield) tiene un 20-F de 2002 sin XBRL — el código anterior
        # encontraba ese filing y retornaba None sin intentar el 40-F (que sí tiene XBRL).
        # Ahora: si un filing no tiene XBRL, se continúa con el siguiente tipo.
        # Orden: 10-K (no amended) → 10-K → 20-F (no amended) → 20-F → 40-F (no amended) → 40-F
        xbrl = None
        for _form, _amend in [("10-K", False), ("10-K", True),
                               ("20-F", False), ("20-F", True),
                               ("40-F", False), ("40-F", True)]:
            try:
                _filings = company.get_filings(form=_form,
                                               amendments=False if not _amend else True)
                _filing = _filings.latest() if _filings else None
                if not _filing:
                    continue
                _xbrl = _filing.xbrl()
                if _xbrl:
                    xbrl = _xbrl
                    break
            except Exception:
                continue
        if not xbrl:
            return None
    except Exception:
        return None

    GEO_KEYWORDS = ["north america", "international", "europe", "asia",
                    "pacific", "latin america", "emea", "apac",
                    "domestic", "foreign", "united states",
                    "rest of world", "global", "americas",
                    "china", "japan", "canada", "korea", "india",
                    "brazil", "germany", "france", "united kingdom",
                    "middle east", "africa", "australia", "mexico"]

    def _is_geographic(labels):
        """Detecta si los segmentos son geográficos por palabras clave."""
        geo_count = sum(1 for lb in labels if any(kw in lb.lower() for kw in GEO_KEYWORDS))
        return geo_count >= len(labels) * 0.5  # ≥50% de labels son geográficos

    # BUG-R4 X0.594: business segments > product/service > consolidation
    # StatementBusinessSegmentsAxis son los segmentos reportables oficiales del 10-K.
    # Si dan segmentos geográficos (ej. AAPL: Americas, Europe...), el filtro geo
    # los descarta y se usa ProductOrServiceAxis automáticamente.
    # X0.69: agrega equivalentes IFRS para filers 20-F (TM, TSM, NVO, SAP, etc.)
    AXIS_PRIORITY = {
        # US-GAAP — segmentos de negocio/producto (máxima prioridad)
        "StatementBusinessSegmentsAxis":                     0,
        "ProductOrServiceAxis":                              1,
        "ConsolidationItemsAxis":                            2,
        # Con prefijo srt_ (algunas empresas usan namespace completo)
        "srt_StatementBusinessSegmentsAxis":                 0,
        "srt_ProductOrServiceAxis":                          1,
        # IFRS equivalentes (ifrs-full_*) — filers 20-F
        # X0.74: ifrs-full_ProductsAndServicesAxis agregado (VALE, WIT, INFY, etc.)
        "ifrs-full_SegmentsAxis":                            0,
        "ifrs-full_ProductsAndServicesAxis":                 1,
        # Variantes de nombre con guión vs guión-bajo (edgartools usa ambas)
        "ifrs-full_ClassesOfIntangibleAssetsOtherThanGoodwillAxis": 5,
        # Geográficos — prioridad MUY BAJA (solo si no hay nada más)
        # X0.73: los geográficos producen desglose menos informativo y
        # se mezclan con ejes de producto causando doble conteo (SBUX, MELI)
        "StatementGeographicalAxis":                         10,
        "srt_StatementGeographicalAxis":                     10,
        "ifrs-full_GeographicalAreasAxis":                   10,
    }
    # Conceptos revenue en orden de preferencia (US-GAAP e IFRS)
    REVENUE_CONCEPTS_SEG = [
        # US-GAAP
        "Revenues", "Revenue",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "RevenuesNetOfInterestExpense",         # bancos (JPM, BAC, etc.) X0.73
        "InterestAndFeeIncomeLoansAndLeases",   # bancos alt
        # IFRS (filers 20-F: NVO, TSM, SAP, INFY, VALE, BABA, NIO, etc.)
        "ifrs-full_Revenue",
        "ifrs-full_RevenueFromContractsWithCustomers",
        # X0.74: bancos IFRS (HSBC, ITUB) — Revenue and Operating Income por segmento
        "ifrs-full_RevenueAndOperatingIncome",
    ]
    axes = list(AXIS_PRIORITY.keys())
    candidates = []

    for axis in axes:
        result = None
        for concept in REVENUE_CONCEPTS_SEG:
            try:
                df = (xbrl.facts.query()
                      .by_concept(concept)
                      .by_dimension(axis)
                      .to_dataframe())
                if not df.empty:
                    result = df
                    break
            except Exception:
                continue
        if result is None:
            continue

        latest_year = result["fiscal_year"].max()
        fy = result[(result["fiscal_year"] == latest_year) & (result["fiscal_period"] == "FY")].copy()
        if fy.empty:
            continue

        max_per = (fy.groupby("label")["numeric_value"]
                   .max().reset_index()
                   .sort_values("numeric_value", ascending=False))
        max_per = max_per[max_per["numeric_value"] > 0]
        if max_per.empty:
            continue

        # Parent detection combinatorio + heurística adicional (BUG-R1 X0.57)
        all_values = [r.numeric_value for r in list(max_per.itertuples())]
        total_sum_all = sum(all_values)
        parents = set()

        # Solo buscar padres si hay doble conteo real (suma > 115% revenue).
        # Si suma ≈ revenue, todos son hojas independientes (ej. MCD: U.S.+IOM+IDLM).
        vals = list(max_per.itertuples())
        # Solo buscar padres si hay doble conteo real (suma > 115% revenue).
        # Si suma ≈ revenue, todos son hojas independientes (ej. MCD: U.S.+IOM+IDLM).
        if not total_revenue or total_sum_all > total_revenue * 1.15:
            for i, row in enumerate(vals):
                # 1) Valor > revenue total × 1.05 → definitivamente padre (SAP, etc.) X0.73
                if total_revenue and row.numeric_value > total_revenue * 1.05:
                    parents.add(row.label)
                    continue
                # 2) Valor ≈ revenue total → consolidado, es padre
                if total_revenue and abs(row.numeric_value - total_revenue) / total_revenue < 0.05:
                    parents.add(row.label)
                    continue
                # 3) Heurística: valor > 40% revenue Y hijo más grande ≥35% → padre
                #    X0.73: umbral bajado de 0.55 a 0.35 (captura BRK-B Insurance)
                #    X0.74: añadir condición que sum(menores) ≈ valor (±20%)
                #    Sin esta condición, segmentos paralelos grandes (HSBC: CIB ≈ HK+IWPB+UK)
                #    se marcan incorrectamente como padres.
                if total_revenue and row.numeric_value > total_revenue * 0.40:
                    menores = [r.numeric_value for j, r in enumerate(vals)
                               if j != i and r.numeric_value < row.numeric_value]
                    if menores and max(menores) / row.numeric_value >= 0.35:
                        sum_menores = sum(menores)
                        # Solo es padre si los menores suman aproximadamente al valor (±10%)
                        # Umbral estricto para evitar falsos positivos en banks/IFRS (HSBC: CIB no es padre)
                        if abs(sum_menores - row.numeric_value) / row.numeric_value <= 0.10:
                            parents.add(row.label)
                            continue
                # 4) Near-duplicate: si dos segmentos tienen valores dentro del 5%
                #    entre sí, el mayor es padre del menor (BRK-B: InsuranceCorp vs InsuranceGroup)
                #    X0.74: solo activar si hay exactamente UNO en rango (no múltiples similares)
                #    X0.76: guard de similitud de nombre — solo disparar si comparten al menos
                #    una palabra significativa (evita "Iron Ore Pellets" ≈ "Nickel And Other Products")
                #    BRK-B: "Insurance Corp" / "Insurance Group" → comparten "insurance" → OK
                #    VALE: "Iron Ore Pellets" / "Nickel And Other Products" → sin palabras comunes → SKIP
                _ND_STOPWORDS = {"and", "the", "of", "in", "or", "for", "to", "a", "an",
                                 "inc", "ltd", "corp", "other", "total", "segment", "segments"}
                _nd_similar = [j for j, other in enumerate(vals)
                               if j != i
                               and other.numeric_value < row.numeric_value
                               and other.numeric_value / row.numeric_value >= 0.95]
                if len(_nd_similar) == 1:
                    # Guard: nombres deben compartir al menos 1 palabra significativa
                    _other_lbl = vals[_nd_similar[0]].label.lower().replace(',', '').replace('&', '')
                    _self_lbl  = row.label.lower().replace(',', '').replace('&', '')
                    _words_self  = {w for w in _self_lbl.split()  if len(w) > 2 and w not in _ND_STOPWORDS}
                    _words_other = {w for w in _other_lbl.split() if len(w) > 2 and w not in _ND_STOPWORDS}
                    if _words_self & _words_other:   # al menos 1 palabra en común
                        parents.add(row.label)
                        break
                if row.label in parents:
                    continue
                # 5) Detección combinatoria (umbral max_child bajado 0.55→0.35)
                # X0.76: tolerancia 5%→3% + cov_ratio dinámico
                # - Tolerancia 3% evita falsos positivos por coincidencias accidentales
                #   (VALE: Nickel $4.29B ≈ Copper $3.75B + OtherFerrous $0.72B = $4.47B a 4.2% → no es padre)
                # - Para match muy exacto (<2%): req_cov=0.50 en lugar de 0.65
                #   (VALE: ETM $8.27B = Nickel+Copper+Other a 1.5%, cov_ratio=0.608 < 0.65 → no detectable antes)
                for n in range(2, min(5, len(vals))):
                    for combo in combinations(
                        [r.numeric_value for j, r in enumerate(vals) if j != i], n
                    ):
                        match_sum = sum(combo)
                        _tol = abs(match_sum - row.numeric_value) / row.numeric_value
                        if _tol < 0.03:   # X0.76: 5% → 3%
                            max_child = max(combo)
                            all_smaller = [v for v in all_values if v != row.numeric_value and v < row.numeric_value]
                            sum_smaller = sum(all_smaller) if all_smaller else row.numeric_value
                            cov_ratio = match_sum / sum_smaller
                            # Umbral dinámico: match muy exacto → menos exigente en cobertura
                            _req_cov = 0.50 if _tol < 0.02 else 0.65
                            if max_child / row.numeric_value >= 0.35 and cov_ratio >= _req_cov:
                                parents.add(row.label)
                            break
                    if row.label in parents:
                        break

        hojas = max_per[~max_per["label"].isin(parents)]
        resultado = [
            {"nombre": r.label, "revenue": int(r.numeric_value)}
            for r in hojas.itertuples()
        ]
        if not resultado:
            continue

        is_geo = _is_geographic([s["nombre"] for s in resultado])
        suma = sum(s["revenue"] for s in resultado)
        coverage = (suma / total_revenue) if total_revenue else 0
        candidates.append((resultado, suma, is_geo, coverage, axis))

    if not candidates:
        # Sin dimensional data — intentar fallback de income statement
        line_segs = _extract_income_stmt_segs(ticker, total_revenue)
        return line_segs if (line_segs and len(line_segs) >= 2) else None

    # Filtrar: cobertura ≥30% si no-geográfico, ≥80% si geográfico.
    # X0.73: upper bound bajado de 2.00 → 1.15 para descartar ejes con doble conteo severo
    # (SBUX mezclaba ProductAxis + ChannelAxis → suma >120%)
    # X0.74: bancos IFRS (ifrs-full_SegmentsAxis) reportan revenue bruto por segmento
    # que puede superar el Net Interest Income del income statement hasta 3x.
    # Usar coverage cap más generoso para ejes de negocio IFRS.
    _GENEROUS_COVERAGE_AXES = {"ifrs-full_SegmentsAxis"}
    good = []
    for c in candidates:
        if not c[1] or not total_revenue:
            continue
        min_cov = 0.30 if not c[2] else 0.80
        # X0.74: eje IFRS de negocio → up-bound 3.0x para capturar bancos (HSBC, ITUB)
        max_cov = 3.0 if (c[4] in _GENEROUS_COVERAGE_AXES and not c[2]) else 1.15
        if min_cov <= c[3] <= max_cov:
            good.append(c)
    if not good:
        good = candidates  # si ninguno pasa, usar todos

    # X0.73: nombres genéricos no aportan info → filtrarlos y activar fallback
    # "Reportable Segment" (CELH), "Restaurants Segment" (WING), etc.
    # X0.74: añadir variantes con sufijo [member] (IFRS edgartools)
    _GENERIC_NAMES = {
        "reportable segment", "reportable segments", "total reportable segments",
        "reportable segments [member]",  # X0.74: NU y otros IFRS single-segment
        "restaurants segment", "consolidated", "total", "all segments",
        "operating segment", "operating segments", "single reportable segment",
        "one reportable segment", "corporate and other",
    }
    def _is_only_generic(segs):
        return (len(segs) == 1 and
                segs[0]["nombre"].lower().strip() in _GENERIC_NAMES)

    # X0.74: Limpiar sufijo " [member]" de nombres IFRS (XBRL artefacto de edgartools)
    # "Entresto [member]" → "Entresto", "Country Of China" → "China", etc.
    def _clean_segment_name(name):
        import re as _re
        # Quitar " [member]" al final (case-insensitive)
        name = _re.sub(r'\s*\[member\]\s*$', '', name, flags=_re.IGNORECASE).strip()
        # "Country Of X" → "X"
        m = _re.match(r'^Country\s+Of\s+(.+)$', name, _re.IGNORECASE)
        if m:
            name = m.group(1).title()
        # "Americas Except United States And Brazil" → dejar como está (informativo)
        return name

    non_geo = [c for c in good if not c[2] and not _is_only_generic(c[0])]
    geo_pool = [c for c in good if c[2] and not _is_only_generic(c[0])]

    # Si no hay no-geográficos útiles → intentar fallback de income statement
    # (conceptos propietarios como mcd_*, luego geo como último recurso)
    if not non_geo:
        line_segs = _extract_income_stmt_segs(ticker, total_revenue)
        if line_segs and len(line_segs) >= 2:
            return line_segs

    # producto > business > geo; dentro del mismo tipo: más segmentos, luego cobertura ≈ 100%
    pool = non_geo if non_geo else geo_pool
    if not pool:
        return None
    pool.sort(key=lambda c: (AXIS_PRIORITY.get(c[4], 99), -len(c[0]), abs(c[3] - 1.0)))
    chosen = pool[0]

    resultado, suma, _, _, axis = chosen

    # X0.74: Limpiar nombres IFRS (sufijo [member], "Country Of X", etc.)
    resultado = [{"nombre": _clean_segment_name(s["nombre"]), "revenue": s["revenue"]}
                 for s in resultado]

    # X0.73: Deduplicación case-insensitive antes de retornar
    # (MELI tenía "Other Countries" y "Other countries" como dos nodos separados)
    seen_names = {}
    deduped = []
    for seg in resultado:
        key = seg["nombre"].lower().strip()
        if key not in seen_names:
            seen_names[key] = len(deduped)
            deduped.append(seg)
        else:
            # Conservar el que tenga mayor revenue
            idx = seen_names[key]
            if abs(seg["revenue"]) > abs(deduped[idx]["revenue"]):
                deduped[idx] = seg
    resultado = deduped

    if total_revenue:
        diff = sum(s["revenue"] for s in resultado) - total_revenue
        # BUG-R2 fix: solo agregar eliminaciones si diff es razonable (1%-40% revenue)
        # Si diff > 40% revenue hay padres sin eliminar — no son eliminaciones reales
        if total_revenue * 0.01 < diff < total_revenue * 0.40:
            resultado.append({"nombre": "Eliminaciones inter-segmento", "revenue": -int(diff)})

    return resultado if resultado else None


def _detect_edgar_currency(raw_data):
    """
    Detecta la moneda de reporte de los datos XBRL inspeccionando el campo 'units'
    (dict periodo→moneda) de los items de edgartools.

    Maneja dos formatos que edgartools devuelve según el filer:
      · Simple:   'twd', 'eur', 'usd'  (IFRS filers como TSM)
      · Compuesto: 'Unit_Standard_EUR_DzninQPyI02xgP6HIeCj9A'  (US-GAAP/custom como SAP)

    Itera todos los items con has_values=True. Retorna "USD" como fallback seguro.
    """
    _NON_CURRENCY = {"THE", "AND", "FOR", "NOT", "ARE", "ALL", "INC", "LTD", "LLC",
                     "PER", "ADR", "ADS", "ORD", "COM", "SHS"}
    for item in raw_data:
        # X0.74: usar both "has_values" y presencia de "values" dict con datos
        # (edgartools varía el formato según el tipo de filing)
        has_data = item.get("has_values") or bool(item.get("values"))
        if not has_data:
            continue
        units_dict = item.get("units") or {}
        if not isinstance(units_dict, dict) or not units_dict:
            continue
        unit = next(iter(units_dict.values()), None)
        if not isinstance(unit, str) or not unit:
            continue
        unit_up = unit.upper()
        # Caso 1: código ISO simple (ej. "twd", "eur", "usd", "ars")
        if len(unit) == 3 and unit.isalpha():
            candidate = unit_up
            if candidate not in _NON_CURRENCY:
                return candidate
        # Caso 2: referencia XBRL compuesta (ej. "Unit_Standard_EUR_DzninQ...")
        m = re.search(r'(?:^|_)([A-Z]{3})(?:_|$)', unit_up)
        if m:
            candidate = m.group(1)
            if candidate not in _NON_CURRENCY:
                return candidate
        # Caso 3: "arsPerShare" o "eurPerShare" — extraer prefijo de 3 letras
        m2 = re.match(r'^([a-zA-Z]{3})Per', unit)
        if m2:
            candidate = m2.group(1).upper()
            if candidate not in _NON_CURRENCY and candidate != "USD":
                return candidate
    return "USD"


def get_edgar_edgartools(ticker):
    """
    Obtiene datos financieros complementarios desde EDGAR via edgartools.
    TIER 2 — Provee SBC exacto, goodwill, deuda, cash real, segmentos.
    Se ejecuta en asyncio.to_thread() por ser síncrono.
    """
    result = {}
    try:
        company, _by_name = _resolve_edgar_company(ticker)
        if company is None:
            # Ticker numérico sin CIK en EDGAR → usar nombre de yfinance, no datos falsos
            _yf_name = None
            try:
                import yfinance as yf
                for _sfx in ["", ".HK", ".SS", ".SZ"]:
                    _info = yf.Ticker(ticker + _sfx).info or {}
                    _yf_name = _info.get("longName") or _info.get("shortName")
                    if _yf_name:
                        break
            except Exception:
                pass
            result["company_name"] = _yf_name or ticker.upper()
            result["cik"] = ND
            print(f"  ⚠ EDGAR: CIK=N/D para ticker numérico {ticker} — nombre: {result['company_name']}")
            return result
        result["company_name"] = company.name or ticker.upper()
        result["cik"] = str(company.cik).zfill(10) if getattr(company, 'cik', None) else ND
        if _by_name:
            print(f"  ✅ EDGAR CIK resuelto por nombre: {result['cik']} ({result['company_name']})")
        else:
            print(f"  ✓ EDGAR CIK: {result['cik']}")

        # X0.77: Sanity check — nombre "Entity NNN" es señal de CIK erróneo
        import re as _re
        if _re.match(r'^Entity\s+\d+$', result.get("company_name", ""), _re.IGNORECASE):
            print(f"  🚨 SANITY FAIL: nombre genérico '{result['company_name']}' sugiere CIK incorrecto para ticker {ticker}")
            result["cik_sanity_warning"] = True

        fin = company.get_financials()
        if not fin:
            print("  ⚠ EDGAR: no se pudieron obtener financials")
            return result

        # Revenue: pick-max entre todos los conceptos conocidos (X0.73)
        # Cubre US-GAAP, IFRS, bancos (RevenuesNetOfInterestExpense), holding cos.
        # Estrategia pick-max: el concepto que devuelva el valor más alto es el correcto
        # (los conceptos parciales —solo fees, solo servicios— siempre son menores).
        inc = fin.income_statement()
        raw_inc = inc.get_raw_data()

        # Detectar moneda de reporte XBRL (X0.68)
        # X0.74: si income stmt tiene pocos items (ej. LOMA solo tiene EPS),
        # también inspeccionar balance sheet para detectar moneda
        result["currency"] = _detect_edgar_currency(raw_inc)
        if result["currency"] == "USD":
            try:
                _bs_tmp = fin.balance_sheet()
                _raw_bs_tmp = _bs_tmp.get_raw_data() if _bs_tmp else []
                _curr_bs = _detect_edgar_currency(_raw_bs_tmp)
                if _curr_bs != "USD":
                    result["currency"] = _curr_bs
            except Exception:
                pass
        if result["currency"] != "USD":
            print(f"  💱 EDGAR: moneda detectada = {result['currency']} (se convertirá a USD)")

        _REVENUE_CONCEPTS_MAIN = [
            "us-gaap_Revenues",
            "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax",
            "us-gaap_SalesRevenueNet",
            "us-gaap_RevenuesNetOfInterestExpense",          # bancos
            "us-gaap_InterestAndFeeIncomeLoansAndLeases",    # bancos alt
            "ifrs-full_Revenue",                             # IFRS filers
            "ifrs-full_RevenueFromContractsWithCustomers",
            # X0.74: bancos IFRS (HSBC, ITUB) — Revenue and Operating Income
            "ifrs-full_RevenueAndOperatingIncome",
        ]
        rev_candidates = []
        for _c in _REVENUE_CONCEPTS_MAIN:
            _v = _extract_concept(raw_inc, _c)
            if _v and _v > 0:
                rev_candidates.append(_v)
        rev_val = max(rev_candidates) if rev_candidates else fin.get_revenue()
        result["revenue"] = rev_val

        # Net Income — intentar via convenience, fallback a raw
        ni = fin.get_net_income()
        if ni is None:
            inc = fin.income_statement()
            raw_inc = inc.get_raw_data()
            ni, _ = _extract_concept_label(raw_inc, "us-gaap_NetIncomeLoss")
        result["net_income"] = ni

        # Operating Income (EBIT) — para que el Sankey no muestre N/D
        try:
            raw_inc_data = fin.income_statement().get_raw_data() if hasattr(fin, 'income_statement') else None
            op_inc = None
            if raw_inc_data:
                op_inc = _extract_concept(raw_inc_data, "us-gaap_OperatingIncomeLoss")
                if op_inc is None:
                    op_inc = _extract_concept(raw_inc_data, "us-gaap_IncomeLossFromContinuingOperations")
            result["operating_income"] = op_inc
        except Exception:
            result["operating_income"] = None

        # Cash flow raw data (needed for CFO fallback and SBC)
        # X0.75: guard against None cashflow statement (VALE, algunos 20-F IFRS)
        raw_cf = []
        try:
            cf = fin.cashflow_statement()
            if cf is not None:
                raw_cf = cf.get_raw_data() or []
        except Exception:
            raw_cf = []

        # Cash flow data — convenience methods, fallback a raw data
        try:
            cfo = fin.get_operating_cash_flow()
        except Exception:
            cfo = None
        try:
            capex = fin.get_capital_expenditures()
        except Exception:
            capex = None
        try:
            fcf = fin.get_free_cash_flow()
        except Exception:
            fcf = None
        if cfo is None and raw_cf:
            cfo = _extract_concept(raw_cf, "us-gaap_NetCashProvidedByUsedInOperatingActivities")
        if fcf is None and cfo is not None and capex is not None:
            fcf = cfo - capex
        result["cfo"] = cfo
        result["capex"] = capex
        result["fcf"] = fcf

        # SBC — desde cash flow raw
        sbc = _extract_concept(raw_cf, "us-gaap_ShareBasedCompensation") if raw_cf else None
        if sbc is None and raw_cf:
            sbc = _extract_concept(raw_cf, "us-gaap_StockCompensationExpenseNonCash")
        result["sbc"] = sbc

        # Dividendos
        div = _extract_concept(raw_cf, "us-gaap_PaymentsOfDividendsCommonStock")
        if div is None:
            div = _extract_concept(raw_cf, "us-gaap_PaymentsOfDividends")
        result["dividendos"] = div

        # Balance sheet data — X0.75: guard contra None (mismo patrón que cashflow)
        raw_bs = []
        try:
            bs = fin.balance_sheet()
            if bs is not None:
                raw_bs = bs.get_raw_data() or []
        except Exception:
            raw_bs = []

        total_assets = fin.get_total_assets()
        result["total_assets"] = total_assets

        goodwill = _extract_concept(raw_bs, "us-gaap_Goodwill")
        if goodwill is None:
            goodwill = _extract_concept(raw_bs, "us-gaap_GoodwillAndOtherIntangibleAssets")
        result["goodwill"] = goodwill

        # Deuda
        lt_debt = _extract_concept(raw_bs, "us-gaap_LongTermDebtNoncurrent")
        st_debt = _extract_concept(raw_bs, "us-gaap_LongTermDebtCurrent")
        if st_debt is None:
            st_debt = _extract_concept(raw_bs, "us-gaap_ShortTermBorrowings")
        result["lt_debt"] = lt_debt
        result["st_debt"] = st_debt
        result["deuda_total"] = (lt_debt or 0) + (st_debt or 0) if (lt_debt is not None or st_debt is not None) else None

        # Cash y short-term investments (con fallbacks para variantes GAAP)
        cash = _extract_concept(raw_bs, "us-gaap_CashAndCashEquivalents")
        if cash is None:
            cash = _extract_concept(raw_bs, "us-gaap_CashAndCashEquivalentsAtCarryingValue")
        sti = _extract_concept(raw_bs, "us-gaap_ShortTermInvestments")
        if sti is None:
            sti = _extract_concept(raw_bs, "us-gaap_AvailableForSaleSecuritiesCurrent")
        if sti is None:
            sti = _extract_concept(raw_bs, "us-gaap_MarketableSecuritiesCurrent")
        # También considerar marketable securities no-current como efectivo disponible
        sti_nc = _extract_concept(raw_bs, "us-gaap_MarketableSecuritiesNoncurrent")
        cash_real_total = (cash or 0)
        if sti is not None:
            cash_real_total += sti
        if sti_nc is not None:
            cash_real_total += sti_nc
        result["cash"] = cash
        result["short_term_investments"] = sti
        result["cash_real"] = cash_real_total if (cash is not None or sti is not None or sti_nc is not None) else None

        # ── CAMPOS NUEVOS X0.82 — Balance Sheet ──────────────────────────────
        # current_assets — AssetsCurrent
        current_assets = _extract_concept(raw_bs, "us-gaap_AssetsCurrent")
        result["current_assets"] = current_assets

        # current_liabilities — LiabilitiesCurrent
        current_liabilities = _extract_concept(raw_bs, "us-gaap_LiabilitiesCurrent")
        result["current_liabilities"] = current_liabilities

        # stockholders_equity — StockholdersEquity con fallback a versión con NCI
        stockholders_equity = _extract_concept(raw_bs, "us-gaap_StockholdersEquity")
        if stockholders_equity is None:
            stockholders_equity = _extract_concept(
                raw_bs,
                "us-gaap_StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
            )
        result["stockholders_equity"] = stockholders_equity

        # ── CAMPOS NUEVOS X0.82 — Cash Flow Statement ────────────────────────
        # depreciation_amortization — D&A desde cash flow (el más confiable para D&A total)
        da = _extract_concept(raw_cf, "us-gaap_DepreciationDepletionAndAmortization")
        if da is None:
            da = _extract_concept(raw_cf, "us-gaap_Depreciation")
        if da is None:
            da = _extract_concept(raw_cf, "us-gaap_DepreciationAndAmortization")
        result["depreciation_amortization"] = da

        # ── CAMPOS NUEVOS X0.82 — Revenue año anterior (para YoY) ────────────
        # Extraer el segundo valor cronológico más reciente de los conceptos de revenue
        revenue_prior_year = None
        try:
            for _c in _REVENUE_CONCEPTS_MAIN:
                for item in raw_inc:
                    if (item['concept'] == _c
                            and not item.get('is_dimension')
                            and item.get('has_values')):
                        vals = item['values']
                        fy_vals = {k: v for k, v in vals.items() if 'duration' in k}
                        if len(fy_vals) >= 2:
                            sorted_keys = sorted(fy_vals.keys())
                            # El penúltimo es el año anterior
                            revenue_prior_year = fy_vals[sorted_keys[-2]]
                            break
                if revenue_prior_year is not None:
                    break
        except Exception:
            pass
        result["revenue_prior_year"] = revenue_prior_year

        # Shares outstanding
        shares = fin.get_shares_outstanding_basic()
        result["shares"] = shares

        # Segmentos via XBRL dimensions
        fy_year = ND
        if rev_val and hasattr(fin, 'income_statement'):
            inc = fin.income_statement()
            try:
                raw_inc_data = inc.get_raw_data()
                # Probar múltiples conceptos revenue — distintas empresas usan distintos nombres
                fy_concepts = [
                    'us-gaap_Revenues',
                    'us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax',
                    'us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax',
                    'us-gaap_SalesRevenueNet',
                    'us-gaap_RevenuesNetOfInterestExpense',   # bancos
                    'ifrs-full_Revenue',                      # IFRS filers (X0.73)
                    'ifrs-full_RevenueFromContractsWithCustomers',
                    'ifrs-full_RevenueAndOperatingIncome',    # bancos IFRS (X0.74)
                ]
                for fy_concept in fy_concepts:
                    for item in raw_inc_data:
                        if (item['concept'] == fy_concept
                                and not item.get('is_dimension')
                                and item.get('has_values')):
                            vals = item['values']
                            fy_vals = {k: v for k, v in vals.items() if 'duration' in k}
                            if fy_vals:
                                latest_key = max(fy_vals.keys())
                                parts = latest_key.split('_')
                                if len(parts) >= 3:
                                    fy_year = parts[-1][:4]
                                elif len(parts) >= 2:
                                    fy_year = parts[1][:4]
                            break
                    if fy_year != ND:
                        break
            except Exception:
                pass
        result["fy_year"] = fy_year

        # Segmentos!
        result["segmentos"] = extract_segments_edgartools(ticker, rev_val)

        print(f"  ✓ EDGAR edgartools — FY{fy_year} · Revenue={fmt_b(rev_val)} · FCF={fmt_b(fcf) if fcf else ND} · Segmentos={'Sí' if result.get('segmentos') else 'No'}")

    except Exception as e:
        print(f"  ⚠ EDGAR error: {e}")
        traceback.print_exc()

    return result


# ─── TIER 3: TRADINGVIEW ───────────────────────────────────────────────────────
async def get_tradingview(session, ticker):
    """Obtiene performance histórica desde TradingView Scanner API."""
    result = {}
    columns = [
        "close", "price_52_week_high", "price_52_week_low",
        "market_cap_basic", "price_earnings_ttm",
        "earnings_per_share_diluted_ttm",
        "Perf.5D", "Perf.1M", "Perf.3M", "Perf.6M",
        "Perf.YTD", "description", "name"
    ]
    try:
        payload = {
            "symbol": {"ticker": "", "query": {"types": []}},
            "columns": columns,
            "filter": [{"left": "name", "operation": "equal", "right": ticker.upper()}],
            "range": [0, 1],
        }
        async with session.post(
            "https://scanner.tradingview.com/america/scan",
            json=payload, headers=TV_HEADERS
        ) as r:
            data = await r.json(content_type=None)
        rows = data.get("data", [])
        if rows and rows[0].get("d"):
            d = rows[0]["d"]
            result["exchange_tv"] = rows[0].get("s", "NASDAQ").split(":")[0]
            result["precio_actual"] = d[0]
            result["w52_high"] = d[1]
            result["w52_low"] = d[2]
            result["market_cap_tv"] = d[3]
            result["pe_ttm_tv"] = d[4]
            result["eps_ttm_tv"] = d[5]
            perf = {}
            perf_keys = ["5D", "1M", "3M", "6M", "YTD"]
            for i, pk in enumerate(perf_keys):
                idx = 6 + i
                if idx < len(d) and d[idx] is not None:
                    perf[pk] = d[idx]
            result["performance"] = perf
            symbol_str = rows[0].get("s", "")
            print(f"  ✓ TradingView — {symbol_str} @ ${d[0]}")
            return result
        print(f"  ⚠ TradingView: no encontrado {ticker}")
    except Exception as e:
        print(f"  ⚠ TradingView error: {e}")
    return result


# ─── TIER 4: YFINANCE — auditoría silenciosa siempre activa ───────────────────
def yfinance_tier4(ticker, canonical):
    """
    TIER 4 — yfinance siempre corre silenciosamente (función sync, llamar via
    asyncio.to_thread desde recolectar()).
    Captura TODOS los campos disponibles y los compara contra lo que ya
    tienen EDGAR+AV (canonical dict).  Solo se USAN para llenar nulls,
    pero el audit se genera siempre → acumula estadísticas de confiabilidad
    con cada corrida, aunque EDGAR+AV hayan traído todo.

    Retorna (fills_dict, audit_dict):
      fills_dict  — solo los campos donde canonical[field] es None
      audit_dict  — registro completo para meta.tier4_audit

    Categorías por campo:
      "match"    — yfinance coincide con EDGAR/AV (dentro de 5%)
      "disagree" — yfinance difiere (sospechoso)
      "filled"   — yfinance aportó dato que era null → usado
      "null"     — yfinance no pudo obtenerlo
      "error"    — excepción al intentarlo
    """
    TOLERANCE = 0.05   # 5% de diferencia = "match"

    audit = {
        "yfinance_version": None,
        "ran":              False,
        "fields_captured":  0,
        "match":            0,
        "disagree":         0,
        "filled":           0,
        "null_in_yf":       0,
        "success_rate":     "0/0 (0%)",
        "detail":           {},
    }

    try:
        import yfinance as yf
        audit["yfinance_version"] = getattr(yf, "__version__", "?")
    except ImportError:
        audit["detail"]["_status"] = "not_installed"
        return {}, audit

    # Todos los campos que yfinance puede proveer
    INFO_MAP = {
        "market_cap":       "marketCap",
        "beta":             "beta",
        "pe_forward":       "forwardPE",
        "analyst_target":   "targetMeanPrice",
        "w52_high":         "fiftyTwoWeekHigh",
        "w52_low":          "fiftyTwoWeekLow",
        "margen_bruto":     "grossMargins",
        "margen_op":        "operatingMargins",
        "margen_neto":      "profitMargins",
        "revenue":          "totalRevenue",
        "shares":           "sharesOutstanding",
        "cash_real":        "totalCash",
        "deuda_total":      "totalDebt",
        # X0.83: campos nuevos
        "lt_debt":          "longTermDebt",
        "st_debt":          "currentDebt",
        "eps_forward":      "forwardEps",
    }
    FIN_MAP = {
        "revenue":          "Total Revenue",
        "net_income":       "Net Income",
        "operating_income": "Operating Income",
        # X0.83: SBC con múltiples nombres alternativos (varía por yfinance version)
        "sbc":              "Stock Based Compensation",
    }
    # X0.83: nombres alternativos para SBC (se prueban si FIN_MAP no los encuentra)
    SBC_FALLBACK_ROWS = [
        "Stock Based Compensation",
        "Share Based Compensation",
        "Stock-based Compensation",
        "Share-based Compensation",
        "Equity-based Compensation",
    ]
    CF_MAP = {
        "cfo":              "Operating Cash Flow",
        "capex":            "Capital Expenditure",
        "dividendos":       "Cash Dividends Paid",
        # X0.83: SBC también puede estar en cash flow statement
        "sbc_cf":           "Stock Based Compensation",
    }

    yf_raw = {}   # todos los valores capturados por yfinance
    fills  = {}   # solo los que se usarán (canonical era null)

    def _compare(field, yf_val):
        """Registra match/disagree/filled según el valor canónico."""
        canonical_val = canonical.get(field)
        if yf_val is None:
            audit["detail"][field] = "null"
            audit["null_in_yf"] += 1
            return
        audit["fields_captured"] += 1
        if canonical_val is None:
            # EDGAR+AV no lo tenían → yfinance llena el hueco
            fills[field] = yf_val
            audit["detail"][field] = "filled"
            audit["filled"] += 1
        else:
            try:
                diff = abs(float(yf_val) - float(canonical_val)) / (abs(float(canonical_val)) or 1)
                if diff <= TOLERANCE:
                    audit["detail"][field] = f"match ({diff*100:.1f}%)"
                    audit["match"] += 1
                else:
                    audit["detail"][field] = f"disagree (yf={fmt_b(yf_val)} vs ref={fmt_b(canonical_val)}, Δ{diff*100:.0f}%)"
                    audit["disagree"] += 1
            except Exception:
                audit["detail"][field] = "compare_error"

    try:
        audit["ran"] = True
        t = yf.Ticker(ticker)

        # info dict
        try:
            info = t.info or {}
            for field, yf_key in INFO_MAP.items():
                v = _float(info.get(yf_key))
                yf_raw[field] = v
                _compare(field, v)
        except Exception as e:
            audit["detail"]["_info_error"] = str(e)

        # financials (P&L anual)
        try:
            fin = t.financials
            if fin is not None and not fin.empty:
                col = fin.columns[0]
                for field, row_key in FIN_MAP.items():
                    if field not in yf_raw:
                        try:
                            v = _float(fin.loc[row_key, col])
                            yf_raw[field] = v
                            _compare(field, v)
                        except Exception:
                            if field not in audit["detail"]:
                                audit["detail"][field] = "not_in_fin"
        except Exception as e:
            audit["detail"]["_fin_error"] = str(e)

        # cashflow
        try:
            cf = t.cashflow
            if cf is not None and not cf.empty:
                col = cf.columns[0]
                for field, row_key in CF_MAP.items():
                    if field not in yf_raw:
                        try:
                            v = _float(cf.loc[row_key, col])
                            if v is not None:
                                # sbc_cf es helper interno → mapear a sbc si sbc aún null
                                real_field = "sbc" if field == "sbc_cf" else field
                                if real_field not in yf_raw or yf_raw[real_field] is None:
                                    yf_raw[real_field] = v
                                    _compare(real_field, v)
                        except Exception:
                            if field not in audit["detail"]:
                                audit["detail"][field] = "not_in_cf"
        except Exception as e:
            audit["detail"]["_cf_error"] = str(e)

        # X0.83: SBC multi-fallback — probar nombres alternativos si sbc aún null
        if yf_raw.get("sbc") is None:
            try:
                for stmt in [getattr(t, "financials", None), getattr(t, "cashflow", None)]:
                    if stmt is None or stmt.empty:
                        continue
                    col = stmt.columns[0]
                    for row_name in SBC_FALLBACK_ROWS:
                        try:
                            v = _float(stmt.loc[row_name, col])
                            if v is not None and v > 0:
                                yf_raw["sbc"] = v
                                _compare("sbc", v)
                                break
                        except Exception:
                            continue
                    if yf_raw.get("sbc") is not None:
                        break
            except Exception as e:
                audit["detail"]["_sbc_fallback_error"] = str(e)

        # X0.83: Performance histórica desde historial de precios (return_1y/3y/5y)
        try:
            import pandas as pd
            hist = t.history(period="5y", auto_adjust=True)
            if hist is not None and not hist.empty and len(hist) > 50:
                closes = hist["Close"]
                now_price = closes.iloc[-1]
                now_idx   = closes.index[-1]

                def _perf_ret(years):
                    cutoff = now_idx - pd.DateOffset(years=years)
                    sub = closes[closes.index <= cutoff]
                    if sub.empty:
                        return None
                    base = sub.iloc[-1]
                    return round((now_price / base) - 1, 4) if base > 0 else None

                for field, yrs in [("return_1y", 1), ("return_3y", 3), ("return_5y", 5)]:
                    v = _perf_ret(yrs)
                    yf_raw[field] = v
                    canonical_perf = canonical.get(field)
                    if v is None:
                        audit["detail"][field] = "null"
                        audit["null_in_yf"] += 1
                    elif canonical_perf is None:
                        fills[field] = v
                        audit["detail"][field] = "filled"
                        audit["filled"] += 1
                    else:
                        audit["detail"][field] = f"match-perf ({v:.1%})"
                        audit["match"] += 1
        except Exception as e:
            audit["detail"]["_hist_error"] = str(e)

    except Exception as e:
        audit["detail"]["_global_error"] = str(e)

    # Success rate = (match + filled) / fields_captured
    evaluated = audit["match"] + audit["disagree"] + audit["filled"]
    reliable  = audit["match"] + audit["filled"]
    pct = int(reliable / evaluated * 100) if evaluated else 0
    audit["success_rate"] = f"{reliable}/{evaluated} ({pct}%)"

    filled_list   = [f for f, s in audit["detail"].items()
                     if isinstance(s, str) and s == "filled"]
    disagree_list = [f for f, s in audit["detail"].items()
                     if isinstance(s, str) and s.startswith("disagree")]
    summary = (f"match={audit['match']} filled={audit['filled']} "
               f"disagree={audit['disagree']} null={audit['null_in_yf']}")
    print(f"  ~ TIER 4 yfinance v{audit['yfinance_version']}: {audit['success_rate']} — {summary}")
    if disagree_list:
        print(f"    ⚠ Discrepancias: {', '.join(disagree_list)}")
    if filled_list:
        print(f"    ✓ Llenó nulls: {', '.join(filled_list)}")

    return fills, audit


# ─── MAIN ──────────────────────────────────────────────────────────────────────
async def recolectar(ticker, precio_usuario, use_yfinance=True, use_av=True):
    global _USE_AV
    _USE_AV = use_av
    print(f"\n{'='*58}")
    print(f"  FEROLDI RECOLECTAR v {VERSION} — ${ticker.upper()} @ ${precio_usuario}")
    print(f"  {TODAY}")
    if not AV_KEYS:
        print(f"  ⚠ No hay AV_API_KEY configurada (muchos campos serán N/D)")
    else:
        print(f"  ⚡ {len(AV_KEYS)} AV key(s) disponibles")
    print(f"  TIER 4 yfinance: {'activo' if use_yfinance else 'deshabilitado (--no-yfinance)'}")
    print(f"{'='*58}\n")

    # ── PRE-FLIGHT: tipo de activo (ETF/forex/crypto/inexistente → abort) ─────
    _validate_ticker_type(ticker)

    # ── RONDA ÚNICA: Tres tiers en paralelo ──────────────────────────────────
    print("📡 TIERS 1+2+3 en paralelo...\n")
    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        av_task   = asyncio.create_task(get_alphavantage(ticker))
        edgar_task = asyncio.to_thread(get_edgar_edgartools, ticker)
        tv_task   = asyncio.create_task(get_tradingview(session, ticker))

        av_ov, av_earn = await av_task
        edgar = await edgar_task
        tv    = await tv_task

    # ── FX CONVERSION — datos EDGAR en moneda local → USD (X0.68) ────────────
    edgar_currency = edgar.get("currency", "USD")
    fx_rate, fx_pair, fx_date = get_fx_rate(edgar_currency)
    _fx_applied = False
    if edgar_currency != "USD":
        if fx_rate:
            print(f"  💱 FX aplicado: {edgar_currency}→USD via {fx_pair}  rate={fx_rate:.6f}  date={fx_date}")
            # Campos monetarios EDGAR — todos en unidades de moneda local
            _EDGAR_MONETARY = [
                "revenue", "net_income", "operating_income",
                "cfo", "capex", "sbc", "dividendos",
                "lt_debt", "st_debt", "deuda_total",
                "cash", "short_term_investments", "cash_real",
                "goodwill", "total_assets", "fcf",
                # X0.82: nuevos campos monetarios
                "current_assets", "current_liabilities", "stockholders_equity",
                "depreciation_amortization", "revenue_prior_year",
            ]
            for field in _EDGAR_MONETARY:
                val = edgar.get(field)
                if val is not None:
                    edgar[field] = round(val * fx_rate, 0)
            # Convertir valores dentro de segmentos (lista de dicts {nombre, revenue})
            segs = edgar.get("segmentos")
            if segs and isinstance(segs, list):
                for seg in segs:
                    if seg.get("revenue") is not None:
                        seg["revenue"] = round(seg["revenue"] * fx_rate, 0)
            _fx_applied = True
        else:
            print(f"  ⚠ FX: {edgar_currency}→USD no disponible — datos EDGAR en moneda local")

    # Metadatos FX para auditoría (siempre presentes, USD si no aplica)
    _fx_meta = {
        "currency_edgar": edgar_currency,
        "fx_applied":     _fx_applied,
        "fx_pair":        fx_pair if edgar_currency != "USD" else "USD",
        "fx_rate_used":   round(fx_rate, 6) if (fx_rate and edgar_currency != "USD") else 1.0,
        "fx_date":        fx_date if edgar_currency != "USD" else datetime.now().strftime("%Y-%m-%d"),
        "fx_source":      ("live" if (fx_pair and "FALLBACK" not in str(fx_pair)) else "fallback")
                           if edgar_currency != "USD" else "N/A",
    }

    # ── ENSAMBLAR JSON ────────────────────────────────────────────────────────
    precio_ref = float(precio_usuario)

    # Market cap: AV > TV > calculated from shares
    market_cap_av = av_ov.get("market_cap")
    market_cap_tv = tv.get("market_cap_tv")
    mkt_cap_calc  = (edgar.get("shares") * precio_ref) if edgar.get("shares") else None
    mkt_cap = pick(market_cap_av, market_cap_tv, mkt_cap_calc)

    # Analyst consensus
    strong_buy = av_ov.get("analyst_strong_buy") or 0
    buy        = av_ov.get("analyst_buy") or 0
    hold       = av_ov.get("analyst_hold") or 0
    sell       = av_ov.get("analyst_sell") or 0
    strong_sell= av_ov.get("analyst_strong_sell") or 0
    total_r = strong_buy + buy + hold + sell + strong_sell
    consenso_parts = []
    if total_r:
        if strong_buy + buy: consenso_parts.append(f"{strong_buy + buy} Buy")
        if hold:             consenso_parts.append(f"{hold} Hold")
        if sell + strong_sell: consenso_parts.append(f"{sell + strong_sell} Sell")
    consenso = " / ".join(consenso_parts) if consenso_parts else ND

    output = {
        "meta": {
            "version":       VERSION,
            "ticker":        ticker.upper(),
            "precio_usuario": precio_ref,
            "exchange":      pick(av_ov.get("exchange"), tv.get("exchange_tv"), ND),
            "fecha":         TODAY,
            "company_name":  edgar.get("company_name", ticker.upper()),
            "sector":        av_ov.get("sector", ND),
            "industry":      av_ov.get("industry", ND),
            "fuentes":       ["Alpha Vantage", "EDGAR (edgartools)", "TradingView"],
            "av_keys":       len(AV_KEYS),
            "fx_info":       _fx_meta,
        },
        "edgar": {
            "cik":                 edgar.get("cik", ND),
            "fy_year":             edgar.get("fy_year", ND),
            "revenue":             edgar.get("revenue"),
            "net_income":          edgar.get("net_income"),
            "operating_income":    edgar.get("operating_income"),
            "cfo":                 edgar.get("cfo"),
            "capex":               edgar.get("capex"),
            "fcf":                 edgar.get("fcf"),
            "lt_debt":             edgar.get("lt_debt"),
            "st_debt":             edgar.get("st_debt"),
            "deuda_total":         edgar.get("deuda_total"),
            "sbc":                 edgar.get("sbc"),
            "dividendos":          edgar.get("dividendos"),
            "total_assets":        edgar.get("total_assets"),
            "goodwill":            edgar.get("goodwill"),
            "cash":                edgar.get("cash"),
            "short_term_investments": edgar.get("short_term_investments"),
            "cash_real":           edgar.get("cash_real"),
            "shares":              edgar.get("shares"),
            "segmentos":           edgar.get("segmentos"),   # null si no disponibles
            # X0.82: campos nuevos
            "current_assets":      edgar.get("current_assets"),
            "current_liabilities": edgar.get("current_liabilities"),
            "stockholders_equity": edgar.get("stockholders_equity"),
            "depreciation_amortization": edgar.get("depreciation_amortization"),
            "revenue_prior_year":  edgar.get("revenue_prior_year"),
        },
        "market": {
            "precio_actual":    pick(tv.get("precio_actual"), precio_ref),
            "w52_high":         pick(av_ov.get("w52_high"), tv.get("w52_high")),
            "w52_low":          pick(av_ov.get("w52_low"), tv.get("w52_low")),
            "market_cap":       mkt_cap,
            "pe_ttm":           pick(av_ov.get("pe_ttm"), tv.get("pe_ttm_tv")),
            "eps_ttm":          pick(av_ov.get("eps_ttm"), tv.get("eps_ttm_tv")),
            "analyst_target":       av_ov.get("analyst_target"),
            "analyst_strong_buy":   strong_buy,
            "analyst_buy":          buy,
            "analyst_hold":         hold,
            "analyst_sell":         sell,
            "analyst_strong_sell":  strong_sell,
            "analyst_consenso":     consenso,
            "latest_quarter":       av_ov.get("latest_quarter", ND),
            "next_earnings_date":   None,   # X0.82: se llena después vía yfinance
        },
        "ratios": {
            "pe_forward":       av_ov.get("pe_forward"),
            "peg":              av_ov.get("peg"),
            "ev_ebitda":        av_ov.get("ev_ebitda"),
            "ev_revenue":       av_ov.get("ev_revenue"),
            "pb":               av_ov.get("pb"),
            "p_sales":          av_ov.get("p_sales"),
            "margen_bruto":     av_ov.get("margen_bruto"),
            "margen_op":        av_ov.get("margen_op"),
            "margen_neto":      av_ov.get("margen_neto"),
            "margen_ebitda":    None,
            "roic":             None,
            "roe":              av_ov.get("roe"),
            "roa":              av_ov.get("roa"),
            "de_ratio":         None,
            "current_ratio":    None,
            "dividend_yield":   av_ov.get("dividend_yield"),
            "beta":             av_ov.get("beta"),
            "revenue_yoy":      av_ov.get("revenue_yoy_q"),
            "ni_yoy":           av_ov.get("earnings_yoy_q"),
            "eps_proj":         None,
            "percent_insiders": av_ov.get("percent_insiders"),
        },
        "earnings": av_earn,
        "performance": tv.get("performance", {}),
        "competidores": [],
        "nd_resumen": {"campos_nd": []},
    }

    # ── ND RESUMEN ────────────────────────────────────────────────────────────
    nd_check = {
        "edgar.revenue":       edgar.get("revenue"),
        "edgar.net_income":    edgar.get("net_income"),
        "edgar.fcf":           edgar.get("fcf"),
        "edgar.deuda_total":   edgar.get("deuda_total"),
        "edgar.cash_real":     edgar.get("cash_real"),
        "ratios.pe_forward":   output["ratios"]["pe_forward"],
        "ratios.peg":          output["ratios"]["peg"],
        "ratios.margen_bruto": output["ratios"]["margen_bruto"],
        "ratios.beta":         output["ratios"]["beta"],
        "ratios.roe":          output["ratios"]["roe"],
    }
    output["nd_resumen"]["campos_nd"] = [k for k, v in nd_check.items() if v is None]

    # ── TIER 4: yfinance — auditoría silenciosa siempre activa ───────────────
    # Corre siempre (salvo --no-yfinance) para acumular estadísticas.
    # Solo APLICA fills donde canonical[field] era null.
    yf_audit = {"ran": False, "yfinance_version": None,
                "success_rate": "0/0 (0%)", "detail": {}}

    if use_yfinance:
        print("\n~ TIER 4 yfinance: auditando silenciosamente...")
        canonical_snapshot = {
            "revenue":          output["edgar"]["revenue"],
            "net_income":       output["edgar"]["net_income"],
            "operating_income": output["edgar"]["operating_income"],
            "cfo":              output["edgar"]["cfo"],
            "capex":            output["edgar"]["capex"],
            "sbc":              output["edgar"]["sbc"],
            "dividendos":       output["edgar"]["dividendos"],
            "lt_debt":          output["edgar"]["lt_debt"],
            "st_debt":          output["edgar"]["st_debt"],
            "deuda_total":      output["edgar"]["deuda_total"],
            "cash_real":        output["edgar"]["cash_real"],
            "shares":           output["edgar"]["shares"],
            "market_cap":       output["market"]["market_cap"],
            "analyst_target":   output["market"]["analyst_target"],
            "w52_high":         _float(output["market"]["w52_high"]),
            "w52_low":          _float(output["market"]["w52_low"]),
            "beta":             output["ratios"]["beta"],
            "pe_forward":       output["ratios"]["pe_forward"],
            "margen_bruto":     output["ratios"]["margen_bruto"],
            "margen_op":        output["ratios"]["margen_op"],
            "margen_neto":      output["ratios"]["margen_neto"],
            # X0.83: nuevos campos
            "eps_forward":      output["ratios"].get("eps_proj"),
            "return_1y":        output.get("performance", {}).get("return_1y"),
            "return_3y":        output.get("performance", {}).get("return_3y"),
            "return_5y":        output.get("performance", {}).get("return_5y"),
        }
        yf_ticker, yf_currency = await asyncio.to_thread(_resolve_yf_ticker, ticker)
        fills, yf_audit = await asyncio.to_thread(yfinance_tier4, yf_ticker, canonical_snapshot)
        # Si EDGAR estaba vacío (no-SEC filer: TSX, LSE, etc.) y yfinance trajo
        # datos en moneda local, convertir fills a USD antes de aplicarlos
        # X0.74: también detectar si yfinance reporta moneda local como "USD"
        # (bug conocido en yfinance para tickers argentinos como LOMA, BBAR)
        # Heurística: si revenue_fill > market_cap * 20 → sospechoso de moneda local
        _yf_fill_rev = fills.get("revenue")
        _yf_fill_mc  = fills.get("market_cap") or tv.get("market_cap_tv") or 0
        _yf_currency_suspect = False
        if _yf_fill_rev and _yf_fill_mc and _yf_fill_mc > 0:
            _rev_mc_ratio = _yf_fill_rev / _yf_fill_mc
            if _rev_mc_ratio > 50:
                # Revenue es >50x market cap → casi seguro en moneda local
                # Intentar detectar la moneda real del ticker via EDGAR XBRL
                _edgar_detected_currency = (edgar.get("currency") or "").upper()
                if _edgar_detected_currency and _edgar_detected_currency != "USD":
                    yf_currency = _edgar_detected_currency
                    _yf_currency_suspect = True
                    print(f"  ⚠ X0.74: revenue/mktcap={_rev_mc_ratio:.0f}x — moneda sospechosa, usando EDGAR currency={yf_currency}")
                # También detectar por balance sheet del filing
                elif edgar.get("currency") in (None, "USD"):
                    # Intentar via XBRL del 20-F
                    try:
                        _company_tmp = Company(ticker.upper())
                        _filing_tmp = _company_tmp.get_filings(form="20-F").latest() or _company_tmp.get_filings(form="10-K").latest()
                        if _filing_tmp:
                            _xbrl_tmp = _filing_tmp.xbrl()
                            if _xbrl_tmp:
                                _facts_tmp = _xbrl_tmp.facts
                                _df_tmp = _facts_tmp.query().to_dataframe()
                                # Buscar currency en los units
                                if _df_tmp is not None and not _df_tmp.empty:
                                    for _, _row in _df_tmp.iterrows():
                                        # Algunos tienen 'units' en el dataframe
                                        pass
                    except Exception:
                        pass

        if edgar.get("revenue") is None and fills.get("revenue") and (yf_currency != "USD" or _yf_currency_suspect):
            yf_fx, yf_fx_pair, yf_fx_date = get_fx_rate(yf_currency)
            if yf_fx:
                print(f"  💱 FX fills yfinance: {yf_currency}→USD via {yf_fx_pair}  rate={yf_fx:.6f}")
                _YF_MONETARY = ["revenue","net_income","operating_income","cfo",
                                "capex","sbc","dividendos","lt_debt","st_debt",
                                "deuda_total","cash_real","shares","market_cap",
                                "total_assets","goodwill","fcf"]
                for f in _YF_MONETARY:
                    if fills.get(f) is not None:
                        fills[f] = round(fills[f] * yf_fx, 0)
                # Actualizar fx_meta para reflejar que la fuente fue yfinance
                _fx_meta.update({
                    "currency_edgar": yf_currency,
                    "fx_applied": True,
                    "fx_pair": yf_fx_pair,
                    "fx_rate_used": round(yf_fx, 6),
                    "fx_date": yf_fx_date,
                    "fx_source": "live" if "FALLBACK" not in str(yf_fx_pair) else "fallback",
                })
        # Aplicar fills (solo campos que eran null)
        if fills.get("revenue"):          output["edgar"]["revenue"]          = fills["revenue"]
        if fills.get("net_income"):       output["edgar"]["net_income"]       = fills["net_income"]
        if fills.get("operating_income"): output["edgar"]["operating_income"] = fills["operating_income"]
        if fills.get("cfo"):              output["edgar"]["cfo"]              = fills["cfo"]
        if fills.get("capex"):            output["edgar"]["capex"]            = abs(fills["capex"])
        if fills.get("sbc"):              output["edgar"]["sbc"]              = fills["sbc"]
        if fills.get("dividendos"):       output["edgar"]["dividendos"]       = fills["dividendos"]
        if fills.get("lt_debt"):          output["edgar"]["lt_debt"]          = fills["lt_debt"]
        if fills.get("st_debt"):          output["edgar"]["st_debt"]          = fills["st_debt"]
        if fills.get("deuda_total"):      output["edgar"]["deuda_total"]      = fills["deuda_total"]
        if fills.get("cash_real"):        output["edgar"]["cash_real"]        = fills["cash_real"]
        if fills.get("shares"):           output["edgar"]["shares"]           = fills["shares"]
        if fills.get("market_cap"):       output["market"]["market_cap"]      = fills["market_cap"]
        if fills.get("analyst_target"):   output["market"]["analyst_target"]  = fills["analyst_target"]
        if fills.get("w52_high"):         output["market"]["w52_high"]        = fills["w52_high"]
        if fills.get("w52_low"):          output["market"]["w52_low"]         = fills["w52_low"]
        if fills.get("beta"):             output["ratios"]["beta"]            = fills["beta"]
        if fills.get("pe_forward"):       output["ratios"]["pe_forward"]      = fills["pe_forward"]
        if fills.get("margen_bruto"):     output["ratios"]["margen_bruto"]    = fills["margen_bruto"]
        if fills.get("margen_op"):        output["ratios"]["margen_op"]       = fills["margen_op"]
        if fills.get("margen_neto"):      output["ratios"]["margen_neto"]     = fills["margen_neto"]
        # X0.83: nuevos fills
        if fills.get("eps_forward"):
            output["ratios"]["eps_proj"] = fills["eps_forward"]
        # X0.83: recalcular deuda_total si se llenaron lt_debt/st_debt
        if fills.get("lt_debt") or fills.get("st_debt"):
            _lt = output["edgar"].get("lt_debt")
            _st = output["edgar"].get("st_debt")
            if (_lt is not None or _st is not None) and output["edgar"].get("deuda_total") is None:
                output["edgar"]["deuda_total"] = (_lt or 0) + (_st or 0)
        # X0.83: performance histórica desde yfinance hist
        if "performance" not in output or not isinstance(output.get("performance"), dict):
            output["performance"] = {}
        for pk in ["return_1y", "return_3y", "return_5y"]:
            if fills.get(pk) is not None and output["performance"].get(pk) is None:
                output["performance"][pk] = fills[pk]
        # Recalcular FCF si se llenaron cfo/capex
        if not output["edgar"]["fcf"] and output["edgar"]["cfo"] and output["edgar"]["capex"]:
            output["edgar"]["fcf"] = output["edgar"]["cfo"] - abs(output["edgar"]["capex"])
    else:
        print("  ~ TIER 4 yfinance deshabilitado (--no-yfinance)")

    # ── X0.82: next_earnings_date via yfinance ───────────────────────────────
    if use_yfinance:
        try:
            import yfinance as yf
            _cal = yf.Ticker(ticker).calendar
            _ned = None
            if _cal is not None:
                # calendar puede ser dict o DataFrame según la versión de yfinance
                if isinstance(_cal, dict):
                    _ned = _cal.get("Earnings Date")
                    if isinstance(_ned, list) and _ned:
                        _ned = str(_ned[0])[:10]
                    elif _ned is not None:
                        _ned = str(_ned)[:10]
                else:
                    # DataFrame: buscar columna "Earnings Date" en índice o columnas
                    try:
                        import pandas as pd
                        if "Earnings Date" in _cal.index:
                            _ned = str(_cal.loc["Earnings Date"].iloc[0])[:10]
                        elif "Earnings Date" in _cal.columns:
                            _ned = str(_cal["Earnings Date"].iloc[0])[:10]
                    except Exception:
                        pass
            output["market"]["next_earnings_date"] = _ned
            if _ned:
                print(f"  ✓ next_earnings_date: {_ned}")
        except Exception as _e:
            print(f"  ~ next_earnings_date no disponible: {_e}")

    # ── X0.82: SECCIÓN computed — ratios calculados desde datos EDGAR ────────
    _rev    = output["edgar"].get("revenue")
    _rev_py = output["edgar"].get("revenue_prior_year")
    _op_inc = output["edgar"].get("operating_income")
    _da     = output["edgar"].get("depreciation_amortization")
    _ca     = output["edgar"].get("current_assets")
    _cl     = output["edgar"].get("current_liabilities")
    _eq     = output["edgar"].get("stockholders_equity")
    _lt_d   = output["edgar"].get("lt_debt")
    _dt     = output["edgar"].get("deuda_total")

    # current_ratio
    _current_ratio = (_ca / _cl) if (_ca is not None and _cl and _cl > 0) else None

    # de_ratio — deuda_total / stockholders_equity
    _de_ratio = None
    if _dt is not None and _eq is not None and _eq > 0:
        _de_ratio = round(_dt / _eq, 4)

    # ebitda = operating_income + D&A
    _ebitda = (_op_inc + _da) if (_op_inc is not None and _da is not None) else None

    # revenue_yoy_calc
    _rev_yoy_calc = None
    if _rev is not None and _rev_py is not None and _rev_py > 0:
        _rev_yoy_calc = round((_rev - _rev_py) / _rev_py, 4)

    # X0.83: roic_calc mejorado — IC neto de cash, fallback a NI cuando op_income es null
    # Para empresas donde EDGAR no reporta operating_income (e.g. seguros, bancos):
    # usar net_income como proxy de NOPAT (ya post-impuestos, sin ajuste adicional)
    _roic_calc = None
    _roic_method = None
    _ni       = output["edgar"].get("net_income")
    _cash_r   = output["edgar"].get("cash_real")
    _st_d_v   = output["edgar"].get("st_debt")

    if _eq is not None and _eq > 0:
        # Invested Capital = Equity + LT Debt + ST Debt - Cash (net IC)
        _ic = (_eq or 0) + (_lt_d or 0) + (_st_d_v or 0) - (_cash_r or 0)
        if _ic > 0:
            if _op_inc is not None:
                _roic_calc = round((_op_inc * 0.75) / _ic, 4)
                _roic_method = "NOPAT/IC"
            elif _ni is not None:
                # Fallback para seguros/bancos: NI/IC (proxy; NI ya es post-tax)
                _roic_calc = round(_ni / _ic, 4)
                _roic_method = "NI/IC_approx"

    output["computed"] = {
        "current_ratio":    round(_current_ratio, 4) if _current_ratio is not None else None,
        "de_ratio":         _de_ratio,
        "ebitda":           int(_ebitda) if _ebitda is not None else None,
        "revenue_yoy_calc": _rev_yoy_calc,
        "roic_calc":        _roic_calc,
        "roic_method":      _roic_method,
        "_nota":            "X0.83: roic_calc=NOPAT/IC (op_income*0.75) o NI/IC (approx para seguros/bancos). IC=Equity+LTDebt+STDebt-Cash",
    }
    _cr_str   = f"{_current_ratio:.2f}" if _current_ratio is not None else "N/D"
    _de_str   = f"{_de_ratio:.2f}"    if _de_ratio is not None else "N/D"
    _yoy_str  = f"{_rev_yoy_calc*100:.1f}%" if _rev_yoy_calc is not None else "N/D"
    _roic_str = f"{_roic_calc*100:.1f}% ({_roic_method})" if _roic_calc is not None else "N/D"
    print(f"  ✓ computed: current_ratio={_cr_str} | de_ratio={_de_str} "
          f"| ebitda={fmt_b(_ebitda)} | rev_yoy={_yoy_str} | roic={_roic_str}")

    # Guardar audit en meta (interno — no para display en Sankey)
    output["meta"]["tier4_audit"] = yf_audit
    if yf_audit.get("ran"):
        output["meta"]["fuentes"].append("yfinance (TIER 4 audit)")

    # ── GUARDAR JSON ──────────────────────────────────────────────────────────
    downloads_dir = os.path.expanduser("~/.openclaw/workspace")
    filename = os.path.join(downloads_dir, f"datos_{ticker.upper()}_{TODAY.replace('-','')}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    # ── Log persistente TIER 4 ────────────────────────────────────────────────
    # Una línea JSONL por corrida → acumula historial en ~/Downloads.
    # Al hacer merge con el log de la Mac externa, tendrás estadísticas
    # cross-machine de confiabilidad real de yfinance.
    LOG_PATH = os.path.join(downloads_dir, "tier4_audit_log.jsonl")
    log_entry = {
        "ts":           datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "ticker":       ticker.upper(),
        "recolectar_v": VERSION,
        "yf_version":   yf_audit.get("yfinance_version"),
        "ran":          yf_audit.get("ran", False),
        "match":        yf_audit.get("match", 0),
        "disagree":     yf_audit.get("disagree", 0),
        "filled":       yf_audit.get("filled", 0),
        "null_in_yf":   yf_audit.get("null_in_yf", 0),
        "success_rate": yf_audit.get("success_rate", "0/0 (0%)"),
        "disagree_fields": [f for f, s in yf_audit.get("detail", {}).items()
                            if isinstance(s, str) and s.startswith("disagree")],
        "source":       "feroldi_recolectar",
    }
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as lf:
            lf.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"  ~ No se pudo escribir log TIER 4: {e}")

    # ── AUTO-NORMALIZAR ────────────────────────────────────────────────────
    # Ejecutar feroldi_normalizar.py si está disponible en el mismo directorio
    import subprocess
    norm_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "feroldi_normalizar.py")
    if os.path.isfile(norm_script):
        result = subprocess.run(
            [sys.executable, norm_script, filename],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  ✅ Normalización automática completada")
        else:
            print(f"  ⚠ Normalización falló (datos crudos guardados igualmente)")
            if result.stderr:
                print(f"    {result.stderr[:120]}")
    else:
        print(f"  ℹ feroldi_normalizar.py no encontrado — datos sin normalizar")

    nd_count = len(output["nd_resumen"]["campos_nd"])
    analyst_target = output["market"].get("analyst_target")
    seg_count = len(edgar.get("segmentos") or []) if edgar.get("segmentos") else 0

    print(f"\n{'='*58}")
    print(f"  ✅ RECOLECCIÓN COMPLETADA — v{VERSION}")
    print(f"  Archivo: {filename}")
    print(f"  Revenue: {fmt_b(output['edgar']['revenue'])} FY{output['edgar']['fy_year']}")
    print(f"  FCF:     {fmt_b(output['edgar']['fcf'])}")
    print(f"  52W:     ${output['market'].get('w52_low')} – ${output['market'].get('w52_high')}")
    print(f"  Beta:    {output['ratios'].get('beta')}")
    print(f"  PE Fwd:  {output['ratios'].get('pe_forward')}")
    if analyst_target:
        print(f"  Analistas: target ${analyst_target} · {consenso}")
    if seg_count:
        print(f"  Segmentos: {seg_count} detectados")
    else:
        print(f"  Segmentos: No disponibles")
    print(f"  N/D:     {nd_count} campo(s) sin resolver")
    if nd_count:
        print(f"  Campos:  {', '.join(output['nd_resumen']['campos_nd'])}")
    print(f"  TIER 4:  {yf_audit.get('success_rate', 'n/a')}")
    print(f"\n  👉 Pega '{filename}' en Claude para el análisis Feroldi")
    print(f"{'='*58}\n")

    return filename


def main():
    parser = argparse.ArgumentParser(
        description=f"Feroldi Recolectar v{VERSION} — recolector local de datos financieros"
    )
    parser.add_argument("ticker", help="Ticker bursátil (ej: AAPL, FSLY)")
    parser.add_argument("precio", type=float,
                        help="Precio actual de referencia (ej: 31.60)")
    parser.add_argument("--no-yfinance", action="store_true",
                        help="Deshabilitar TIER 4 yfinance")
    parser.add_argument("--no-av", action="store_true",
                        help="Deshabilitar Alpha Vantage (TIER 1) — útil para batch sin rate limits")
    args = parser.parse_args()

    import time as _time
    _t0 = _time.time()
    asyncio.run(recolectar(args.ticker.lstrip("$").upper(), args.precio,
                           use_yfinance=not args.no_yfinance,
                           use_av=not args.no_av))
    _elapsed = _time.time() - _t0
    print(f"  ⏱  Recolector: {_elapsed:.1f}s ({_elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
