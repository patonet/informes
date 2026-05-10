#!/usr/bin/env python3
"""
FEROLDI NORMALIZAR — v X0.58
Sistema Feroldi · @patonet
  Sistema: X0.72 (release actual)
  Archivo: X0.72 (última modificación en este archivo)
======================================
Capa de normalización entre feroldi_recolectar y feroldi_sankey.

Input:  datos_TICKER_raw_FECHA.json  (output de feroldi_recolectar)
Output: datos_TICKER_FECHA.json      (JSON canónico limpio)

ARQUITECTURA:
  feroldi_recolectar → [raw] → feroldi_normalizar → [clean] → feroldi_sankey

PRINCIPIOS:
  1. Una cadena de prioridad explícita y documentada por campo
  2. Nunca crashea — siempre devuelve JSON válido
  3. null explícito, nunca [] vacío ni valor inventado
  4. Idempotente — correr 2 veces da mismo resultado
  5. Sin efectos secundarios — no llama APIs, solo transforma datos

CADENAS DE PRIORIDAD:
  Financials  → EDGAR primario (auditado, SEC)
  EBIT        → EDGAR.operating_income → AV derivado → null
  Márgenes    → Alpha Vantage TTM → calculado EDGAR → null
  Ratios      → Alpha Vantage únicamente → null
  Segmentos   → EDGAR edgartools → limpieza → null (nunca [])
  Performance → TradingView únicamente → null por período

USO:
  python3 feroldi_normalizar.py datos_AAPL_raw_07052026.json
  python3 feroldi_normalizar.py datos_AAPL_raw_07052026.json --out datos_AAPL_07052026.json
"""

import json
import sys
import os
from itertools import combinations
from pathlib import Path

VERSION = "X0.58"
ND = "N/D"

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def _f(v):
    """Convierte a float, None si inválido."""
    if v is None or v in ("None", "N/D", "", "-"): return None
    try:
        f = float(v)
        return None if f != f else f  # NaN check
    except: return None

def _i(v):
    """Convierte a int, None si inválido."""
    if v is None: return None
    try: return int(float(v))
    except: return None

def _pct(v):
    """Formatea como porcentaje string."""
    f = _f(v)
    if f is None: return ND
    return f"{f*100:.1f}%"

def _first(*vals):
    """Retorna el primer valor no-None de la lista."""
    for v in vals:
        if v is not None: return v
    return None

# ─── SEGMENTOS — LÓGICA DE LIMPIEZA ────────────────────────────────────────────
GEO_KEYWORDS = [
    "north america", "international", "europe", "asia", "pacific",
    "latin america", "emea", "apac", "domestic", "foreign",
    "united states", "rest of world", "global", "americas",
    "china", "japan", "india", "canada", "australia"
]

def _is_geographic(labels):
    """True si la mayoría de etiquetas son nombres geográficos."""
    if not labels: return False
    geo = sum(1 for lb in labels
              if any(kw in lb.lower() for kw in GEO_KEYWORDS))
    return geo >= len(labels) * 0.5

def _remove_parents_iterative(segs, total_revenue):
    """
    Elimina segmentos padre iterativamente.
    Un segmento es padre si SIN ÉL el resto sigue cubriendo ≥70% del revenue.
    Esto detecta doble-conteo (ej: AMZN Net service sales + Net product sales).
    """
    if not total_revenue or not segs:
        return segs

    result = list(segs)
    for _ in range(10):  # máximo 10 pases
        padre_idx = -1
        for i, seg in enumerate(result):
            v = seg.get("revenue", 0)
            if v <= total_revenue * 0.35:
                continue  # segmento pequeño no puede ser padre
            resto = sum(s.get("revenue", 0) for j, s in enumerate(result) if j != i)
            if resto < total_revenue * 0.70:
                continue  # sin este segmento no cubrimos revenue → es hoja real
            # Confirmar: el hijo más grande representa ≥55% del candidato
            otros = [s.get("revenue", 0) for j, s in enumerate(result)
                     if j != i and s.get("revenue", 0) > 0]
            if otros and max(otros) / v >= 0.55:
                padre_idx = i
                break
        if padre_idx == -1:
            break  # no hay más padres
        result.pop(padre_idx)
    return result

def _clean_segments(raw_segs, total_revenue):
    """
    Limpia lista de segmentos crudos:
    1. Eliminar valores negativos (eliminaciones brutas mal calculadas)
    2. Eliminar padres (doble conteo)
    3. Agrupar segmentos <3% del revenue en "Otros"
    4. Calcular Eliminaciones si suma > revenue (inter-segmento real)
    5. Máximo 7 segmentos visibles + Otros
    6. Agregar % a cada segmento

    Retorna: lista limpia, o None si no hay datos válidos
    """
    if not raw_segs or not isinstance(raw_segs, list):
        return None

    # Paso 1: filtrar positivos
    segs_pos = [s for s in raw_segs if s.get("revenue", 0) > 0]
    if not segs_pos:
        return None

    # Paso 2: eliminar padres
    segs_clean = _remove_parents_iterative(segs_pos, total_revenue)
    if not segs_clean:
        return None

    # Paso 3: agrupar <3%
    threshold = (total_revenue * 0.03) if total_revenue else 0
    grandes = [s for s in segs_clean if s.get("revenue", 0) >= threshold]
    pequenos = [s for s in segs_clean if s.get("revenue", 0) < threshold]

    if pequenos:
        otros_rev = sum(s.get("revenue", 0) for s in pequenos)
        grandes.append({"nombre": "Otros", "revenue": int(otros_rev)})

    # Paso 4: eliminar geographic si existe opción producto (ya procesado en recolectar)
    # La preferencia de eje se maneja en feroldi_recolectar. Aquí solo verificamos.
    labels = [s.get("nombre", "") for s in grandes]
    if _is_geographic(labels) and len(grandes) <= 3:
        # Si solo tenemos geográficos y son pocos, marcar como sospechoso pero mantener
        pass  # no podemos hacer más sin re-llamar a EDGAR

    # Paso 5: ordenar y limitar
    grandes.sort(key=lambda x: x.get("revenue", 0), reverse=True)
    resultado = grandes[:7]

    if not resultado:
        return None

    # Paso 6: Eliminaciones inter-segmento si aplica
    if total_revenue:
        suma = sum(s.get("revenue", 0) for s in resultado)
        diff = suma - total_revenue
        # Solo agregar si diff es razonable: 1%-40% del revenue
        # Si diff > 40% hay padres sin eliminar — no son eliminaciones
        if total_revenue * 0.01 < diff < total_revenue * 0.40:
            resultado.append({
                "nombre": "Eliminaciones inter-segmento",
                "revenue": -int(diff)
            })

    # Paso 7: agregar porcentaje
    for s in resultado:
        if total_revenue and total_revenue > 0:
            s["pct"] = round(s["revenue"] / total_revenue, 4)
        else:
            s["pct"] = None

    return resultado


# ─── NORMALIZADOR PRINCIPAL ────────────────────────────────────────────────────
def normalizar(raw: dict) -> dict:
    """
    Toma JSON crudo de feroldi_recolectar y produce JSON canónico normalizado.
    Nunca lanza excepciones — campos que no se pueden resolver quedan en null.
    """
    meta    = raw.get("meta", {})
    edgar   = raw.get("edgar", {})
    av_ov   = raw.get("av_overview", raw.get("ratios", {}))   # soporte ambas estructuras
    ratios  = raw.get("ratios", {})
    market  = raw.get("market", {})
    earn    = raw.get("earnings", {})
    perf    = raw.get("performance", {})

    # ── Financials (EDGAR primario) ─────────────────────────────────────────
    revenue        = _f(edgar.get("revenue"))
    net_income     = _f(edgar.get("net_income"))
    operating_inc  = _f(edgar.get("operating_income"))
    cfo            = _f(edgar.get("cfo"))
    capex          = _f(edgar.get("capex"))
    fcf            = _f(edgar.get("fcf")) or \
                     ((cfo - capex) if (cfo and capex) else None)
    sbc            = _f(edgar.get("sbc"))
    dividendos     = _f(edgar.get("dividendos"))
    lt_debt        = _f(edgar.get("lt_debt"))
    st_debt        = _f(edgar.get("st_debt"))
    deuda_total    = _f(edgar.get("deuda_total")) or \
                     (((lt_debt or 0) + (st_debt or 0)) if (lt_debt or st_debt) else None)
    cash_real      = _f(edgar.get("cash_real"))
    goodwill       = _f(edgar.get("goodwill"))
    total_assets   = _f(edgar.get("total_assets"))
    shares         = _f(edgar.get("shares"))
    fy_year        = edgar.get("fy_year", ND)

    # ── Márgenes (AV primario → calculado) ─────────────────────────────────
    margen_bruto = _f(ratios.get("margen_bruto"))
    if margen_bruto is None and revenue and revenue > 0:
        # Intentar calcular si AV dio GrossProfitTTM implícito en market
        gp_ttm = _f(market.get("gross_profit_ttm"))
        if gp_ttm:
            margen_bruto = gp_ttm / revenue

    margen_op = _f(ratios.get("margen_op"))
    if margen_op is None and operating_inc and revenue and revenue > 0:
        margen_op = operating_inc / revenue

    margen_neto = _f(ratios.get("margen_neto"))
    if margen_neto is None and net_income and revenue and revenue > 0:
        margen_neto = net_income / revenue

    roe = _f(ratios.get("roe"))
    roa = _f(ratios.get("roa"))

    # ── EBIT (operating_income) ─────────────────────────────────────────────
    # Cadena: EDGAR.operating_income → AV derivado → null
    if operating_inc is None and margen_op and revenue:
        operating_inc = revenue * margen_op

    # ── Ratios de valoración (AV únicamente) ───────────────────────────────
    pe_ttm     = _f(ratios.get("pe_ttm"))   or _f(market.get("pe_ttm"))
    pe_forward = _f(ratios.get("pe_forward"))
    peg        = _f(ratios.get("peg"))
    ev_ebitda  = _f(ratios.get("ev_ebitda"))
    ev_revenue = _f(ratios.get("ev_revenue"))
    pb         = _f(ratios.get("pb"))
    p_sales    = _f(ratios.get("p_sales"))
    beta       = _f(ratios.get("beta"))
    div_yield  = _f(ratios.get("dividend_yield"))
    rev_yoy    = _f(ratios.get("revenue_yoy"))
    ni_yoy     = _f(ratios.get("ni_yoy"))
    pct_insiders = _f(ratios.get("percent_insiders"))

    # ── Market (AV + cálculo) ───────────────────────────────────────────────
    precio       = _f(meta.get("precio_usuario")) or _f(market.get("precio_actual"))
    market_cap   = _f(market.get("market_cap"))
    if market_cap is None and shares and precio:
        market_cap = shares * precio

    w52_high     = _f(market.get("w52_high"))
    w52_low      = _f(market.get("w52_low"))
    eps_ttm      = _f(market.get("eps_ttm"))
    anal_target  = _f(market.get("analyst_target"))
    anal_buy     = (_i(market.get("analyst_strong_buy")) or 0) + \
                   (_i(market.get("analyst_buy")) or 0)
    anal_hold    = _i(market.get("analyst_hold")) or 0
    anal_sell    = (_i(market.get("analyst_sell")) or 0) + \
                   (_i(market.get("analyst_strong_sell")) or 0)
    anal_total   = anal_buy + anal_hold + anal_sell
    anal_consenso = f"{anal_buy} Buy / {anal_hold} Hold / {anal_sell} Sell" \
                    if anal_total > 0 else None

    # ── Segmentos (limpieza completa) ───────────────────────────────────────
    raw_segs  = edgar.get("segmentos")      # puede ser lista cruda o null
    segmentos = _clean_segments(raw_segs, revenue)

    # ── Earnings ────────────────────────────────────────────────────────────
    annual_eps    = earn.get("annual_eps") or []
    quarterly_eps = earn.get("quarterly_eps") or []

    # ── Performance ─────────────────────────────────────────────────────────
    performance = {
        k: _f(perf.get(k))
        for k in ["5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "10Y", "All"]
        if perf.get(k) is not None
    }

    # ── N/D count ───────────────────────────────────────────────────────────
    campos_criticos = {
        "edgar.revenue":        revenue,
        "edgar.net_income":     net_income,
        "edgar.fcf":            fcf,
        "edgar.deuda_total":    deuda_total,
        "edgar.cash_real":      cash_real,
        "edgar.operating_income": operating_inc,
        "ratios.margen_bruto":  margen_bruto,
        "ratios.margen_op":     margen_op,
        "ratios.margen_neto":   margen_neto,
        "ratios.beta":          beta,
        "ratios.pe_forward":    pe_forward,
        "ratios.roe":           roe,
    }
    campos_nd = [k for k, v in campos_criticos.items() if v is None]

    # ── JSON normalizado ─────────────────────────────────────────────────────
    out = {
        "meta": {
            "version":        VERSION,
            "ticker":         meta.get("ticker", "???"),
            "precio_usuario": precio,
            "exchange":       meta.get("exchange", ND),
            "fecha":          meta.get("fecha", ND),
            "company_name":   meta.get("company_name", ND),
            "sector":         meta.get("sector", ND),
            "industry":       meta.get("industry", ND),
            "fuentes":        meta.get("fuentes", ["EDGAR", "Alpha Vantage", "TradingView"]),
            "normalized":     True,
            "nd_count":       len(campos_nd),
            "nd_fields":      campos_nd,
        },
        "edgar": {
            "cik":              edgar.get("cik", ND),
            "fy_year":          fy_year,
            "revenue":          revenue,
            "net_income":       net_income,
            "operating_income": operating_inc,
            "cfo":              cfo,
            "capex":            capex,
            "fcf":              fcf,
            "sbc":              sbc,
            "dividendos":       dividendos,
            "lt_debt":          lt_debt,
            "st_debt":          st_debt,
            "deuda_total":      deuda_total,
            "cash_real":        cash_real,
            "goodwill":         goodwill,
            "total_assets":     total_assets,
            "shares":           shares,
            "segmentos":        segmentos,   # null o lista limpia con pct
        },
        "margins": {
            "margen_bruto":  margen_bruto,
            "margen_op":     margen_op,
            "margen_neto":   margen_neto,
            "margen_ebitda": None,           # no disponible sin EBITDA explícito
            "roe":           roe,
            "roa":           roa,
        },
        "ratios": {
            "pe_ttm":        pe_ttm,
            "pe_forward":    pe_forward,
            "peg":           peg,
            "ev_ebitda":     ev_ebitda,
            "ev_revenue":    ev_revenue,
            "pb":            pb,
            "p_sales":       p_sales,
            "beta":          beta,
            "dividend_yield": div_yield,
            "revenue_yoy":   rev_yoy,
            "ni_yoy":        ni_yoy,
            "percent_insiders": pct_insiders,
        },
        "market": {
            "precio_actual":  _f(market.get("precio_actual")) or precio,
            "market_cap":     market_cap,
            "w52_high":       w52_high,
            "w52_low":        w52_low,
            "pe_ttm":         pe_ttm,
            "eps_ttm":        eps_ttm,
            "analyst_target": anal_target,
            "analyst_buy":    anal_buy,
            "analyst_hold":   anal_hold,
            "analyst_sell":   anal_sell,
            "analyst_consenso": anal_consenso,
            "latest_quarter": market.get("latest_quarter"),
        },
        "earnings": {
            "annual_eps":    annual_eps,
            "quarterly_eps": quarterly_eps,
        },
        "performance": performance,
    }

    return out


# ─── CLI ───────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("USO: python3 feroldi_normalizar.py datos_TICKER_raw_FECHA.json")
        print("     python3 feroldi_normalizar.py datos_TICKER_raw_FECHA.json --out datos_TICKER_FECHA.json")
        sys.exit(1)

    in_path = sys.argv[1]
    if not os.path.isfile(in_path):
        print(f"❌ Archivo no encontrado: {in_path}")
        sys.exit(1)

    # Output path
    out_path = None
    if "--out" in sys.argv:
        idx = sys.argv.index("--out")
        if idx + 1 < len(sys.argv):
            out_path = sys.argv[idx + 1]

    if out_path is None:
        # Si el input tiene "_raw_" en el nombre, output sin "_raw_"
        if "_raw_" in in_path:
            out_path = in_path.replace("_raw_", "_")
        else:
            # Overwrite
            out_path = in_path

    with open(in_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    print(f"\n{'='*55}")
    print(f"  FEROLDI NORMALIZAR v {VERSION}")
    print(f"  Input:  {in_path}")
    print(f"  Output: {out_path}")
    print(f"{'='*55}\n")

    normalized = normalizar(raw)

    ticker  = normalized["meta"]["ticker"]
    fy      = normalized["edgar"]["fy_year"]
    revenue = normalized["edgar"]["revenue"]
    nd      = normalized["meta"]["nd_count"]
    segs    = normalized["edgar"]["segmentos"]

    def fmt_b(v):
        if v is None: return ND
        v = float(v)
        if abs(v) >= 1e9: return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6: return f"${v/1e6:.1f}M"
        return f"${v:,.0f}"

    print(f"  Ticker:   {ticker}")
    print(f"  Revenue:  {fmt_b(revenue)} FY{fy}")
    print(f"  FCF:      {fmt_b(normalized['edgar']['fcf'])}")
    print(f"  EBIT:     {fmt_b(normalized['edgar']['operating_income'])}")
    print(f"  Margen N: {_pct(normalized['margins']['margen_neto'])}")
    print(f"  Beta:     {normalized['ratios']['beta']}")
    print(f"  N/D:      {nd} campo(s)")
    if nd > 0:
        print(f"  Campos:   {', '.join(normalized['meta']['nd_fields'])}")
    if segs:
        seg_sum = sum(s.get("revenue", 0) for s in segs)
        seg_cov = (seg_sum / revenue) if revenue else 0
        cov_pct = f"{seg_cov*100:.1f}%"
        # BUG-N1 X0.594: alarma si segmentos no cubren el revenue total
        if seg_cov < 0.75:
            print(f"  ⚠⚠ ALERTA CRÍTICA: segmentos suman {fmt_b(seg_sum)} ({cov_pct} revenue) — falta ≥25% sin segmentar")
            warnings = normalized["meta"].setdefault("warnings", [])
            warnings.append(f"seg_coverage_critical:{seg_cov:.3f}")
        elif seg_cov < 0.90:
            print(f"  ⚠  ALERTA: segmentos suman {fmt_b(seg_sum)} ({cov_pct} revenue) — cobertura baja, posible segmento faltante")
            warnings = normalized["meta"].setdefault("warnings", [])
            warnings.append(f"seg_coverage_low:{seg_cov:.3f}")
        print(f"  Segmentos: {len(segs)} (cobertura {cov_pct})")
        for s in segs:
            pct = f"{s.get('pct', 0)*100:.1f}%" if s.get('pct') else "?"
            print(f"    · {s['nombre']}: {fmt_b(s['revenue'])} ({pct})")
    else:
        print(f"  Segmentos: null")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  ✅ Normalizado → {out_path}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
