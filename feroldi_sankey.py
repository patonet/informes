#!/usr/bin/env python3
"""
FEROLDI SANKEY — v X0.56
Sistema Feroldi · @patonet
======================================
CHANGELOG X0.56:
  [F6] Font scaling proporcional a altura de nodo (sqrt scaling, con min/max caps)
  [F5b] Normalización alturas COL3 — mismo algoritmo que COL1 (overflow fix)
  [F5]  Normalización alturas COL1 post-mínimo
  [F4]  Font stack macOS-first
  [F3]  will-change + contain → animaciones no se pausan en Firefox
  [F2]  stroke-dasharray:1000 → animaciones siempre visibles
  [F1]  SVG CSS aspect-ratio + display:block (no height='auto') → Firefox fix
OPCION C: JSON enriquecido opcional. Sin 'enriquecido' → modo basico.
"""
import json, sys
from pathlib import Path
from datetime import datetime

FONT_UI   = "-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif"
FONT_MONO = "'Courier New',SFMono-Regular,Consolas,monospace"

def fmt_b(v, decimals=2):
    if v is None: return "N/D"
    v=float(v); neg=v<0; sign="-" if neg else ""; v=abs(v)
    if v>=1e12: return f"${sign}{v/1e12:.{decimals}f}T"
    if v>=1e9:  return f"${sign}{v/1e9:.{decimals}f}B"
    if v>=1e6:  return f"${sign}{v/1e6:.1f}M"
    return f"${sign}{v:,.0f}"

def pct(v,d=1):
    if v is None: return "N/D"
    return f"{float(v):.{d}f}%"

def safe_val(v):
    if v is None: return "N/D"
    try: return round(float(v),2)
    except: return "N/D"

def sw(val,total,mn=2,mx=28):
    if not val or not total: return mn
    return max(mn,min(mx,round(abs(float(val))/abs(float(total))*mx)))

def fs(base, h, mn, mx, ref=80):
    """Font size proporcional a altura del nodo. sqrt evita escalado agresivo."""
    scaled = round(base * (max(h, mn*4) / ref) ** 0.5)
    return max(mn, min(mx, scaled))

def r(x,y,w,h,fill,stroke,sw=1.5,glow=False,rx=6):
    g=' filter="url(#glow)"' if glow else ''
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{g}/>'

def t(x,y,s,size,fill,anchor="middle",bold=False,font=None):
    f=font or FONT_UI; w=' font-weight="bold"' if bold else ''
    return f'<text x="{x}" y="{y}" font-family="{f}" font-size="{size}"{w} fill="{fill}" text-anchor="{anchor}">{s}</text>'

def fl(cls,d,stroke,sw_val,opacity=.5):
    return f'<path class="{cls}" d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw_val}" opacity="{opacity}"/>'

def calcular(d):
    e=d.get("edgar",{}); ra=d.get("ratios",{})
    rev=e.get("revenue") or 0; ni=e.get("net_income") or 0
    cfo=e.get("cfo") or 0; capex=e.get("capex") or 0
    fcf=e.get("fcf") or 0; sbc=e.get("sbc") or 0
    div=e.get("dividendos") or 0; deuda=e.get("deuda_total") or 0
    gw=e.get("goodwill") or 0; ta=e.get("total_assets") or 1
    cash=e.get("cash_real") or 0
    mb=ra.get("margen_bruto"); mop=ra.get("margen_op"); me=ra.get("margen_ebitda")
    gp=(rev*mb/100) if mb else None
    cogs=(rev-gp) if gp is not None else None
    ebit=(rev*mop/100) if mop else None
    opex=(gp-ebit) if (gp and ebit) else None
    ebitda=(rev*me/100) if me else None
    da=(ebitda-ebit) if (ebitda and ebit) else None
    taxes=(ebit-ni) if (ebit and ni) else None
    etr=(taxes/ebit*100) if (taxes and ebit) else None
    gw_pct=(gw/ta*100) if gw else None
    return dict(revenue=rev,cogs=cogs,gross_profit=gp,op_expenses=opex,
                ebit=ebit,da=da,ebitda=ebitda,taxes=taxes,etr=etr,
                net_income=ni,cfo=cfo,capex=capex,fcf=fcf,sbc=sbc,
                dividendos=div,deuda=deuda,goodwill=gw,goodwill_pct=gw_pct,
                cash_real=cash,total_assets=ta)

def generar_html(d):
    meta=d.get("meta",{}); edgar=d.get("edgar",{}); ratios=d.get("ratios",{})
    market=d.get("market",{}); perf=d.get("performance",{}); enr=d.get("enriquecido",{})
    IS_ENR=bool(enr)
    ticker=meta.get("ticker","TICKER"); precio=meta.get("precio_usuario",0)
    exchange=meta.get("exchange","NYSE"); fecha=meta.get("fecha",datetime.now().strftime("%d-%m-%Y"))
    company=meta.get("company_name",ticker); fy_year=edgar.get("fy_year","2025")
    f=calcular(d); rev=f["revenue"] or 1
    segs=edgar.get("segmentos",[])
    if not segs: segs=[{"nombre":company,"revenue":f["revenue"]}]
    for s in segs: s["pct"]=(s["revenue"]/rev*100) if s.get("revenue") else 0
    SEG_COLORS=[("#1a5fa0","#4090d0"),("#e53935","#e57373"),("#ffd700","#ffd700"),
                ("#00838f","#00bcd4"),("#6a1b9a","#ce93d8"),("#2e7d32","#81c784"),("#e65100","#ff8c00")]
    VH=860 if IS_ENR else 760; AVAIL_H=700

    # F5: normalizar alturas
    seg_gap=20; _av=AVAIL_H-seg_gap*(len(segs)-1); _mh=60
    _raw=[s["pct"]/100*_av for s in segs]; _wm=[max(_mh,r2) for r2 in _raw]
    if sum(_wm)>_av:
        _atm=[_raw[i]<_mh for i in range(len(segs))]
        _fix=sum(_mh for am in _atm if am)
        _sc2=sum(r2 for i,r2 in enumerate(_wm) if not _atm[i])
        _scale=(_av-_fix)/_sc2 if _sc2>0 else 1
        heights=[_mh if _atm[i] else max(_mh,round(_wm[i]*_scale)) for i in range(len(segs))]
    else: heights=[round(r2) for r2 in _wm]

    seg_nodes=[]; y=30; segs_extra=enr.get("segmentos_extra",[]) if IS_ENR else []
    for i,s in enumerate(segs):
        cs,cf=SEG_COLORS[i%len(SEG_COLORS)]; h=heights[i]; cy=y+h//2
        ex=next((e2 for e2 in segs_extra if e2.get("nombre")==s["nombre"]),{})
        seg_nodes.append({"x":20,"y":y,"w":200,"h":h,"cy":cy,
                          "nombre":s["nombre"],"revenue":s.get("revenue",0),
                          "pct":s["pct"],"stroke":cs,"text_color":cf,"extra":ex})
        y+=h+seg_gap
    rev_cy=30+AVAIL_H//2

    # Gradients
    grads="\n  ".join([
        f'<linearGradient id="flow-seg{i}" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="{SEG_COLORS[i%len(SEG_COLORS)][0]}" stop-opacity=".6"/><stop offset="100%" stop-color="#00a8cc" stop-opacity=".4"/></linearGradient>'
        for i in range(len(seg_nodes))
    ]+['<linearGradient id="flow-ebit" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#00a8cc" stop-opacity=".4"/><stop offset="100%" stop-color="#00ff9d" stop-opacity=".5"/></linearGradient>',
       '<linearGradient id="flow-ni" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#00ff9d" stop-opacity=".4"/><stop offset="100%" stop-color="#00d4ff" stop-opacity=".5"/></linearGradient>',
       '<linearGradient id="flow-fcf" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#4caf50" stop-opacity=".4"/><stop offset="100%" stop-color="#00c853" stop-opacity=".5"/></linearGradient>'])

    # COL1
    col1=[]
    for n in seg_nodes:
        ex=n["extra"]; cy=n["cy"]; h=n["h"]
        p=[r(n["x"],n["y"],n["w"],h,"#0d1f35",n["stroke"],glow=True),
           t(120,cy-int(h*0.12),n["nombre"][:24],fs(13,h,9,16),n["text_color"],bold=True),
           t(120,cy+int(h*0.06),fmt_b(n["revenue"]),fs(16,h,11,22),"#00ff9d",font=FONT_MONO,bold=True),
           t(120,cy+int(h*0.22),f"{n['pct']:.1f}% del revenue",fs(10,h,7,12),"#94a3b8")]
        if ex and IS_ENR:
            if ex.get("detalle"): p.append(t(120,cy-33,ex["detalle"],8.5,"#6b7fa3"))
            if ex.get("yoy_pct") is not None:
                yc="#00c853" if ex["yoy_pct"]>=0 else "#ff3a3a"
                sg="+" if ex["yoy_pct"]>=0 else ""
                rk=" 🚀" if ex.get("rocket") else ""
                p.append(t(120,cy+37,f"YoY: {sg}{ex['yoy_pct']}%{rk}",10,yc))
            if ex.get("nota"): p.append(t(120,cy+51,ex["nota"][:28],8,"#94a3b8"))
            if ex.get("nota2"): p.append(t(120,cy+63,ex["nota2"][:28],7.5,"#6b7fa3"))
        col1.append(f'<g class="node" data-tip="{n["nombre"]}: {fmt_b(n["revenue"])} ({n["pct"]:.1f}%)">{"".join(p)}</g>')

    flows_c1=[fl("flow-path",f"M 220 {n['cy']} C 260 {n['cy']}, 260 {rev_cy}, 300 {rev_cy}",
                 n["stroke"],sw(n["revenue"],rev,3,28),.6) for n in seg_nodes]

    # COL2
    qtr=enr.get("quarterly",{}) if IS_ENR else {}
    yoy=ratios.get("revenue_yoy")
    yoy_str=f"+{yoy:.1f}% YoY" if yoy and yoy>=0 else (f"{yoy:.1f}% YoY" if yoy else "")
    rev_h=300 if (IS_ENR and qtr) else 240; rev_y=rev_cy-rev_h//2
    col2=[r(300,rev_y,170,rev_h,"#0d1f35","#00a8cc",2,glow=True),
          t(385,rev_y+30,"REVENUE GAAP",11,"#00d4ff",bold=True),
          t(385,rev_y+47,f"FY{fy_year} · {yoy_str}",9,"#94a3b8"),
          t(385,rev_y+78,fmt_b(f["revenue"]),20,"#00ff9d",font=FONT_MONO,bold=True),
          f'<line x1="315" y1="{rev_y+93}" x2="455" y2="{rev_y+93}" stroke="#1a2a4a" stroke-width="1"/>',
          t(385,rev_y+113,f"Margen Bruto: {pct(ratios.get('margen_bruto'))}",10,"#94a3b8",font=FONT_MONO),
          t(385,rev_y+131,f"Margen Op: {pct(ratios.get('margen_op'))}",10,"#94a3b8",font=FONT_MONO),
          t(385,rev_y+149,f"Margen Neto: {pct(ratios.get('margen_neto'))}",10,"#94a3b8",font=FONT_MONO),
          t(385,rev_y+169,f"ROIC: {pct(ratios.get('roic'))}",10,"#00c853",font=FONT_MONO),
          t(385,rev_y+189,f"P/E Fwd: {safe_val(ratios.get('pe_forward'))}x · PEG: {safe_val(ratios.get('peg'))}",10,"#94a3b8",font=FONT_MONO)]
    if IS_ENR and qtr:
        q4c="#ffd700" if qtr.get("q4_record") else "#00ff9d"
        q4s=f"Q4: {fmt_b(qtr.get('q4'))} (REC.)" if qtr.get("q4_record") else f"Q4: {fmt_b(qtr.get('q4'))}"
        col2+=[f'<line x1="315" y1="{rev_y+203}" x2="455" y2="{rev_y+203}" stroke="#1a2a4a" stroke-width="1"/>',
               t(385,rev_y+218,f"Q1: {fmt_b(qtr.get('q1'))}",9,"#94a3b8",font=FONT_MONO),
               t(385,rev_y+233,f"Q2: {fmt_b(qtr.get('q2'))}",9,"#94a3b8",font=FONT_MONO),
               t(385,rev_y+248,f"Q3: {fmt_b(qtr.get('q3'))}",9,"#94a3b8",font=FONT_MONO),
               t(385,rev_y+263,q4s,9,q4c,bold=True,font=FONT_MONO),
               t(385,rev_y+281,f"Q4 GM: {pct(qtr.get('q4_gm_pct'))} {'(RÉCORD)' if qtr.get('q4_record') else ''}",9,"#ffd700" if qtr.get("q4_record") else "#94a3b8"),
               t(385,rev_y+295,f"EV/Sales: {qtr.get('ev_sales','N/D')}",9,"#94a3b8")]

    # COL3
    opex_b=enr.get("opex_breakdown",{}) if IS_ENR else {}
    c3_items=[]; col3_nodes=[]; col3=[]; col3_ebit_cy=rev_cy
    if IS_ENR and opex_b:
        if f["cogs"] is not None:
            c3_items.append({"label":"COGS","val":f["cogs"],"fill":"#200a0a","stroke":"#ff3a3a",
                "notas":[opex_b.get("cogs_nota",""),opex_b.get("cogs_nota2",""),
                         opex_b.get("cogs_alerta",""),f"{pct(100-(ratios.get('margen_bruto') or 0))} del rev."]})
        if f["gross_profit"] is not None:
            c3_items.append({"label":"Gross Profit","val":f["gross_profit"],"fill":"#081a10","stroke":"#00ff9d",
                "notas":[f"Margen bruto: {pct(ratios.get('margen_bruto'))} GAAP",
                         f"{pct(opex_b.get('gp_ngaap_pct'))} non-GAAP" if opex_b.get("gp_ngaap_pct") else "",
                         f"Q4: {pct(opex_b.get('gp_q4_pct'))} GAAP (récord ↑)" if opex_b.get("gp_q4_pct") else ""]})
        for key,label in [("rd","R&D"),("sm","Sales &amp; Marketing"),("ga","G&A")]:
            ob=opex_b.get(key)
            if ob: c3_items.append({"label":label,"val":ob["valor"],"fill":"#1a1208","stroke":"#ff6b35",
                "notas":[f"{pct(ob.get('pct_rev'))} revenue",ob.get("nota",""),ob.get("nota2","")]})
    else:
        if f["cogs"] and f["cogs"]>0:
            c3_items.append({"label":"COGS","val":f["cogs"],"fill":"#200a0a","stroke":"#ff3a3a",
                "notas":[f"{pct(100-(ratios.get('margen_bruto') or 0))} del rev."]})
        if f["op_expenses"] and f["op_expenses"]>0:
            c3_items.append({"label":"Op. Expenses","val":f["op_expenses"],"fill":"#1f1008","stroke":"#ff6b35",
                "notas":[f"{pct(f['op_expenses']/rev*100)} del rev."]})
        if f["da"] and f["da"]>0:
            c3_items.append({"label":"D&A","val":f["da"],"fill":"#1a1508","stroke":"#ff9800",
                "notas":[f"{pct(f['da']/rev*100)} del rev."]})
    # EBIT siempre al final
    if f["ebit"] is not None:
        ngaap=enr.get("ngaap",{}) if IS_ENR else {}
        en=[f"Margen Op: {pct(ratios.get('margen_op'))}"]
        if ngaap.get("op_income") is not None:
            sg="+" if ngaap["op_income"]>=0 else ""
            en.append(f"nGAAP: {sg}{fmt_b(ngaap['op_income'])} (+{pct(ngaap.get('delta_pct'))})")
        if ngaap.get("q4_op_income") is not None:
            en.append(f"Q4: {fmt_b(ngaap['q4_op_income'])} {'(mejora)' if ngaap.get('q4_mejora') else ''}")
        if ngaap.get("q4_margin_pct") is not None:
            en.append(f"Q4 GAAP: {pct(ngaap['q4_margin_pct'])} margin")
        ebit_lbl="Op. Income (GAAP)" if (f["ebit"] or 0)>=0 else "Op. Loss"
        ec="#00ff9d" if (f["ebit"] or 0)>=0 else "#ff3a3a"
        ef="#0a1f0a" if (f["ebit"] or 0)>=0 else "#200505"
        c3_items.append({"label":ebit_lbl,"val":f["ebit"],"fill":ef,"stroke":ec,"notas":en,"is_ebit":True})

    c3_gap=12; c3_y=30; c3_av=VH-60-c3_gap*(len(c3_items)-1)
    # F5b: normalizar alturas COL3 (mismo fix que COL1 — evita overflow con muchos items)
    _c3_min=55
    _c3_raw=[abs(item["val"])/rev*c3_av if rev else 75 for item in c3_items]
    _c3_wm=[max(_c3_min,r) for r in _c3_raw]
    if sum(_c3_wm)>c3_av:
        _c3_atm=[_c3_raw[i]<_c3_min for i in range(len(c3_items))]
        _c3_fix=sum(_c3_min for am in _c3_atm if am)
        _c3_sc=sum(r for i,r in enumerate(_c3_wm) if not _c3_atm[i])
        _c3_scale=(c3_av-_c3_fix)/_c3_sc if _c3_sc>0 else 1
        _c3_heights=[_c3_min if _c3_atm[i] else max(_c3_min,round(_c3_wm[i]*_c3_scale)) for i in range(len(c3_items))]
    else: _c3_heights=[round(r) for r in _c3_wm]
    _c3_hi=iter(_c3_heights)
    for item in c3_items:
        is_ebit=item.get("is_ebit",False); val=item["val"]
        h=next(_c3_hi); cy=c3_y+h//2
        col3_nodes.append({"label":item["label"],"val":val,"stroke":item["stroke"],"cy":cy,"is_ebit":is_ebit})
        if is_ebit: col3_ebit_cy=cy
        vc="#00ff9d" if (val or 0)>=0 else "#ff3a3a"
        col3+=[r(550,c3_y,195,h,item["fill"],item["stroke"],1.5 if not is_ebit else 2,glow=is_ebit),
               t(647,cy-int(h*0.12),item["label"],fs(11,h,8,15),item["stroke"],bold=True),
               t(647,cy+int(h*0.06),fmt_b(val),fs(14,h,10,20),vc,font=FONT_MONO,bold=True)]
        notas=[n2 for n2 in item.get("notas",[]) if n2]
        nota_size=fs(9,h,7,11)
        for ni2,nota in enumerate(notas[:3]):
            is_al=nota.startswith("⚠️")
            nc="#ffd700" if is_al else ("#94a3b8" if ni2>0 else "#b0bec5")
            col3.append(t(647,cy+int(h*0.22)+ni2*int(nota_size*1.4),nota[:36],nota_size,nc))
        c3_y+=h+c3_gap

    flows_c2=[]
    nf=len(col3_nodes); spread=min(60,240//(nf+1))
    for i,node in enumerate(col3_nodes):
        off=(i-(nf-1)/2)*spread; ey=int(rev_cy+off)
        cls="flow-path" if node["is_ebit"] else "flow-path-slow"
        flows_c2.append(fl(cls,f"M 470 {ey} C 510 {ey}, 510 {node['cy']}, 550 {node['cy']}",
                           node["stroke"],sw(node["val"],rev,2,20)))

    # COL4
    ec2="#00ff9d" if (f["ebit"] or 0)>=0 else "#ff3a3a"
    ef2="#0a1f0a" if (f["ebit"] or 0)>=0 else "#200505"
    elc="#81c784" if (f["ebit"] or 0)>=0 else "#ff5252"
    etr_str=f" ({pct(f['etr'])} ETR)" if f["etr"] else ""
    col4=[r(820,290,155,140,ef2,ec2,glow=True),
          t(897,314,"Op. Income (GAAP)",10,elc,bold=True),
          t(897,338,fmt_b(f["ebit"]),16,ec2,font=FONT_MONO,bold=True),
          t(897,355,f"Op Margin: {pct(ratios.get('margen_op'))}",9,"#94a3b8"),
          t(897,371,f"Impuestos: {fmt_b(f['taxes'])}{etr_str}",9,"#ffd700",font=FONT_MONO),
          t(897,387,f"Net Income: {fmt_b(f['net_income'])}",9,"#00d4ff",font=FONT_MONO),
          t(897,403,f"Margen Neto: {pct(ratios.get('margen_neto'))}",8.5,"#94a3b8")]
    sbc_b=enr.get("sbc_dilucion",{}) if IS_ENR else {}
    sbc_y=450
    if IS_ENR and sbc_b and f["sbc"]:
        fp=sbc_b.get("fcf_post_sbc")
        col4+=[r(820,sbc_y,155,105,"#1a0a1f","#9c27b0"),
               t(897,sbc_y+22,"SBC (diluye accionista)",9.5,"#ce93d8",bold=True),
               t(897,sbc_y+43,fmt_b(f["sbc"]),15,"#e040fb",font=FONT_MONO,bold=True),
               t(897,sbc_y+59,f"{pct(f['sbc']/rev*100)} revenue 🚨",9,"#ff8c00"),
               t(897,sbc_y+73,f"FCF post-SBC: {fmt_b(fp)}",9,"#ff3a3a" if (fp or 0)<0 else "#00ff9d",font=FONT_MONO),
               t(897,sbc_y+87,f"Dilución ~{sbc_b.get('pct_anual','?')}%/año",8.5,"#94a3b8"),
               t(897,sbc_y+99,sbc_b.get("conversion_nota",""),8,"#6b7fa3")]
        cfo_y=sbc_y+120
    else: cfo_y=460
    col4+=[r(820,cfo_y,155,100,"#051a0a","#4caf50",glow=True),
           t(897,cfo_y+22,"Cash From Ops",10,"#81c784",bold=True),
           t(897,cfo_y+44,fmt_b(f["cfo"]),15,"#00c853",font=FONT_MONO,bold=True),
           t(897,cfo_y+60,f"Menos Capex: -{fmt_b(f['capex'])}",9,"#94a3b8"),
           t(897,cfo_y+74,f"= FCF: {fmt_b(f['fcf'])}",9,"#00ff9d",font=FONT_MONO),
           t(897,cfo_y+88,f"(SBC add-back {fmt_b(f['sbc'])})" if IS_ENR and f["sbc"] else "",8,"#6b7fa3")]

    sw_eb=sw(f["ebit"],rev,2,18); sw_ni2=sw(f["net_income"],rev,2,16); sw_fcf=sw(f["fcf"],rev,2,14)
    ni_dy=510; fcf_dy=640
    flows_mid=[fl("flow-path",f"M 745 {col3_ebit_cy} C 780 {col3_ebit_cy}, 780 360, 820 360","url(#flow-ebit)",sw_eb,.45),
               fl("flow-path",f"M 975 350 C 1010 350, 1010 {ni_dy}, 1050 {ni_dy}","url(#flow-ni)",sw_ni2,.4),
               fl("flow-path-slow",f"M 975 {cfo_y+50} C 1010 {cfo_y+50}, 1010 {fcf_dy}, 1050 {fcf_dy}","url(#flow-fcf)",sw_fcf,.4)]

    # COL5
    nc2="#00d4ff" if (f["net_income"] or 0)>=0 else "#ff3a3a"
    nf2="#051828" if (f["net_income"] or 0)>=0 else "#1f0505"
    ns2="#00a8cc" if (f["net_income"] or 0)>=0 else "#ff3a3a"
    eps=market.get("eps_ttm"); eps_str=f"EPS: ${eps:.2f}" if eps else ""
    col5=[r(1050,ni_dy,155,90,nf2,ns2),
          t(1127,ni_dy+22,"Net Income (GAAP)",10,nc2,bold=True),
          t(1127,ni_dy+44,fmt_b(f["net_income"]),15,nc2,font=FONT_MONO,bold=True),
          t(1127,ni_dy+60,f"{eps_str} · {pct(ratios.get('margen_neto'))} margen",8.5,"#94a3b8"),
          t(1127,ni_dy+76,f"NI YoY: {pct(ratios.get('ni_yoy'))}",8.5,"#94a3b8")]
    dil_y=ni_dy+105
    if IS_ENR and sbc_b:
        fp2=sbc_b.get("fcf_post_sbc")
        col5+=[r(1050,dil_y,155,80,"#140a1f","#9c27b0"),
               t(1127,dil_y+20,"Dilución SBC",10,"#ce93d8",bold=True),
               t(1127,dil_y+40,f"~{sbc_b.get('pct_anual','?')}%/año acciones",13,"#e040fb",font=FONT_MONO,bold=True),
               t(1127,dil_y+56,sbc_b.get("conversion_nota",""),8.5,"#94a3b8"),
               t(1127,dil_y+70,f"FCF post-SBC: {fmt_b(fp2)}",8,"#ff3a3a" if (fp2 or 0)<0 else "#00c853",font=FONT_MONO)]
        fcf_box_y=dil_y+95
    else: fcf_box_y=fcf_dy
    col5+=[r(1050,fcf_box_y,155,90,"#051a0a","#00c853",glow=True),
           t(1127,fcf_box_y+20,"FCF (GAAP) / Capex",10,"#81c784",bold=True),
           t(1127,fcf_box_y+42,f"{fmt_b(f['fcf'])} FCF",14,"#00c853",font=FONT_MONO,bold=True),
           t(1127,fcf_box_y+57,f"Capex: {fmt_b(f['capex'])}",8.5,"#94a3b8"),
           t(1127,fcf_box_y+70,f"CFO: {fmt_b(f['cfo'])}",8.5,"#94a3b8")]
    if IS_ENR and sbc_b:
        fp3=sbc_b.get("fcf_post_sbc")
        col5.append(t(1127,fcf_box_y+83,f"Post-SBC: {fmt_b(fp3)} 🚨",8,"#ff3a3a" if (fp3 or 0)<0 else "#00c853"))
    if f["dividendos"]:
        dy2=ni_dy-80
        col5+=[r(1050,dy2,155,65,"#1a1400","#ffd700"),
               t(1127,dy2+20,"Dividendos",10,"#ffd700",bold=True),
               t(1127,dy2+40,fmt_b(f["dividendos"]),14,"#ffd700",font=FONT_MONO,bold=True),
               t(1127,dy2+55,f"Yield: {pct(ratios.get('dividend_yield'))}",8.5,"#94a3b8")]

    # COL6
    gw_pct=f"{f['goodwill_pct']:.1f}% total assets" if f["goodwill_pct"] else ""
    w52h=market.get("w52_high"); w52l=market.get("w52_low")
    pct52=round((precio-w52l)/(w52h-w52l)*100) if (w52h and w52l and w52h!=w52l) else None
    gw_ex=enr.get("goodwill_extra",{}) if IS_ENR else {}
    col6=[r(1220,30,160,145 if IS_ENR else 130,"#1a1400","#ffd700"),
          t(1300,55,"⚠️ Goodwill" if IS_ENR else "⚖️ Balance",10,"#ffd700",bold=True),
          t(1300,74,fmt_b(f["goodwill"]) if IS_ENR else f"Deuda: {fmt_b(f['deuda'])}",12,"#ffd700",font=FONT_MONO,bold=True),
          t(1300,91,gw_pct,9,"#ff8c00"),
          t(1300,107,gw_ex.get("acquisicion","") if IS_ENR else f"Cash: {fmt_b(f['cash_real'])}",9,"#94a3b8"),
          t(1300,123,gw_ex.get("riesgo","")[:34] if IS_ENR else f"Goodwill: {fmt_b(f['goodwill'])}",8,"#ff6b35" if IS_ENR else "#94a3b8"),
          t(1300,139,f"D/E: {ratios.get('de_ratio','N/D')}x · CR: {ratios.get('current_ratio','N/D')}",8.5,"#94a3b8")]
    ctx_y=195
    bl=enr.get("backlog",{}) if IS_ENR else {}
    if IS_ENR and bl:
        col6+=[r(1220,ctx_y,160,120,"#081f10","#00c853"),
               t(1300,ctx_y+22,"✅ Backlog / RPO",10,"#00c853",bold=True),
               t(1300,ctx_y+42,fmt_b(bl.get("rpo")),14,"#00ff9d",font=FONT_MONO,bold=True),
               t(1300,ctx_y+58,f"+{pct(bl.get('rpo_yoy_pct'))} YoY (contratado)",9,"#00c853"),
               t(1300,ctx_y+73,f"NRR: {pct(bl.get('nrr_pct'))} Q4 2025",9,"#94a3b8"),
               t(1300,ctx_y+88,f"{bl.get('enterprise_customers','?')} ent. (+{bl.get('enterprise_yoy','?')} YoY)",8.5,"#94a3b8")]
        ctx_y+=135
    else:
        col6+=[r(1220,ctx_y,160,120,"#0a1a30","#00d4ff",glow=True),
               t(1300,ctx_y+22,"📊 Valoración",10,"#00d4ff",bold=True),
               t(1300,ctx_y+41,f"P/E TTM: {safe_val(market.get('pe_ttm'))}x",12,"#00d4ff",font=FONT_MONO,bold=True),
               t(1300,ctx_y+58,f"P/E Fwd: {safe_val(ratios.get('pe_forward'))}x",11,"#94a3b8",font=FONT_MONO),
               t(1300,ctx_y+74,f"PEG: {safe_val(ratios.get('peg'))}",11,"#ffd700",font=FONT_MONO),
               t(1300,ctx_y+90,f"EV/EBITDA: {safe_val(ratios.get('ev_ebitda'))}x · Beta: {safe_val(ratios.get('beta'))}",9,"#94a3b8"),
               t(1300,ctx_y+106,f"P/B: {safe_val(ratios.get('pb'))}x",8.5,"#94a3b8")]
        ctx_y+=135
    sotp=enr.get("sotp",{}) if IS_ENR else {}
    if IS_ENR and sotp:
        bc="#ff3a3a" if (sotp.get("bull_vs_actual_pct") or 0)<0 else "#00ff9d"
        col6+=[r(1220,ctx_y,160,130,"#0a1228","#ff3a3a" if (sotp.get("vs_actual_pct") or 0)<0 else "#00ff9d"),
               t(1300,ctx_y+22,"SOTP Fair Value",10,"#e57373" if (sotp.get("vs_actual_pct") or 0)<0 else "#81c784",bold=True),
               t(1300,ctx_y+42,f"${sotp.get('base','?')} base",14,"#ff3a3a",font=FONT_MONO,bold=True),
               t(1300,ctx_y+58,f"{sotp.get('vs_actual_pct','?')}% vs ${precio} actual",9,"#ff3a3a"),
               t(1300,ctx_y+73,f"${sotp.get('bull','?')} bull ({sotp.get('bull_vs_actual_pct','?')}%)",9,bc),
               t(1300,ctx_y+88,sotp.get("multiplos",""),8.5,"#94a3b8"),
               t(1300,ctx_y+103,f"Al premium pagado: {sotp.get('premium_pagado','')}",8,"#ff8c00"),
               t(1300,ctx_y+117,"⚠️ SOTP no garantiza retorno",7.5,"#6b7fa3")]
        ctx_y+=145
    else:
        col6+=[r(1220,ctx_y,160,110,"#050a12","#00ff9d"),
               t(1300,ctx_y+22,"📈 Precio",10,"#00ff9d",bold=True),
               t(1300,ctx_y+42,f"${precio}",14,"#00ff9d",font=FONT_MONO,bold=True),
               t(1300,ctx_y+58,f"52W: ${w52l} – ${w52h}",8.5,"#94a3b8")]
        if pct52 is not None: col6.append(t(1300,ctx_y+73,f"Al {pct52}% del rango 52W",8.5,"#00bcd4"))
        col6.append(t(1300,ctx_y+88,f"YTD: {pct(perf.get('YTD'))} · 1Y: {pct(perf.get('1Y'))}",9,"#ff3a3a" if (perf.get("YTD") or 0)<0 else "#00c853",font=FONT_MONO))
        ctx_y+=125
    fsc=enr.get("feroldi_score",{}) if IS_ENR else {}
    if IS_ENR and fsc:
        zc={"Verde":"#00c853","Amarilla":"#ffd700","Roja":"#ff3a3a"}.get(fsc.get("zona",""),"#94a3b8")
        col6+=[r(1220,ctx_y,160,150,"#0a1228",zc),
               t(1300,ctx_y+22,f"🟡 {fsc.get('rating','?')}",11,zc,bold=True),
               t(1300,ctx_y+42,f"Score Feroldi: {fsc.get('score','?')}/{fsc.get('max','?')}",10,"#94a3b8"),
               t(1300,ctx_y+57,f"Zona {fsc.get('zona','?')}",10,zc,bold=True),
               t(1300,ctx_y+73,f"TP1 ${fsc.get('tp1','?')} · TP2 ${fsc.get('tp2','?')} · TP3 ${fsc.get('tp3','?')}",9,"#94a3b8",font=FONT_MONO),
               t(1300,ctx_y+88,f"SL ${fsc.get('sl','?')} / ${fsc.get('sl_duro','?')}",9,"#ff3a3a",font=FONT_MONO),
               t(1300,ctx_y+104,f"⚠️ {fsc.get('posicion','STARTER')} position only",8.5,"#ff8c00"),
               t(1300,ctx_y+119,f"52W: ${w52l} – ${w52h}",8.5,"#94a3b8"),
               t(1300,ctx_y+135,f"YTD: {pct(perf.get('YTD'))} · 1Y: {pct(perf.get('1Y'))}",8.5,"#ff3a3a" if (perf.get("YTD") or 0)<0 else "#00c853",font=FONT_MONO)]
    else:
        col6+=[r(1220,ctx_y,160,110,"#0a1f0a","#00c853"),
               t(1300,ctx_y+22,"💰 Rentabilidad",10,"#00c853",bold=True),
               t(1300,ctx_y+41,f"ROIC: {pct(ratios.get('roic'))}",11,"#00ff9d",font=FONT_MONO),
               t(1300,ctx_y+57,f"ROE: {pct(ratios.get('roe'))} · ROA: {pct(ratios.get('roa'))}",11,"#94a3b8",font=FONT_MONO),
               t(1300,ctx_y+73,f"FCF/Rev: {pct(f['fcf']/rev*100 if rev else None)}",9,"#94a3b8"),
               t(1300,ctx_y+89,f"SBC: {fmt_b(f['sbc'])} ({pct(f['sbc']/rev*100 if rev else None)} rev)",8.5,"#94a3b8")]

    col_labels="\n".join([t(120,18,"COL 1 — SEGMENTOS",9,"#94a3b8"),
                          t(385,18,"COL 2 — REVENUE",9,"#94a3b8"),
                          t(647,18,"COL 3 — COSTOS &amp; GP" if IS_ENR else "COL 3 — ESTRUCTURA P&amp;L",9,"#94a3b8"),
                          t(897,18,"COL 4 — RESULTADO",9,"#94a3b8"),
                          t(1127,18,"COL 5 — DESTINO",9,"#94a3b8"),
                          t(1300,18,"CONTEXTO",9,"#94a3b8")])

    audit_rows=[("Revenue",fmt_b(f["revenue"]),"EDGAR XBRL","✅",f"FY{fy_year}"),
                ("Gross Profit",fmt_b(f["gross_profit"]),"StockAnalysis","⚡",f"{pct(ratios.get('margen_bruto'))} margen"),
                ("EBIT",fmt_b(f["ebit"]),"StockAnalysis","⚡",f"{pct(ratios.get('margen_op'))} margen"),
                ("Net Income",fmt_b(f["net_income"]),"EDGAR XBRL","✅",f"{pct(ratios.get('margen_neto'))} margen"),
                ("CFO",fmt_b(f["cfo"]),"EDGAR XBRL","✅","Cash Flow Statement"),
                ("FCF",fmt_b(f["fcf"]),"EDGAR XBRL","✅","CFO − Capex"),
                ("SBC",fmt_b(f["sbc"]),"EDGAR XBRL","✅",f"{pct(f['sbc']/rev*100 if rev else None)} del revenue"),
                ("Deuda",fmt_b(f["deuda"]),"EDGAR XBRL","✅","LT + ST debt"),
                ("Cash Real",fmt_b(f["cash_real"]),"EDGAR XBRL","✅","Cash + ShortTermInv"),
                ("Goodwill",fmt_b(f["goodwill"]),"EDGAR XBRL","✅",f"{pct(f['goodwill_pct'])} de total assets")]
    def ar(rw): vc="#00ff9d" if rw[3]=="✅" else "#ffd700"; cs="status-ok" if rw[3]=="✅" else "status-est"; return f'<tr><td>{rw[0]}</td><td><strong style="color:{vc}">{rw[1]}</strong></td><td>{rw[2]}</td><td class="{cs}">{rw[3]}</td><td style="color:#94a3b8">{rw[4]}</td></tr>'
    audit_html="\n".join(ar(rw) for rw in audit_rows)

    leg_items=[(n["stroke"],f"{n['nombre']} — {fmt_b(n['revenue'])}") for n in seg_nodes]
    leg_items+=[("#00ff9d",f"Op. Income — {fmt_b(f['ebit'])}"),("#00d4ff",f"Net Income — {fmt_b(f['net_income'])}"),("#00c853",f"FCF — {fmt_b(f['fcf'])}"),("#9c27b0",f"SBC — {fmt_b(f['sbc'])}")]
    legend_html="\n".join(f'<div class="leg-item"><div class="leg-dot" style="background:{c}"></div>{l}</div>' for c,l in leg_items)

    def kpi(v,lbl,cls=""):
        c="#00ff9d" if cls=="green" else ("#ffd700" if cls=="gold" else "#00d4ff")
        if isinstance(v,str) and v.startswith("-"): c="#ff3a3a"
        return f'<div class="kpi"><div class="kpi-val" style="color:{c}">{v}</div><div class="kpi-lbl">{lbl}</div></div>'
    kpis_html="\n".join([kpi(fmt_b(f["revenue"]),f"Revenue FY{fy_year}","green"),
                         kpi(fmt_b(f["ebitda"]) if f["ebitda"] else "N/D","EBITDA"),
                         kpi(fmt_b(f["net_income"]),"Net Income"),
                         kpi(fmt_b(f["fcf"]),"FCF GAAP","green"),
                         kpi(pct(ratios.get("margen_neto")),"Margen Neto","gold"),
                         kpi(pct(ratios.get("roic")),"ROIC","gold"),
                         kpi(f'{ratios.get("pe_ttm"):.1f}x' if isinstance(ratios.get("pe_ttm"),(int,float)) else "N/D","P/E TTM"),
                         kpi(f'PEG: {safe_val(ratios.get("peg"))}','Valoración')])
    enr_badge='<span style="background:#ffd700;color:#050a12;font-size:.6rem;font-weight:900;padding:.1rem .4rem;border-radius:.25rem;margin-left:.5rem">ENRIQUECIDO</span>' if IS_ENR else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{ticker} · Sankey FY{fy_year} · @patonet</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:clamp(10px,1.1vw,16px)}}
body{{background:#050a12;color:#c8d8f0;font-family:{FONT_UI};min-height:100vh;display:flex;flex-direction:column;overflow-x:hidden}}
body::after{{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.04) 2px,rgba(0,0,0,.04) 4px);pointer-events:none;z-index:999}}
header{{background:linear-gradient(135deg,#050a12 0%,#0a1e3a 60%,#050a12 100%);border-bottom:1px solid #1a2a4a;padding:.8rem 1.5rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem}}
.hdr-left h1{{font-size:1.1rem;font-weight:900;color:#00d4ff;letter-spacing:.04em}}
.hdr-left p{{font-size:.75rem;color:#94a3b8;margin-top:.1rem}}
.hdr-right{{text-align:right}}
.hdr-right .patonet{{font-size:.88rem;font-weight:900;color:#ffd700;letter-spacing:.06em}}
.hdr-right .meta{{font-size:.72rem;color:#94a3b8}}
.kpi-bar{{display:flex;gap:.5rem;flex-wrap:wrap;padding:.7rem 1.5rem;background:#080f1c;border-bottom:1px solid #1a2a4a}}
.kpi{{display:flex;flex-direction:column;align-items:center;padding:.3rem .7rem;border-right:1px solid #1a2a4a;flex:1;min-width:6rem}}
.kpi:last-child{{border-right:none}}
.kpi-val{{font-size:.95rem;font-weight:900;font-family:{FONT_MONO}}}
.kpi-lbl{{font-size:.62rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-top:.1rem;text-align:center}}
.sankey-container{{flex:1;padding:1rem 1.5rem;overflow-x:auto;will-change:transform}}
.sankey-wrap{{min-width:1100px;max-width:1400px;margin:0 auto}}
svg#sankey{{width:100%;height:auto;display:block;aspect-ratio:1400/{VH}}}
@keyframes flowAnim{{0%{{stroke-dashoffset:1000;opacity:.3}}60%{{opacity:.7}}100%{{stroke-dashoffset:0;opacity:.3}}}}
@keyframes flowSlow{{0%{{stroke-dashoffset:1000;opacity:.3}}60%{{opacity:.6}}100%{{stroke-dashoffset:0;opacity:.3}}}}
.flow-path{{stroke-dasharray:1000;animation:flowAnim 4s linear infinite}}
.flow-path-slow{{stroke-dasharray:1000;animation:flowSlow 5.5s linear infinite}}
.legend{{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.4rem;padding:.7rem 1.5rem;background:#080f1c;border-top:1px solid #1a2a4a;border-bottom:1px solid #1a2a4a}}
.leg-item{{display:flex;align-items:center;gap:.4rem;font-size:.72rem;color:#94a3b8}}
.leg-dot{{width:.6rem;height:.6rem;border-radius:50%;flex-shrink:0}}
.audit{{padding:.8rem 1.5rem}}
.audit-title{{font-size:.78rem;font-weight:700;color:#00d4ff;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.5rem}}
.audit-table{{width:100%;border-collapse:collapse;font-size:.75rem;max-width:1400px}}
.audit-table th{{color:#00d4ff;font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;padding:.3rem .5rem;border-bottom:1px solid #1a2a4a;text-align:left;background:#0d1428}}
.audit-table td{{padding:.3rem .5rem;border-bottom:1px solid #1a2a4a}}
.audit-table tr:nth-child(even) td{{background:rgba(255,255,255,.02)}}
.status-ok{{color:#00ff9d;font-weight:700}}.status-est{{color:#ffd700;font-weight:700}}
#tooltip{{position:fixed;background:#0a1628;border:1px solid #00d4ff;border-radius:.5rem;padding:.6rem .8rem;font-size:.78rem;color:#c8d8f0;max-width:18rem;pointer-events:none;z-index:9999;display:none;box-shadow:0 0 20px rgba(0,212,255,.2)}}
footer{{text-align:center;font-size:.68rem;color:#94a3b8;padding:.7rem;border-top:1px solid #1a2a4a;background:#050a12}}
</style></head><body>
<header>
  <div class="hdr-left">
    <h1>{company} · <span style="color:#ffd700">Flujo de Dinero FY{fy_year}</span>{enr_badge}</h1>
    <p>{exchange}:{ticker} · Método Feroldi · SEC 10-K · StockAnalysis · Yahoo Finance</p>
  </div>
  <div class="hdr-right">
    <div class="patonet">@patonet</div>
    <div class="meta">{exchange}:{ticker} · ${precio} · {fecha} · {fmt_b(f["revenue"])} GAAP</div>
  </div>
</header>
<div class="kpi-bar">{kpis_html}</div>
<div class="sankey-container"><div class="sankey-wrap">
<svg id="sankey" viewBox="0 0 1400 {VH}" preserveAspectRatio="xMidYMid meet"
  xmlns="http://www.w3.org/2000/svg" style="contain:layout style">
<defs>
  <filter id="glow"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="glowStrong"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  {grads}
</defs>
{col_labels}
{"".join(flows_c1)}{"".join(col1)}{"".join(col2)}{"".join(flows_c2)}{"".join(col3)}{"".join(flows_mid)}{"".join(col4)}{"".join(col5)}{"".join(col6)}
</svg></div></div>
<div class="legend">{legend_html}</div>
<div class="audit">
  <div class="audit-title">📊 Auditoría FY{fy_year} — SEC 10-K · StockAnalysis · Yahoo Finance</div>
  <table class="audit-table">
    <thead><tr><th>Rubro</th><th>Valor FY{fy_year}</th><th>Fuente</th><th>Estado</th><th>Nota</th></tr></thead>
    <tbody>{audit_html}</tbody>
  </table>
</div>
<footer>@patonet · Sistema Feroldi X0.56 · {ticker} · FY{fy_year} · {fecha} · {'Modo enriquecido' if IS_ENR else 'Modo básico'} · No constituye asesoría financiera.</footer>
<div id="tooltip"></div>
<script>
document.querySelectorAll('.node').forEach(el=>{{
  el.addEventListener('mouseenter',e=>{{const t2=document.getElementById('tooltip');t2.innerHTML='<strong style="color:#00d4ff">'+el.dataset.tip+'</strong>';t2.style.display='block';t2.style.left=Math.min(e.clientX+12,window.innerWidth-300)+'px';t2.style.top=Math.min(e.clientY-30,window.innerHeight-200)+'px';}});
  el.addEventListener('mousemove',e=>{{const t2=document.getElementById('tooltip');t2.style.left=Math.min(e.clientX+12,window.innerWidth-300)+'px';t2.style.top=Math.min(e.clientY-30,window.innerHeight-200)+'px';}});
  el.addEventListener('mouseleave',()=>document.getElementById('tooltip').style.display='none');
}});
</script>
</body></html>"""

def main():
    if len(sys.argv)<2: print("USO: python3 feroldi_sankey.py datos.json [--output DIR]"); sys.exit(1)
    jp=Path(sys.argv[1])
    if not jp.exists(): print(f"❌ No encontrado: {jp}"); sys.exit(1)
    od=Path(".")
    if "--output" in sys.argv: od=Path(sys.argv[sys.argv.index("--output")+1])
    with open(jp,"r",encoding="utf-8") as fh: data=json.load(fh)
    meta=data.get("meta",{}); ticker=meta.get("ticker","TICKER")
    precio=meta.get("precio_usuario",0); fecha=meta.get("fecha",datetime.now().strftime("%d-%m-%Y"))
    modo="ENRIQUECIDO" if data.get("enriquecido") else "BÁSICO"
    print(f"\n{'='*52}\n  FEROLDI SANKEY X0.56 — {ticker} @ ${precio} [{modo}]\n{'='*52}\n")
    html=generar_html(data)
    fn=f"Diagrama_Sankey_{ticker}_{precio}_{fecha}.html"; out=od/fn
    with open(out,"w",encoding="utf-8") as fh: fh.write(html)
    print(f"  ✅ {out}  ({out.stat().st_size/1024:.1f} KB)\n  👉 Abre en browser · python3 feroldi_push.py\n{'='*52}\n")

if __name__=="__main__": main()
