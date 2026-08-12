# -*- coding: utf-8 -*-
"""
baseline_script.py — Baseline "tonto" del Experimento 2: tráfico generado por un
SCRIPT SIMPLE, sin agente, sin planner y sin navegador.

Por qué existe: el baseline interno de exp1 (`exp1/random`) cambia solo el
*planner* — sigue siendo el mismo Chrome ejecutando el mismo catálogo de acciones,
y a nivel de flujo produce tráfico casi idéntico al del perfil regular
(KS D = 0,036; ver RESULTADOS.md §3). Es un contraste entre planners, no entre
comportamientos. Este baseline sí es el contraste ingenuo que pide el experimento:

  - **Sin navegador**: `urllib`, una petición GET y punto. No hay motor JS, ni
    subrecursos (CSS/JS/imágenes), ni prefetch, ni QUIC, ni cookies, ni sesión.
  - **Sin comportamiento**: intervalo FIJO entre peticiones (no hay tiempos de
    lectura, ni scroll, ni encadenar acciones según lo que se ve).
  - **Sin estado**: cada petición es independiente; el orden sale de un `random`
    con seed, sobre una lista fija de URLs.

Mismas condiciones que el resto del experimento: misma máquina, misma interfaz de
captura (tshark), misma duración de sesión (900 s) y el MISMO extractor de flujos.

Uso:
  python -m exp2.scripts.baseline_script --runs 3 --duration 900
  python -m exp2.scripts.baseline_script --smoke        # 1 run de 60 s
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import captura_combinada  # noqa: E402
from exp1.src.orchestrate import detectar_iface_activa  # noqa: E402

SALIDA = _ROOT / "exp2" / "baseline_script"
INTERVALO_S = 10.0        # intervalo FIJO: sin jitter, sin tiempo de lectura
TIMEOUT_S = 20
SEED_BASE = 3000          # seed = SEED_BASE + índice_de_run
UA = "Mozilla/5.0 (compatible; tfm-baseline-script/1.0)"

# Lista fija de URLs. Son los mismos dominios que toca el agente web, para que la
# diferencia medida sea el COMPORTAMIENTO (script vs agente) y no el destino.
URLS = [
    "https://www.google.com/",
    "https://www.youtube.com/",
    "https://x.com/",
    "https://mail.google.com/",
    "https://www.wikipedia.org/",
    "https://www.amazon.es/",
    "https://www.elpais.com/",
    "https://www.marca.com/",
    "https://www.twitch.tv/",
    "https://www.netflix.com/",
]


def generar_trafico(duracion_s: float, seed: int, csv_out: Path) -> dict:
    """Bucle GET a intervalo fijo. Devuelve el recuento de peticiones."""
    rng = random.Random(seed)
    filas: list[dict] = []
    t0 = time.time()
    i = 0

    while time.time() - t0 < duracion_s:
        url = rng.choice(URLS)
        i += 1
        inicio = time.time()
        estado, bytes_leidos, error = "", 0, ""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                estado = str(r.status)
                bytes_leidos = len(r.read())
        except urllib.error.HTTPError as e:
            estado, error = str(e.code), "HTTPError"
        except Exception as e:                       # DNS, TLS, timeout...
            estado, error = "ERR", type(e).__name__

        filas.append({
            "i": i, "t_rel_s": round(inicio - t0, 2), "url": url,
            "status": estado, "bytes": bytes_leidos,
            "latencia_s": round(time.time() - inicio, 3), "error": error,
        })
        print(f"  [{i:03d}] {inicio - t0:6.1f}s {estado:>4} {bytes_leidos:>9,} B  {url}",
              flush=True)

        # Intervalo FIJO desde el inicio de la petición (no acumula la latencia).
        espera = INTERVALO_S - (time.time() - inicio)
        restante = duracion_s - (time.time() - t0)
        if restante <= 0:
            break
        time.sleep(max(0.0, min(espera, restante)))

    with csv_out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]) if filas else ["i"])
        w.writeheader()
        w.writerows(filas)

    ok = sum(1 for f in filas if f["status"].startswith("2"))
    return {
        "peticiones": len(filas), "ok": ok, "fallidas": len(filas) - ok,
        "bytes_leidos": sum(f["bytes"] for f in filas),
    }


def ejecutar_run(i: int, duracion: int, iface: str) -> dict:
    run_dir = SALIDA / f"run_{i:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pcap = run_dir / "capture.pcap"
    seed = SEED_BASE + i

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_ROOT,
                            capture_output=True, text=True).stdout.strip()
    print(f"\n[run_{i:02d}] seed={seed} dur={duracion}s iface={iface} -> {run_dir}")

    proc = captura_combinada.iniciar_tshark(str(pcap))
    if proc is None:
        return {"run_id": f"script_run{i:02d}", "status": "failed",
                "error": "tshark no arrancó"}

    t0 = time.time()
    try:
        stats = generar_trafico(duracion, seed, run_dir / "requests.csv")
    finally:
        time.sleep(2)               # deja cerrar las conexiones en vuelo
        captura_combinada.detener_tshark(proc)

    manifest = {
        "run_id": f"script_run{i:02d}", "status": "completed",
        "baseline": "script_simple_sin_navegador",
        "seed": seed, "commit": commit,
        "inicio_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duracion_solicitada_s": duracion,
        "duracion_real_s": round(time.time() - t0, 1),
        "intervalo_fijo_s": INTERVALO_S,
        "n_urls_catalogo": len(URLS),
        "iface_captura": iface,
        "pcap": str(pcap),
        "pcap_bytes": pcap.stat().st_size if pcap.exists() else 0,
        **stats,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[run_{i:02d}] {stats['peticiones']} peticiones "
          f"({stats['ok']} OK) | PCAP {manifest['pcap_bytes'] / 1e6:.1f} MB")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser(description="Baseline script simple (exp2)")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--duration", type=int, default=900)
    p.add_argument("--smoke", action="store_true", help="1 run de 60 s")
    p.add_argument("--iface", default="")
    args = p.parse_args()

    # captura_combinada imprime con caracteres fuera de cp1252 (la consola de
    # Windows por defecto). Se reconfigura la salida en vez de tocar ese fichero,
    # que es compartido con exp1.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    runs = 1 if args.smoke else args.runs
    duracion = 60 if args.smoke else args.duration

    iface = args.iface or detectar_iface_activa()
    captura_combinada.IFACE_WINDOWS = iface

    SALIDA.mkdir(parents=True, exist_ok=True)
    manifiestos = [ejecutar_run(i, duracion, iface) for i in range(1, runs + 1)]

    (SALIDA / "runs.json").write_text(
        json.dumps(manifiestos, ensure_ascii=False, indent=2), encoding="utf-8")
    okey = sum(1 for m in manifiestos if m.get("status") == "completed")
    print(f"\n[FIN] {okey}/{len(manifiestos)} runs completados -> {SALIDA}")
    return 0 if okey == len(manifiestos) else 1


if __name__ == "__main__":
    sys.exit(main())
