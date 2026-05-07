#!/usr/bin/env python3
"""
FEROLDI RECOLECTAR — v X0.56
Sistema Feroldi · @patonet
======================================
Recolecta datos financieros con jerarquía de fuentes:
  TIER 1 — EDGAR XBRL     (fuente oficial SEC, máxima fiabilidad)
  TIER 2 — Alpha Vantage  (ratios, métricas, analistas — NUEVO X0.56)
  TIER 3 — TradingView    (performance, competidores)

CAMBIOS X0.56 vs X0.55:
  [NUEVO]   TIER 2 = Alpha Vantage API (reemplaza StockAnalysis + Yahoo)
  [NUEVO]   Sección earnings{} en JSON con EPS history + surprises
  [NUEVO]   Campos: analyst_target, beta, márgenes, ROE/ROA, ratings analistas
  [ELIMINADO] StockAnalysis scraper (frágil, riesgo ban)
  [ELIMINADO] Yahoo Finance / Macrotrends fallback
  [MANTENIDO] TradingView solo para performance + competidores
  [MANTENIDO] EDGAR XBRL como fuente primaria (con BUG-7 fix)

USO:
  export AV_API_KEY="tu_key_alphavantage"
  python3 feroldi_recolectar.py FSLY 31.60

INSTALAR (una sola vez):
  pip3 install aiohttp requests

TIERS:
  TIER 1 — EDGAR XBRL API  (fuente oficial SEC)
  TIER 2 — Alpha Vantage   (ratios, márgenes, analistas, EPS)
  TIER 3 — TradingView     (performance 5D→all-time, competidores)
"""

import asyncio
import aiohttp
import requests
import json
import sys
import re
import os
import time
from datetime import datetime
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────────────────────
VERSION   = "X0.56"
UA        = "patonet@example.com"
AV_KEY    = os.environ.get("AV_API_KEY", "")
AV_BASE   = "https://www.alphavantage.co/query"
AV_SLEEP  = 13          # segundos entre calls AV (5 calls/min en free tier)
TV_HEADERS = {
    "Origin":       "https://www.tradingview.com",
    "Referer":      "https://www.tradingview.com/",
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0"
}
TODAY = datetime.now().strftime("%d-%m-%Y")
ND    = "N/D"

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
    """Convierte valor AV (puede ser string '0.492' o 'None') a float."""
    if v is None or v in ("None", "-", "", "N/A"): return None
    try:
        f = float(v)
        return None if f != f else f   # NaN check
    except: return None

def _int(v):
    if v is None or v in ("None", "-", "", "N/A"): return None
    try: return int(float(v))
    except: return None

def pick(*vals):
    for v in vals:
        if v is not None and v != ND: return v
    return None

# ─── TIER 1: EDGAR XBRL ────────────────────────────────────────────────────────
async def get_edgar(session, ticker):
    result = {}
    try:
        async with session.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": UA}
        ) as r:
            tickers_data = await r.json(content_type=None)

        cik = None
        for _, val in tickers_data.items():
            if val.get("ticker", "").upper() == ticker.upper():
                cik = str(val["cik_str"]).zfill(10)
                result["company_name"] = val.get("title", ticker)
                break

        if not cik:
            print(f"  ⚠ EDGAR: CIK no encontrado para {ticker}")
            return result

        result["cik"] = cik
        print(f"  ✓ EDGAR CIK: {cik}")

        async with session.get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            headers={"User-Agent": UA}
        ) as r:
            facts = await r.json(content_type=None)

        gaap = facts.get("facts", {}).get("us-gaap", {})

        def extract(tags, form="10-K", period="FY"):
            """BUG-7 FIX X0.55: incluye 10-K/A, excluye end vacío, desempate por filed."""
            forms_ok = {form, form + "/A"}
            for tag in tags:
                if tag not in gaap: continue
                units = gaap[tag].get("units", {})
                vals  = units.get("USD", units.get("shares", []))
                fy_vals = [
                    v for v in vals
                    if v.get("form") in forms_ok
                    and v.get("fp") == period
                    and v.get("val") is not None
                    and v.get("end", "")
                ]
                if fy_vals:
                    latest = sorted(fy_vals,
                                    key=lambda x: (x.get("end",""), x.get("filed","")))[-1]
                    return latest.get("val"), latest.get("end","")[:4]
            return None, None

        rev, fy_year = extract([
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax"
        ])
        result["revenue"]  = rev
        result["fy_year"]  = fy_year or ND

        ni, _  = extract(["NetIncomeLoss","NetIncomeLossAvailableToCommonStockholdersBasic"])
        result["net_income"] = ni

        cfo, _ = extract(["NetCashProvidedByUsedInOperatingActivities"])
        result["cfo"] = cfo

        capex, _ = extract(["PaymentsToAcquirePropertyPlantAndEquipment"])
        result["capex"] = capex
        result["fcf"]   = (cfo - capex) if (cfo and capex) else None

        lt_debt, _ = extract(["LongTermDebt","LongTermDebtNoncurrent"])
        st_debt, _ = extract(["LongTermDebtCurrent","ShortTermBorrowings"])
        result["lt_debt"]     = lt_debt
        result["st_debt"]     = st_debt
        result["deuda_total"] = (lt_debt or 0)+(st_debt or 0) if (lt_debt or st_debt) else None

        sbc, _ = extract(["ShareBasedCompensation"])
        result["sbc"] = sbc

        div, _ = extract(["PaymentsOfDividendsCommonStock","PaymentsOfDividends"])
        result["dividendos"] = div

        assets, _   = extract(["Assets"])
        result["total_assets"] = assets

        goodwill, _ = extract(["Goodwill"])
        result["goodwill"] = goodwill

        cash, _ = extract(["CashAndCashEquivalents"])
        sti,  _ = extract(["ShortTermInvestments","AvailableForSaleSecuritiesCurrent"])
        result["cash"] = cash
        result["short_term_investments"] = sti
        result["cash_real"] = (cash or 0)+(sti or 0) if (cash is not None or sti is not None) else None

        shares, _ = extract(["CommonStockSharesOutstanding"], form="10-K", period="FY")
        result["shares"] = shares

        result["segmentos_raw"] = _extract_segments(gaap, rev)

        print(f"  ✓ EDGAR XBRL — FY{fy_year} · Revenue={fmt_b(rev)} · FCF={fmt_b(result.get('fcf'))}")

    except Exception as e:
        print(f"  ⚠ EDGAR error: {e}")
    return result


def _extract_segments(gaap, total_revenue):
    segments = []
    seg_tags = [k for k in gaap.keys() if "Segment" in k and "Revenue" in k]
    for tag in seg_tags[:8]:
        units   = gaap[tag].get("units", {}).get("USD", [])
        fy_vals = [v for v in units if v.get("form") == "10-K" and v.get("fp") == "FY"]
        if fy_vals:
            latest = sorted(fy_vals, key=lambda x: x.get("end",""))[-1]
            val = latest.get("val")
            if val and total_revenue and val < total_revenue:
                name = tag.replace("RevenueFrom","").replace("Revenue","").replace("Segment"," ")
                segments.append({"nombre": name.strip(), "revenue": val})
    return segments


# ─── TIER 2: ALPHA VANTAGE ─────────────────────────────────────────────────────
async def get_alphavantage(ticker):
    """
    Obtiene ratios, métricas y EPS desde Alpha Vantage.
    SECUENCIAL por rate limit (5 calls/min en free tier).
    Requiere: export AV_API_KEY="tu_key"
    """
    if not AV_KEY:
        print("  ⚠ AV_API_KEY no configurado — saltando Alpha Vantage")
        print("    Configura: export AV_API_KEY='tu_key'")
        return {}, {}

    async def av_call(function):
        params = {"function": function, "symbol": ticker, "apikey": AV_KEY}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(AV_BASE, params=params,
                                  timeout=aiohttp.ClientTimeout(total=20)) as r:
                    data = await r.json(content_type=None)
            if "Information" in data or "Note" in data:
                msg = data.get("Information") or data.get("Note","")
                print(f"  ⚠ AV rate limit ({function}): {msg[:90]}")
                return {}
            if "Error Message" in data:
                print(f"  ⚠ AV error ({function}): {data['Error Message'][:80]}")
                return {}
            return data
        except Exception as e:
            print(f"  ⚠ AV error ({function}): {e}")
            return {}

    # ── CALL 1: OVERVIEW ─────────────────────────────────────────────────────
    print(f"  📡 AV OVERVIEW...")
    ov = await av_call("OVERVIEW")

    await asyncio.sleep(AV_SLEEP)   # respeta rate limit

    # ── CALL 2: EARNINGS ─────────────────────────────────────────────────────
    print(f"  📡 AV EARNINGS...")
    earn = await av_call("EARNINGS")

    # ── PROCESAR OVERVIEW ─────────────────────────────────────────────────────
    result_ov = {}
    if ov and "Symbol" in ov:
        gp_ttm  = _float(ov.get("GrossProfitTTM")) or 0
        rev_ttm = _float(ov.get("RevenueTTM")) or 1
        gm_calc = (gp_ttm / rev_ttm) if rev_ttm else None

        result_ov = {
            # Precio y mercado
            "market_cap":     _float(ov.get("MarketCapitalization")),
            "w52_high":       _float(ov.get("52WeekHigh")),
            "w52_low":        _float(ov.get("52WeekLow")),
            "shares_av":      _int(ov.get("SharesOutstanding")),
            "percent_insiders": _float(ov.get("PercentInsiders")),
            # Valoración
            "pe_ttm":         _float(ov.get("PERatio")),
            "pe_forward":     _float(ov.get("ForwardPE")),
            "peg":            _float(ov.get("PEGRatio")),
            "ev_ebitda":      _float(ov.get("EVToEBITDA")),
            "ev_revenue":     _float(ov.get("EVToRevenue")),
            "pb":             _float(ov.get("PriceToBookRatio")),
            "p_sales":        _float(ov.get("PriceToSalesRatioTTM")),
            # Earnings
            "eps_ttm":        _float(ov.get("DilutedEPSTTM")),
            # Márgenes y rentabilidad
            "margen_bruto":   gm_calc,
            "margen_op":      _float(ov.get("OperatingMarginTTM")),
            "margen_neto":    _float(ov.get("ProfitMargin")),
            "roe":            _float(ov.get("ReturnOnEquityTTM")),
            "roa":            _float(ov.get("ReturnOnAssetsTTM")),
            # Riesgo y dividendos
            "beta":           _float(ov.get("Beta")),
            "dividend_yield": _float(ov.get("DividendYield")),
            # Crecimiento reciente
            "revenue_yoy_q":  _float(ov.get("QuarterlyRevenueGrowthYOY")),
            "earnings_yoy_q": _float(ov.get("QuarterlyEarningsGrowthYOY")),
            # Analistas
            "analyst_target":      _float(ov.get("AnalystTargetPrice")),
            "analyst_strong_buy":  _int(ov.get("AnalystRatingStrongBuy")),
            "analyst_buy":         _int(ov.get("AnalystRatingBuy")),
            "analyst_hold":        _int(ov.get("AnalystRatingHold")),
            "analyst_sell":        _int(ov.get("AnalystRatingSell")),
            "analyst_strong_sell": _int(ov.get("AnalystRatingStrongSell")),
            # Info empresa
            "exchange":       ov.get("Exchange"),
            "sector":         ov.get("Sector"),
            "industry":       ov.get("Industry"),
            "latest_quarter": ov.get("LatestQuarter"),
            "ebitda_ttm":     _float(ov.get("EBITDA")),
        }
        resueltos = sum(1 for v in result_ov.values() if v is not None)
        print(f"  ✓ AV OVERVIEW — {resueltos}/{len(result_ov)} campos resueltos")
    else:
        print(f"  ⚠ AV OVERVIEW: sin datos para {ticker}")

    # ── PROCESAR EARNINGS ─────────────────────────────────────────────────────
    result_earn = {}
    if earn and "annualEarnings" in earn:
        annual    = earn.get("annualEarnings", [])[:5]
        quarterly = earn.get("quarterlyEarnings", [])[:4]
        result_earn = {
            "annual_eps": [
                {"fy":  e.get("fiscalDateEnding","")[:4],
                 "eps": _float(e.get("reportedEPS"))}
                for e in annual
            ],
            "quarterly_eps": [
                {
                    "fecha":       e.get("fiscalDateEnding"),
                    "reported":    _float(e.get("reportedEPS")),
                    "estimated":   _float(e.get("estimatedEPS")),
                    "surprise_pct": _float(e.get("surprisePercentage")),
                    "report_date": e.get("reportedDate"),
                }
                for e in quarterly
            ],
        }
        print(f"  ✓ AV EARNINGS — {len(annual)} años · {len(quarterly)} trimestres")
    else:
        print(f"  ⚠ AV EARNINGS: sin datos para {ticker}")

    return result_ov, result_earn


# ─── TIER 3: TRADINGVIEW (solo performance + competidores) ─────────────────────
async def get_tradingview(session, ticker):
    """Solo performance histórica. Precio y ratios ahora vienen de Alpha Vantage."""
    result = {}
    columns = [
        "close", "price_52_week_high", "price_52_week_low",
        "market_cap_basic", "price_earnings_ttm",
        "earnings_per_share_diluted_ttm",
        "Perf.5D", "Perf.1M", "Perf.3M", "Perf.6M",
        "Perf.YTD", "Perf.Y", "Perf.5Y", "Perf.10Y", "Perf.All"
    ]
    for exchange in ["NASDAQ", "NYSE", "AMEX", "TSX"]:
        try:
            payload = {
                "symbols": {"tickers": [f"{exchange}:{ticker.upper()}"]},
                "columns": columns
            }
            async with session.post(
                "https://scanner.tradingview.com/america/scan",
                json=payload, headers=TV_HEADERS
            ) as r:
                data = await r.json(content_type=None)

            rows = data.get("data", [])
            if rows and rows[0].get("d"):
                d = rows[0]["d"]
                result["exchange_tv"]   = exchange
                result["precio_tv"]     = d[0]
                result["w52_high_tv"]   = d[1]
                result["w52_low_tv"]    = d[2]
                result["market_cap_tv"] = d[3]
                result["performance"]   = {
                    "5D": d[6], "1M": d[7], "3M": d[8], "6M": d[9],
                    "YTD": d[10], "1Y": d[11], "5Y": d[12], "10Y": d[13], "All": d[14]
                }
                print(f"  ✓ TradingView — {exchange}:{ticker} @ ${d[0]} (solo performance)")
                break
        except: continue

    if not result:
        print(f"  ⚠ TradingView: no se encontró {ticker}")
    return result


async def get_competidores_tv(session, tickers_list):
    results = []
    columns = ["close","price_52_week_high","price_52_week_low",
               "market_cap_basic","price_earnings_ttm","earnings_per_share_diluted_ttm"]
    for comp in tickers_list:
        found = False
        for exchange in ["NASDAQ","NYSE","AMEX"]:
            try:
                payload = {"symbols":{"tickers":[f"{exchange}:{comp.upper()}"]},
                           "columns": columns}
                async with session.post(
                    "https://scanner.tradingview.com/america/scan",
                    json=payload, headers=TV_HEADERS
                ) as r:
                    data = await r.json(content_type=None)
                rows = data.get("data",[])
                if rows and rows[0].get("d"):
                    d = rows[0]["d"]
                    results.append({"ticker":comp.upper(), "exchange":exchange,
                                    "precio":d[0], "w52_high":d[1], "w52_low":d[2],
                                    "market_cap":d[3], "pe_ttm":d[4], "eps_ttm":d[5],
                                    "revenue_fy": ND, "op_margin": ND, "net_margin": ND})
                    found = True; break
            except: continue
        if not found:
            results.append({"ticker":comp.upper(), "precio": ND})
    return results


# ─── MAIN ──────────────────────────────────────────────────────────────────────
async def recolectar(ticker, precio_usuario):
    print(f"\n{'='*58}")
    print(f"  FEROLDI RECOLECTAR v {VERSION} — ${ticker.upper()} @ ${precio_usuario}")
    print(f"  {TODAY}")
    if not AV_KEY:
        print(f"  ⚠ AV_API_KEY no configurado (muchos campos serán N/D)")
    print(f"{'='*58}\n")

    # ── RONDA 1: EDGAR + TradingView en paralelo ─────────────────────────────
    print("📡 RONDA 1 — EDGAR + TradingView en paralelo...\n")
    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        edgar_task = asyncio.create_task(get_edgar(session, ticker))
        tv_task    = asyncio.create_task(get_tradingview(session, ticker))
        edgar, tv  = await asyncio.gather(edgar_task, tv_task)

    # ── RONDA 2: Alpha Vantage (secuencial) ──────────────────────────────────
    print("\n📡 RONDA 2 — Alpha Vantage (secuencial, rate limit ~30s)...\n")
    av_ov, av_earn = await get_alphavantage(ticker)

    # ── ENSAMBLAR JSON ────────────────────────────────────────────────────────
    precio_ref     = float(precio_usuario)
    market_cap_calc = (edgar.get("shares") * precio_ref) if edgar.get("shares") else None

    # Analistas: calcular consenso
    strong_buy = av_ov.get("analyst_strong_buy") or 0
    buy        = av_ov.get("analyst_buy") or 0
    hold       = av_ov.get("analyst_hold") or 0
    sell       = av_ov.get("analyst_sell") or 0
    strong_sell= av_ov.get("analyst_strong_sell") or 0
    total_ratings = strong_buy + buy + hold + sell + strong_sell

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
            "fuentes":       ["EDGAR XBRL", "Alpha Vantage", "TradingView"]
        },
        "edgar": {
            "cik":                   edgar.get("cik", ND),
            "fy_year":               edgar.get("fy_year", ND),
            "revenue":               edgar.get("revenue"),
            "net_income":            edgar.get("net_income"),
            "cfo":                   edgar.get("cfo"),
            "capex":                 edgar.get("capex"),
            "fcf":                   edgar.get("fcf"),
            "lt_debt":               edgar.get("lt_debt"),
            "st_debt":               edgar.get("st_debt"),
            "deuda_total":           edgar.get("deuda_total"),
            "sbc":                   edgar.get("sbc"),
            "dividendos":            edgar.get("dividendos"),
            "total_assets":          edgar.get("total_assets"),
            "goodwill":              edgar.get("goodwill"),
            "cash":                  edgar.get("cash"),
            "short_term_investments": edgar.get("short_term_investments"),
            "cash_real":             edgar.get("cash_real"),
            "shares":                edgar.get("shares"),
            "segmentos":             edgar.get("segmentos_raw", [])
        },
        "market": {
            "precio_actual":    pick(tv.get("precio_tv"), precio_ref),
            "w52_high":         pick(av_ov.get("w52_high"), tv.get("w52_high_tv")),
            "w52_low":          pick(av_ov.get("w52_low"), tv.get("w52_low_tv")),
            "market_cap":       pick(av_ov.get("market_cap"), market_cap_calc,
                                     tv.get("market_cap_tv")),
            "pe_ttm":           pick(av_ov.get("pe_ttm")),
            "eps_ttm":          pick(av_ov.get("eps_ttm")),
            # Analistas (nuevo X0.56)
            "analyst_target":      av_ov.get("analyst_target"),
            "analyst_strong_buy":  av_ov.get("analyst_strong_buy"),
            "analyst_buy":         av_ov.get("analyst_buy"),
            "analyst_hold":        av_ov.get("analyst_hold"),
            "analyst_sell":        av_ov.get("analyst_sell"),
            "analyst_strong_sell": av_ov.get("analyst_strong_sell"),
            "analyst_consenso":    f"{strong_buy+buy} Buy / {hold} Hold / {sell+strong_sell} Sell"
                                   if total_ratings > 0 else ND,
            "latest_quarter":      av_ov.get("latest_quarter"),
        },
        "ratios": {
            "pe_forward":     pick(av_ov.get("pe_forward")),
            "peg":            pick(av_ov.get("peg")),
            "ev_ebitda":      pick(av_ov.get("ev_ebitda")),
            "ev_revenue":     pick(av_ov.get("ev_revenue")),
            "pb":             pick(av_ov.get("pb")),
            "p_sales":        pick(av_ov.get("p_sales")),
            "margen_bruto":   pick(av_ov.get("margen_bruto")),
            "margen_op":      pick(av_ov.get("margen_op")),
            "margen_neto":    pick(av_ov.get("margen_neto")),
            "margen_ebitda":  None,         # no disponible en AV OVERVIEW TTM
            "roic":           None,         # AV no lo tiene en OVERVIEW
            "roe":            pick(av_ov.get("roe")),
            "roa":            pick(av_ov.get("roa")),
            "de_ratio":       None,         # calcular de edgar si es necesario
            "current_ratio":  None,         # no disponible en AV OVERVIEW
            "dividend_yield": pick(av_ov.get("dividend_yield")),
            "beta":           pick(av_ov.get("beta")),
            "revenue_yoy":    pick(av_ov.get("revenue_yoy_q")),   # quarterly YoY
            "ni_yoy":         pick(av_ov.get("earnings_yoy_q")),
            "eps_proj":       None,         # en EARNINGS se puede calcular si hay estimados
            "percent_insiders": av_ov.get("percent_insiders"),
        },
        "earnings": av_earn,                # NUEVO X0.56
        "performance": tv.get("performance", {}),
        "competidores": [],
        "nd_resumen": {
            "campos_nd": []     # se llena abajo
        }
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

    # ── GUARDAR JSON ──────────────────────────────────────────────────────────
    filename = f"datos_{ticker.upper()}_{TODAY.replace('-','')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    nd_count = len(output["nd_resumen"]["campos_nd"])
    analyst_target = output["market"].get("analyst_target")

    print(f"\n{'='*58}")
    print(f"  ✅ RECOLECCIÓN COMPLETADA — v{VERSION}")
    print(f"  Archivo: {filename}")
    print(f"  Revenue: {fmt_b(output['edgar']['revenue'])} FY{output['edgar']['fy_year']}")
    print(f"  FCF:     {fmt_b(output['edgar']['fcf'])}")
    print(f"  52W:     ${output['market'].get('w52_low')} – ${output['market'].get('w52_high')}")
    print(f"  Beta:    {output['ratios'].get('beta')}")
    print(f"  PE Fwd:  {output['ratios'].get('pe_forward')}")
    if analyst_target:
        consenso = output['market'].get('analyst_consenso','N/D')
        print(f"  Analistas: target ${analyst_target} · {consenso}")
    print(f"  N/D:     {nd_count} campo(s) sin resolver")
    if nd_count:
        print(f"  Campos:  {', '.join(output['nd_resumen']['campos_nd'])}")
    print(f"\n  👉 Pega '{filename}' en Claude para el análisis Feroldi")
    print(f"{'='*58}\n")

    return filename


def main():
    if len(sys.argv) < 3:
        print("USO: python3 feroldi_recolectar.py TICKER PRECIO")
        print("EJ:  python3 feroldi_recolectar.py FSLY 31.60")
        print("")
        print("REQUISITO: export AV_API_KEY='tu_key_alphavantage'")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    try:
        precio = float(sys.argv[2])
    except ValueError:
        print(f"Error: '{sys.argv[2]}' no es un precio válido")
        sys.exit(1)

    asyncio.run(recolectar(ticker, precio))


if __name__ == "__main__":
    main()
