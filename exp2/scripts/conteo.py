# -*- coding: utf-8 -*-
"""
conteo.py — Genera exp2/conteo_flows.md a partir de los CSV de flujos y de los
resúmenes de sesión. Se regenera siempre desde los datos: no se escribe a mano.

Uso: python -m exp2.scripts.conteo
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
EXP2 = _ROOT / "exp2"

ORIGEN = {
    "ours_regular": "Nuestro · perfil regular (agentev7 + planner LLM) — exp1/llm/run_01..10",
    "ours_gamer": "Nuestro · perfil gamer (Discord + Steam) — Articulo/capturaAgenteGamer15m1..5",
    "ours_admin": "Nuestro · perfil admin de red (SSH multi-host) — Articulo/capturaAgenteAdmin15m1..5",
    "baseline_interno": "Baseline interno · planner aleatorio (mismo navegador, sin LLM) — exp1/random/run_01..10",
    "baseline_script": "Baseline interno · script simple (urllib, intervalo fijo, SIN navegador) — exp2/baseline_script/run_01..03",
    "baseline_publico_ctu": "Baseline público en PCAP — Stratosphere CTU-Normal-7 (nuestro extractor)",
    "baseline_publico_ids2018": "Baseline público en CSV — CSE-CIC-IDS2018 Wednesday, clase Benign (CICFlowMeter)",
}


def main() -> int:
    flows_dir = EXP2 / "flows"
    res_path = EXP2 / "aggregated" / "resumenes_sesion.json"
    resumenes = (json.loads(res_path.read_text(encoding="utf-8"))["resumenes"]
                 if res_path.exists() else [])
    por_run = {r["run_id"]: r for r in resumenes}

    filas, detalle = [], []
    for src, descripcion in ORIGEN.items():
        f = flows_dir / f"{src}.csv"
        if not f.exists():
            continue
        df = pd.read_csv(f)
        runs = sorted(df["run_id"].unique())
        pkts = sum(por_run.get(r, {}).get("packets", 0) for r in runs)
        dur = sum(por_run.get(r, {}).get("duration_s", 0) for r in runs)
        filas.append({
            "fuente": src,
            "perfil": df["profile"].iloc[0],
            "runs": len(runs),
            "flows": len(df),
            "flows_por_run": round(len(df) / len(runs), 1),
            "paquetes": pkts,
            "duracion_total_s": round(dur),
            "descripcion": descripcion,
        })
        for r in runs:
            sub = df[df["run_id"] == r]
            meta = por_run.get(r, {})
            detalle.append({
                "fuente": src, "run_id": r, "flows": len(sub),
                "paquetes": meta.get("packets", ""),
                "duracion_s": meta.get("duration_s", ""),
                "dns_queries": meta.get("dns_queries", ""),
                "unique_dst_ips": meta.get("unique_dst_ips", ""),
                "truncado": meta.get("pcap_truncado", ""),
            })

    t = ["# Nº de flujos analizados por fuente — Experimento 2", "",
         "Generado por `python -m exp2.scripts.conteo`. **Todo estadístico de este",
         "experimento hay que leerlo con estos tamaños de muestra delante.**", "",
         "## Resumen por fuente", "",
         "| Fuente | Perfil | Runs | Flujos | Flujos/run | Paquetes | Duración total |",
         "|---|---|---:|---:|---:|---:|---:|"]
    for f in filas:
        pk = f"{f['paquetes']:,}".replace(",", ".") if f["paquetes"] else "n/d"
        du = f"{f['duracion_total_s'] / 60:.0f} min" if f["duracion_total_s"] else "n/d"
        t.append(f"| `{f['fuente']}` | {f['perfil']} | {f['runs']} | "
                 f"{f['flows']:,}".replace(",", ".")
                 + f" | {f['flows_por_run']} | {pk} | {du} |")

    total = sum(f["flows"] for f in filas)
    t += ["", f"**Total: {total:,} flujos**".replace(",", "."), "",
          "## Procedencia", ""]
    for f in filas:
        t.append(f"- **`{f['fuente']}`** — {f['descripcion']}")

    t += ["", "## Desbalance (declarado, no corregido)", "",
          "- El perfil **regular** tiene 10 runs; **gamer** y **admin**, 5. Se usan",
          "  las capturas existentes (ver LIMITACIONES.md §7).",
          "- El baseline **CTU-Normal** es **una sola captura** de 21 min: no hay",
          "  varianza entre runs que reportar.",
          "- El baseline **IDS2018** es una **muestra aleatoria (seed 2000)** de los",
          "  flujos Benign de un día completo, no una sesión: su 'run' es el día.",
          "", "## Detalle por run", "",
          "| Fuente | Run | Flujos | Paquetes | Duración (s) | DNS queries | IPs destino únicas |",
          "|---|---|---:|---:|---:|---:|---:|"]
    for d in detalle:
        t.append(f"| `{d['fuente']}` | {d['run_id']} | {d['flows']:,}".replace(",", ".")
                 + f" | {d['paquetes']} | {d['duracion_s']} | {d['dns_queries']}"
                 f" | {d['unique_dst_ips']} |")

    destino = EXP2 / "conteo_flows.md"
    destino.write_text("\n".join(t) + "\n", encoding="utf-8")
    print(f"[OK] {destino} ({total} flujos, {len(filas)} fuentes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
