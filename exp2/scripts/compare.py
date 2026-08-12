# -*- coding: utf-8 -*-
"""
compare.py — Análisis comparativo del Experimento 2.

Lee los CSV de flujos de exp2/flows/ (todas las fuentes, mismo esquema) y produce:

  aggregated/por_perfil_dataset.csv   descriptivos por fuente/perfil y feature
                                      (n, media, mediana, std, IQR, min, max)
  aggregated/distancias.csv           KS (D y p), Jensen-Shannon y Wasserstein
                                      de cada perfil nuestro frente a cada baseline
  aggregated/servicios.csv            distribución de servicios y ratio TCP/UDP
  plots/box_<feature>.png             boxplots por fuente (escala log)
  plots/cdf_<feature>.png             CDFs superpuestas por fuente
  plots/servicios.png                 distribución de servicios por fuente

Notas de interpretación (van también en LIMITACIONES.md):

- Con n de decenas de miles de flujos, el p-valor del KS es ~0 para cualquier
  diferencia mínima. El estadístico D (tamaño del efecto, en [0,1]) es lo que hay
  que leer; el p-valor se reporta por completitud. Se añade `ks_D_submuestra`
  (media de D sobre 20 submuestras de 1.000 flujos por lado, seed fija) para
  comprobar que D es estable y no un artefacto del tamaño muestral.
- Wasserstein se reporta en crudo (unidades de la feature) y normalizado por la
  desviación típica conjunta: las features son de cola pesada y la distancia en
  crudo la domina la escala.
- Jensen-Shannon se calcula sobre histogramas con bordes COMUNES, definidos por
  los cuantiles de la muestra conjunta. Es una distancia en [0,1] (base 2).

Uso: python -m exp2.scripts.compare
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt        # noqa: E402
import numpy as np                     # noqa: E402
import pandas as pd                    # noqa: E402
from scipy.spatial.distance import jensenshannon   # noqa: E402
from scipy.stats import ks_2samp, wasserstein_distance  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
EXP2 = _ROOT / "exp2"

SEED = 2000
N_SUB, N_REP = 1_000, 20      # submuestras para el KS estable

# Fuentes en orden fijo. El color va con la ENTIDAD, no con su posición en el
# gráfico (paleta categórica validada: CVD >= 21 ΔE, ver README).
FUENTES = {
    "ours_regular":              {"etiqueta": "Nuestro · regular",     "color": "#2a78d6"},
    "ours_gamer":                {"etiqueta": "Nuestro · gamer",       "color": "#eda100"},
    "ours_admin":                {"etiqueta": "Nuestro · admin",       "color": "#1baf7a"},
    "baseline_interno":          {"etiqueta": "Baseline planner rnd.", "color": "#e34948"},
    "baseline_script":           {"etiqueta": "Baseline script",       "color": "#e87ba4"},
    "baseline_publico_ctu":      {"etiqueta": "CTU-Normal (PCAP)",     "color": "#4a3aa7"},
    "baseline_publico_ids2018":  {"etiqueta": "CIC-IDS2018 (CSV)",     "color": "#eb6834"},
}
NUESTRAS = ["ours_regular", "ours_gamer", "ours_admin"]
BASELINES = ["baseline_interno", "baseline_script",
             "baseline_publico_ctu", "baseline_publico_ids2018"]

# Features comparables en TODAS las fuentes (incluido el CSV público).
FEATURES = {
    "duration_s":            {"nombre": "Duración del flujo (s)",        "log": True},
    "packets":               {"nombre": "Paquetes por flujo",            "log": True},
    "bytes_payload":         {"nombre": "Bytes por flujo (payload)",     "log": True},
    "pkt_size_mean_payload": {"nombre": "Tamaño medio de paquete (B)",   "log": True},
    "packets_per_s":         {"nombre": "Packet rate (pkt/s)",           "log": True},
    "bytes_per_s_payload":   {"nombre": "Byte rate (B/s)",               "log": True},
    "syn_count":             {"nombre": "TCP SYN por flujo",             "log": False},
    "psh_count":             {"nombre": "TCP PSH por flujo",             "log": True},
    "ack_count":             {"nombre": "TCP ACK por flujo",             "log": True},
    "fin_count":             {"nombre": "TCP FIN por flujo",             "log": False},
    "rst_count":             {"nombre": "TCP RST por flujo",             "log": False},
    "dst_port":              {"nombre": "Puerto destino",                "log": False},
}
# Solo disponibles en las fuentes con PCAP (el CSV de IDS2018 no las trae).
FEATURES_SOLO_PCAP = {
    "bytes_wire":         {"nombre": "Bytes por flujo (trama)", "log": True},
    "pkt_size_mean_wire": {"nombre": "Tamaño medio trama (B)",  "log": True},
    "src_port":           {"nombre": "Puerto origen",           "log": False},
}


def cargar() -> dict[str, pd.DataFrame]:
    datos = {}
    for src in FUENTES:
        f = EXP2 / "flows" / f"{src}.csv"
        if not f.exists():
            print(f"[AVISO] falta {f.name}: la fuente se omite del análisis")
            continue
        datos[src] = pd.read_csv(f)
        print(f"[OK] {src:<26} {len(datos[src]):>7} flujos")
    return datos


# ── Descriptivos ──
def descriptivos(datos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    filas = []
    todas = {**FEATURES, **FEATURES_SOLO_PCAP}
    for src, df in datos.items():
        n_runs = df["run_id"].nunique()
        for feat, cfg in todas.items():
            if feat not in df.columns:
                continue
            s = pd.to_numeric(df[feat], errors="coerce").dropna()
            if s.empty:
                continue
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            filas.append({
                "fuente": src, "perfil": df["profile"].iloc[0], "feature": feat,
                "n_runs": n_runs, "n_flows": int(s.size),
                "media": s.mean(), "mediana": s.median(), "std": s.std(),
                "p25": q1, "p75": q3, "iqr": q3 - q1,
                "min": s.min(), "max": s.max(),
            })
    return pd.DataFrame(filas)


# ── Distancias ──
def _js(a: np.ndarray, b: np.ndarray, bins: int = 64) -> float:
    """Jensen-Shannon (base 2) sobre histogramas con bordes comunes por cuantiles."""
    pool = np.concatenate([a, b])
    bordes = np.unique(np.quantile(pool, np.linspace(0, 1, bins + 1)))
    if bordes.size < 3:
        return 0.0
    pa, _ = np.histogram(a, bins=bordes)
    pb, _ = np.histogram(b, bins=bordes)
    eps = 1e-12
    return float(jensenshannon(pa + eps, pb + eps, base=2))


def _ks_submuestra(a: np.ndarray, b: np.ndarray) -> float:
    """D medio del KS sobre N_REP submuestras de N_SUB por lado (D es sensible a n)."""
    rng = np.random.default_rng(SEED)
    n = min(N_SUB, a.size, b.size)
    if n < 50:
        return float("nan")
    ds = [ks_2samp(rng.choice(a, n, replace=False),
                   rng.choice(b, n, replace=False), method="asymp").statistic
          for _ in range(N_REP)]
    return float(np.mean(ds))


def distancias(datos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    filas = []
    for src in NUESTRAS:
        if src not in datos:
            continue
        for base in BASELINES:
            if base not in datos:
                continue
            for feat, cfg in FEATURES.items():
                a = pd.to_numeric(datos[src][feat], errors="coerce").dropna().to_numpy()
                b = pd.to_numeric(datos[base][feat], errors="coerce").dropna().to_numpy()
                if a.size < 10 or b.size < 10:
                    continue
                ks = ks_2samp(a, b)
                w = wasserstein_distance(a, b)
                std_pool = np.std(np.concatenate([a, b])) or 1.0
                filas.append({
                    "fuente": src, "baseline": base, "feature": feat,
                    "n_fuente": int(a.size), "n_baseline": int(b.size),
                    "ks_D": ks.statistic, "ks_p": ks.pvalue,
                    "ks_D_submuestra": _ks_submuestra(a, b),
                    "js_distance": _js(a, b),
                    "wasserstein": w,
                    "wasserstein_norm": w / std_pool,
                    "mediana_fuente": float(np.median(a)),
                    "mediana_baseline": float(np.median(b)),
                })
    return pd.DataFrame(filas)


# ── Servicios / protocolos ──
def servicios(datos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    filas = []
    for src, df in datos.items():
        n = len(df)
        tcp = int((df["protocol"] == "TCP").sum())
        udp = int((df["protocol"] == "UDP").sum())
        for serv, cnt in df["service"].value_counts().items():
            filas.append({
                "fuente": src, "perfil": df["profile"].iloc[0],
                "servicio": serv, "flows": int(cnt), "share": cnt / n,
                "n_flows_fuente": n,
                "flows_tcp": tcp, "flows_udp": udp,
                "ratio_tcp_udp": round(tcp / udp, 4) if udp else None,
            })
    return pd.DataFrame(filas)


# ── Gráficas ──
def _estilo(ax) -> None:
    ax.set_facecolor("#fcfcfb")
    ax.grid(axis="y", color="#e1e0d9", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#898781")
    ax.tick_params(colors="#52514e", labelsize=9)


def graficas(datos: dict[str, pd.DataFrame]) -> None:
    destino = EXP2 / "plots"
    destino.mkdir(parents=True, exist_ok=True)
    presentes = [s for s in FUENTES if s in datos]
    todas = {**FEATURES, **FEATURES_SOLO_PCAP}

    for feat, cfg in todas.items():
        series, etiquetas, colores = [], [], []
        for src in presentes:
            s = pd.to_numeric(datos[src].get(feat), errors="coerce")
            s = s.dropna() if s is not None else pd.Series(dtype=float)
            if s.empty:
                continue
            v = s.to_numpy()
            if cfg["log"]:
                # Un eje log no puede representar el 0 (flujos sin payload, de un
                # solo paquete...). Se excluyen del DIBUJO y se declara cuántos
                # son; las tablas y las distancias sí los incluyen.
                pos = v[v > 0]
                cero = 100 * (v.size - pos.size) / v.size
                series.append(pos)
                etiquetas.append(f"{FUENTES[src]['etiqueta']}\n(n={pos.size:,}"
                                 f" · {cero:.0f}% en 0)".replace(",", "."))
            else:
                series.append(v)
                etiquetas.append(f"{FUENTES[src]['etiqueta']}\n(n={v.size:,})".replace(",", "."))
            colores.append(FUENTES[src]["color"])
        series = [s for s in series if s.size]
        if len(series) < 2:
            continue

        # Boxplot: la forma para comparar magnitud y dispersión entre grupos.
        fig, ax = plt.subplots(figsize=(9, 4.6), facecolor="#fcfcfb")
        bp = ax.boxplot(series, patch_artist=True, showfliers=False,
                        widths=0.55, medianprops=dict(color="#0b0b0b", linewidth=1.6),
                        whiskerprops=dict(color="#898781"),
                        capprops=dict(color="#898781"),
                        boxprops=dict(linewidth=0))
        for caja, color in zip(bp["boxes"], colores):
            caja.set_facecolor(color)
            caja.set_edgecolor("#fcfcfb")       # separador de 2 px entre rellenos
            caja.set_linewidth(2)
        if cfg["log"]:
            ax.set_yscale("log")
        ax.set_xticklabels(etiquetas, fontsize=8)
        ax.set_ylabel(cfg["nombre"], color="#52514e", fontsize=10)
        ax.set_title(f"{cfg['nombre']} por fuente" + ("  ·  escala log" if cfg["log"] else ""),
                     color="#0b0b0b", fontsize=12, loc="left", pad=12)
        _estilo(ax)
        nota = "cajas: IQR · línea: mediana · sin outliers"
        if cfg["log"]:
            nota += " · los flujos con valor 0 no son representables en log"
        fig.tight_layout(rect=(0, 0.05, 1, 1))
        fig.text(0.99, 0.015, nota, ha="right", color="#898781", fontsize=8)
        fig.savefig(destino / f"box_{feat}.png", dpi=150)
        plt.close(fig)

        # CDF: permite leer la distribución completa, no solo los cuartiles.
        fig, ax = plt.subplots(figsize=(8, 4.6), facecolor="#fcfcfb")
        for s, etiqueta, color in zip(series, etiquetas, colores):
            x = np.sort(s)
            y = np.arange(1, x.size + 1) / x.size
            ax.plot(x, y, color=color, linewidth=2, label=etiqueta.split("\n")[0])
        if cfg["log"]:
            ax.set_xscale("log")
        ax.set_xlabel(cfg["nombre"], color="#52514e", fontsize=10)
        ax.set_ylabel("F(x)", color="#52514e", fontsize=10)
        ax.set_ylim(0, 1.02)
        ax.set_title(f"CDF · {cfg['nombre']}", color="#0b0b0b", fontsize=12, loc="left", pad=12)
        _estilo(ax)
        ax.grid(axis="x", color="#e1e0d9", linewidth=0.8)
        ax.legend(frameon=False, fontsize=8, labelcolor="#52514e", loc="lower right")
        fig.tight_layout()
        fig.savefig(destino / f"cdf_{feat}.png", dpi=150)
        plt.close(fig)

    # Distribución de servicios: barras agrupadas por servicio.
    df_s = servicios(datos)
    top = (df_s.groupby("servicio")["flows"].sum().sort_values(ascending=False).head(7).index)
    fig, ax = plt.subplots(figsize=(10, 4.8), facecolor="#fcfcfb")
    ancho = 0.8 / len(presentes)
    x = np.arange(len(top))
    for i, src in enumerate(presentes):
        sub = df_s[df_s["fuente"] == src].set_index("servicio")["share"]
        vals = [100 * sub.get(s, 0.0) for s in top]
        ax.bar(x + i * ancho, vals, ancho * 0.88, label=FUENTES[src]["etiqueta"],
               color=FUENTES[src]["color"], edgecolor="#fcfcfb", linewidth=2, zorder=3)
    ax.set_xticks(x + 0.4 - ancho / 2)
    ax.set_xticklabels(top, fontsize=9)
    ax.set_ylabel("% de flujos de la fuente", color="#52514e", fontsize=10)
    ax.set_title("Distribución de servicios por fuente", color="#0b0b0b",
                 fontsize=12, loc="left", pad=12)
    _estilo(ax)
    ax.legend(frameon=False, fontsize=8, labelcolor="#52514e", ncols=2)
    fig.tight_layout()
    fig.savefig(destino / "servicios.png", dpi=150)
    plt.close(fig)
    print(f"[OK] gráficas -> {destino}")


def main() -> int:
    argparse.ArgumentParser(description="Análisis comparativo exp2").parse_args()
    datos = cargar()
    if len(datos) < 2:
        print("[ERROR] hacen falta al menos 2 fuentes.")
        return 1

    agg = EXP2 / "aggregated"
    agg.mkdir(parents=True, exist_ok=True)

    desc = descriptivos(datos)
    desc.to_csv(agg / "por_perfil_dataset.csv", index=False, encoding="utf-8")
    print(f"[OK] descriptivos -> {agg / 'por_perfil_dataset.csv'} ({len(desc)} filas)")

    dist = distancias(datos)
    dist.to_csv(agg / "distancias.csv", index=False, encoding="utf-8")
    print(f"[OK] distancias   -> {agg / 'distancias.csv'} ({len(dist)} filas)")

    serv = servicios(datos)
    serv.to_csv(agg / "servicios.csv", index=False, encoding="utf-8")
    print(f"[OK] servicios    -> {agg / 'servicios.csv'} ({len(serv)} filas)")

    graficas(datos)

    # Resumen legible: ¿nos separamos más del baseline interno o del público?
    if not dist.empty:
        print("\n== KS D medio por (fuente, baseline) ==")
        piv = dist.pivot_table(index="fuente", columns="baseline",
                               values="ks_D", aggfunc="mean").round(3)
        print(piv.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
