# -*- coding: utf-8 -*-
"""
analyze.py — Agregación y gráficas del Experimento 1.

Recorre exp1/<planner>/run_XX/, cruza manifest.json + metrics.json + actions.csv
y produce:
  exp1/summary_por_sesion.csv   una fila por run (métricas de tráfico + acciones)
  exp1/actions_agregado.csv     todas las acciones (sin prompts, para tamaño)
  exp1/plots/*.png              boxplots comparativos + distribución de tipos

Uso:
  python -m exp1.src.analyze [--out exp1]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

PLANNERS = ["llm", "random", "rule"]

# Paleta categórica validada (dataviz reference, modo claro): orden fijo por planner
COLOR = {"llm": "#2a78d6", "random": "#1baf7a", "rule": "#eda100"}
INK, INK_MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"


def _entropia(c: Counter) -> float:
    total = sum(c.values())
    if total <= 0:
        return 0.0
    return -sum((v / total) * math.log2(v / total) for v in c.values() if v > 0)


def _metricas_acciones(actions_csv: Path) -> dict:
    """Diversidad y repetición sobre la secuencia de acciones ejecutadas."""
    tipos_ejecutados: list[str] = []
    if actions_csv.is_file():
        with open(actions_csv, encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                if fila.get("validada") == "ok":
                    tipos_ejecutados.append(fila["tipo"])
    c = Counter(tipos_ejecutados)
    n = len(tipos_ejecutados)
    bigramas = list(zip(tipos_ejecutados, tipos_ejecutados[1:]))
    rep_inmediata = sum(1 for a, b in bigramas if a == b) / len(bigramas) if bigramas else 0.0
    bigramas_unicos = len(set(bigramas)) / len(bigramas) if bigramas else 0.0
    return {
        "n_tipos_distintos": len(c),
        "entropia_tipos": round(_entropia(c), 4),
        "tasa_repeticion_inmediata": round(rep_inmediata, 4),
        "ratio_bigramas_unicos": round(bigramas_unicos, 4),
        "tipos_counter": c,
    }


def cargar_runs(out_dir: Path) -> list[dict]:
    filas = []
    for planner in PLANNERS:
        pdir = out_dir / planner
        if not pdir.is_dir():
            continue
        for run_dir in sorted(pdir.glob("run_*")):
            mpath = run_dir / "manifest.json"
            if not mpath.is_file():
                continue
            man = json.loads(mpath.read_text(encoding="utf-8"))
            met = {}
            metp = run_dir / "metrics.json"
            if metp.is_file():
                met = json.loads(metp.read_text(encoding="utf-8"))
            acc = man.get("acciones") or {}
            div = _metricas_acciones(run_dir / "actions.csv")

            emitidas = acc.get("emitidas", 0)
            validas = acc.get("validas", 0)
            fila = {
                "run_id": man.get("run_id"),
                "planner": planner,
                "run_dir": str(run_dir),
                "seed": man.get("seed"),
                "status": man.get("status"),
                "inicio": man.get("inicio"),
                "duracion_solicitada_s": man.get("duracion_solicitada_s"),
                "duracion_real_s": man.get("duracion_real_s"),
                "commit": (man.get("git") or {}).get("commit_hash", "")[:12],
                "n_errores": len(man.get("errores") or []),
                # acciones
                "acc_emitidas": emitidas,
                "acc_validas": validas,
                "acc_rechazadas_validacion": acc.get("rechazadas_validacion", 0),
                "acc_llm_intentos_rechazados": acc.get("llm_intentos_rechazados", 0),
                "acc_fallbacks": acc.get("fallbacks", 0),
                "acc_ejecutadas_ok": acc.get("ejecutadas_ok", 0),
                "acc_ejecutadas_fallo": acc.get("ejecutadas_fallo", 0),
                "tasa_acciones_validas": round(validas / emitidas, 4) if emitidas else None,
                "fallback_rate": round(acc.get("fallbacks", 0) / emitidas, 4) if emitidas else None,
                "tasa_exec_ok": round(acc.get("ejecutadas_ok", 0) / validas, 4) if validas else None,
                # diversidad de acciones
                "n_tipos_distintos": div["n_tipos_distintos"],
                "entropia_tipos": div["entropia_tipos"],
                "tasa_repeticion_inmediata": div["tasa_repeticion_inmediata"],
                "ratio_bigramas_unicos": div["ratio_bigramas_unicos"],
                # tráfico
                "packets": met.get("packets"),
                "bytes": met.get("bytes"),
                "mbytes": round(met.get("bytes", 0) / 1e6, 2) if met else None,
                "traffic_duration_s": met.get("duration_s"),
                "flows_total": met.get("flows_total"),
                "unique_dst_ips": met.get("unique_dst_ips"),
                "entropy_dst_ips": met.get("entropy_dst_ips"),
                "unique_dns_domains": met.get("unique_dns_domains"),
                "entropy_dns_domains": met.get("entropy_dns_domains"),
                "pkts_tcp": met.get("pkts_tcp"),
                "pkts_udp": met.get("pkts_udp"),
                "pkts_dns": met.get("pkts_dns"),
                "pkts_http": met.get("pkts_http"),
                "pkts_https": met.get("pkts_https"),
                "pkts_quic": met.get("pkts_quic"),
            }
            for grupo in ("flow_duration_s", "flow_bytes", "flow_packets",
                          "packet_size", "packet_iat_s"):
                g = met.get(grupo) or {}
                for stat in ("mean", "median", "p95"):
                    fila[f"{grupo}_{stat}"] = g.get(stat)
            fila["_tipos_counter"] = div["tipos_counter"]  # solo para plots
            filas.append(fila)
    return filas


def _estilo_ejes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(INK_MUTED)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def boxplot_metric(df: pd.DataFrame, col: str, titulo: str, ylabel: str,
                   outpath: Path) -> None:
    datos, etiquetas, colores = [], [], []
    for p in PLANNERS:
        vals = df.loc[(df["planner"] == p) & df[col].notna(), col].astype(float)
        if len(vals):
            datos.append(vals.values)
            etiquetas.append(f"{p}\n(n={len(vals)})")
            colores.append(COLOR[p])
    if not datos:
        return
    fig, ax = plt.subplots(figsize=(5.2, 4), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _estilo_ejes(ax)
    bp = ax.boxplot(datos, labels=etiquetas, patch_artist=True, widths=0.55,
                    medianprops={"color": INK, "linewidth": 1.6},
                    whiskerprops={"color": INK_MUTED, "linewidth": 1.2},
                    capprops={"color": INK_MUTED, "linewidth": 1.2},
                    flierprops={"marker": "o", "markersize": 4,
                                "markerfacecolor": "none",
                                "markeredgecolor": INK_MUTED})
    for caja, color in zip(bp["boxes"], colores):
        caja.set(facecolor=color, alpha=0.45, edgecolor=color, linewidth=1.6)
    # puntos individuales encima (n=10 por grupo: se ven todos los runs)
    for x, (vals, color) in enumerate(zip(datos, colores), start=1):
        ax.scatter([x] * len(vals), vals, s=14, color=color, zorder=3,
                   edgecolors=SURFACE, linewidths=0.6)
    ax.set_title(titulo, color=INK, fontsize=11)
    ax.set_ylabel(ylabel, color=INK_MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(outpath, facecolor=SURFACE)
    plt.close(fig)


def barras_tipos(filas: list[dict], outpath: Path) -> None:
    """Distribución de tipos de acción ejecutados, por planner (proporciones)."""
    todos_tipos = sorted({t for f in filas for t in f["_tipos_counter"]})
    if not todos_tipos:
        return
    fig, ax = plt.subplots(figsize=(7.5, 4), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _estilo_ejes(ax)
    ancho = 0.26
    xs = range(len(todos_tipos))
    for j, p in enumerate(PLANNERS):
        c = Counter()
        for f in filas:
            if f["planner"] == p:
                c.update(f["_tipos_counter"])
        total = sum(c.values()) or 1
        vals = [c.get(t, 0) / total for t in todos_tipos]
        ax.bar([x + (j - 1) * ancho for x in xs], vals, width=ancho - 0.02,
               color=COLOR[p], label=p)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(todos_tipos, rotation=20, ha="right", color=INK_MUTED)
    ax.set_ylabel("proporción de acciones válidas", color=INK_MUTED, fontsize=9)
    ax.set_title("Distribución de tipos de acción por planner", color=INK, fontsize=11)
    leg = ax.legend(frameon=False, fontsize=9)
    for txt in leg.get_texts():
        txt.set_color(INK)
    fig.tight_layout()
    fig.savefig(outpath, facecolor=SURFACE)
    plt.close(fig)


def agregar_actions(out_dir: Path, filas: list[dict], outpath: Path) -> None:
    """Concatena los actions.csv (sin prompts/respuestas, por tamaño)."""
    columnas = ["idx", "ts_iso", "run_id", "planner", "seed", "tipo",
                "params_json", "source", "validada", "motivo_rechazo",
                "ejecutada", "error_ejecucion", "delay_s", "exec_s"]
    with open(outpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            acsv = Path(fila["run_dir"]) / "actions.csv"
            if not acsv.is_file():
                continue
            with open(acsv, encoding="utf-8") as g:
                for r in csv.DictReader(g):
                    w.writerow(r)


def main() -> int:
    parser = argparse.ArgumentParser(description="Análisis Experimento 1")
    parser.add_argument("--out", default=str(_ROOT / "exp1"))
    args = parser.parse_args()
    out_dir = Path(args.out)

    filas = cargar_runs(out_dir)
    if not filas:
        print(f"No hay runs en {out_dir}")
        return 1

    df = pd.DataFrame([{k: v for k, v in f.items() if k != "_tipos_counter"}
                       for f in filas])
    resumen_path = out_dir / "summary_por_sesion.csv"
    df.to_csv(resumen_path, index=False, encoding="utf-8")
    print(f"[OK] {resumen_path} ({len(df)} runs)")

    agregar_actions(out_dir, filas, out_dir / "actions_agregado.csv")
    print(f"[OK] {out_dir / 'actions_agregado.csv'}")

    plots = out_dir / "plots"
    plots.mkdir(exist_ok=True)
    boxplot_metric(df, "flows_total", "Flows por sesión", "nº flows", plots / "box_flows.png")
    boxplot_metric(df, "packets", "Paquetes por sesión", "nº paquetes", plots / "box_packets.png")
    boxplot_metric(df, "mbytes", "Volumen por sesión", "MB capturados", plots / "box_bytes.png")
    boxplot_metric(df, "unique_dst_ips", "Destinos IP únicos por sesión", "nº IPs destino", plots / "box_unique_dst.png")
    boxplot_metric(df, "tasa_acciones_validas", "Tasa de acciones válidas", "válidas / emitidas", plots / "box_valid_rate.png")
    boxplot_metric(df, "fallback_rate", "Tasa de fallback del planner", "fallbacks / emitidas", plots / "box_fallback_rate.png")
    # extras útiles para el análisis del paper
    boxplot_metric(df, "entropia_tipos", "Diversidad de acciones (entropía de tipos)", "bits", plots / "box_entropia_tipos.png")
    boxplot_metric(df, "unique_dns_domains", "Dominios DNS únicos por sesión", "nº dominios", plots / "box_unique_domains.png")
    barras_tipos(filas, plots / "acciones_tipos.png")
    print(f"[OK] gráficas en {plots}")

    # resumen por consola
    print("\n── Resumen por planner (medianas) ──")
    cols = ["flows_total", "packets", "mbytes", "unique_dst_ips",
            "tasa_acciones_validas", "fallback_rate", "entropia_tipos"]
    print(df.groupby("planner")[cols].median(numeric_only=True).to_string())
    fallidos = df[df["status"] != "completed"]
    if len(fallidos):
        print(f"\n⚠️ Runs no completados: {list(fallidos['run_id'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
