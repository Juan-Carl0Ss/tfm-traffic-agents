# -*- coding: utf-8 -*-
"""
extract_all.py — Aplica el MISMO extractor (`flow_features.py`) a todas las
fuentes en PCAP del Experimento 2 y escribe un CSV de flujos por fuente.

Fuentes (ver exp2/README.md para la procedencia de cada una):

  ours_regular      exp1/llm/run_01..10/capture.pcap        (agente web + planner LLM)
  ours_gamer        Articulo/capturaAgenteGamer15m{1..5}    (agente gamer)
  ours_admin        Articulo/capturaAgenteAdmin15m{1..5}    (agente admin de red)
  baseline_interno  exp1/random/run_01..10/capture.pcap     (planner aleatorio, sin LLM)
  baseline_script   exp2/baseline_script/run_01..03         (script simple, sin navegador)
  baseline_publico_ctu  exp2/public/ctu_normal_7.pcap       (Stratosphere CTU-Normal)

El baseline público en CSV (CSE-CIC-IDS2018) NO pasa por aquí: no hay PCAP
descargable. Lo alinea `adapt_ids2018.py`.

Uso:
  python -m exp2.scripts.extract_all                 # todas las fuentes
  python -m exp2.scripts.extract_all --fuentes ours_gamer
  python -m exp2.scripts.extract_all --smoke         # 20 s por PCAP (prueba rápida)
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from exp2.scripts.flow_features import ESQUEMA_FLOW, extraer_flows  # noqa: E402

EXP2 = _ROOT / "exp2"
ARTICULO = Path("C:/Users/juanc/Desktop/Articulo")

# (source, profile, [(run_id, ruta_pcap), ...])
FUENTES: dict[str, dict] = {
    "ours_regular": {
        "profile": "regular",
        "pcaps": [(f"llm_run{i:02d}", _ROOT / "exp1" / "llm" / f"run_{i:02d}" / "capture.pcap")
                  for i in range(1, 11)],
    },
    "ours_gamer": {
        "profile": "gamer",
        "pcaps": [(f"gamer_run{i:02d}", ARTICULO / f"capturaAgenteGamer15m{i}.pcapng")
                  for i in range(1, 6)],
    },
    "ours_admin": {
        "profile": "admin",
        "pcaps": [(f"admin_run{i:02d}", ARTICULO / f"capturaAgenteAdmin15m{i}.pcapng")
                  for i in range(1, 6)],
    },
    "baseline_interno": {
        "profile": "random_baseline",
        "pcaps": [(f"random_run{i:02d}", _ROOT / "exp1" / "random" / f"run_{i:02d}" / "capture.pcap")
                  for i in range(1, 11)],
    },
    "baseline_script": {
        "profile": "script_simple",
        "pcaps": [(f"script_run{i:02d}", EXP2 / "baseline_script" / f"run_{i:02d}" / "capture.pcap")
                  for i in range(1, 4)],
    },
    "baseline_publico_ctu": {
        "profile": "ctu_normal",
        "pcaps": [("ctu_normal_7", EXP2 / "public" / "ctu_normal_7.pcap")],
    },
}


def _procesar(args: tuple) -> tuple[str, list[dict], dict]:
    source, profile, run_id, ruta, max_seconds = args
    t = time.time()
    filas, resumen = extraer_flows(
        ruta, source=source, profile=profile, run_id=run_id, max_seconds=max_seconds)
    resumen["segundos_proceso"] = round(time.time() - t, 1)
    resumen["fichero_bytes"] = Path(ruta).stat().st_size
    return source, filas, resumen


def main() -> int:
    p = argparse.ArgumentParser(description="Extracción de flujos exp2")
    p.add_argument("--fuentes", nargs="*", default=list(FUENTES),
                   help="subconjunto de fuentes a procesar")
    p.add_argument("--smoke", action="store_true",
                   help="solo los primeros 20 s de cada PCAP (validación rápida)")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()

    max_seconds = 20.0 if args.smoke else 0.0
    salida = EXP2 / ("flows_smoke" if args.smoke else "flows")
    salida.mkdir(parents=True, exist_ok=True)

    tareas, ausentes = [], []
    for source in args.fuentes:
        cfg = FUENTES[source]
        for run_id, ruta in cfg["pcaps"]:
            if Path(ruta).exists():
                tareas.append((source, cfg["profile"], run_id, str(ruta), max_seconds))
            else:
                ausentes.append((source, run_id, str(ruta)))

    for source, run_id, ruta in ausentes:
        print(f"[AUSENTE] {source}/{run_id}: no existe {ruta}")
    if not tareas:
        print("[ERROR] Ninguna fuente disponible.")
        return 1

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_ROOT,
                            capture_output=True, text=True).stdout.strip()
    print(f"[INFO] commit={commit} | {len(tareas)} PCAPs | workers={args.workers}"
          f"{' | SMOKE 20 s' if args.smoke else ''}")

    por_fuente: dict[str, list[dict]] = {}
    resumenes: list[dict] = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futuros = {pool.submit(_procesar, t): t for t in tareas}
        for fut in as_completed(futuros):
            source, filas, resumen = fut.result()
            por_fuente.setdefault(source, []).extend(filas)
            resumenes.append(resumen)
            print(f"  [OK] {resumen['run_id']:<14} {resumen['packets']:>9} pkts"
                  f"  {resumen['flows']:>7} flows  {resumen['segundos_proceso']:>6.1f}s"
                  + ("  [TRUNCADO]" if resumen["pcap_truncado"] else ""))

    for source, filas in sorted(por_fuente.items()):
        filas.sort(key=lambda r: (r["run_id"], int(r["flow_id"].rsplit("_", 1)[-1])))
        destino = salida / f"{source}.csv"
        with destino.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=ESQUEMA_FLOW)
            w.writeheader()
            w.writerows(filas)
        print(f"[CSV] {destino.name:<26} {len(filas):>8} flujos")

    agg = EXP2 / "aggregated"
    agg.mkdir(parents=True, exist_ok=True)
    (agg / ("resumenes_sesion_smoke.json" if args.smoke else "resumenes_sesion.json")).write_text(
        json.dumps({"commit": commit, "smoke": args.smoke, "resumenes": resumenes},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[FIN] {sum(len(v) for v in por_fuente.values())} flujos en "
          f"{time.time() - t0:.0f}s -> {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
