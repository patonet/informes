#!/usr/bin/env python3
"""
FEROLDI PENSANTE — v X0.90
Sistema Feroldi · @patonet
  Sistema: X0.90
  Archivo: X0.90

Orquestador de análisis: lee JSON de datos + prefetch + prompt_maestro y
llama al modelo PENSANTE vía API OpenAI-compatible (DeepSeek por defecto).
El modelo es configurable — hoy DeepSeek V4 Pro, mañana cualquier otro.

Uso:
  python3 feroldi_pensante.py --ticker PGR --precio 194.00
  python3 feroldi_pensante.py --ticker MELI --precio 1532 --modo heavy
  python3 feroldi_pensante.py --ticker AAPL --precio 200 --modelo deepseek-chat

API: DeepSeek (api.deepseek.com) — compatible OpenAI. Key: DEEPSEEK_API_KEY
Para cambiar proveedor: ajustar GATEWAY_URL + DEFAULT_MODEL + variable de env.
Modelos disponibles:
  deepseek-v4-pro    ← default (mayor razonamiento, streaming, ~7 min pero output inmediato)
  deepseek-v4-flash  ← más rápido (Kika usa este)
  deepseek-chat      ← V3.2 sin thinking (131K contexto, el más rápido)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

VERSION       = "X0.94"
TODAY         = datetime.now().strftime("%d-%m-%Y")
TODAY_COMPACT = datetime.now().strftime("%d%m%Y")

WORKSPACE     = os.path.expanduser("~/.openclaw/workspace")
GATEWAY_URL   = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-pro"
TIMEOUT       = 600   # segundos — razonamiento extendido puede tardar; socket timeout (no total)
MAX_TOKENS    = 32000  # X0.93: reasoning_tokens consumen presupuesto — 12K era demasiado ajustado

# Paths de archivos de soporte
PROMPT_PATHS = [
    os.path.join(WORKSPACE, "prompt_maestro_X0.50.txt"),
    os.path.expanduser("~/prompt_maestro_X0.50.txt"),
]
PREFETCH_DIR = os.path.join(WORKSPACE, "prefetch_cache")


# ─── API KEY ──────────────────────────────────────────────────────────────────
def get_api_key():
    """
    Retorna la API key para el proveedor activo.
    Orden de búsqueda: DEEPSEEK_API_KEY → OPENROUTER_API_KEY → OPENAI_API_KEY
    (permite migrar de proveedor con solo cambiar la variable de entorno)
    """
    for var in ("DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        key = os.environ.get(var, "")
        if key:
            return key, var
    return "", ""


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def find_datos_json(ticker):
    """Busca el JSON de datos más reciente para el ticker en WORKSPACE."""
    ticker = ticker.upper()
    try:
        files = [
            f for f in os.listdir(WORKSPACE)
            if f.startswith(f"datos_{ticker}_") and f.endswith(".json")
        ]
    except FileNotFoundError:
        return None
    if not files:
        return None
    files.sort(reverse=True)
    return os.path.join(WORKSPACE, files[0])


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠ No se pudo cargar {path}: {e}")
        return None


def load_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def find_prompt_maestro():
    for p in PROMPT_PATHS:
        if os.path.isfile(p):
            return p
    return None


# ─── CONSTRUCCIÓN DEL CONTEXTO ────────────────────────────────────────────────
def _extraer_campos_nd(datos_json):
    """
    Recorre el JSON de datos y retorna lista de rutas con valor null/None/'N/D'.
    Útil para presentarle al PENSANTE exactamente qué necesita resolver vía PASO 2.
    """
    campos = []

    def _walk(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.startswith("_"):
                    continue
                _walk(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            # No recurrir en listas (segmentos, earnings, etc.) — solo primer nivel
            pass
        elif obj is None or obj == "N/D":
            campos.append(path)

    _walk(datos_json, "")
    return campos


def build_context(ticker, precio, modo, datos_json, prefetch_data, prompt_maestro):
    """
    Ensambla el prompt completo para el PENSANTE.
    Orden: [PROMPT MAESTRO] --- [N/D DESTACADOS] --- [JSON DATOS] --- [PREFETCH] --- INSTRUCCIÓN FINAL
    """
    parts = []

    # 1. Prompt maestro
    if prompt_maestro:
        parts.append("[PROMPT MAESTRO — FEROLDI X0.50]")
        parts.append(prompt_maestro)
        parts.append("---")
    else:
        parts.append("[ADVERTENCIA: prompt_maestro no encontrado — análisis sin protocolo]")
        parts.append("---")

    # 2. Campos N/D detectados — destacar ANTES del JSON completo
    nd_campos = _extraer_campos_nd(datos_json)
    if nd_campos:
        parts.append("[CAMPOS EN N/D — REQUIEREN RESOLUCIÓN VÍA PASO 2]")
        parts.append(
            "Los siguientes campos están vacíos (null) en el JSON recolectado. "
            "Para cada uno: buscar en tu conocimiento de entrenamiento (TIER 2→4 del protocolo). "
            "PROHIBIDO inventar — solo asignar si podés verificarlo con certeza razonable. "
            "Si no podés verificar: dejar como N/D."
        )
        for campo in nd_campos:
            parts.append(f"  • {campo}")
        parts.append("---")

    # 3. JSON de datos financieros
    parts.append("[JSON DE DATOS FINANCIEROS — feroldi_recolectar.py X0.83]")
    parts.append(json.dumps(datos_json, ensure_ascii=False, indent=2))
    parts.append("---")

    # 4. Prefetch (si existe)
    if prefetch_data:
        parts.append("[DATOS PRE-FETCHEADOS — feroldi_prefetch.py]")
        # Post-earnings data (X0.91) — va PRIMERO: datos más frescos que el JSON
        post_e = prefetch_data.get("post_earnings", {})
        if post_e and (post_e.get("kpis_consolidados") or post_e.get("articulos")):
            quarter_pe = post_e.get("quarter", "trimestre reciente")
            kpis_pe    = post_e.get("kpis_consolidados", {})
            arts_pe    = post_e.get("articulos", [])
            parts.append(f"[POST-EARNINGS {quarter_pe.upper()} — DATOS MÁS RECIENTES QUE EL JSON]")
            parts.append(
                "⚠️ Los siguientes datos son del trimestre más reciente reportado. "
                "Tienen PRIORIDAD sobre campos equivalentes del JSON de datos financieros. "
                "Usarlos para corregir EPS forward, márgenes, guidance y cualquier KPI actualizado."
            )
            if kpis_pe:
                parts.append("KPIs extraídos de noticias de earnings:")
                for k, v in kpis_pe.items():
                    parts.append(f"  • {k.replace('_', ' ')}: {v}")
            if arts_pe:
                parts.append("Fuentes:")
                for a in arts_pe[:4]:
                    t = a.get("titulo", "")
                    s = a.get("snippet", "")
                    if t:
                        parts.append(f"  • {t}" + (f"\n    {s}" if s else ""))
            parts.append("---")

        # FIX: clave correcta es noticias_b0 (no "noticias"); claves titulo/snippet (no title)
        noticias = prefetch_data.get("noticias_b0") or prefetch_data.get("noticias", [])
        if noticias:
            parts.append("NOTICIAS RECIENTES:")
            for n in noticias[:6]:
                title   = n.get("titulo") or n.get("title", "")
                snippet = n.get("snippet", "")
                url     = n.get("url", "")
                parts.append(f"  • {title}")
                if snippet:
                    parts.append(f"    {snippet}")
                if url:
                    parts.append(f"    URL: {url}")

        # N/D resueltos por prefetch
        nd = prefetch_data.get("nd_resueltos", {})
        nd_limpio = {k: v for k, v in nd.items() if v is not None and not k.startswith("_")}
        if nd_limpio:
            parts.append("\nN/D RESUELTOS POR PREFETCH:")
            parts.append(json.dumps(nd_limpio, ensure_ascii=False, indent=2))

        # Forecast / Price Targets individuales (X0.89+)
        forecast = prefetch_data.get("forecast_pts", [])
        if forecast:
            parts.append("\nPRICE TARGETS INDIVIDUALES (analistas):")
            for pt in forecast[:10]:
                analyst = pt.get("analyst", "")
                target  = pt.get("target", "")
                rating  = pt.get("rating", "")
                parts.append(f"  • {analyst}: ${target} ({rating})")

        # CEO quote (X0.89+)
        ceo_quote = prefetch_data.get("ceo_quote", "")
        if ceo_quote:
            parts.append(f"\nCEO — FRASE RECIENTE:\n  {ceo_quote}")

        # Competidores (FIX: es lista de dicts, no dict con ticker_candidates)
        comp = prefetch_data.get("competidores", [])
        if isinstance(comp, list) and comp:
            parts.append("\nCOMPETIDORES CON DATOS:")
            for c in comp[:6]:
                ticker_c = c.get("ticker", "")
                nombre_c = c.get("nombre", "")
                mcap_c   = c.get("market_cap", "N/D")
                pe_c     = c.get("pe_forward") or c.get("pe_ttm", "N/D")
                parts.append(f"  • {ticker_c} ({nombre_c}): MktCap={mcap_c} | P/E={pe_c}")
        elif isinstance(comp, dict) and comp.get("ticker_candidates"):
            parts.append(f"\nCOMPETIDORES DETECTADOS: {', '.join(comp['ticker_candidates'][:8])}")

        parts.append("---")

    # 5. Instrucción final
    if modo.upper() == "LIGHT":
        instruccion = (
            f"TICKER: ${ticker.upper()} | PRECIO DE ENTRADA: ${precio}\n"
            "Ejecutar SECCIÓN A completa (B0 → N/D → Segmentos → Commodity → "
            "Competidores → Cuadro de Cierre) + SECCIÓN B completa "
            "(Bloques A→H→X + ENRIQUECIDO_JSON Light) SIN PAUSAR ni pedir confirmación."
        )
    else:
        instruccion = (
            f"TICKER: ${ticker.upper()} | PRECIO DE ENTRADA: ${precio}\n"
            "Ejecutar SECCIÓN A completa (B0 → N/D → Segmentos → Commodity → "
            "Competidores → Cuadro de Cierre) + SECCIÓN C completa "
            "(H1→H3 → Bloques A→I→X + ENRIQUECIDO_JSON Heavy) SIN PAUSAR ni pedir confirmación."
        )
    parts.append(instruccion)

    return "\n".join(parts)


# ─── LLAMADA AL GATEWAY (STREAMING SSE) ──────────────────────────────────────
def call_pensante(context, api_key, model, verbose=True):
    """
    Llama al PENSANTE vía API OpenAI-compatible con streaming SSE.
    Imprime el output a medida que llega (sin esperar al final del razonamiento).
    Retorna (texto_completo, usage_dict, error_str_or_None).

    Por qué streaming: los modelos de razonamiento (V4 Pro / R1) tardan minutos
    en "pensar" antes de generar el primer token. Sin streaming el usuario ve
    silencio total. Con streaming, los primeros tokens aparecen en pantalla ~30s
    después del thinking phase, aunque el total tarde lo mismo.
    """
    system_msg = (
        "Sos un analista financiero senior con acceso a dos fuentes simultáneas: "
        "(1) el JSON estructurado del recolector — datos verificados y precisos sobre métricas financieras; "
        "(2) tu propio conocimiento de entrenamiento sobre la empresa — adquisiciones, programas internos, "
        "eventos recientes, ciclo del sector, riesgos específicos, historia competitiva. "
        "USÁ AMBAS FUENTES. El JSON es la base numérica; tu conocimiento llena el contexto que el JSON no puede capturar. "
        "Si tu conocimiento contradice o enriquece un dato del JSON, decilo explícitamente. "
        "Seguí el protocolo del prompt_maestro al pie de la letra, incluyendo PASO 2 de resolución de N/D. "
        "PROHIBIDO inventar datos sin certeza — si no podés verificarlo, marcarlo como N/D. "
        "Respondé en español."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": context},
        ],
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
        "stream": True,   # SSE streaming — output aparece a medida que se genera
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        GATEWAY_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": f"feroldi-pensante/{VERSION}",
        },
        method="POST",
    )

    full_text    = []
    usage        = {}
    reasoning_shown = False  # flag para mostrar aviso de thinking phase

    # Errores transitorios que justifican reintento (caída de red, servidor ocupado).
    # HTTPError 4xx NO se reintenta — son errores del cliente (auth, bad request).
    _TRANSIENT = ("RemoteDisconnected", "ConnectionResetError", "ConnectionError",
                  "TimeoutError", "BrokenPipeError", "URLError")
    MAX_RETRIES = 3
    BACKOFF     = [10, 30, 60]   # segundos de espera entre reintentos

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        full_text        = []
        usage            = {}
        reasoning_shown  = False

        try:
            with urlopen(req, timeout=TIMEOUT) as resp:
                if verbose:
                    prefix = f" (intento {attempt + 1})" if attempt > 0 else ""
                    print(f"\n  ⏳ Pensando{prefix}", end="", flush=True)

                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").rstrip()

                    # SSE: cada evento empieza con "data: "
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # Extraer delta de contenido
                    delta   = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")

                    # Los modelos de razonamiento a veces tienen reasoning_content separado
                    # Solo mostramos "content" (la respuesta real, no el thinking interno)
                    if content:
                        if not reasoning_shown and verbose:
                            # Primer token de contenido real — salto de línea y empieza el informe
                            print("\n")
                            reasoning_shown = True
                        if verbose:
                            print(content, end="", flush=True)
                        full_text.append(content)
                    elif verbose and not reasoning_shown:
                        # Todavía en fase de reasoning — mostrar progreso
                        print(".", end="", flush=True)

                    # Capturar usage si viene en el último chunk
                    if chunk.get("usage"):
                        usage = chunk["usage"]

            # Éxito — salir del loop de reintentos
            break

        except HTTPError as e:
            body_err = e.read().decode("utf-8", errors="replace")
            # 4xx: error del cliente, no reintentable
            if 400 <= e.code < 500:
                return None, {}, f"HTTP {e.code}: {body_err[:400]}"
            # 5xx: error del servidor, reintentable
            last_error = f"HTTP {e.code}: {body_err[:200]}"
        except URLError as e:
            last_error = f"URLError: {e.reason}"
        except Exception as e:
            err_type = type(e).__name__
            last_error = f"{err_type}: {e}"
            # Solo reintenta errores de red/conexión conocidos
            if not any(err_type.startswith(t) or err_type == t for t in _TRANSIENT):
                return None, {}, last_error

        # Si llegamos aquí: error transitorio
        if attempt < MAX_RETRIES:
            wait = BACKOFF[attempt]
            if verbose:
                print(f"\n\n  ↻ Error de red ({last_error}). Reintento {attempt + 1}/{MAX_RETRIES} en {wait}s...")
            import time as _time
            _time.sleep(wait)
        else:
            return None, {}, last_error

    text = "".join(full_text)
    if not text:
        return None, usage, "Respuesta vacía del modelo"

    return text, usage, None


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description=f"Feroldi Pensante v{VERSION} — análisis con cualquier LLM vía gateway OpenClaw"
    )
    parser.add_argument("--ticker",  required=True, help="Ticker bursátil (ej: PGR, MELI)")
    parser.add_argument("--precio",  type=float, required=True, help="Precio de entrada")
    parser.add_argument("--modo",    choices=["light", "heavy"], default="light")
    parser.add_argument("--modelo",  default=DEFAULT_MODEL,
                        help=f"Modelo a usar (default: {DEFAULT_MODEL})")
    parser.add_argument("--datos",   default=None, help="Ruta explícita al JSON de datos")
    parser.add_argument("--push",    action="store_true",
                        help="Subir informe MD a GitHub (patonet/informes/equities/) y devolver link")
    args = parser.parse_args()

    ticker = args.ticker.lstrip("$").upper()
    precio = args.precio
    modo   = args.modo
    modelo = args.modelo

    print(f"\n{'='*60}")
    print(f"  FEROLDI PENSANTE v{VERSION}")
    print(f"  Ticker: {ticker} | Precio: ${precio} | Modo: {modo.upper()}")
    print(f"  Modelo: {modelo}")
    print(f"  {TODAY}")
    print(f"{'='*60}\n")

    # ── API KEY ───────────────────────────────────────────────────────────────
    api_key, key_var = get_api_key()
    if not api_key:
        print("  ⛔ No se encontró API key.")
        print("     Configurar: export DEEPSEEK_API_KEY='tu_key'")
        sys.exit(1)
    print(f"  ✓ {key_var} presente ({len(api_key)} chars)")

    # ── DATOS FINANCIEROS ─────────────────────────────────────────────────────
    datos_path = args.datos or find_datos_json(ticker)
    if not datos_path or not os.path.isfile(datos_path):
        print(f"\n  ⛔ No se encontró JSON de datos para {ticker} en {WORKSPACE}")
        print(f"     Para recolectar: python3 ~/feroldi_recolectar.py {ticker} {precio}")
        sys.exit(1)
    print(f"  ✓ JSON de datos: {os.path.basename(datos_path)}")
    datos_json = load_json(datos_path)
    if not datos_json:
        sys.exit(1)

    # ── PREFETCH ──────────────────────────────────────────────────────────────
    prefetch_path = os.path.join(PREFETCH_DIR, f"prefetch_{ticker}.json")
    prefetch_data = None
    if os.path.isfile(prefetch_path):
        prefetch_data = load_json(prefetch_path)
        status = "✓" if prefetch_data else "⚠"
        print(f"  {status} Prefetch: {os.path.basename(prefetch_path)}")
    else:
        print(f"  ~ Sin prefetch (ejecutar: python3 ~/feroldi_prefetch.py {ticker} {precio})")

    # ── PROMPT MAESTRO ────────────────────────────────────────────────────────
    prompt_path = find_prompt_maestro()
    prompt_maestro = load_text(prompt_path) if prompt_path else None
    if prompt_maestro:
        print(f"  ✓ Prompt maestro: {os.path.basename(prompt_path)} ({len(prompt_maestro):,} chars)")
    else:
        print(f"  ⚠ Prompt maestro no encontrado — análisis sin protocolo Feroldi")

    # ── CONSTRUIR CONTEXTO ────────────────────────────────────────────────────
    print("\n  Construyendo contexto...")
    context = build_context(ticker, precio, modo, datos_json, prefetch_data, prompt_maestro)
    ctx_chars  = len(context)
    ctx_tokens = ctx_chars // 4
    print(f"  ✓ Contexto: {ctx_chars:,} chars (~{ctx_tokens:,} tokens est.)")

    # ── LLAMAR AL PENSANTE (streaming) ───────────────────────────────────────
    print(f"\n  Llamando {modelo} (streaming, timeout socket={TIMEOUT}s)...")
    print(f"  Los modelos de razonamiento piensan antes de escribir — los '...' son el thinking.")
    t0 = time.time()
    response_text, usage, error = call_pensante(context, api_key, modelo, verbose=True)
    elapsed = time.time() - t0

    if error or not response_text:
        print(f"\n\n  ⛔ El modelo no respondió.")
        print(f"  Error: {error}")
        sys.exit(1)

    # ── GUARDAR INFORME ───────────────────────────────────────────────────────
    modelo_slug = modelo.replace("/", "-").replace(":", "-")
    out_filename = f"informe_{ticker}_{TODAY_COMPACT}_{modo}_{modelo_slug}.md"
    out_path     = os.path.join(WORKSPACE, out_filename)
    header = (
        f"# INFORME FEROLDI — {ticker} @ ${precio}\n"
        f"**Fecha:** {TODAY} | **Modo:** {modo.upper()} | "
        f"**Modelo:** {modelo} | **v{VERSION}**\n\n"
        "---\n\n"
    )
    # Escritura atómica
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(header + response_text)
    os.replace(tmp_path, out_path)

    # ── PUSH A GITHUB (si --push está activo) ────────────────────────────────
    gh_url = None
    if args.push:
        import base64
        try:
            import requests as _req
        except ImportError:
            import urllib.request as _req
            _req = None

        gh_token = os.environ.get("GH_TOKEN", "")
        if not gh_token:
            # Fallback: leer de ~/.zshrc
            import re as _re
            zshrc = os.path.expanduser("~/.zshrc")
            if os.path.isfile(zshrc):
                for line in open(zshrc).readlines():
                    m = _re.search(r'export\s+GH_TOKEN=["\']?(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)', line)
                    if m:
                        gh_token = m.group(1)  # toma la última ocurrencia
            if gh_token:
                print("  ~ GH_TOKEN leído de ~/.zshrc")

        if not gh_token:
            print("\n  ⚠ --push: GH_TOKEN no encontrado — informe guardado solo localmente")
        else:
            repo_path = f"equities/{out_filename}"
            api_url   = f"https://api.github.com/repos/patonet/informes/contents/{repo_path}"
            headers   = {
                "Authorization": f"token {gh_token}",
                "Accept":        "application/vnd.github.v3+json",
                "Content-Type":  "application/json",
            }
            content_b64 = base64.b64encode(open(out_path, "rb").read()).decode()
            payload_dict = {
                "message": f"feat: informe {ticker} {TODAY}",
                "content": content_b64,
            }

            print(f"\n  ⬆ Subiendo a GitHub: {repo_path} ...")
            import urllib.request, urllib.error, json as _json

            def _put(payload):
                data_bytes = _json.dumps(payload).encode("utf-8")
                req_obj = urllib.request.Request(api_url, data=data_bytes, headers=headers, method="PUT")
                with urllib.request.urlopen(req_obj, timeout=30) as resp:
                    return resp.getcode(), _json.loads(resp.read())

            try:
                status_code, _ = _put(payload_dict)
                if status_code in (200, 201):
                    gh_url = f"https://patonet.github.io/informes/{repo_path}"
                    print(f"  ✅ Subido exitosamente")
            except urllib.error.HTTPError as e_http:
                if e_http.code == 422:
                    # El archivo ya existe — la API requiere el sha para overwrite.
                    print(f"  ↻ Archivo existe, leyendo sha para update...")
                    try:
                        req_get = urllib.request.Request(api_url, headers=headers, method="GET")
                        with urllib.request.urlopen(req_get, timeout=30) as r_get:
                            existing = _json.loads(r_get.read())
                        payload_dict["sha"] = existing["sha"]
                        status_code, _ = _put(payload_dict)
                        if status_code in (200, 201):
                            gh_url = f"https://patonet.github.io/informes/{repo_path}"
                            print(f"  ✅ Actualizado exitosamente (overwrite)")
                        else:
                            print(f"  ❌ Update falló: HTTP {status_code}")
                    except Exception as e_retry:
                        print(f"  ❌ Update falló: {e_retry}")
                else:
                    print(f"  ❌ Push falló: HTTP {e_http.code}")
            except Exception as e_push:
                print(f"  ❌ Push falló: {e_push}")

    # ── REPORTE FINAL (el informe ya se imprimió en streaming) ───────────────
    print(f"\n\n{'='*60}")
    print(f"  REPORTE DE EJECUCIÓN")
    print(f"  Modelo:    {modelo}")
    print(f"  Tiempo:    {elapsed:.1f}s")
    if usage:
        p = usage.get("prompt_tokens", "N/D")
        c = usage.get("completion_tokens", "N/D")
        t = usage.get("total_tokens", "N/D")
        print(f"  Tokens entrada:  {p:,}" if isinstance(p, int) else f"  Tokens entrada:  {p}")
        print(f"  Tokens salida:   {c:,}" if isinstance(c, int) else f"  Tokens salida:   {c}")
        print(f"  Tokens total:    {t:,}" if isinstance(t, int) else f"  Tokens total:    {t}")
    print(f"  Guardado:  {out_filename}")
    if gh_url:
        print(f"  GitHub:    {gh_url}")
    print(f"{'='*60}\n")
    if gh_url:
        # Línea especial que Kika puede parsear fácilmente
        print(f"GITHUB_URL={gh_url}")


if __name__ == "__main__":
    main()
