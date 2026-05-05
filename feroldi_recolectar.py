#!/usr/bin/env python3
"""
FEROLDI RECOLECTAR — v X0.50
Sistema Feroldi · @patonet
======================================
Recolecta datos financieros en paralelo con jerarquía TIER 1→4.
Genera datos_[TICKER]_[FECHA].json listo para pegar en Claude/ChatGPT/Gemini.

USO:
  python3 feroldi_recolectar.py FSLR 211.39

INSTALAR (una sola vez):
  pip3 install aiohttp requests beautifulsoup4

TIER 1 — EDGAR XBRL API  (fuente oficial SEC, máxima fiabilidad)
TIER 2 — StockAnalysis   (ratios, márgenes, proyecciones)
TIER 3 — TradingView     (precio, 52W, performance, competidores)
TIER 4 — Macrotrends / Yahoo Finance (fallback para N/D)
"""

import asyncio
import aiohttp
import requests
import json
import sys
import re
import os
from datetime import datetime, date
from bs4 import BeautifulSoup

# ─── CONFIG ────────────────────────────────────────────────────────────────────
UA = "patonet@example.com"          # User-Agent para EDGAR
TV_HEADERS = {
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}
TODAY = datetime.now().strftime("%d-%m-%Y")
ND = "N/D"

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def fmt_b(v):
    """Formatea número a $XB o $XM."""
    if v is None:
        return ND
    try:
        v = float(v)
        if abs(v) >= 1e9:
            return f"${v/1e9:.2f}B"
        elif abs(v) >= 1e6:
            return f"${v/1e6:.1f}M"
        else:
            return f"${v:,.0f}"
    except:
        return ND

def pct(v):
    if v is None:
        return ND
    try:
        return f"{float(v)*100:.1f}%"
    except:
        return ND

def safe(v, decimals=2):
    if v is None:
        return ND
    try:
        return round(float(v), decimals)
    except:
        return ND

# ─── TIER 1: EDGAR XBRL ────────────────────────────────────────────────────────
async def get_edgar(session, ticker):
    """Obtiene datos financieros desde EDGAR XBRL API."""
    result = {}
    try:
        # Paso 1: Obtener CIK
        async with session.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": UA}
        ) as r:
            tickers_data = await r.json(content_type=None)

        cik = None
        ticker_upper = ticker.upper()
        for key, val in tickers_data.items():
            if val.get("ticker", "").upper() == ticker_upper:
                cik = str(val["cik_str"]).zfill(10)
                result["company_name"] = val.get("title", ticker)
                break

        if not cik:
            print(f"  ⚠ EDGAR: CIK no encontrado para {ticker}")
            return result

        result["cik"] = cik
        print(f"  ✓ EDGAR CIK: {cik}")

        # Paso 2: Obtener company facts
        async with session.get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            headers={"User-Agent": UA}
        ) as r:
            facts = await r.json(content_type=None)

        gaap = facts.get("facts", {}).get("us-gaap", {})

        def extract(tags, form="10-K", period="FY"):
            """Extrae el valor más reciente de una lista de tags GAAP."""
            for tag in tags:
                if tag not in gaap:
                    continue
                units = gaap[tag].get("units", {})
                vals = units.get("USD", units.get("shares", []))
                fy_vals = [
                    v for v in vals
                    if v.get("form") == form and v.get("fp") == period
                    and v.get("val") is not None
                ]
                if fy_vals:
                    latest = sorted(fy_vals, key=lambda x: x.get("end", ""))[-1]
                    return latest.get("val"), latest.get("end", "")[:4]
            return None, None

        # Revenue
        rev, fy_year = extract([
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax"
        ])
        result["revenue"] = rev
        result["fy_year"] = fy_year or "N/D"

        # Net Income
        ni, _ = extract(["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"])
        result["net_income"] = ni

        # CFO
        cfo, _ = extract(["NetCashProvidedByUsedInOperatingActivities"])
        result["cfo"] = cfo

        # Capex (tag exacto EDGAR)
        capex, _ = extract(["PaymentsToAcquirePropertyPlantAndEquipment"])
        result["capex"] = capex

        # FCF = CFO - Capex
        if cfo is not None and capex is not None:
            result["fcf"] = cfo - capex
        else:
            result["fcf"] = None

        # Deuda
        lt_debt, _ = extract(["LongTermDebt", "LongTermDebtNoncurrent"])
        st_debt, _ = extract(["LongTermDebtCurrent", "ShortTermBorrowings"])
        result["lt_debt"] = lt_debt
        result["st_debt"] = st_debt
        result["deuda_total"] = (lt_debt or 0) + (st_debt or 0) if (lt_debt or st_debt) else None

        # SBC
        sbc, _ = extract(["ShareBasedCompensation"])
        result["sbc"] = sbc

        # Dividendos
        div, _ = extract(["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"])
        result["dividendos"] = div

        # Balance
        assets, _ = extract(["Assets"])
        result["total_assets"] = assets

        goodwill, _ = extract(["Goodwill"])
        result["goodwill"] = goodwill

        # Cash real = Cash + ShortTermInvestments
        cash, _ = extract(["CashAndCashEquivalents"])
        sti, _ = extract(["ShortTermInvestments", "AvailableForSaleSecuritiesCurrent"])
        result["cash"] = cash
        result["short_term_investments"] = sti
        result["cash_real"] = (cash or 0) + (sti or 0) if (cash is not None or sti is not None) else None

        # Shares
        shares, _ = extract(["CommonStockSharesOutstanding"], form="10-K", period="FY")
        result["shares"] = shares

        # Segmentos (intentar extraer del 10-K)
        result["segmentos_raw"] = _extract_segments(gaap, rev)

        print(f"  ✓ EDGAR XBRL — FY{fy_year} · Revenue={fmt_b(rev)} · FCF={fmt_b(result.get('fcf'))}")

    except Exception as e:
        print(f"  ⚠ EDGAR error: {e}")

    return result


def _extract_segments(gaap, total_revenue):
    """Intenta extraer segmentos de revenue del JSON XBRL."""
    segments = []
    seg_tags = [k for k in gaap.keys() if "Segment" in k and "Revenue" in k]
    for tag in seg_tags[:8]:
        units = gaap[tag].get("units", {}).get("USD", [])
        fy_vals = [v for v in units if v.get("form") == "10-K" and v.get("fp") == "FY"]
        if fy_vals:
            latest = sorted(fy_vals, key=lambda x: x.get("end", ""))[-1]
            val = latest.get("val")
            if val and total_revenue and val < total_revenue:
                name = tag.replace("RevenueFrom", "").replace("Revenue", "").replace("Segment", " ")
                segments.append({"nombre": name.strip(), "revenue": val})
    return segments


# ─── TIER 2: STOCKANALYSIS ─────────────────────────────────────────────────────
async def get_stockanalysis(session, ticker):
    """Obtiene ratios y proyecciones de StockAnalysis.com."""
    result = {}
    try:
        url = f"https://stockanalysis.com/stocks/{ticker.lower()}/"
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
            html = await r.text()

        soup = BeautifulSoup(html, "html.parser")

        # Extraer datos del JSON embebido en la página
        scripts = soup.find_all("script", type="application/json")
        for script in scripts:
            try:
                data = json.loads(script.string or "")
                # Buscar datos financieros en el JSON
                if isinstance(data, dict):
                    props = data.get("props", {}).get("pageProps", {})
                    if props:
                        info = props.get("info", {})
                        if info:
                            result["pe_ttm"] = info.get("pe")
                            result["pe_forward"] = info.get("peForward")
                            result["peg"] = info.get("peg")
                            result["eps_ttm"] = info.get("eps")
                            result["eps_forward"] = info.get("epsForward")
                            result["market_cap"] = info.get("marketCap")
                            result["ev_ebitda"] = info.get("evEbitda")
                            result["pb"] = info.get("pb")
                            result["beta"] = info.get("beta")
                            result["dividend_yield"] = info.get("dividendYield")
                            result["next_earnings"] = info.get("nextEarnings")
                            result["revenue_guide"] = info.get("revenueGuide")
            except:
                continue

        # Si no encontró via JSON, intentar scraping directo de la tabla de stats
        if not result.get("pe_ttm"):
            stat_items = soup.select("[data-test='stat-value']") or soup.select(".stat-value")
            # Intentar extraer de meta tags o texto estructurado
            text = soup.get_text()
            # Buscar P/E ratio
            pe_match = re.search(r"P/E Ratio[:\s]+([0-9.]+)", text)
            if pe_match:
                result["pe_ttm"] = float(pe_match.group(1))

        # Intentar financials page para márgenes
        fin_url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/"
        async with session.get(fin_url, headers={"User-Agent": "Mozilla/5.0"}) as r2:
            html2 = await r2.text()

        soup2 = BeautifulSoup(html2, "html.parser")
        for script in soup2.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "")
                props = data.get("props", {}).get("pageProps", {})
                fin_data = props.get("financials", {}) or props.get("data", {})
                if fin_data:
                    # Extraer márgenes y ratios
                    rows = fin_data.get("annual", {})
                    if rows:
                        # Buscar gross margin, net margin, etc.
                        for key, label in [
                            ("grossMargin", "margen_bruto"),
                            ("operatingMargin", "margen_op"),
                            ("netMargin", "margen_neto"),
                            ("ebitdaMargin", "margen_ebitda"),
                            ("roic", "roic"),
                            ("roe", "roe"),
                            ("roa", "roa"),
                            ("debtToEquity", "de_ratio"),
                            ("currentRatio", "current_ratio"),
                            ("revenueGrowth", "revenue_yoy"),
                            ("netIncomeGrowth", "ni_yoy"),
                        ]:
                            val_list = rows.get(key, [])
                            if val_list and isinstance(val_list, list):
                                result[label] = val_list[-1] if val_list else None
            except:
                continue

        nd_count = sum(1 for v in result.values() if v is None)
        print(f"  ✓ StockAnalysis — {len(result)} campos · {nd_count} N/D")

    except Exception as e:
        print(f"  ⚠ StockAnalysis error: {e}")

    return result


# ─── TIER 3: TRADINGVIEW ───────────────────────────────────────────────────────
async def get_tradingview(session, ticker):
    """Obtiene precio, 52W range y performance de TradingView Scanner API."""
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
                json=payload,
                headers=TV_HEADERS
            ) as r:
                data = await r.json(content_type=None)

            rows = data.get("data", [])
            if rows and rows[0].get("d"):
                d = rows[0]["d"]
                result["exchange"] = exchange
                result["precio_actual"] = d[0]
                result["w52_high"] = d[1]
                result["w52_low"] = d[2]
                result["market_cap_tv"] = d[3]
                result["pe_ttm_tv"] = d[4]
                result["eps_ttm_tv"] = d[5]
                result["perf"] = {
                    "5D": d[6], "1M": d[7], "3M": d[8], "6M": d[9],
                    "YTD": d[10], "1Y": d[11], "5Y": d[12], "10Y": d[13], "All": d[14]
                }
                print(f"  ✓ TradingView — {exchange}:{ticker} @ ${result['precio_actual']}")
                break
        except Exception as e:
            continue

    if not result:
        print(f"  ⚠ TradingView: no se encontró {ticker} en ningún exchange")

    return result


async def get_competidores_tv(session, tickers_list):
    """Obtiene datos de competidores desde TradingView."""
    results = []
    columns = [
        "close", "price_52_week_high", "price_52_week_low",
        "market_cap_basic", "price_earnings_ttm", "earnings_per_share_diluted_ttm"
    ]

    for comp in tickers_list:
        found = False
        for exchange in ["NASDAQ", "NYSE", "AMEX"]:
            try:
                payload = {
                    "symbols": {"tickers": [f"{exchange}:{comp.upper()}"]},
                    "columns": columns
                }
                async with session.post(
                    "https://scanner.tradingview.com/america/scan",
                    json=payload,
                    headers=TV_HEADERS
                ) as r:
                    data = await r.json(content_type=None)

                rows = data.get("data", [])
                if rows and rows[0].get("d"):
                    d = rows[0]["d"]
                    results.append({
                        "ticker": comp.upper(),
                        "exchange": exchange,
                        "precio": d[0],
                        "w52_high": d[1],
                        "w52_low": d[2],
                        "market_cap": d[3],
                        "pe_ttm": d[4],
                        "eps_ttm": d[5],
                        "revenue_fy": ND,
                        "op_margin": ND,
                        "net_margin": ND
                    })
                    found = True
                    break
            except:
                continue
        if not found:
            results.append({"ticker": comp.upper(), "precio": ND})

    return results


# ─── TIER 4: MACROTRENDS / YAHOO (fallback N/D) ────────────────────────────────
async def get_tier4_fallback(session, ticker, nd_fields):
    """Intenta resolver N/D con Macrotrends y Yahoo Finance."""
    result = {}

    if not nd_fields:
        return result

    print(f"\n  🔄 Ronda 2 — buscando {len(nd_fields)} N/D en TIER 4...")

    # Yahoo Finance para datos básicos faltantes
    try:
        yahoo_url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker.upper()}"
        modules = "defaultKeyStatistics,financialData,summaryDetail"
        async with session.get(
            f"{yahoo_url}?modules={modules}",
            headers={"User-Agent": "Mozilla/5.0"}
        ) as r:
            yahoo_data = await r.json(content_type=None)

        summary = yahoo_data.get("quoteSummary", {}).get("result", [{}])[0]
        key_stats = summary.get("defaultKeyStatistics", {})
        fin_data = summary.get("financialData", {})
        summary_detail = summary.get("summaryDetail", {})

        def yval(d, key):
            v = d.get(key, {})
            return v.get("raw") if isinstance(v, dict) else v

        field_map = {
            "peg": (key_stats, "pegRatio"),
            "pe_forward": (fin_data, "forwardPE"),
            "eps_forward": (key_stats, "forwardEps"),
            "beta": (summary_detail, "beta"),
            "dividend_yield": (summary_detail, "dividendYield"),
            "de_ratio": (fin_data, "debtToEquity"),
            "current_ratio": (fin_data, "currentRatio"),
            "margen_bruto": (fin_data, "grossMargins"),
            "margen_op": (fin_data, "operatingMargins"),
            "margen_neto": (fin_data, "profitMargins"),
            "roic": (fin_data, "returnOnAssets"),  # approx
            "roe": (fin_data, "returnOnEquity"),
        }

        for field in nd_fields:
            if field in field_map:
                d, key = field_map[field]
                val = yval(d, key)
                if val is not None:
                    result[field] = val
                    print(f"    ✓ {field} = {val} (Yahoo Finance)")

    except Exception as e:
        print(f"  ⚠ Yahoo Finance error: {e}")

    return result


# ─── MAIN ──────────────────────────────────────────────────────────────────────
async def recolectar(ticker, precio_usuario):
    print(f"\n{'='*55}")
    print(f"  FEROLDI RECOLECTAR v X0.50 — ${ticker.upper()} @ ${precio_usuario}")
    print(f"  {TODAY}")
    print(f"{'='*55}\n")

    print("📡 RONDA 1 — TIER 1+2+3 en paralelo...\n")

    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Ejecutar TIER 1, 2 y 3 en paralelo
        edgar_task = asyncio.create_task(get_edgar(session, ticker))
        sa_task = asyncio.create_task(get_stockanalysis(session, ticker))
        tv_task = asyncio.create_task(get_tradingview(session, ticker))

        edgar, sa, tv = await asyncio.gather(edgar_task, sa_task, tv_task)

        # Detectar N/D para Ronda 2
        all_data = {**edgar, **sa, **tv}
        critical_fields = [
            "pe_ttm", "pe_forward", "peg", "eps_ttm", "eps_forward",
            "margen_bruto", "margen_op", "margen_neto", "margen_ebitda",
            "roic", "roe", "roa", "de_ratio", "current_ratio",
            "beta", "dividend_yield", "revenue_yoy", "ni_yoy"
        ]
        nd_fields = [f for f in critical_fields if all_data.get(f) is None]

        # Ronda 2: TIER 4 para N/D
        tier4 = {}
        if nd_fields:
            tier4 = await get_tier4_fallback(session, ticker, nd_fields)

        # Competidores (se piden en Ronda 1 pero procesamos aquí)
        # Los competidores específicos los determinará Claude; aquí dejamos placeholder
        competidores = []

    # ─── ENSAMBLAR JSON FINAL ───────────────────────────────────────────────────
    # Prioridad: EDGAR > StockAnalysis > TradingView > Yahoo/Tier4

    def pick(*vals):
        for v in vals:
            if v is not None and v != ND:
                return v
        return None

    precio_ref = float(precio_usuario)
    market_cap_calc = None
    if edgar.get("shares") and precio_ref:
        market_cap_calc = edgar["shares"] * precio_ref

    output = {
        "meta": {
            "version": "X0.50",
            "ticker": ticker.upper(),
            "precio_usuario": precio_ref,
            "exchange": tv.get("exchange", ND),
            "fecha": TODAY,
            "company_name": edgar.get("company_name", ticker.upper()),
            "fuentes": ["EDGAR XBRL", "StockAnalysis", "TradingView", "Yahoo Finance"]
        },
        "edgar": {
            "cik": edgar.get("cik", ND),
            "fy_year": edgar.get("fy_year", ND),
            "revenue": edgar.get("revenue"),
            "net_income": edgar.get("net_income"),
            "cfo": edgar.get("cfo"),
            "capex": edgar.get("capex"),
            "fcf": edgar.get("fcf"),
            "lt_debt": edgar.get("lt_debt"),
            "st_debt": edgar.get("st_debt"),
            "deuda_total": edgar.get("deuda_total"),
            "sbc": edgar.get("sbc"),
            "dividendos": edgar.get("dividendos"),
            "total_assets": edgar.get("total_assets"),
            "goodwill": edgar.get("goodwill"),
            "cash": edgar.get("cash"),
            "short_term_investments": edgar.get("short_term_investments"),
            "cash_real": edgar.get("cash_real"),
            "shares": edgar.get("shares"),
            "segmentos": edgar.get("segmentos_raw", [])
        },
        "market": {
            "precio_actual": pick(tv.get("precio_actual"), precio_ref),
            "w52_high": tv.get("w52_high"),
            "w52_low": tv.get("w52_low"),
            "market_cap": pick(market_cap_calc, tv.get("market_cap_tv"), sa.get("market_cap")),
            "pe_ttm": pick(sa.get("pe_ttm"), tv.get("pe_ttm_tv"), tier4.get("pe_ttm")),
            "eps_ttm": pick(sa.get("eps_ttm"), tv.get("eps_ttm_tv"), tier4.get("eps_ttm"))
        },
        "ratios": {
            "pe_forward": pick(sa.get("pe_forward"), tier4.get("pe_forward")),
            "peg": pick(sa.get("peg"), tier4.get("peg")),
            "ev_ebitda": pick(sa.get("ev_ebitda")),
            "pb": pick(sa.get("pb")),
            "margen_bruto": pick(sa.get("margen_bruto"), tier4.get("margen_bruto")),
            "margen_op": pick(sa.get("margen_op"), tier4.get("margen_op")),
            "margen_neto": pick(sa.get("margen_neto"), tier4.get("margen_neto")),
            "margen_ebitda": pick(sa.get("margen_ebitda")),
            "roic": pick(sa.get("roic"), tier4.get("roic")),
            "roe": pick(sa.get("roe"), tier4.get("roe")),
            "roa": pick(sa.get("roa"), tier4.get("roa")),
            "de_ratio": pick(sa.get("de_ratio"), tier4.get("de_ratio")),
            "current_ratio": pick(sa.get("current_ratio"), tier4.get("current_ratio")),
            "dividend_yield": pick(sa.get("dividend_yield"), tier4.get("dividend_yield")),
            "beta": pick(sa.get("beta"), tier4.get("beta")),
            "revenue_yoy": pick(sa.get("revenue_yoy"), tier4.get("revenue_yoy")),
            "ni_yoy": pick(sa.get("ni_yoy"), tier4.get("ni_yoy")),
            "eps_proj": pick(sa.get("eps_forward"), tier4.get("eps_forward"))
        },
        "performance": tv.get("perf", {}),
        "competidores": competidores,
        "next_earnings": sa.get("next_earnings", ND),
        "revenue_guide": sa.get("revenue_guide", ND),
        "nd_resumen": {
            "campos_nd": [
                k for k, v in {
                    **{f"edgar.{k}": v for k, v in {
                        "revenue": edgar.get("revenue"),
                        "net_income": edgar.get("net_income"),
                        "fcf": edgar.get("fcf"),
                        "deuda_total": edgar.get("deuda_total"),
                        "cash_real": edgar.get("cash_real")
                    }.items()},
                    **{f"ratios.{k}": v for k, v in {
                        "pe_forward": pick(sa.get("pe_forward"), tier4.get("pe_forward")),
                        "peg": pick(sa.get("peg"), tier4.get("peg")),
                        "margen_bruto": pick(sa.get("margen_bruto"), tier4.get("margen_bruto")),
                        "roic": pick(sa.get("roic"), tier4.get("roic")),
                        "beta": pick(sa.get("beta"), tier4.get("beta")),
                    }.items()}
                }.items()
                if v is None
            ]
        }
    }

    # ─── GUARDAR JSON ───────────────────────────────────────────────────────────
    filename = f"datos_{ticker.upper()}_{TODAY.replace('-', '')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    nd_count = len(output["nd_resumen"]["campos_nd"])

    print(f"\n{'='*55}")
    print(f"  ✅ RECOLECCIÓN COMPLETADA")
    print(f"  Archivo: {filename}")
    print(f"  Revenue: {fmt_b(output['edgar']['revenue'])} FY{output['edgar']['fy_year']}")
    print(f"  FCF:     {fmt_b(output['edgar']['fcf'])}")
    print(f"  52W:     ${output['market'].get('w52_low')} – ${output['market'].get('w52_high')}")
    print(f"  N/D:     {nd_count} campo(s) sin resolver")
    if nd_count:
        print(f"  Campos:  {', '.join(output['nd_resumen']['campos_nd'])}")
    print(f"\n  👉 Pega el contenido de '{filename}' en Claude/ChatGPT/Gemini")
    print(f"  👉 Claude hará una búsqueda final para resolver los {nd_count} N/D restantes")
    print(f"{'='*55}\n")

    return filename


def main():
    if len(sys.argv) < 3:
        print("USO: python3 feroldi_recolectar.py TICKER PRECIO")
        print("EJ:  python3 feroldi_recolectar.py FSLR 211.39")
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
