# -*- coding: utf-8 -*-
"""
salvage.py — Recupera runs marcados como 'failed' cuyo único problema fue un
PCAP truncado (tshark detenido en duro dejó el último bloque pcapng a medias).

Re-extrae métricas con el extractor tolerante, escribe metrics.json y marca el
manifest como 'completed' con la anotación pcap_truncado. No re-captura: los
paquetes completos ya están en el fichero.

  python -m exp1.src.salvage [--out exp1]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from exp1.src.manifest import actualizar_manifest, cargar_manifest  # noqa: E402
from exp1.src.traffic_metrics import extraer_metricas  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Recupera runs con PCAP truncado")
    parser.add_argument("--out", default=str(_ROOT / "exp1"))
    args = parser.parse_args()
    out_dir = Path(args.out)

    recuperados, sin_arreglo = [], []
    for planner_dir in out_dir.iterdir():
        if not planner_dir.is_dir() or planner_dir.name in ("src", "plots", "__pycache__"):
            continue
        for run_dir in sorted(planner_dir.glob("run_*")):
            man = cargar_manifest(run_dir)
            if not man or man.get("status") != "failed":
                continue
            pcap = run_dir / "capture.pcap"
            if not (pcap.is_file() and pcap.stat().st_size > 0):
                sin_arreglo.append(str(run_dir) + " (sin PCAP)")
                continue
            try:
                met = extraer_metricas(pcap)
            except Exception as e:
                sin_arreglo.append(f"{run_dir} ({e})")
                continue
            (run_dir / "metrics.json").write_text(
                json.dumps(met, ensure_ascii=False, indent=2), encoding="utf-8")
            actualizar_manifest(
                run_dir,
                status="completed",
                recuperado_de_truncamiento=True,
                rutas={"metrics_json": str(run_dir / "metrics.json")},
            )
            recuperados.append(
                f"{man['run_id']}: {met['packets']} pkts, {met['flows_total']} flows "
                f"(truncado={met['pcap_truncado']})")

    print("Recuperados:")
    for r in recuperados:
        print("  ", r)
    if sin_arreglo:
        print("Sin arreglo:")
        for s in sin_arreglo:
            print("  ", s)
    if not recuperados and not sin_arreglo:
        print("  (no había runs failed que recuperar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
