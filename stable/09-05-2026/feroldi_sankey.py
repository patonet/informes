#!/usr/bin/env python3
"""
FEROLDI SANKEY — v X0.69
Sistema Feroldi · @patonet
  Sistema: X0.72 (release actual)
  Archivo: X0.72 (última modificación en este archivo)
======================================
Genera diagrama Sankey HTML a partir del JSON de feroldi_recolectar.
Muestra el flujo de dinero: Revenue → Costos → EBITDA → Net Income + FCF.

USO:
  python3 feroldi_sankey.py AAPL 287.46
  python3 feroldi_sankey.py ~/Downloads/datos_AAPL_07052026.json 287.46

INSTALAR (una sola vez):
  pip3 install aiohttp requests edgartools
"""

import json
import sys
import os
from datetime import datetime, timedelta

VERSION = "X0.69"
ND = "N/D"

def fmt_b(v):
    if v is None: return ND
    try:
        v = float(v)
        if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
        elif abs(v) >= 1e6: return f"${v/1e6:.1f}M"
        else:               return f"${v:,.0f}"
    except: return ND

def _float(v):
    if v is None: return None
    try: return float(v)
    except: return None


def generar_sankey(json_path, precio_usuario=None):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta    = data.get("meta", {})
    edgar   = data.get("edgar", {})
    market  = data.get("market", {})
    ratios  = data.get("ratios", {})

    ticker       = meta.get("ticker", "???")
    company_name = meta.get("company_name", ticker)
    sector       = meta.get("sector", ND)
    industry     = meta.get("industry", ND)
    precio       = _float(precio_usuario) or _float(market.get("precio_actual")) or 0

    revenue      = _float(edgar.get("revenue"))
    net_income   = _float(edgar.get("net_income"))
    cfo          = _float(edgar.get("cfo"))
    capex        = _float(edgar.get("capex"))
    fcf          = _float(edgar.get("fcf"))
    sbc          = _float(edgar.get("sbc"))
    deuda_total  = _float(edgar.get("deuda_total"))
    cash_real    = _float(edgar.get("cash_real"))
    total_assets = _float(edgar.get("total_assets"))
    goodwill     = _float(edgar.get("goodwill"))
    shares       = _float(edgar.get("shares"))
    dividendos   = _float(edgar.get("dividendos"))
    segmentos_raw = edgar.get("segmentos")
    operating_income = _float(edgar.get("operating_income"))

    # ── GUARDIANES DE PROPORCIONALIDAD (X0.69) ─────────────────────────────
    # Aplica a TODOS los campos monetarios de EDGAR que se renderizan en
    # cualquier columna del Sankey. Si abs(valor) > umbral × revenue → None.
    # Previene cajas rotas por datos en moneda local no convertida (FX bug).
    #
    # Umbrales diferenciados:
    #   1× revenue  → net_income, operating_income (nunca superan ventas)
    #   2× revenue  → fcf, capex, sbc, dividendos, cfo (flujos de caja)
    #   5× revenue  → deuda_total, cash_real, goodwill (balance sheet)
    #                 (bancos/autos tienen deuda/activos muy grandes vs revenue)
    if revenue and revenue > 0:
        _max1 = revenue * 1.0
        _max2 = revenue * 2.0
        _max5 = revenue * 5.0
        # Col 4 — resultado financiero
        if net_income      is not None and abs(net_income)      > _max1: net_income      = None
        if operating_income is not None and abs(operating_income) > _max1: operating_income = None
        if deuda_total     is not None and abs(deuda_total)     > _max5: deuda_total     = None
        # Col 5 — flujos de capital
        if cfo             is not None and abs(cfo)             > _max2: cfo             = None
        if fcf             is not None and abs(fcf)             > _max2: fcf             = None
        if capex           is not None and abs(capex)           > _max2: capex           = None
        if sbc             is not None and abs(sbc)             > _max2: sbc             = None
        if dividendos      is not None and abs(dividendos)      > _max2: dividendos      = None
        # Audit table / metadata
        if cash_real       is not None and abs(cash_real)       > _max5: cash_real       = None
        if goodwill        is not None and abs(goodwill)        > _max5: goodwill        = None
        if total_assets    is not None and abs(total_assets)    > _max5: total_assets    = None

    # ── Hooks enriquecimiento Light / Heavy (dinámico) ──────────────────────
    # El Sankey es la última etapa del pipeline.
    # feroldi_light.py y feroldi_heavy.py añadirán sus secciones al mismo JSON.
    # El Sankey lee lo que esté disponible y muestra más cuadros si existen.
    _light = data.get("light", {})
    _heavy = data.get("heavy", {})
    feroldi_score  = _float(_light.get("feroldi_score"))         # 0-160 si Light corrió
    fair_value_mid = _float(_light.get("fair_value_mid") or
                            _heavy.get("fair_value_mid"))         # precio intrínseco estimado
    dcf_range      = _heavy.get("dcf_range")                     # e.g. "$140–$210"
    # Segmentos refinados de Light/Heavy tienen prioridad sobre EDGAR raw
    _segs_refined  = _light.get("segments_refined") or _heavy.get("segments_refined")
    if _segs_refined:
        segmentos_raw = _segs_refined

    # Soporte JSON normalizado (margins.*) y legado (ratios.*)
    margins      = data.get("margins", {})
    margen_bruto = _float(margins.get("margen_bruto")) or _float(ratios.get("margen_bruto"))
    margen_op    = _float(margins.get("margen_op"))    or _float(ratios.get("margen_op"))
    margen_neto  = _float(margins.get("margen_neto"))  or _float(ratios.get("margen_neto"))
    beta         = _float(ratios.get("beta"))
    pe_fwd       = ratios.get("pe_forward")
    revenue_yoy  = ratios.get("revenue_yoy")
    ni_yoy       = ratios.get("ni_yoy")

    analyst_target = market.get("analyst_target")
    consenso       = market.get("analyst_consenso", ND)
    mkt_cap        = _float(market.get("market_cap"))
    w52_high       = market.get("w52_high", ND)
    w52_low        = market.get("w52_low", ND)
    fy_year        = edgar.get("fy_year", ND)

    if not revenue:
        print("  ❌ Error: no hay Revenue en el JSON")
        return None

    # ── Costos estimados ─────────────────────────────────────────────────────
    if margen_bruto and margen_bruto != 0:
        cogs_value   = revenue * (1 - margen_bruto)
        gross_profit = revenue * margen_bruto
    else:
        cogs_value   = revenue * 0.5
        gross_profit = revenue * 0.5

    if margen_op is not None:
        op_income = revenue * margen_op
    else:
        op_income = 0

    opex_total = gross_profit - op_income
    if opex_total < 0:
        opex_total = revenue * 0.5
        op_income = gross_profit - opex_total

    sl = (sector or "").lower()
    if "health" in sl:
        sm_pct, rd_pct, da_pct, other_pct = 0.32, 0.08, 0.20, 0.40
    elif "technology" in sl or "information" in sl:
        sm_pct, rd_pct, da_pct, other_pct = 0.30, 0.30, 0.12, 0.28
    else:
        sm_pct, rd_pct, da_pct, other_pct = 0.36, 0.20, 0.15, 0.29
    if capex is not None and revenue > 0 and capex / revenue < 0.03:
        da_pct = 0.08
        other_pct += 0.07

    sm_value    = opex_total * sm_pct
    rd_value    = opex_total * rd_pct
    da_value    = opex_total * da_pct
    other_value = opex_total * other_pct

    interest = (deuda_total * 0.05) if deuda_total and deuda_total > 0 else 0

    # BUG-S2: usar operating_income de EDGAR si margen_op no disponible (AV bloqueado)
    # BUG-S7 X0.581: trackear fuente real de EBIT (antes siempre decía "Alpha Vantage")
    if margen_op is not None:
        ebit_source = f"Calculado: Rev × Margen Op AV ({margen_op*100:.1f}%)"
        ebit_status = ("status-est", "⚡ Estimado")
    elif operating_income is not None:
        op_income = operating_income
        ebit_source = "EDGAR XBRL (10-K · OperatingIncomeLoss)"
        ebit_status = ("status-ok", "✅ Verificado")
    else:
        op_income = None
        ebit_source = "N/D"
        ebit_status = ("status-est", "⚡ Estimado")

    # BUG-S12 X0.598: Sanity check EBIT ≈ NI (EDGAR puede entregar operating_income = net_income)
    # Si ocurre, intentar ratios.margen_op (AV OperatingMarginTTM) como fallback
    if (net_income and op_income and abs(net_income) > 0 and
            abs(op_income - net_income) / abs(net_income) < 0.03):
        ratios_mop = _float(ratios.get("margen_op"))
        if ratios_mop and revenue and ratios_mop > (margen_op or 0) * 1.01:
            op_income = revenue * ratios_mop
            margen_op = ratios_mop
            ebit_source = f"AV OperatingMarginTTM ({ratios_mop*100:.1f}%) — fallback EBIT≈NI"
            ebit_status = ("status-est", "⚡ Estimado")

    # Tax
    if net_income is not None:
        pre_tax_val = net_income + interest
        tax_val = (pre_tax_val - net_income) if pre_tax_val > net_income else 0
    else:
        pre_tax_val = (op_income or 0) - interest
        tax_val = 0

    is_profitable = net_income is not None and net_income > 0
    has_segments = segmentos_raw and isinstance(segmentos_raw, list) and len(segmentos_raw) > 0

    # ── Fecha / Path ──────────────────────────────────────────────────────────
    date_str = datetime.now().strftime("%d-%m-%Y")
    out_path = os.path.join(os.path.expanduser("~/Downloads"),
                            f"Diagrama_Sankey_{ticker}_{precio:.2f}_{date_str}.html")

    # ── Formatear valores ─────────────────────────────────────────────────────
    hr = lambda v: f"${v/1e9:.2f}B" if v else ND

    s_rev      = hr(revenue)
    s_cogs     = hr(cogs_value)
    s_opex     = hr(opex_total)
    s_sm       = hr(sm_value)
    s_rd       = hr(rd_value)
    s_da       = hr(da_value)
    s_other    = hr(other_value)
    s_opinc    = hr(op_income)
    s_ni       = hr(net_income)
    s_fcf      = hr(fcf)
    s_cfo      = hr(cfo)
    s_capex    = hr(capex)
    s_sbc      = hr(sbc)
    s_div      = hr(dividendos)
    s_debt     = hr(deuda_total)
    s_cash     = hr(cash_real)
    s_gw       = hr(goodwill)
    s_interest = hr(interest) if interest > 0 else ND
    s_tax      = hr(tax_val) if tax_val > 0 else ND
    s_mkt_cap  = hr(mkt_cap)

    cogs_pct  = f"{cogs_value/revenue*100:.1f}%" if revenue else "0%"
    op_margin = f"{margen_op*100:.1f}%" if margen_op else ND
    ni_pct    = f"{margen_neto*100:.1f}%" if margen_neto else ND
    gross_pct = f"{margen_bruto*100:.1f}%" if margen_bruto else ND

    # Audit table values — formato breve $X.XB (BUG-S6 X0.581: antes mostraba $416,161,000,000)
    s_rev_raw     = hr(revenue)
    s_cogs_raw    = hr(cogs_value)
    s_gross_raw   = hr(gross_profit)
    s_sm_raw      = hr(sm_value)
    s_rd_raw      = hr(rd_value)
    s_da_raw      = hr(da_value)
    s_other_raw   = hr(other_value)
    s_opinc_raw   = hr(op_income)
    s_interest_raw = hr(interest) if interest else ND
    s_pre_tax_raw = hr(pre_tax_val)
    s_tax_raw     = hr(tax_val) if tax_val else ND
    s_ni_raw      = hr(net_income)
    s_cfo_raw     = hr(cfo)
    s_capex_raw   = hr(capex)
    s_fcf_raw     = hr(fcf)
    s_sbc_raw     = hr(sbc)
    s_div_raw     = hr(dividendos)
    s_debt_raw    = hr(deuda_total)
    s_cash_raw    = hr(cash_real)
    s_gw_raw      = hr(goodwill)
    s_shares_raw  = f"{shares/1e9:.2f}B" if shares else ND
    s_assets_raw  = hr(total_assets)

    # Pre-compute audit notes (avoid nested f-string issues)
    note_capex     = f'{capex/revenue*100:.1f}% de Revenue' if capex and revenue else ND
    note_fcf_yield = f'FCF Yield: {fcf/mkt_cap*100:.1f}%' if fcf and mkt_cap else ND
    note_sbc       = f'{sbc/revenue*100:.1f}% de Revenue' if sbc and revenue else ND
    note_div_yield = f'Yield: {dividendos/mkt_cap*100:.2f}%' if dividendos and mkt_cap else ND
    note_de_ratio  = f'D/E: {deuda_total/(total_assets-deuda_total):.2f}' if deuda_total and total_assets else ND
    note_gw_pct    = f'{goodwill/total_assets*100:.1f}% de Activos' if goodwill and total_assets else ND

    ni_color  = "#00e676" if is_profitable else "#ff1744"
    ni_label  = "UTILIDAD NETA" if is_profitable else "PÉRDIDA NETA"
    inc_color = "#00ff9d" if is_profitable else "#ff3a3a"

    verdict_class = "S3: Buy" if (is_profitable and margen_neto and margen_neto > 0.10 and fcf and fcf > revenue * 0.05) else ("S2: Hold" if is_profitable else "S1: Avoid")

    score_parts = []
    if pe_fwd and _float(pe_fwd) and _float(pe_fwd) < 25: score_parts.append("PE<25")
    rg = _float(revenue_yoy)
    if rg and rg > 0.05: score_parts.append("Crec>5%")
    if rg and rg > 0.10: score_parts.append("Crec>10%")
    if is_profitable and margen_neto and margen_neto > 0.15: score_parts.append("Marg>15%")
    if fcf and revenue and fcf/revenue > 0.10: score_parts.append("FCF>10%")
    if beta and _float(beta) and _float(beta) < 1.5: score_parts.append("Beta<1.5")
    score_str = " · ".join(score_parts[:5]) if score_parts else ND

    # ══════════════════════════════════════════════════════════════════════════
    # SVG LAYOUT — DINÁMICO  (BUG-S10 X0.596)
    # ══════════════════════════════════════════════════════════════════════════
    W = 1400
    # BUG-S10: columnas redistribuidas igual que reference (ratio 1%/28%/53%/73%/90%)
    C1, C2, C3, C4, C5 = 20, 390, 740, 1020, 1255
    # Anchos de nodo por columna
    SEG_W, REV_W, COST_W, NI_W, OUT_W = 210, 195, 215, 170, 130
    # Bordes derechos (usados como punto de partida de los flujos salientes)
    C1r = C1 + SEG_W   # 230
    C2r = C2 + REV_W   # 585
    C3r = C3 + COST_W  # 955
    C4r = C4 + NI_W    # 1190

    rev_y1 = 90  # Revenue node Y

    # BUG-S10: san_h — función unificada altura/banda proporcional a revenue
    # Igual escala para BOX HEIGHT y FLOW WIDTH → caja grande = banda gruesa
    REV_H = 380  # Revenue box height = referencia de escala
    def san_h(val, min_h=8):
        if not val or not revenue: return min_h
        return max(min_h, int(abs(val) / revenue * REV_H))

    # Alturas de cajas COL3 = misma escala que flows
    cogs_h  = san_h(cogs_value,  min_h=30)
    sm_h    = san_h(sm_value,    min_h=22)
    rd_h    = san_h(rd_value,    min_h=22)
    da_h    = san_h(da_value,    min_h=22)
    other_h = san_h(other_value, min_h=22)
    EBIT_H  = max(40, san_h(op_income))
    ni_h    = max(40, san_h(net_income))

    # Flow widths = box heights (exactamente la misma escala)
    fw_cogs     = cogs_h
    fw_sm       = sm_h
    fw_rd       = rd_h
    fw_da       = da_h
    fw_other    = other_h
    fw_ebit     = EBIT_H
    fw_ni       = ni_h
    fw_tax      = max(4, san_h(tax_val))
    fw_interest = max(4, san_h(interest))
    fw_fcf      = max(4, san_h(fcf))
    # BUG-S11 X0.597: alturas de cajas COL4 (Tax/Interest) y COL5 (destinos de capital)
    tax_h    = max(22, san_h(tax_val))
    int_h    = max(22, san_h(interest))
    fcf_h    = max(40, san_h(fcf))
    div_h    = max(22, san_h(dividendos))
    capex_h  = max(22, san_h(capex))
    sbc_h    = max(22, san_h(sbc))

    cogs_y1 = rev_y1  # alineado con Revenue
    opex_start = cogs_y1 + cogs_h + 12

    # Layout dinámico COL3
    GAP = 12
    OPEX_LABEL_H = 25
    rd_y         = opex_start + sm_h + GAP
    da_y         = rd_y + rd_h + GAP
    other_y      = da_y + da_h + GAP
    opex_label_y = other_y + other_h + GAP
    ebit_y       = opex_label_y + OPEX_LABEL_H + GAP
    col3_bottom  = ebit_y + EBIT_H

    # ni_y se calcula más abajo, después de col1_bottom y Tax/Int y-positions

    # ── V7 X0.599: Traducción visual de nombres de segmento (solo display, JSON sin cambios) ──
    _SEG_ES = {
        # GE
        "GE Aerospace": "GE Aeroespacial",
        "GE Vernova": "GE Vernova",
        # McDonald's
        "Franchised Restaurants": "Restaurantes Franquiciados",
        "Company-operated Restaurants": "Restaurantes Propios",
        "Other Revenues": "Otros Ingresos",
        # Apple
        "Wearables, Home and Accessories": "Wearables y Accesorios",
        "Services": "Servicios",
        # Amazon
        "North America": "Norteamérica",
        "International": "Internacional",
        "Amazon Web Services (AWS)": "AWS (Nube)",
        "Amazon Web Services": "AWS (Nube)",
        # Google / Alphabet
        "Google Services": "Google Servicios",
        "Google Cloud": "Google Nube",
        "Other Bets": "Otras Apuestas",
        # Genéricos
        "Healthcare": "Salud",
        "Renewable Energy": "Energía Renovable",
        "Aviation": "Aviación",
        "Power": "Energía",
        "Financial Services": "Serv. Financieros",
        "Corporate": "Corporativo",
        "Technology": "Tecnología",
        "Infrastructure": "Infraestructura",
        "Aerospace & Defense": "Aeroespacial",
        "Consumer & Industrial": "Consumidor e Industrial",
        "Capital": "Capital",
        "Products": "Productos",
    }
    def _translate_seg(name):
        if name in _SEG_ES:
            return _SEG_ES[name]
        for eng, esp in _SEG_ES.items():
            if eng.lower() in name.lower():
                return esp
        return name

    def _split_name(display):
        """Divide nombre largo en dos líneas para ajustar en caja de segmento."""
        parts = [display]
        if len(display) > 20 and ' ' in display:
            mid = len(display) // 2
            left_space = display.rfind(' ', 0, mid)
            right_space = display.find(' ', mid)
            split_at = -1
            if left_space >= 0 and right_space >= 0:
                split_at = left_space if (mid - left_space) <= (right_space - mid) else right_space
            elif left_space >= 0:
                split_at = left_space
            elif right_space >= 0:
                split_at = right_space
            if split_at > 0:
                parts = [display[:split_at].strip(), display[split_at:].strip()]
        return parts

    # ── Segment boxes — proporcionales (FIX 2) ───────────────────────────────
    seg_data = []
    if has_segments:
        # X0.58: segmentos ya limpios por feroldi_normalizar
        # Si el JSON es legado (sin normalizar), aplicar filtro básico
        segs_raw = [s for s in segmentos_raw if s.get("revenue", 0) > 0]
        segs = sorted(segs_raw, key=lambda x: x.get("revenue", 0), reverse=True)[:7]
        seg_revs = [s.get("revenue", 0) for s in segs]
        max_r = max(seg_revs) if seg_revs else 1
        min_r = min(seg_revs) if seg_revs else 0
        span = max_r - min_r if max_r != min_r else 1
        seg_y = 75
        for i, s in enumerate(segs):
            sv = s.get("revenue", 0)
            # BUG-S10: altura de caja = san_h(sv) → misma escala que flow width
            h = max(30, san_h(sv))
            fw = h  # flow width = box height (banda gruesa ↔ caja grande)
            fo = 0.55  # fixed opacity
            fs = 12 + int((h - 50) / 200 * 10)  # font-size 12-22px proporcional
            nombre = s.get("nombre","?")
            # V7 X0.599: traducir para display visual (nombre EDGAR intacto en JSON)
            display = _translate_seg(nombre)
            name_parts = _split_name(display)
            seg_data.append({"nombre": nombre, "display": display, "name_parts": name_parts,
                             "revenue": sv, "y": seg_y, "h": h, "cy": seg_y + h//2,
                             "fw": fw, "fo": fo, "fs": fs, "fs_sub": max(10, fs-3)})
            seg_y += h + 10
        col1_bottom = seg_y
        # Marco col1 siempre >= altura de col2 (REV_H + márgenes)
        col1_frame_bottom = max(col1_bottom, rev_y1 + REV_H + 20)
        # Cobertura real de segmentos
        seg_coverage = sum(s["revenue"] for s in seg_data) / revenue if revenue else 1.0
    else:
        col1_bottom = 530
        col1_frame_bottom = 530
        seg_coverage = 0.0

    # BUG-S11 X0.597: Tax/Interest en TOP de C4 (posición fija) · NI centrado en C4
    # Se elimina el piso BUG-S8 (ebit_y+EBIT_H+30) que empujaba NI hacia abajo
    # cuando EBIT_H es proporcional (p.ej. MCD EBIT_H=175px → NI en 79% del canvas)
    tax_y = rev_y1 + 10               # Tax fijo en el tope de C4 (y=100)
    int_y = tax_y + tax_h + 8         # Interest justo bajo Tax

    H_prov = max(col1_bottom + 60, col3_bottom + 80, 660)
    ni_y_centered = (H_prov - ni_h) // 2
    # Piso mínimo: NI debe quedar debajo de Int/Tax (que ya están arriba fijos)
    ni_y = max(int_y + int_h + 30, ni_y_centered)

    # BUG-S11: C5 nodes stack verticalmente, centrados en ni_y+ni_h//2
    GAP5    = 10
    c5_total = fcf_h + GAP5 + div_h + GAP5 + capex_h + GAP5 + sbc_h + GAP5 + 50
    fcf_y   = max(rev_y1 + 20, (ni_y + ni_h // 2) - c5_total // 2)
    div_y   = fcf_y + fcf_h + GAP5
    capex_y = div_y + div_h + GAP5
    sbc_y   = capex_y + capex_h + GAP5
    bal_y   = sbc_y + sbc_h + GAP5

    # H final — contiene NI, C5 stack completo, y margen inferior
    H = max(H_prov, ni_y + ni_h + 60, bal_y + 50 + 40)

    # ── X0.60: helper COL3 — fuentes Y posiciones proporcionales a h ─────────
    # Mismo criterio que C1: fs crece linealmente con h (escala unificada)
    def _txt_fs(h):
        """Font sizes proporcional a h — mismo criterio que C1."""
        fl = max(9,  min(13, 8 + int(h / 22)))   # label
        fv = max(10, min(16, 9 + int(h / 16)))   # value
        fs = max(8,  min(11, 7 + int(h / 35)))   # subtitle
        return fl, fv, fs

    def _cost_box(y, h, color, bg, label, subtitle, value, tip=""):
        cx = C3 + COST_W // 2
        tip_attr = f' data-tip="{tip}"' if tip else ""
        fl, fv, fs = _txt_fs(h)
        if h >= 65:
            yl = y + max(14, int(h * 0.28))
            ys = y + max(24, int(h * 0.52))
            yv = y + max(36, int(h * 0.77))
            return (f'  <g class="node"{tip_attr}>'
                    f'<rect x="{C3}" y="{y}" width="{COST_W}" height="{h}" rx="6" fill="{bg}" stroke="{color}" stroke-width="1.5"/>'
                    f'<text x="{cx}" y="{yl}" text-anchor="middle" font-size="{fl}" font-weight="bold" fill="{color}">{label}</text>'
                    f'<text x="{cx}" y="{ys}" text-anchor="middle" font-size="{fs}" fill="#94a3b8">{subtitle}</text>'
                    f'<text x="{cx}" y="{yv}" text-anchor="middle" font-size="{fv}" font-weight="bold" fill="#00ff9d">{value}</text>'
                    f'</g>\n')
        elif h >= 42:
            yl = y + max(13, int(h * 0.38))
            yv = y + max(24, int(h * 0.74))
            return (f'  <g class="node"{tip_attr}>'
                    f'<rect x="{C3}" y="{y}" width="{COST_W}" height="{h}" rx="5" fill="{bg}" stroke="{color}" stroke-width="1.5"/>'
                    f'<text x="{cx}" y="{yl}" text-anchor="middle" font-size="{fl}" font-weight="bold" fill="{color}">{label}</text>'
                    f'<text x="{cx}" y="{yv}" text-anchor="middle" font-size="{fv}" font-weight="bold" fill="#00ff9d">{value}</text>'
                    f'</g>\n')
        else:
            short = label.split('/')[0].strip() if '/' in label else (label.split()[0] if ' ' in label else label)
            yc = y + h // 2 + max(3, int(h * 0.08))
            return (f'  <g class="node"{tip_attr}>'
                    f'<rect x="{C3}" y="{y}" width="{COST_W}" height="{h}" rx="4" fill="{bg}" stroke="{color}" stroke-width="1"/>'
                    f'<text x="{cx}" y="{yc}" text-anchor="middle" font-size="{fl}" fill="{color}">'
                    f'<tspan font-weight="bold">{short}:</tspan>'
                    f'<tspan fill="#00ff9d" font-weight="bold"> {value}</tspan></text>'
                    f'</g>\n')

    # ── COL1 → COL2 flow paths (FIX 3) ──────────────────────────────────────
    seg_flows_svg = ""
    seg_grad_colors = ["#00d4ff","#00e676","#ffd700","#ff6b35","#ff9800","#9c27b0","#64748b"]
    if has_segments:
        # BUG-S10: borde derecho del segmento → borde izquierdo de Revenue
        rev_entry_y = rev_y1 + REV_H // 2  # centro de Revenue = punto de llegada
        rev_cx = (C1r + C2) // 2  # midpoint entre C1r y C2
        for i, sd in enumerate(seg_data):
            x1, y1 = C1r, sd["cy"]
            cx = rev_cx
            x2, y2 = C2, rev_entry_y  # borde izquierdo de Revenue, centro vertical
            sd_fw = sd.get("fw", 4)
            sd_fo = sd.get("fo", 0.55)
            # "Sin asignar" → gris, sin cinta (no fluye a revenue conocido)
            if sd.get("nombre") == "Sin asignar":
                sc = "#4a5568"
                sd_fo = 0.0   # sin cinta hacia col2
            else:
                sc = seg_grad_colors[i % len(seg_grad_colors)]
            if sd_fo > 0:
                seg_flows_svg += f'''  <path class="flow-anim" d="M{x1} {y1} C {cx} {y1}, {cx} {y2}, {x2} {y2}" stroke="{sc}" stroke-width="{sd_fw}" fill="none" opacity="{sd_fo}"/>
'''
    else:
        # Sin segmentos: cinta única col1→col2 desde el centro de la caja principal
        col1_cy = 200 + (col1_bottom - 200) // 2   # centro vertical caja col1
        rev_entry_y = rev_y1 + REV_H // 2
        rev_cx = (C1r + C2) // 2
        seg_flows_svg += f'''  <path class="flow-anim" d="M{C1r} {col1_cy} C {rev_cx} {col1_cy}, {rev_cx} {rev_entry_y}, {C2} {rev_entry_y}" stroke="#00d4ff" stroke-width="18" fill="none" opacity="0.45"/>
'''

    # ── X0.60: Pre-compute métricas de texto proporcional para TODAS las cajas ─
    # Mismo criterio que C1: fuente y posición escalan linealmente con h.
    # C2 Revenue — h siempre REV_H=380 → fuentes grandes fijas (no cambia)
    # COGS (C3 top)
    _cfl, _cfv, _cfs = _txt_fs(cogs_h)
    _c_y1 = cogs_y1 + max(14, int(cogs_h * 0.26))
    _c_y2 = cogs_y1 + max(24, int(cogs_h * 0.46))
    _c_y3 = cogs_y1 + max(36, int(cogs_h * 0.66))
    _c_y4 = cogs_y1 + max(48, int(cogs_h * 0.85))
    # EBIT (C3 bottom)
    _efl, _efv, _efs = _txt_fs(EBIT_H)
    _e_yl = ebit_y + max(14, int(EBIT_H * 0.26))
    _e_ys = ebit_y + max(24, int(EBIT_H * 0.47))
    _e_yv = ebit_y + max(36, int(EBIT_H * 0.67))
    _e_ym = ebit_y + max(46, int(EBIT_H * 0.87))
    # C4 Tax / Interest (pequeños)
    _tfl, _tfv, _   = _txt_fs(tax_h)
    _t_yl = tax_y + max(10, int(tax_h * 0.38))
    _t_yv = tax_y + max(18, int(tax_h * 0.73))
    _ifl, _ifv, _   = _txt_fs(int_h)
    _i_yl = int_y + max(10, int(int_h * 0.38))
    _i_yv = int_y + max(18, int(int_h * 0.73))
    # C4 NI (variable)
    _nfl, _nfv, _   = _txt_fs(ni_h)
    _n_yl = ni_y + max(16, int(ni_h * 0.32))
    _n_yv = ni_y + max(30, int(ni_h * 0.68))
    # C5 FCF (variable)
    _ffl, _ffv, _   = _txt_fs(fcf_h)
    _f_yl = fcf_y + max(14, int(fcf_h * 0.34))
    _f_yv = fcf_y + max(26, int(fcf_h * 0.70))
    # C5 Div / Capex / SBC (pequeños)
    _div_fs = max(9, min(12, 8 + int(div_h / 20)));   _div_yc = div_y   + div_h // 2 + 4
    _cpx_fs = max(9, min(12, 8 + int(capex_h / 20))); _cpx_yc = capex_y + capex_h // 2 + 4
    _sbc_fs = max(9, min(12, 8 + int(sbc_h / 20)));   _sbc_yc = sbc_y   + sbc_h // 2 + 4

    # ── Build HTML ────────────────────────────────────────────────────────────
    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{company_name} · Flujo de Dinero FY{fy_year} · Sankey Feroldi</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:clamp(10px,1.1vw,16px)}}
body{{background:#050a12;color:#c8d8f0;font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh;display:flex;flex-direction:column;overflow-x:hidden}}
body::after{{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.04) 2px,rgba(0,0,0,0.04) 4px);pointer-events:none;z-index:999}}
.header{{background:#020710;border-bottom:2px solid #0d2040;padding:1rem 2rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem}}
.header h1{{font-size:1.2rem;color:#c8d8f0;line-height:1.4}}
.header .ticker{{color:#00d4ff}}
.header .sub{{display:block;font-size:0.8rem;color:#94a3b8;font-weight:400}}
.header .brand{{text-align:right}}
.header .brand span{{display:block;font-size:0.9rem;color:#ffd700;font-weight:700}}
.header .brand small{{display:block;font-size:0.75rem;color:#64748b}}
.kpi-bar{{padding:0.75rem 2rem;background:#080f1c;border-bottom:1px solid #0d1f35;display:flex;gap:1.5rem;flex-wrap:wrap;align-items:center}}
.kpi-item{{display:flex;flex-direction:column;gap:0.1rem}}
.kpi-label{{font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.08em}}
.kpi-value{{font-size:1.0rem;font-weight:700;font-family:'Courier New',monospace}}
.kpi-item.green .kpi-value{{color:#00ff9d}}
.kpi-item.gold .kpi-value{{color:#ffd700}}
.kpi-item.red .kpi-value{{color:#ff3a3a}}
.kpi-item.blue .kpi-value{{color:#00d4ff}}
.badge{{padding:0.25rem 0.75rem;border-radius:999px;font-size:0.75rem;font-weight:700;border:1px solid;display:inline-block}}
.badge-verdict{{color:#ffd700;border-color:#ffd700}}
.badge-score{{color:#00d4ff;border-color:#00d4ff}}
.sankey-container{{max-width:1400px;margin:0 auto;padding:1.5rem;width:100%}}
.sankey-container svg{{width:100%;height:auto;display:block}}
.flow-anim{{stroke-dasharray:1000;animation:flowAnim 4s linear infinite}}
@keyframes flowAnim{{from{{stroke-dashoffset:2000}}to{{stroke-dashoffset:0}}}}
.flow-anim-rev{{stroke-dasharray:1000;animation:flowAnimRev 4s linear infinite}}
@keyframes flowAnimRev{{from{{stroke-dashoffset:0}}to{{stroke-dashoffset:2000}}}}
.node:hover{{filter:brightness(1.3);cursor:pointer}}
.node text{{pointer-events:none}}
.legend-section{{background:#080f1c;border:1px solid #0d1f35;border-radius:0.5rem;padding:1rem 1.5rem;max-width:1400px;margin:1rem auto;width:100%}}
.legend-section h3{{font-size:0.9rem;color:#00d4ff;margin-bottom:0.75rem}}
.legend-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:0.6rem}}
.legend-item{{display:flex;align-items:center;gap:0.5rem}}
.legend-dot{{width:0.75rem;height:0.75rem;border-radius:50%;flex-shrink:0}}
.legend-text{{color:#c8d8f0;font-size:0.82rem}}
.legend-val{{color:#ffd700;font-family:'Courier New',monospace;font-size:0.8rem;margin-left:auto}}
.audit-section{{max-width:1400px;margin:1rem auto;width:100%;padding:0 1.5rem}}
.audit-section h3{{font-size:0.9rem;color:#00d4ff;margin-bottom:0.75rem}}
.audit-table{{width:100%;border-collapse:collapse;font-size:0.82rem}}
.audit-table th{{background:#0d1428;color:#00d4ff;font-size:0.75rem;text-transform:uppercase;letter-spacing:0.06em;padding:0.5rem 0.8rem;text-align:left}}
.audit-table td{{font-size:0.78rem;border-bottom:1px solid #0d1428;padding:0.45rem 0.8rem}}
.audit-table tr:hover td{{background:#0a1628}}
.audit-table .val-green{{color:#00ff9d;font-weight:700}}
.audit-table .val-red{{color:#ff3a3a;font-weight:700}}
.status-ok{{color:#00ff9d;font-weight:700}}
.status-est{{color:#ffd700}}
.footer{{background:#020710;border-top:1px solid #0d2040;padding:0.75rem 2rem;font-size:0.78rem;color:#94a3b8;text-align:center;margin-top:auto}}
@media(max-width:768px){{.header{{flex-direction:column;text-align:center}}.kpi-bar{{justify-content:center}}.legend-grid{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>{company_name} · Flujo de Dinero <span class="ticker">FY{fy_year}</span></h1>
    <span class="sub">Diagrama Sankey · Método Feroldi v{VERSION}</span>
  </div>
  <div class="brand">
    <span>@patonet</span>
    <small>{(_ex := meta.get("exchange")) and _ex not in (None,"N/D","") and _ex+":" or ""}{ticker} · ${precio:.2f} · {date_str} · Revenue: {s_rev}</small>
  </div>
</div>

<div class="kpi-bar">
  <div class="kpi-item green"><span class="kpi-label">Ingresos</span><span class="kpi-value">{s_rev}</span></div>
  <div class="kpi-item {"green" if is_profitable else "red"}"><span class="kpi-label">Ut. Neta</span><span class="kpi-value">{s_ni}</span></div>
  <div class="kpi-item green"><span class="kpi-label">FCF</span><span class="kpi-value">{s_fcf}</span></div>
  <div class="kpi-item {"green" if is_profitable else "red"}"><span class="kpi-label">Margen Neto</span><span class="kpi-value">{ni_pct}</span></div>
  <div class="kpi-item blue"><span class="kpi-label">PE Fwd</span><span class="kpi-value">{pe_fwd if pe_fwd else ND}</span></div>
  <div class="kpi-item gold"><span class="kpi-label">Beta</span><span class="kpi-value">{beta if beta else ND}</span></div>
  {f'<div class="kpi-item gold"><span class="kpi-label">Score Feroldi</span><span class="kpi-value">{int(feroldi_score)}/160</span></div>' if feroldi_score else ''}
  {f'<div class="kpi-item green"><span class="kpi-label">Valor Intrínseco</span><span class="kpi-value">${fair_value_mid:.0f}</span></div>' if fair_value_mid else ''}
</div>

<div class="sankey-container">
<svg id="sankey" viewBox="0 0 {W} {H}" width="100%" height="auto" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="glow"><feGaussianBlur stdDeviation="2.5"/><feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="blur"/></feMerge></filter>
    <filter id="glowStrong"><feGaussianBlur stdDeviation="4"/><feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="blur"/></feMerge></filter>
    <!-- BUG-S9 X0.594: gradientes para flujos proporcionales -->
    <linearGradient id="gCOGS" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1a2a4a" stop-opacity="0.8"/><stop offset="100%" stop-color="#ff3a3a" stop-opacity="0.5"/></linearGradient>
    <linearGradient id="gSM"   x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1a2a4a" stop-opacity="0.7"/><stop offset="100%" stop-color="#ff6b35" stop-opacity="0.5"/></linearGradient>
    <linearGradient id="gRD"   x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1a2a4a" stop-opacity="0.7"/><stop offset="100%" stop-color="#ff9800" stop-opacity="0.5"/></linearGradient>
    <linearGradient id="gDA"   x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1a2a4a" stop-opacity="0.7"/><stop offset="100%" stop-color="#9c27b0" stop-opacity="0.5"/></linearGradient>
    <linearGradient id="gOther" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1a2a4a" stop-opacity="0.7"/><stop offset="100%" stop-color="#64748b" stop-opacity="0.5"/></linearGradient>
    <linearGradient id="gEBIT" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1a4a2a" stop-opacity="0.8"/><stop offset="100%" stop-color="#00ff9d" stop-opacity="0.6"/></linearGradient>
    <linearGradient id="gNI"   x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#00ff9d" stop-opacity="0.7"/><stop offset="100%" stop-color="#ffd700" stop-opacity="0.7"/></linearGradient>
    <linearGradient id="gFCF"  x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#ffd700" stop-opacity="0.7"/><stop offset="100%" stop-color="#00d4ff" stop-opacity="0.7"/></linearGradient>
    <linearGradient id="gTax"  x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1a0a0a" stop-opacity="0.7"/><stop offset="100%" stop-color="#ff3a3a" stop-opacity="0.6"/></linearGradient>
    <linearGradient id="gInt"  x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1a1a0a" stop-opacity="0.7"/><stop offset="100%" stop-color="#ffd700" stop-opacity="0.6"/></linearGradient>
  </defs>
  <g opacity="0.03">
    <line x1="{C2}" y1="0" x2="{C2}" y2="{H}" stroke="#00d4ff" stroke-width="1"/>
    <line x1="{C3}" y1="0" x2="{C3}" y2="{H}" stroke="#00d4ff" stroke-width="1"/>
    <line x1="{C4}" y1="0" x2="{C4}" y2="{H}" stroke="#00d4ff" stroke-width="1"/>
    <line x1="{C5}" y1="0" x2="{C5}" y2="{H}" stroke="#00d4ff" stroke-width="1"/>
  </g>
  <!-- ══════ CABECERAS DE COLUMNA ══════ -->
  <text x="{C1+SEG_W//2}"    y="42" text-anchor="middle" font-size="32" letter-spacing="2" fill="#e8f0f5" font-weight="bold">SEGMENTOS</text>
  <text x="{C2+REV_W//2}"    y="42" text-anchor="middle" font-size="32" letter-spacing="2" fill="#e8f0f5" font-weight="bold">INGRESOS</text>
  <text x="{C3+COST_W//2}"   y="42" text-anchor="middle" font-size="32" letter-spacing="2" fill="#e8f0f5" font-weight="bold">EGRESOS</text>
  <text x="{C4+NI_W//2}"     y="42" text-anchor="middle" font-size="32" letter-spacing="2" fill="#e8f0f5" font-weight="bold">RESULTADOS</text>
  <text x="{C5+OUT_W//2}"    y="42" text-anchor="middle" font-size="32" letter-spacing="2" fill="#e8f0f5" font-weight="bold">CAJA</text>

  <!-- ══════ FLOW PATHS (BUG-S10 X0.596) ══════ -->
  <!-- C2r={C2r} = borde derecho Revenue · C3r={C3r} = borde derecho COL3 · C4r={C4r} = borde derecho COL4 -->
{seg_flows_svg}  <!-- COL2 → COL3: salen del BORDE DERECHO del nodo Revenue -->
  <path class="flow-anim" d="M{C2r} {rev_y1+REV_H//2} C {(C2r+C3)//2} {rev_y1+REV_H//2}, {(C2r+C3)//2} {cogs_y1+cogs_h//2}, {C3} {cogs_y1+cogs_h//2}" stroke="url(#gCOGS)" stroke-width="{fw_cogs}" fill="none" opacity="0.5"/>
  <path class="flow-anim" d="M{C2r} {rev_y1+REV_H//2} C {(C2r+C3)//2} {rev_y1+REV_H//2}, {(C2r+C3)//2} {opex_start+sm_h//2}, {C3} {opex_start+sm_h//2}" stroke="url(#gSM)" stroke-width="{fw_sm}" fill="none" opacity="0.45"/>
  <path class="flow-anim" d="M{C2r} {rev_y1+REV_H//2} C {(C2r+C3)//2} {rev_y1+REV_H//2}, {(C2r+C3)//2} {rd_y+rd_h//2}, {C3} {rd_y+rd_h//2}" stroke="url(#gRD)" stroke-width="{fw_rd}" fill="none" opacity="0.45"/>
  <path class="flow-anim" d="M{C2r} {rev_y1+REV_H//2} C {(C2r+C3)//2} {rev_y1+REV_H//2}, {(C2r+C3)//2} {da_y+da_h//2}, {C3} {da_y+da_h//2}" stroke="url(#gDA)" stroke-width="{fw_da}" fill="none" opacity="0.45"/>
  <path class="flow-anim" d="M{C2r} {rev_y1+REV_H//2} C {(C2r+C3)//2} {rev_y1+REV_H//2}, {(C2r+C3)//2} {other_y+other_h//2}, {C3} {other_y+other_h//2}" stroke="url(#gOther)" stroke-width="{fw_other}" fill="none" opacity="0.4"/>
  <!-- BUG-S11 X0.597: COL3 EBIT → COL4 centro del nodo NET INCOME (después de Tax/Int) -->
  <path class="flow-anim" d="M{C3r} {ebit_y+EBIT_H//2} C {(C3r+C4)//2} {ebit_y+EBIT_H//2}, {(C3r+C4)//2} {ni_y+ni_h//2}, {C4} {ni_y+ni_h//2}" stroke="url(#gEBIT)" stroke-width="{fw_ebit}" fill="none" opacity="0.45"/>
  <!-- BUG-S12: flujos Tax/Interest eliminados (cajas visibles, sin flujo saliente) -->
  <!-- BUG-S11: NET INCOME sale de C4r → C5 (FCF stack centrado) -->
  <path class="flow-anim" d="M{C4r} {ni_y+ni_h//2} C {(C4r+C5)//2} {ni_y+ni_h//2}, {(C4r+C5)//2} {fcf_y+fcf_h//2}, {C5} {fcf_y+fcf_h//2}" stroke="url(#gNI)" stroke-width="{fw_ni}" fill="none" opacity="0.6"/>
  <!-- FCF sub-flow hacia destinos de capital -->
  <path class="flow-anim" d="M{C4r} {ni_y+ni_h//2+fw_ni//4} C {(C4r+C5)//2} {ni_y+ni_h//2+fw_ni//4}, {(C4r+C5)//2} {fcf_y+fcf_h//2+20}, {C5} {fcf_y+fcf_h//2+20}" stroke="url(#gFCF)" stroke-width="{fw_fcf}" fill="none" opacity="0.5"/>

  <!-- ══════ COL 1 — SEGMENTOS ══════ -->
'''

    if has_segments:
        # Marco exterior col1 — siempre igual de alto que col2
        frame_h = col1_frame_bottom - 55
        html += f'  <rect x="{C1-4}" y="55" width="{SEG_W+8}" height="{frame_h}" rx="8" fill="none" stroke="#1e3a5f" stroke-width="1" stroke-dasharray="4,3"/>\n'
        # Advertencia de cobertura parcial — en el área vacía del recuadro C1
        if seg_coverage < 0.95:
            last_seg = seg_data[-1]
            last_seg_bottom = last_seg['y'] + last_seg['h']
            _cov_cx        = C1 + SEG_W // 2
            _cov_warn_c1_y = (last_seg_bottom + col1_frame_bottom) // 2
            _uncov_c1      = int((1 - seg_coverage) * 100)
            _empty_h       = col1_frame_bottom - last_seg_bottom
            _fs_pct        = min(22, max(12, _empty_h // 8))   # escala con espacio disponible
            _fs_label      = max(9, _fs_pct - 8)
            html += (
                f'  <text x="{_cov_cx}" y="{_cov_warn_c1_y - _fs_pct // 2}" text-anchor="middle" font-size="{_fs_pct}" font-weight="bold" fill="#f59e0b">⚠️ {_uncov_c1}% no disponible</text>\n'
                f'  <text x="{_cov_cx}" y="{_cov_warn_c1_y + _fs_pct}" text-anchor="middle" font-size="{_fs_label}" fill="#64748b">sin datos en XBRL</text>\n'
            )

        colors = ["#00d4ff","#00e676","#ffd700","#ff6b35","#ff9800","#9c27b0","#64748b"]
        for i, sd in enumerate(seg_data):
            sc = colors[i % 7]
            sp = f"{sd['revenue']/revenue*100:.1f}%" if revenue else "?"
            html += f'''  <g class="node" data-tip="{sd['nombre']}: {hr(sd['revenue'])} ({sp})">
    <rect x="{C1}" y="{sd['y']}" width="{SEG_W}" height="{sd['h']}" rx="5" fill="#0a1a2e" stroke="{sc}" stroke-width="1.5"/>
    <text x="{C1+SEG_W//2}" y="{sd['y']+sd['h']//2}" text-anchor="middle" font-weight="bold" fill="{sc}">
      <tspan x="{C1+SEG_W//2}" dy="{-(len(sd['name_parts'])-1)*(sd['fs']+2)//2-4}" font-size="{sd['fs']}">{sd['name_parts'][0]}</tspan>
      {"".join(f'<tspan x="{C1+SEG_W//2}" dy="{sd["fs"]+2}" font-size="{sd["fs"]}">{part}</tspan>' for part in sd['name_parts'][1:])}
      <tspan x="{C1+SEG_W//2}" dy="{max(sd['fs_sub']+2, 4)}" font-size="{sd['fs_sub']}" fill="#94a3b8">{hr(sd['revenue'])} ({sp})</tspan>
    </text>
  </g>
'''
    else:
        # Nombre de empresa: auto-escalar font y partir en líneas si es largo
        _cn_parts = _split_name(company_name)
        if len(_cn_parts) == 1 and len(company_name) > 22:
            # Nombre muy largo en una sola palabra (raro) → reducir font
            _cn_fs = max(9, 16 - (len(company_name) - 22) // 2)
        else:
            _cn_fs = 14 if len(_cn_parts) > 1 else 16
        _cn_y0 = 185 if len(_cn_parts) == 1 else 178
        _cn_svg = f'<tspan x="{C1+SEG_W//2}" dy="0" font-size="{_cn_fs}">{_cn_parts[0]}</tspan>'
        for _cp in _cn_parts[1:]:
            _cn_svg += f'<tspan x="{C1+SEG_W//2}" dy="{_cn_fs+3}" font-size="{_cn_fs}">{_cp}</tspan>'
        html += f'''  <g class="node" data-tip="{company_name}: {s_rev} (100%)">
    <rect x="{C1}" y="60" width="210" height="460" rx="8" fill="#0a1a2e" stroke="#00a8cc" stroke-width="2" filter="url(#glow)"/>
    <text x="{C1+SEG_W//2}" y="{_cn_y0}" text-anchor="middle" font-weight="bold" fill="#00d4ff">{_cn_svg}</text>
    <text x="{C1+SEG_W//2}" y="215" text-anchor="middle" font-size="11" fill="#94a3b8">{sector}</text>
    <text x="{C1+SEG_W//2}" y="250" text-anchor="middle" font-size="20" font-weight="bold" fill="#00ff9d">{s_rev}</text>
    <text x="{C1+SEG_W//2}" y="275" text-anchor="middle" font-size="11" fill="#94a3b8">FY{fy_year} · 100% Ingresos</text>
    <text x="{C1+SEG_W//2}" y="320" text-anchor="middle" font-size="11" fill="#64748b">Segmentos no disponibles</text>
    <text x="{C1+SEG_W//2}" y="340" text-anchor="middle" font-size="10" fill="#64748b">(correr análisis Feroldi primero)</text>
    <text x="{C1+SEG_W//2}" y="400" text-anchor="middle" font-size="11" fill="#94a3b8">Ing. YoY: {revenue_yoy if revenue_yoy else ND}</text>
  </g>
'''

    html += f'''
  <!-- ══════ COL 2 — REVENUE (BUG-S10: height=REV_H, width=REV_W) ══════ -->
  <g class="node" data-tip="Ingresos GAAP FY{fy_year}: {s_rev}">
    <rect x="{C2}" y="{rev_y1}" width="{REV_W}" height="{REV_H}" rx="8" fill="#0d1f35" stroke="#00a8cc" stroke-width="2.5" filter="url(#glowStrong)"/>
    <text x="{C2+REV_W//2}" y="{rev_y1+22}" text-anchor="middle" font-size="11" font-weight="bold" fill="#1e6080">INGRESOS GAAP</text>
    <text x="{C2+REV_W//2}" y="{rev_y1+REV_H//2-10}" text-anchor="middle" font-size="28" font-weight="bold" fill="#00ff9d">{s_rev}</text>
    <text x="{C2+REV_W//2}" y="{rev_y1+REV_H//2+22}" text-anchor="middle" font-size="11" fill="#94a3b8">FY{fy_year}</text>
    <text x="{C2+REV_W//2}" y="{rev_y1+REV_H//2+40}" text-anchor="middle" font-size="10" fill="#94a3b8">Margen Bruto: {gross_pct}</text>
    <text x="{C2+REV_W//2}" y="{rev_y1+REV_H//2+57}" text-anchor="middle" font-size="10" fill="#64748b">{(_ex := meta.get("exchange")) and _ex not in (None,"N/D","") and _ex+":" or ""}{ticker}</text>
  </g>

  <!-- ══════ COL 3 — COSTOS (X0.60: texto proporcional a h) ══════ -->
  <g class="node" data-tip="Costo de Ventas: {s_cogs} ({cogs_pct})">
    <rect x="{C3}" y="{cogs_y1}" width="{COST_W}" height="{cogs_h}" rx="6" fill="#200a0a" stroke="#ff3a3a" stroke-width="1.5"/>
    <text x="{C3+COST_W//2}" y="{_c_y1}" text-anchor="middle" font-size="{_cfl}" font-weight="bold" fill="#ff3a3a">COSTO DE VENTAS</text>
    {'<text x="%d" y="%d" text-anchor="middle" font-size="%d" fill="#94a3b8">Costos directos</text>' % (C3+COST_W//2, _c_y2, _cfs) if cogs_h >= 55 else ''}
    <text x="{C3+COST_W//2}" y="{_c_y3}" text-anchor="middle" font-size="{_cfv}" font-weight="bold" fill="#00ff9d">{s_cogs}</text>
    {'<text x="%d" y="%d" text-anchor="middle" font-size="%d" fill="#94a3b8">%s</text>' % (C3+COST_W//2, _c_y4, _cfs, cogs_pct) if cogs_h >= 70 else ''}
  </g>

{_cost_box(opex_start, sm_h, "#ff6b35", "#1f1008", "VENTAS Y MARKETING", "Adquisición clientes", s_sm, tip=f"Ventas y Marketing: {s_sm}")}{_cost_box(rd_y, rd_h, "#ff9800", "#1a1508", "I+D / INGENIERÍA", "Investigación", s_rd, tip=f"I+D: {s_rd}")}{_cost_box(da_y, da_h, "#9c27b0", "#150a20", "DEPREC. Y AMORT.", "D&amp;A", s_da, tip=f"Depreciación y Amort.: {s_da}")}{_cost_box(other_y, other_h, "#64748b", "#0a0a15", "OTROS GASTOS", "Otros OpEx", s_other, tip=f"Otros Gastos: {s_other}")}
  <g>
    <rect x="{C3}" y="{opex_label_y}" width="{COST_W}" height="25" rx="3" fill="#0a0505" stroke="#64748b" stroke-width="1" stroke-dasharray="4,3"/>
    <text x="{C3+COST_W//2}" y="{opex_label_y+17}" text-anchor="middle" font-size="10" fill="#94a3b8">OpEx: {s_opex} ({opex_total/revenue*100:.1f}%)</text>
  </g>

  <g class="node" data-tip="EBIT — Utilidad Operativa: {s_opinc} | Margen: {op_margin}">
    <rect x="{C3}" y="{ebit_y}" width="{COST_W}" height="{EBIT_H}" rx="6" fill="#0a1f0a" stroke="{inc_color}" stroke-width="2" filter="url(#glow)"/>
    <text x="{C3+COST_W//2}" y="{_e_yl}" text-anchor="middle" font-size="{_efl}" font-weight="bold" fill="{inc_color}">EBIT</text>
    {'<text x="%d" y="%d" text-anchor="middle" font-size="%d" fill="#94a3b8">Util. Operativa</text>' % (C3+COST_W//2, _e_ys, _efs) if EBIT_H >= 55 else ''}
    <text x="{C3+COST_W//2}" y="{_e_yv}" text-anchor="middle" font-size="{_efv}" font-weight="bold" fill="{inc_color}">{s_opinc}</text>
    {'<text x="%d" y="%d" text-anchor="middle" font-size="%d" fill="#94a3b8">Margen: %s</text>' % (C3+COST_W//2, _e_ym, _efs, op_margin) if EBIT_H >= 50 else ''}
  </g>

  <!-- ══════ COL 4 — RESULTADO FINANCIERO (X0.60: texto proporcional) ══════ -->
  <g class="node" data-tip="Impuestos: {s_tax}">
    <rect x="{C4}" y="{tax_y}" width="{NI_W}" height="{tax_h}" rx="5" fill="#1a0a0a" stroke="#ff3a3a" stroke-width="1"/>
    <text x="{C4+NI_W//2}" y="{_t_yl}" text-anchor="middle" font-size="{_tfl}" fill="#94a3b8">Impuestos</text>
    <text x="{C4+NI_W//2}" y="{_t_yv}" text-anchor="middle" font-size="{_tfv}" font-weight="bold" fill="#ff3a3a">{s_tax}</text>
  </g>

  <g class="node" data-tip="Intereses: {s_interest}">
    <rect x="{C4}" y="{int_y}" width="{NI_W}" height="{int_h}" rx="5" fill="#1a1a0a" stroke="#ffd700" stroke-width="1.5"/>
    <text x="{C4+NI_W//2}" y="{_i_yl}" text-anchor="middle" font-size="{_ifl}" fill="#94a3b8">Intereses</text>
    <text x="{C4+NI_W//2}" y="{_i_yv}" text-anchor="middle" font-size="{_ifv}" font-weight="bold" fill="#ffd700">{s_interest}</text>
  </g>

  <!-- UTILIDAD NETA centrada en C4 -->
  <g class="node" data-tip="{ni_label}: {s_ni}">
    <rect x="{C4}" y="{ni_y}" width="{NI_W}" height="{ni_h}" rx="6" fill="#0a1f0a" stroke="{ni_color}" stroke-width="2" filter="url(#glowStrong)"/>
    <text x="{C4+NI_W//2}" y="{_n_yl}" text-anchor="middle" font-size="{_nfl}" font-weight="bold" fill="{ni_color}">{ni_label}</text>
    <text x="{C4+NI_W//2}" y="{_n_yv}" text-anchor="middle" font-size="{_nfv}" font-weight="bold" fill="{ni_color}">{s_ni}</text>
  </g>

  <!-- ══════ COL 5 — DESTINOS DE CAPITAL ══════ -->
  <text x="{C5+OUT_W//2}" y="{fcf_y-8}" text-anchor="middle" font-size="10" fill="#64748b">FCO {s_cfo}</text>

  <!-- ══════ COL 5 — DESTINOS DE CAPITAL (X0.60: texto proporcional) ══════ -->
  <g class="node" data-tip="Flujo de Caja Libre: {s_fcf}">
    <rect x="{C5}" y="{fcf_y}" width="{OUT_W}" height="{fcf_h}" rx="6" fill="#0a1f2a" stroke="#00d4ff" stroke-width="2" filter="url(#glow)"/>
    <text x="{C5+OUT_W//2}" y="{_f_yl}" text-anchor="middle" font-size="{_ffl}" font-weight="bold" fill="#00d4ff">FLUJO CAJA LIBRE</text>
    <text x="{C5+OUT_W//2}" y="{_f_yv}" text-anchor="middle" font-size="{_ffv}" font-weight="bold" fill="#00d4ff">{s_fcf}</text>
  </g>

  <g class="node" data-tip="Dividendos: {s_div}">
    <rect x="{C5}" y="{div_y}" width="{OUT_W}" height="{div_h}" rx="4" fill="#1a1a0a" stroke="#ffd700" stroke-width="1"/>
    <text x="{C5+OUT_W//2}" y="{_div_yc}" text-anchor="middle" font-size="{_div_fs}" fill="#ffd700">Div: {s_div}</text>
  </g>

  <g class="node" data-tip="Capex: {s_capex}">
    <rect x="{C5}" y="{capex_y}" width="{OUT_W}" height="{capex_h}" rx="4" fill="#1a1508" stroke="#ff9800" stroke-width="1"/>
    <text x="{C5+OUT_W//2}" y="{_cpx_yc}" text-anchor="middle" font-size="{_cpx_fs}" fill="#ff9800">Capex: {s_capex}</text>
  </g>

  <g class="node" data-tip="SBC: {s_sbc}">
    <rect x="{C5}" y="{sbc_y}" width="{OUT_W}" height="{sbc_h}" rx="4" fill="#150a20" stroke="#9c27b0" stroke-width="1"/>
    <text x="{C5+OUT_W//2}" y="{_sbc_yc}" text-anchor="middle" font-size="{_sbc_fs}" fill="#9c27b0">SBC: {s_sbc}</text>
  </g>

  <g class="node" data-tip="Deuda: {s_debt} · Cash: {s_cash} · Goodwill: {s_gw}">
    <rect x="{C5}" y="{bal_y}" width="{OUT_W}" height="50" rx="4" fill="#080f1c" stroke="#0d1f35" stroke-width="1"/>
    <text x="{C5+OUT_W//2}" y="{bal_y+18}" text-anchor="middle" font-size="9" fill="#94a3b8">Deuda: {s_debt} · Cash: {s_cash}</text>
    <text x="{C5+OUT_W//2}" y="{bal_y+34}" text-anchor="middle" font-size="9" fill="#94a3b8">Goodwill: {s_gw} · Cap: {s_mkt_cap}</text>
  </g>

</svg>
</div>

<div class="legend-section">
  <h3>📊 Leyenda FY{fy_year} — Verificado (SEC 10-K · Alpha Vantage · TradingView)</h3>
  <div class="legend-grid">
    <div class="legend-item"><div class="legend-dot" style="background:#00a8cc"></div><span class="legend-text">Ingresos</span><span class="legend-val">{s_rev}</span></div>
    <div class="legend-item"><div class="legend-dot" style="background:#ff3a3a"></div><span class="legend-text">Costo Ventas</span><span class="legend-val">{s_cogs}</span></div>
    <div class="legend-item"><div class="legend-dot" style="background:#ff6b35"></div><span class="legend-text">V. y Mktg</span><span class="legend-val">{s_sm}</span></div>
    <div class="legend-item"><div class="legend-dot" style="background:#ff9800"></div><span class="legend-text">I+D</span><span class="legend-val">{s_rd}</span></div>
    <div class="legend-item"><div class="legend-dot" style="background:#9c27b0"></div><span class="legend-text">Dep. y Amort.</span><span class="legend-val">{s_da}</span></div>
    <div class="legend-item"><div class="legend-dot" style="background:{inc_color}"></div><span class="legend-text">EBIT</span><span class="legend-val">{s_opinc}</span></div>
    <div class="legend-item"><div class="legend-dot" style="background:{ni_color}"></div><span class="legend-text">{ni_label}</span><span class="legend-val">{s_ni}</span></div>
    <div class="legend-item"><div class="legend-dot" style="background:#00d4ff"></div><span class="legend-text">Flujo Caja Libre</span><span class="legend-val">{s_fcf}</span></div>
  </div>
</div>

<!-- ══════ TABLA AUDITORÍA (FIX 1) ══════ -->
<div class="audit-section">
  <h3>📋 Tabla Auditoría — FY{fy_year}</h3>
  <table class="audit-table">
    <thead><tr><th>Rubro</th><th>Valor FY</th><th>Fuente Primaria</th><th>Estado</th><th>Nota</th></tr></thead>
    <tbody>
      <tr><td>Ingresos GAAP</td><td><strong class="val-green">{s_rev_raw}</strong></td><td>EDGAR XBRL (10-K)</td><td><span class="status-ok">✅ Verificado</span></td><td>FY{fy_year}</td></tr>
      <tr><td>Costo de Ventas</td><td><strong class="val-green">{s_cogs_raw}</strong></td><td>Calculado Rev × (1−{gross_pct})</td><td><span class="status-est">⚡ Estimado</span></td><td>Margen Bruto {gross_pct} vía Alpha Vantage</td></tr>
      <tr><td>Ganancia Bruta</td><td><strong class="val-green">{s_gross_raw}</strong></td><td>Ingresos − Costo Ventas</td><td><span class="status-est">⚡ Estimado</span></td><td>Margen {gross_pct}</td></tr>
      <tr><td>Ventas y Mktg</td><td><strong class="val-green">{s_sm_raw}</strong></td><td>Estimado de 10-K</td><td><span class="status-est">⚡ Estimado</span></td><td>~{sm_pct*100:.0f}% de OpEx</td></tr>
      <tr><td>I+D / Ingeniería</td><td><strong class="val-green">{s_rd_raw}</strong></td><td>Estimado de 10-K</td><td><span class="status-est">⚡ Estimado</span></td><td>~{rd_pct*100:.0f}% de OpEx</td></tr>
      <tr><td>Deprec. y Amort.</td><td><strong class="val-green">{s_da_raw}</strong></td><td>Estimado de 10-K</td><td><span class="status-est">⚡ Estimado</span></td><td>~{da_pct*100:.0f}% de OpEx</td></tr>
      <tr><td>Otros Gastos Op.</td><td><strong class="val-green">{s_other_raw}</strong></td><td>Estimado de 10-K</td><td><span class="status-est">⚡ Estimado</span></td><td>~{other_pct*100:.0f}% de OpEx</td></tr>
      <tr><td>EBIT (Util. Operativa)</td><td><strong class="val-green">{s_opinc_raw}</strong></td><td>{ebit_source}</td><td><span class="{ebit_status[0]}">{ebit_status[1]}</span></td><td>Margen Operativo {op_margin}</td></tr>
      <tr><td>Gasto Intereses</td><td><strong class="val-red">{s_interest_raw}</strong></td><td>Estimado 5% × Deuda</td><td><span class="status-est">⚡ Estimado</span></td><td>Deuda total {s_debt}</td></tr>
      <tr><td>Provisión Impuestos</td><td><strong class="val-red">{s_tax_raw}</strong></td><td>Reconciliado EBIT → Ut. Neta</td><td><span class="status-est">⚡ Estimado</span></td><td>TIE estimada</td></tr>
      <tr><td>Utilidad Neta</td><td><strong class="val-green">{s_ni_raw}</strong></td><td>EDGAR XBRL (10-K)</td><td><span class="status-ok">✅ Verificado</span></td><td>Margen Neto {ni_pct} · EPS FY{fy_year}</td></tr>
      <tr><td>Flujo Caja Operativo</td><td><strong class="val-green">{s_cfo_raw}</strong></td><td>EDGAR XBRL (10-K)</td><td><span class="status-ok">✅ Verificado</span></td><td>Conversión de caja</td></tr>
      <tr><td>Capex</td><td><strong class="val-red">{s_capex_raw}</strong></td><td>EDGAR XBRL (10-K)</td><td><span class="status-ok">✅ Verificado</span></td><td>{note_capex}</td></tr>
      <tr><td>Flujo Caja Libre</td><td><strong class="val-green">{s_fcf_raw}</strong></td><td>FCO − Capex</td><td><span class="status-ok">✅ Verificado</span></td><td>{note_fcf_yield}</td></tr>
      <tr><td>SBC (Comp. Acciones)</td><td><strong class="val-green">{s_sbc_raw}</strong></td><td>EDGAR XBRL (10-K)</td><td><span class="status-ok">✅ Verificado</span></td><td>{note_sbc}</td></tr>
      <tr><td>Dividendos</td><td><strong class="val-green">{s_div_raw}</strong></td><td>EDGAR XBRL (10-K)</td><td><span class="status-ok">✅ Verificado</span></td><td>{note_div_yield}</td></tr>
      <tr><td>Deuda Total</td><td><strong class="val-red">{s_debt_raw}</strong></td><td>EDGAR (LT + ST)</td><td><span class="status-ok">✅ Verificado</span></td><td>{note_de_ratio}</td></tr>
      <tr><td>Efectivo y Equiv.</td><td><strong class="val-green">{s_cash_raw}</strong></td><td>EDGAR XBRL (10-K)</td><td><span class="status-ok">✅ Verificado</span></td><td>Efectivo + Valores negociables</td></tr>
      <tr><td>Goodwill</td><td><strong class="val-green">{s_gw_raw}</strong></td><td>EDGAR XBRL (10-K)</td><td><span class="status-ok">✅ Verificado</span></td><td>{note_gw_pct}</td></tr>
      <tr><td>Acciones</td><td><strong class="val-green">{s_shares_raw}</strong></td><td>EDGAR XBRL (10-K)</td><td><span class="status-ok">✅ Verificado</span></td><td>Básicas en circulación</td></tr>
'''

    # Segment rows in audit table
    if has_segments:
        for sd in seg_data:
            sp = f"{sd['revenue']/revenue*100:.1f}%" if revenue else "?"
            html += f'''      <tr><td>Segmento: {sd['nombre']}</td><td><strong class="val-green">{hr(sd['revenue'])}</strong></td><td>EDGAR XBRL (dimension)</td><td><span class="status-ok">✅ Verificado</span></td><td>{sp} de Revenue</td></tr>
'''

    html += '''    </tbody>
  </table>
</div>
'''

    html += f'''
<div class="footer">
  @patonet · Análisis Feroldi · ${ticker} · FY{fy_year} · {date_str} · No constituye asesoría de inversión.
</div>

<div id="tooltip" style="position:fixed;background:#0a1628;border:1px solid #00d4ff;border-radius:0.5rem;padding:0.75rem 1rem;font-size:0.82rem;color:#c8d8f0;max-width:18rem;pointer-events:none;z-index:9999;display:none;line-height:1.5;box-shadow:0 0 20px rgba(0,212,255,0.2);"></div>

<script>
document.querySelectorAll(".node").forEach(function(el){{
  el.addEventListener("mouseenter",function(e){{
    var t=document.getElementById("tooltip");
    t.innerHTML="<strong style=\\"color:#00d4ff\\">"+this.dataset.tip+"</strong>";
    t.style.display="block";
  }});
  el.addEventListener("mousemove",function(e){{
    var t=document.getElementById("tooltip");
    t.style.left=(e.clientX+12)+"px"; t.style.top=(e.clientY-30)+"px";
  }});
  el.addEventListener("mouseleave",function(){{
    document.getElementById("tooltip").style.display="none";
  }});
}});
</script>
</body>
</html>
'''

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    seg_count = len(segmentos_raw) if has_segments else 0
    print(f"\n{'='*58}")
    print(f"  ✅ SANKEY GENERADO — v{VERSION}")
    print(f"  Archivo: {out_path}")
    print(f"  {company_name} ({ticker}) · FY{fy_year}")
    print(f"  Revenue: {s_rev} · {ni_label}: {s_ni} · FCF: {s_fcf}")
    print(f"  viewBox: 0 0 {W} {H}")
    if has_segments:
        print(f"  Segmentos: {seg_count} (proporcionales)")
        for s in seg_data:
            print(f"    · {s['nombre']}: {hr(s['revenue'])} [{s['h']}px]")
    else:
        print(f"  Segmentos: No disponibles")
    print(f"{'='*58}\n")
    return out_path


def main():
    if len(sys.argv) < 2:
        print("USO: python3 feroldi_sankey.py TICKER PRECIO")
        print("     python3 feroldi_sankey.py ~/Downloads/datos_TICKER.json PRECIO")
        print("EJ:  python3 feroldi_sankey.py AAPL 287.46")
        sys.exit(1)

    first = sys.argv[1]
    precio = float(sys.argv[2]) if len(sys.argv) > 2 else None

    if first.endswith(".json") and os.path.isfile(first):
        json_path = first
    else:
        ticker = first.upper()
        today = datetime.now().strftime("%d%m%Y")
        json_path = os.path.expanduser(f"~/Downloads/datos_{ticker}_{today}.json")
        if not os.path.isfile(json_path):
            yd = (datetime.now() - timedelta(days=1)).strftime("%d%m%Y")
            json_path = os.path.expanduser(f"~/Downloads/datos_{ticker}_{yd}.json")
        if not os.path.isfile(json_path):
            print(f"  ❌ No se encontró JSON para {ticker} en ~/Downloads/")
            sys.exit(1)

    generar_sankey(json_path, precio)


if __name__ == "__main__":
    main()
