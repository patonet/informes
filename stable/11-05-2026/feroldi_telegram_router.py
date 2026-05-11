#!/usr/bin/env python3 -u
"""
feroldi_telegram_router.py v2.0
Router autónomo de Telegram para el pipeline Feroldi.
Intercepta mensajes con patrón $TICKER PRECIO y corre el pipeline completo.

⚠️  CORRE COMO PROCESO APARTE de OpenClaw.
     Usa el MISMO bot token → NO hacer polling si OpenClaw ya está conectado.
     En ese caso, OpenClaw recibe los mensajes y Kika puede invocar este script.

🔧  FLUJO RECOMENDADO:
     - Con OpenClaw activo con Telegram: Kika recibe $ONON 35.20, invoca:
         python3 ~/feroldi_telegram_router.py --ticker ONON --precio 35.20
     - Sin OpenClaw o con Telegram deshabilitado en OpenClaw: modo daemon con polling.
"""

import os, sys, re, json, time, subprocess, urllib.request, base64, logging
from pathlib import Path
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SCRIPTS_DIR   = os.path.expanduser("~")
WORKSPACE     = os.path.expanduser("~/.openclaw/workspace")
STATE_DIR     = os.path.join(WORKSPACE, "router")
STATE_FILE    = os.path.join(STATE_DIR, "offset.json")
LOG_FILE      = os.path.join(STATE_DIR, "router.log")
GH_TOKEN_FILE = os.path.join(WORKSPACE, ".gh_token")
PREFETCH_DIR  = os.path.join(WORKSPACE, "prefetch_cache")

# Asegurar directorios
os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(PREFETCH_DIR, exist_ok=True)

# Logging
logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# También stdout
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logging.getLogger().addHandler(console)

log = logging.getLogger(__name__)

# ─── TOKENS Y CREDENCIALES ───────────────────────────────────────────────────
# ORDEN: env → archivo dedicado → prompt_maestro (para GH_TOKEN)
TOKEN_ENV_VARS = {
    "BOT_TOKEN":        "FEROLDI_BOT_TOKEN",
    "DEEPSEEK_API_KEY": "DEEPSEEK_API_KEY",
}

def _read_env_or_file(var_name: str, file_path: str = None) -> str:
    """Lee de variable de entorno, y si no existe, de archivo."""
    val = os.environ.get(var_name, "")
    if val:
        return val
    if file_path and os.path.isfile(file_path):
        try:
            return open(file_path).read().strip()
        except:
            pass
    return ""

def _find_in_prompt_maestro() -> str:
    """Busca GH_TOKEN en prompt_maestro (fallback de feroldi_pensante.py)."""
    import glob as _g
    files = sorted(_g.glob(os.path.join(WORKSPACE, "prompt_maestro_*.txt")))
    for fp in files:
        try:
            text = open(fp).read()
            m = re.search(r'(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)', text)
            if m:
                return m.group(1)
        except:
            pass
    return ""

# ─── CONSTANTES (no hardcodeadas en el código fuente) ────────────────────────
BOT_TOKEN        = _read_env_or_file("FEROLDI_BOT_TOKEN") or _read_env_or_file("BOT_TOKEN")
if not BOT_TOKEN:
    # Fallback: leer de openclaw.json
    try:
        oc_config = json.load(open(os.path.expanduser("~/.openclaw/openclaw.json")))
        bt = oc_config.get("channels", {}).get("telegram", {}).get("botToken", "")
        if bt:
            BOT_TOKEN = bt
    except:
        pass

# FEROLDI_CHAT_ID: ID de respaldo cuando no hay remitente (notificaciones de error, etc.)
CHAT_ID          = _read_env_or_file("FEROLDI_CHAT_ID") or "7962682313"

# FEROLDI_ALLOWED_IDS: lista de IDs de Telegram autorizados a disparar el pipeline.
# Separados por coma. Si está vacío, solo se permite CHAT_ID.
# Ejemplo: "7962682313,8578818099"
_allowed_raw = _read_env_or_file("FEROLDI_ALLOWED_IDS") or ""
ALLOWED_IDS: set[str] = set(filter(None, _allowed_raw.split(","))) | {CHAT_ID}

# Contexto del mensaje actual — ID al que responder (se actualiza por cada mensaje entrante).
# El loop de polling lo setea antes de llamar handle_message() para que tg_send()
# devuelva la respuesta al remitente correcto, no siempre al CHAT_ID fijo.
_reply_to: str = CHAT_ID

# GH_TOKEN: env → archivo dedicado → prompt_maestro
GH_TOKEN         = _read_env_or_file("GH_TOKEN", GH_TOKEN_FILE) or _find_in_prompt_maestro()
log.info(f"GH_TOKEN: {'✅ SET' if GH_TOKEN else '❌ VACÍO'}")

# API keys para subprocess
DEEPSEEK_API_KEY = _read_env_or_file("DEEPSEEK_API_KEY")
OPENAI_API_KEY   = _read_env_or_file("OPENAI_API_KEY")

if not BOT_TOKEN:
    log.error("❌ BOT_TOKEN no encontrado. Seteá FEROLDI_BOT_TOKEN en env o .gh_token")
    sys.exit(1)

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ─── PATRONES ────────────────────────────────────────────────────────────────
# Ticker enmascarado con letra+dígito decreciente (NKE → N9K8E7, AAPL → A9A8P7L6).
# Dígito en posición i (0-indexed) debe ser exactamente 9-i.
RE_TICKER  = re.compile(r'^((?:[A-Z]\d){1,7})\s+(\d+(?:[.,]\d+)?)\s*$', re.IGNORECASE)
RE_SANKEY  = re.compile(r'^((?:[A-Z]\d){1,7})\s+SANKEY\s*$', re.IGNORECASE)
# Formato plain para el segundo bot (sin máscara): "NKE 235.40" o "$NKE 235.40"
RE_TICKER_PLAIN = re.compile(r'^\$?([A-Z]{1,7})\s+(\d+(?:[.,]\d+)?)\s*$', re.IGNORECASE)
RE_SANKEY_PLAIN = re.compile(r'^\$?([A-Z]{1,7})\s+SANKEY\s*$', re.IGNORECASE)


def _unmask_ticker(masked: str) -> str | None:
    """Desenmascara N9K8E7 → NKE. Retorna None si no es válido."""
    u = masked.upper()
    if len(u) < 2 or len(u) % 2 != 0:
        return None
    out = []
    for i in range(0, len(u), 2):
        letter, digit = u[i], u[i + 1]
        if not ("A" <= letter <= "Z"):
            return None
        if digit != str(9 - i // 2):
            return None
        out.append(letter)
    return "".join(out)

# ─── HELPERS TELEGRAM ────────────────────────────────────────────────────────
def tg_send(text: str, parse_mode: str = "Markdown", chat_id: str = None):
    target = chat_id or _reply_to
    payload = json.dumps({"chat_id": target, "text": text, "parse_mode": parse_mode}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/sendMessage", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            log.info(f"📤 Enviado: {text[:60]}...")
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error(f"tg_send HTTP {e.code}: {body[:200]}")
    except Exception as e:
        log.error(f"tg_send error: {e}")


def set_webhook(url: str = ""):
    """Registra o elimina webhook."""
    payload = json.dumps({"url": url, "drop_pending_updates": True}).encode()
    action = "setWebhook" if url else "deleteWebhook"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"{API_BASE}/{action}", data=payload,
                headers={"Content-Type": "application/json"}, method="POST"),
            timeout=15
        ) as r:
            resp = json.loads(r.read())
            log.info(f"🔗 Webhook {url or 'eliminado'}: {resp.get('description', 'OK')}")
            return resp.get("ok")
    except Exception as e:
        log.error(f"Webhook error: {e}")
        return False


def get_updates(offset: int, retries: int = 3) -> list:
    """Polling con manejo de 409 Conflict y retry."""
    url = f"{API_BASE}/getUpdates?offset={offset}&timeout=25&allowed_updates=[\"message\"]"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.loads(r.read())
                if data.get("ok"):
                    return data.get("result", [])
                log.warning(f"getUpdates !ok: {data.get('description', '?')}")
                return []
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 409:
                log.warning(f"⚠️ 409 Conflict (OpenClaw está polleando con el mismo token)")
                log.warning("   → Opción 1: Deshabilitar Telegram en OpenClaw con:")
                log.warning("     openclaw config set channels.telegram.enabled false")
                log.warning("   → Opción 2: Usar otro bot token en FEROLDI_BOT_TOKEN")
                log.warning("   → Opción 3: Kika invoca el router directamente sin polling")
                if attempt < retries - 1:
                    wait = 5 * (attempt + 1)
                    log.info(f"   Reintentando en {wait}s (intento {attempt+2}/{retries})...")
                    time.sleep(wait)
                    continue
            else:
                log.error(f"getUpdates HTTP {e.code}: {body[:200]}")
            return []
        except Exception as e:
            log.error(f"getUpdates error: {e}")
            if attempt < retries - 1:
                time.sleep(5)
                continue
            return []
    return []


# ─── PERSISTENCIA ────────────────────────────────────────────────────────────
def _load_offset() -> int:
    if os.path.isfile(STATE_FILE):
        try:
            return json.load(open(STATE_FILE)).get("offset", 0)
        except:
            pass
    return 0

def _save_offset(offset: int):
    json.dump({"offset": offset, "updated_at": datetime.now().isoformat()},
              open(STATE_FILE, "w"))


# ─── PIPELINE ────────────────────────────────────────────────────────────────
def _find_datos_json(ticker: str) -> str:
    """Busca JSON de datos más reciente para un ticker."""
    files = [f for f in os.listdir(WORKSPACE)
             if f.startswith(f"datos_{ticker}_") and f.endswith(".json")]
    if not files:
        return ""
    files.sort(reverse=True)
    return os.path.join(WORKSPACE, files[0])

def _has_prefetch(ticker: str) -> bool:
    return os.path.isfile(os.path.join(PREFETCH_DIR, f"prefetch_{ticker}.json"))


def _build_env() -> dict:
    """Construye entorno para subprocess con todas las keys necesarias."""
    env = dict(os.environ)
    env["HOME"] = os.path.expanduser("~")
    if GH_TOKEN:
        env["GH_TOKEN"] = GH_TOKEN
    if DEEPSEEK_API_KEY:
        env["DEEPSEEK_API_KEY"] = DEEPSEEK_API_KEY
    if OPENAI_API_KEY:
        env["OPENAI_API_KEY"] = OPENAI_API_KEY
    return env


def _extract_precio_from_json(datos_path: str) -> str:
    """Extrae el precio del JSON de datos. Campos en orden de prioridad."""
    try:
        datos = json.load(open(datos_path))
        val = (
            datos.get("meta", {}).get("precio_usuario") or
            datos.get("market", {}).get("precio_actual") or
            datos.get("precio_usuario") or
            datos.get("precio_actual") or
            datos.get("precio")
        )
        if val:
            return f"{float(val):.2f}"
    except Exception as e:
        log.warning(f"_extract_precio_from_json error: {e}")
    return ""


def run_sankey(ticker: str) -> dict:
    """
    Genera Sankey para el ticker usando el datos JSON más reciente disponible.
    El Sankey es independiente del informe LIGHT: usa el JSON de la última
    corrida del pipeline ($TICKER PRECIO), no de feroldi_pensante.py.
    Retorna dict con 'sankey_url' (puede ser None).

    ⚠️  P8: _push_html_to_github hace un push directo a diagramas/equities/
    sin actualizar el dashboard. Para registrar en dashboard, correr
    feroldi_push.py manualmente después.
    """
    result = {"sankey_url": None}

    datos_path = _find_datos_json(ticker)
    if not datos_path:
        tg_send(
            f"❌ No hay datos para *${ticker}*.\n"
            f"Primero corré el pipeline con `${ticker} PRECIO`."
        )
        return result

    precio_f = _extract_precio_from_json(datos_path)
    if not precio_f:
        tg_send(
            f"❌ No se encontró el precio en `{os.path.basename(datos_path)}`.\n"
            f"Revisá que el JSON tenga `meta.precio_usuario` o `market.precio_actual`."
        )
        return result

    log.info(f"📊 Sankey ${ticker} @ {precio_f} — {os.path.basename(datos_path)}")

    sankey_script = os.path.join(SCRIPTS_DIR, "feroldi_sankey.py")
    if not os.path.isfile(sankey_script):
        tg_send(f"❌ `feroldi_sankey.py` no encontrado en `{SCRIPTS_DIR}`")
        return result

    env = _build_env()
    cmd = f"python3 {sankey_script} {datos_path} {precio_f}"
    log.info(f"▶ {cmd}")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, timeout=180)
        log.info(f"   → exit {r.returncode}, {len(r.stdout + r.stderr)} chars")
        if r.returncode != 0:
            err = (r.stderr or r.stdout)[-400:]
            tg_send(f"❌ Sankey falló para *${ticker}*:\n```\n{err}\n```")
            return result

        sankey_path = _find_sankey_file(ticker, precio_f)
        if not sankey_path:
            tg_send(
                f"⚠️ `feroldi_sankey.py` terminó OK pero no encontré el HTML en `~/Downloads/`\n"
                f"Esperaba: `Diagrama_Sankey_{ticker}_{precio_f}_*.html`"
            )
            return result

        log.info(f"   HTML generado: {sankey_path}")

        if GH_TOKEN:
            gh_url = _push_html_to_github(sankey_path, GH_TOKEN)
            if gh_url:
                result["sankey_url"] = gh_url
            else:
                tg_send(
                    f"⚠️ Sankey generado pero falló el push a GitHub.\n"
                    f"Local: `{sankey_path}`"
                )
        else:
            tg_send(
                f"⚠️ Sankey generado localmente (GH_TOKEN vacío).\n"
                f"Local: `{sankey_path}`"
            )

    except subprocess.TimeoutExpired:
        tg_send(f"⏰ Timeout generando Sankey para *${ticker}* (>3 min)")
    except Exception as e:
        log.error(f"run_sankey exception: {e}")
        tg_send(f"❌ Error inesperado en Sankey para *${ticker}*: {e}")

    return result


def _push_html_to_github(local_path: str, gh_token: str) -> str:
    """
    Sube un archivo HTML a patonet/informes/diagramas/equities/ vía GitHub API.
    Retorna la URL de GitHub o None si falla.
    """
    import base64
    try:
        filename = os.path.basename(local_path)
        repo_path = f"diagramas/equities/{filename}"
        api_url = f"https://api.github.com/repos/patonet/informes/contents/{repo_path}"

        with open(local_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode()

        # Verificar si ya existe (para obtener sha)
        req_get = urllib.request.Request(api_url, headers={"Authorization": f"token {gh_token}"})
        sha = None
        try:
            with urllib.request.urlopen(req_get, timeout=15) as r:
                sha = json.loads(r.read()).get("sha")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                log.warning(f"GitHub check: HTTP {e.code}")

        payload = {"message": f"Add {filename}", "content": content_b64}
        if sha:
            payload["sha"] = sha

        req_put = urllib.request.Request(
            api_url, data=json.dumps(payload).encode(),
            headers={"Authorization": f"token {gh_token}", "Content-Type": "application/json"},
            method="PUT"
        )
        with urllib.request.urlopen(req_put, timeout=30) as r:
            result = json.loads(r.read())
            blob_url = result.get("content", {}).get("html_url", "")
            # Convertir blob URL → GitHub Pages URL para ver el HTML renderizado
            # github.com/patonet/informes/blob/main/PATH → patonet.github.io/informes/PATH
            pages_url = blob_url.replace(
                "https://github.com/patonet/informes/blob/main/",
                "https://patonet.github.io/informes/"
            ) if blob_url else ""
            log.info(f"✅ Sankey subido — Pages: {pages_url}")
            return pages_url or blob_url
    except Exception as e:
        log.error(f"_push_html_to_github error: {e}")
        return None


def _find_sankey_file(ticker: str, precio: str) -> str:
    """
    Busca el archivo Sankey en ~/Downloads/ para este ticker.
    Usa os.path.isfile() en lugar de os.listdir() para evitar
    el bloqueo TCC de macOS en subprocesos de OpenClaw.
    feroldi_sankey.py genera: Diagrama_Sankey_{TICKER}_{precio}_{DD-MM-YYYY}.html
    """
    downloads = os.path.expanduser("~/Downloads")
    precio_f = f"{float(precio):.2f}"
    # Intentar hoy y ayer (por si corre cerca de medianoche)
    from datetime import timedelta
    for delta in (0, 1):
        date_str = (datetime.now() - timedelta(days=delta)).strftime("%d-%m-%Y")
        path = os.path.join(downloads, f"Diagrama_Sankey_{ticker}_{precio_f}_{date_str}.html")
        if os.path.isfile(path):
            return path
    return ""


def run_pipeline(ticker: str, precio: str) -> dict:
    """
    Corre pipeline completo.
    Salta recolectar si ya existe JSON de datos.
    Salta prefetch si ya existe prefetch cache.
    Retorna dict con 'informe_url' y 'sankey_url' (ambos pueden ser None).
    """
    result = {"informe_url": None, "sankey_url": None}
    env = _build_env()
    precio_f = f"{float(precio):.2f}"

    # ── Paso 1: Recolectar (opcional) ──
    datos_path = _find_datos_json(ticker)
    if datos_path:
        log.info(f"⏭ Saltando recolectar — ya existe {os.path.basename(datos_path)}")
    else:
        cmd = f"python3 ~/feroldi_recolectar.py {ticker} {precio}"
        log.info(f"▶ Recolectar: {cmd}")
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, timeout=300)
        log.info(f"   → exit {r.returncode}, {len(r.stdout+r.stderr)} chars")
        if r.returncode != 0:
            err = (r.stderr or r.stdout)[-400:]
            tg_send(f"❌ Error en Recolector para ${ticker}:\n```\n{err}\n```")
            log.error(f"Recolectar falló: {err[:200]}")
            return None
        # Re-chequear
        datos_path = _find_datos_json(ticker)
        if not datos_path:
            tg_send(f"❌ Recolector terminó pero no encontró JSON para ${ticker}")
            log.error("Recolectar terminó OK pero no hay JSON")
            return None

    # ── Paso 2: Prefetch (opcional) ──
    if _has_prefetch(ticker):
        log.info(f"⏭ Saltando prefetch — ya existe prefetch_{ticker}.json")
    else:
        cmd = f"python3 ~/feroldi_prefetch.py {ticker} {precio_f}"
        log.info(f"▶ Prefetch: {cmd}")
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, timeout=180)
        log.info(f"   → exit {r.returncode}, {len(r.stdout+r.stderr)} chars")
        # Prefetch puede fallar parcialmente (web scraping). No fatal.
        if r.returncode != 0:
            log.warning(f"   ⚠ Prefetch retornó {r.returncode}")
            log.warning(f"   {r.stderr[:200] if r.stderr else r.stdout[:200]}")

    # ── Paso 3: Pensante + Push ──
    cmd = (f"python3 ~/feroldi_pensante.py --ticker {ticker} --precio {precio_f} "
           f"--modo light {'--push' if GH_TOKEN else ''}")
    log.info(f"▶ Pensante: {cmd}")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, timeout=1800)
        output = r.stdout + r.stderr
        log.info(f"   → exit {r.returncode}, {len(output)} chars, last 200:\n{output[-400:]}")

        # Buscar GITHUB_URL
        for line in output.splitlines():
            if line.startswith("GITHUB_URL="):
                result["informe_url"] = line.split("=", 1)[1].strip()
                break

        if r.returncode != 0:
            err = (r.stderr or r.stdout)[-400:]
            tg_send(f"❌ Error en Pensante para ${ticker}:\n```\n{err}\n```")
            return result  # puede haber url aunque haya error parcial

    except subprocess.TimeoutExpired:
        tg_send(f"⏰ Timeout en Pensante para ${ticker} (>10 min)")
        log.error("Pensante timeout")
        return result
    except Exception as e:
        log.error(f"Pensante exception: {e}")
        return result

    # Paso 4 (Sankey) se omite del pipeline automático.
    # El Sankey se dispara SOLO cuando el usuario escribe explícitamente "SANKEY".

    return result


# ─── HANDLER ─────────────────────────────────────────────────────────────────
def handle_message(text: str) -> bool:
    """Procesa un mensaje. Retorna True si lo manejó."""
    text = text.strip()

    # ── Comando SANKEY: enmascarado (N9K8E7 SANKEY) o plain ($NKE SANKEY) ──
    m_sk = RE_SANKEY.match(text)
    sankey_ticker = _unmask_ticker(m_sk.group(1)) if m_sk else None
    if not sankey_ticker:
        m_sk_p = RE_SANKEY_PLAIN.match(text)
        sankey_ticker = m_sk_p.group(1).upper() if m_sk_p else None
    if sankey_ticker:
        log.info(f"📊 Sankey request: ${sankey_ticker}")
        tg_send(f"⏳ Generando Sankey para <b>${sankey_ticker}</b>...", parse_mode="HTML")
        result = run_sankey(sankey_ticker)
        if result.get("sankey_url"):
            tg_send(f"📊 Sankey <b>${sankey_ticker}</b> listo → {result['sankey_url']}", parse_mode="HTML")
        return True

    # ── Comando PRECIO: enmascarado (N9K8E7 235.40) o plain ($NKE 235.40) ──
    m = RE_TICKER.match(text)
    ticker = _unmask_ticker(m.group(1)) if m else None
    precio = m.group(2) if m else None
    if not ticker:
        m_p = RE_TICKER_PLAIN.match(text)
        if m_p:
            ticker = m_p.group(1).upper()
            precio = m_p.group(2)
    if not ticker:
        return False

    log.info(f"📩 $${ticker} {precio} — iniciando pipeline")

    # Notificar al usuario
    tg_send(f"⏳ Pipeline Feroldi para <b>${ticker}</b> @ {precio} — ~7 min, te aviso cuando esté listo.", parse_mode="HTML")
    if not GH_TOKEN:
        tg_send("⚠️ GH_TOKEN no configurado — el informe se guardará solo localmente (sin push a GitHub)", parse_mode="HTML")

    result = run_pipeline(ticker, precio)
    informe_url = result.get("informe_url") if result else None
    sankey_url  = result.get("sankey_url")  if result else None

    if informe_url:
        msg = f"✅ Informe <b>${ticker}</b> listo\n📄 {informe_url}"
        if sankey_url:
            msg += f"\n📊 Sankey: {sankey_url}"
        tg_send(msg, parse_mode="HTML")
        log.info(f"✅ Pipeline exitoso: informe={informe_url} sankey={sankey_url}")
    else:
        # El informe se generó localmente aunque sin push
        inf = f"informe_{ticker}_{datetime.now().strftime('%d%m%Y')}_light*.md"
        tg_send(
            f"⚠️ Pipeline completado para **${ticker}** pero sin link de GitHub.\n"
            f"Revisá: `~/.openclaw/workspace/{inf}`",
            parse_mode="Markdown"
        )
        log.info("⚠️ Pipeline completado sin GITHUB_URL")

    return True


# ─── WEBHOOK MODE (servidor HTTP local) ──────────────────────────────────────
def run_webhook_server(host: str = "127.0.0.1", port: int = 8787):
    """Modo webhook: servidor HTTP mínimo que recibe POSTs de Telegram."""
    import http.server

    class WebhookHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                update = json.loads(body)
                msg = update.get("message", {})
                text = msg.get("text", "")
                from_id = str(msg.get("from", {}).get("id", ""))
                chat_id = str(msg.get("chat", {}).get("id", ""))

                if chat_id != CHAT_ID and from_id != CHAT_ID:
                    self.send_response(200)
                    self.end_headers()
                    return

                log.info(f"📩 Webhook: {repr(text[:80])}")
                if text:
                    handle_message(text)

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            except Exception as e:
                log.error(f"Webhook handler error: {e}")
                self.send_response(200)
                self.end_headers()

        def log_message(self, format, *args):
            log.debug(f"HTTP: {format % args}")

    server = http.server.HTTPServer((host, port), WebhookHandler)
    log.info(f"🌐 Webhook server escuchando en http://{host}:{port}")
    log.info(f"   Para usar: configura el webhook de Telegram apuntando a tu URL pública")
    log.info(f"   Ejemplo con ngrok: ngrok http {port}")
    log.info(f"   Luego: python3 ~/feroldi_telegram_router.py --set-webhook https://xxxx.ngrok.io")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Webhook server detenido.")
        server.server_close()


# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Feroldi Telegram Router")
    parser.add_argument("--ticker", help="Ejecuta pipeline para un ticker y termina (modo one-shot)")
    parser.add_argument("--precio", help="Precio (requerido con --ticker)")
    parser.add_argument("--sankey", metavar="TICKER",
                        help="Genera Sankey para un ticker usando el JSON más reciente y termina")
    parser.add_argument("--mode", choices=["polling", "webhook", "auto"], default="auto",
                        help="Modo de operación. auto=polling si no hay conflicto, webhook si hay")
    parser.add_argument("--set-webhook", metavar="URL",
                        help="Configura webhook de Telegram apuntando a esta URL y termina")
    parser.add_argument("--delete-webhook", action="store_true",
                        help="Elimina webhook y termina")
    parser.add_argument("--check", action="store_true",
                        help="Verifica configuración y termina")
    args = parser.parse_args()

    # ── Modo one-shot Sankey ──
    if args.sankey:
        log.info(f"=== MODO ONE-SHOT SANKEY: ${args.sankey.upper()} ===")
        result = run_sankey(args.sankey.upper())
        sankey_url = result.get("sankey_url")
        if sankey_url:
            print(f"\nSANKEY_URL={sankey_url}")
        else:
            print("\n⚠️ Sankey completado sin URL")
        return

    # ── Modo one-shot pipeline ──
    if args.ticker:
        if not args.precio:
            print("❌ --precio es requerido con --ticker")
            sys.exit(1)
        log.info(f"=== MODO ONE-SHOT: ${args.ticker} @ ${args.precio} ===")
        result = run_pipeline(args.ticker.upper(), args.precio)
        informe_url = result.get("informe_url") if result else None
        sankey_url  = result.get("sankey_url")  if result else None
        if informe_url:
            print(f"\nGITHUB_URL={informe_url}")
        else:
            print("\n⚠️ Pipeline completado sin GITHUB_URL")
        if sankey_url:
            print(f"SANKEY_URL={sankey_url}")
        return

    # ── Acciones administrativas ──
    if args.set_webhook:
        set_webhook(args.set_webhook)
        return
    if args.delete_webhook:
        set_webhook("")
        return

    # ── Diagnóstico ──
    if args.check:
        print(f"\n{'='*50}")
        print(f"  FEROLDI TELEGRAM ROUTER — DIAGNÓSTICO")
        print(f"{'='*50}")
        print(f"  BOT_TOKEN:        {'✅' if BOT_TOKEN else '❌'} {BOT_TOKEN[:12] if BOT_TOKEN else 'FALTANTE'}...")
        print(f"  CHAT_ID:          {CHAT_ID}")
        print(f"  GH_TOKEN:         {'✅' if GH_TOKEN else '❌'} {'SET' if GH_TOKEN else 'VACÍO'}")
        print(f"  DEEPSEEK_API_KEY: {'✅' if DEEPSEEK_API_KEY else '❌'} {'SET' if DEEPSEEK_API_KEY else 'VACÍA'}")
        print(f"  OPENAI_API_KEY:   {'✅' if OPENAI_API_KEY else '❌'} {'SET' if OPENAI_API_KEY else 'VACÍA'}")
        print(f"  LOG:              {LOG_FILE}")
        print(f"  SCRIPT RECOLECTAR: {'✅' if os.path.isfile(os.path.join(SCRIPTS_DIR, 'feroldi_recolectar.py')) else '❌'}")
        print(f"  SCRIPT PREFETCH:   {'✅' if os.path.isfile(os.path.join(SCRIPTS_DIR, 'feroldi_prefetch.py')) else '❌'}")
        print(f"  SCRIPT PENSANTE:   {'✅' if os.path.isfile(os.path.join(SCRIPTS_DIR, 'feroldi_pensante.py')) else '❌'}")
        print(f"  SCRIPT SANKEY:     {'✅' if os.path.isfile(os.path.join(SCRIPTS_DIR, 'feroldi_sankey.py')) else '❌'}")
        print(f"  WORKSPACE:         {WORKSPACE}")
        print(f"{'='*50}")
        # Verificar webhook actual
        try:
            with urllib.request.urlopen(f"{API_BASE}/getWebhookInfo", timeout=10) as r:
                wh = json.loads(r.read())
                wu = wh.get("result", {}).get("url", "")
                print(f"  Webhook actual:   {wu or '(ninguno)'}")
                if wu:
                    print(f"  Pending updates:  {wh['result'].get('pending_update_count', '?')}")
        except:
            pass
        print(f"{'='*50}\n")
        return

    # ── Modo daemon ──
    mode = args.mode

    # Auto-detectar: si webhook está configurado, usarlo; si no, polling
    if mode == "auto":
        try:
            with urllib.request.urlopen(f"{API_BASE}/getWebhookInfo", timeout=10) as r:
                wh = json.loads(r.read())
                wu = wh.get("result", {}).get("url", "")
                if wu:
                    log.info(f"🔗 Webhook detectado: {wu}")
                    mode = "webhook"
                else:
                    mode = "polling"
        except:
            mode = "polling"

    if mode == "webhook":
        log.info("🌐 Modo WEBHOOK")
        run_webhook_server()
        return

    # ── Modo polling daemon ──
    print(f"\n{'='*55}")
    print(f"  FEROLDI TELEGRAM ROUTER v2.0")
    print(f"  Bot: {BOT_TOKEN[:12]}...")
    print(f"  Chat: {CHAT_ID}")
    print(f"  GH_TOKEN: {'✅' if GH_TOKEN else '❌'}")
    print(f"  DEEPSEEK_API_KEY: {'✅' if DEEPSEEK_API_KEY else '❌'}")
    print(f"  Log: {LOG_FILE}")
    print(f"  Escuchando: $TICKER PRECIO")
    if not GH_TOKEN:
        print(f"  ⚠️  GH_TOKEN vacío → --push deshabilitado (sin GitHub)")
    print(f"{'='*55}\n")

    offset = _load_offset()
    log.info(f"Iniciando daemon, offset={offset}")

    polling_errors = 0
    while True:
        try:
            updates = get_updates(offset)
            if updates:
                polling_errors = 0  # reset en éxito

            for upd in updates:
                offset = upd["update_id"] + 1
                _save_offset(offset)

                msg = upd.get("message", {})
                text = msg.get("text", "")
                from_id = str(msg.get("from", {}).get("id", ""))
                chat_id = str(msg.get("chat", {}).get("id", ""))
                requester = chat_id or from_id

                # Filtrar solo IDs autorizados
                if requester not in ALLOWED_IDS and from_id not in ALLOWED_IDS:
                    log.info(f"  Ignorado de {requester} (no autorizado)")
                    continue

                if not text:
                    continue

                # Setear contexto de respuesta: las respuestas van al remitente
                global _reply_to
                _reply_to = requester or CHAT_ID

                log.info(f"📩 [{_reply_to}] Mensaje: {repr(text[:80])}")
                handled = handle_message(text)
                if not handled:
                    log.info(f"  ~ No es comando Feroldi, ignorando")

        except KeyboardInterrupt:
            log.info("Router detenido por el usuario.")
            sys.exit(0)
        except Exception as e:
            polling_errors += 1
            log.error(f"Error en loop: {e}", exc_info=True)
            wait = min(polling_errors * 5, 60)  # backoff hasta 60s
            time.sleep(wait)


if __name__ == "__main__":
    main()
