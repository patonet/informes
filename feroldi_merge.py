#!/usr/bin/env python3
"""
FEROLDI MERGE — v X0.56
Sistema Feroldi · @patonet
======================================
Mergea el JSON base (feroldi_recolectar.py) con el bloque ENRIQUECIDO
que emite Claude Code al final del análisis Heavy.

FLUJO AUTOMÁTICO KIKA:
  1. feroldi_recolectar.py FSLY 31.60   → datos_FSLY_05052026.json
  2. Claude Code (prompt_heavy)         → análisis + bloque ENRIQUECIDO_JSON:{...}
  3. feroldi_merge.py <base.json> <analisis.json>  → datos_FSLY_full.json
  4. feroldi_sankey.py datos_FSLY_full.json        → Diagrama_Sankey_FSLY_*.html
  5. feroldi_push.py                               → GitHub → link

USO:
  python3 feroldi_merge.py datos_FSLY_05052026.json enriquecido_FSLY.json
  python3 feroldi_merge.py datos_FSLY_05052026.json enriquecido_FSLY.json --output ~/Desktop/

  El segundo argumento puede ser:
    a) Un archivo JSON con solo el bloque {"enriquecido": {...}}
    b) Un archivo de texto con el bloque ENRIQUECIDO_JSON:{...} en cualquier posición
       (como lo emite Claude Code al final del análisis)
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

VERSION = "X0.56"

def extraer_enriquecido(texto_o_path: str) -> dict:
    """
    Extrae el bloque enriquecido desde:
      a) Un archivo .json limpio con {"enriquecido": {...}}
      b) Un archivo de texto/html que contiene ENRIQUECIDO_JSON:{...}
         en cualquier posición (output de Claude Code)
    """
    p = Path(texto_o_path)
    if not p.exists():
        raise FileNotFoundError(f"No se encontró: {texto_o_path}")

    contenido = p.read_text(encoding="utf-8")

    # Intento A: JSON limpio
    try:
        data = json.loads(contenido)
        if "enriquecido" in data:
            print(f"  ✓ Enriquecido extraído como JSON directo")
            return data["enriquecido"]
        # Si tiene estructura plana, asumir que TODO es el enriquecido
        if any(k in data for k in ["quarterly", "sotp", "feroldi_score", "backlog"]):
            print(f"  ✓ Enriquecido extraído (JSON plano)")
            return data
    except json.JSONDecodeError:
        pass

    # Intento B: buscar bloque ENRIQUECIDO_JSON:{...} en texto libre
    # Claude Code lo emite como: ENRIQUECIDO_JSON:\n{...}
    patterns = [
        r'ENRIQUECIDO_JSON:\s*(\{.*?\})\s*(?:```|$|\n\n)',
        r'ENRIQUECIDO_JSON:\s*(```json\s*\{.*?\}\s*```)',
        r'"enriquecido"\s*:\s*(\{.*\})',
    ]
    for pat in patterns:
        m = re.search(pat, contenido, re.DOTALL | re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            raw = re.sub(r'^```json\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            try:
                data = json.loads(raw)
                print(f"  ✓ Enriquecido extraído via regex del output del análisis")
                return data
            except json.JSONDecodeError as e:
                print(f"  ⚠ Regex match encontrado pero JSON inválido: {e}")
                continue

    raise ValueError(
        "No se encontró bloque ENRIQUECIDO_JSON en el archivo.\n"
        "Asegúrate que Claude Code emitió el bloque al final del análisis.\n"
        "Formato esperado: ENRIQUECIDO_JSON:\\n{...}"
    )


def merge(base_path: str, enr_path: str, output_dir: Path = None) -> Path:
    """Mergea base JSON + enriquecido → _full.json"""

    # Leer base
    bp = Path(base_path)
    if not bp.exists():
        raise FileNotFoundError(f"JSON base no encontrado: {base_path}")

    with open(bp, "r", encoding="utf-8") as f:
        base = json.load(f)

    print(f"\n{'='*55}")
    print(f"  FEROLDI MERGE {VERSION} · @patonet")
    print(f"{'='*55}")
    ticker = base.get("meta", {}).get("ticker", "?")
    precio = base.get("meta", {}).get("precio_usuario", "?")
    fecha  = base.get("meta", {}).get("fecha", datetime.now().strftime("%d-%m-%Y"))
    print(f"\n  Base:    {bp.name}  ({ticker} @ ${precio})")
    print(f"  Fuente:  {Path(enr_path).name}\n")

    # Extraer enriquecido
    enriquecido = extraer_enriquecido(enr_path)

    # Merge — el bloque enriquecido se añade bajo la clave "enriquecido"
    base["enriquecido"] = enriquecido
    base["meta"]["version"] = VERSION
    base["meta"]["modo"] = "enriquecido"
    base["meta"]["merge_fecha"] = datetime.now().strftime("%d-%m-%Y %H:%M")

    # Nombre del output
    if output_dir is None:
        output_dir = bp.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = bp.stem.replace("_full", "")  # evitar _full_full si se corre dos veces
    out_path = output_dir / f"{stem}_full.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2, default=str)

    # Resumen de campos enriquecidos encontrados
    campos = list(enriquecido.keys())
    print(f"  ✅ Merge exitoso → {out_path.name}")
    print(f"  📦 Campos enriquecidos: {', '.join(campos)}")
    print(f"\n  👉 Siguiente paso:")
    print(f"     python3 feroldi_sankey.py {out_path.name}")
    print(f"{'='*55}\n")

    return out_path


def main():
    if len(sys.argv) < 3:
        print("USO: python3 feroldi_merge.py <base.json> <enriquecido.json> [--output DIR]")
        print("EJ:  python3 feroldi_merge.py datos_FSLY_05052026.json enriquecido_FSLY.json")
        sys.exit(1)

    base_path = sys.argv[1]
    enr_path  = sys.argv[2]
    output_dir = None
    if "--output" in sys.argv:
        output_dir = Path(sys.argv[sys.argv.index("--output") + 1])

    try:
        merge(base_path, enr_path, output_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
