# -*- coding: utf-8 -*-
"""
adapt_ids2018.py — Alinea los flujos de CSE-CIC-IDS2018 (CICFlowMeter) con el
esquema de `flow_features.py`, para poder compararlos con el resto de fuentes.

Este es el ÚNICO punto del experimento donde una fuente NO pasa por nuestro
extractor: el CIC no publica los PCAP de forma descargable (solo ZIPs de 38-59 GB)
y el dataset se distribuye ya en features de flujo. Toda la traducción está aquí,
a la vista, y las diferencias de definición se listan en exp2/LIMITACIONES.md.

Correspondencia de columnas (CICFlowMeter -> nuestro esquema):

  Dst Port                                  -> dst_port
  Protocol (6/17)                           -> protocol (TCP/UDP)
  Flow Duration (microsegundos)             -> duration_s      (/1e6)
  Tot Fwd Pkts + Tot Bwd Pkts               -> packets
  TotLen Fwd Pkts + TotLen Bwd Pkts         -> bytes_payload   (*)
  (recalculado) packets / duration_s        -> packets_per_s   (**)
  (recalculado) bytes_payload / duration_s  -> bytes_per_s_payload
  (recalculado) bytes_payload / packets     -> pkt_size_mean_payload
  FIN/SYN/RST/PSH/ACK/URG Flag Cnt          -> *_count
  Dst Port                                  -> service (misma heurística de puertos)

  (*)  CICFlowMeter cuenta SOLO payload L4, no la trama. Por eso nuestro extractor
       emite bytes_payload además de bytes_wire, y el análisis comparativo usa
       bytes_payload en ambos lados. `bytes_wire` queda vacío aquí (no derivable).
  (**) No se usan las columnas Flow Pkts/s y Flow Byts/s del dataset: valen
       Infinity/NaN cuando la duración es 0. Se recalculan con la MISMA regla que
       aplicamos a nuestras fuentes (tasa = 0 si la duración es 0).

  NO disponibles en el CSV: src_ip, dst_ip, src_port -> columnas vacías. En
  consecuencia, "destinos únicos" y "DNS queries" no son computables para esta
  fuente (ver LIMITACIONES.md).

Acotado: se filtra Label == "Benign" y se toma una muestra aleatoria de
--n-muestra flujos con seed fija (por defecto 50.000, seed 2000).

Uso:
  python -m exp2.scripts.adapt_ids2018
  python -m exp2.scripts.adapt_ids2018 --n-muestra 50000 --seed 2000
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from estadisticas4 import heuristic_app_proto  # noqa: E402

from exp2.scripts.flow_features import ESQUEMA_FLOW  # noqa: E402

CSV_IN = _ROOT / "exp2" / "public" / "ids2018_wednesday-14-02-2018.csv"
CSV_OUT = _ROOT / "exp2" / "flows" / "baseline_publico_ids2018.csv"

PROTO = {"6": "TCP", "17": "UDP", "0": "HOPOPT"}


def _num(fila: dict, col: str) -> float:
    try:
        v = float(fila[col])
    except (KeyError, TypeError, ValueError):
        return 0.0
    return v if v == v and abs(v) != float("inf") else 0.0   # descarta NaN/Inf


def adaptar(csv_in: Path, csv_out: Path, n_muestra: int, seed: int) -> dict:
    rng = random.Random(seed)
    reservorio: list[dict] = []          # muestreo por reservorio: una pasada, sin cargar 358 MB
    n_total = n_benign = n_descartados = 0
    etiquetas, protos = Counter(), Counter()

    with csv_in.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for fila in csv.DictReader(fh):
            n_total += 1
            etiqueta = (fila.get("Label") or "").strip()
            # Los CSV de IDS2018 repiten la cabecera a mitad de fichero
            if etiqueta == "Label" or not etiqueta:
                n_descartados += 1
                continue
            etiquetas[etiqueta] += 1
            if etiqueta != "Benign":
                continue

            proto = PROTO.get((fila.get("Protocol") or "").strip(), "")
            if proto not in ("TCP", "UDP"):    # nuestros flujos son TCP/UDP
                n_descartados += 1
                continue

            dur = _num(fila, "Flow Duration") / 1e6          # µs -> s
            pkts = int(_num(fila, "Tot Fwd Pkts") + _num(fila, "Tot Bwd Pkts"))
            bytes_pl = int(_num(fila, "TotLen Fwd Pkts") + _num(fila, "TotLen Bwd Pkts"))
            if pkts <= 0:
                n_descartados += 1
                continue
            dport = int(_num(fila, "Dst Port"))
            n_benign += 1
            protos[proto] += 1

            registro = {
                "source": "baseline_publico_ids2018", "profile": "ids2018_benign",
                "run_id": "wednesday-14-02-2018", "flow_id": f"ids2018_{n_benign}",
                "ip_version": "", "protocol": proto,
                "src_ip": "", "dst_ip": "", "src_port": "", "dst_port": dport,
                "duration_s": round(dur, 6),
                "packets": pkts,
                "bytes_wire": "",                              # no derivable del CSV
                "bytes_payload": bytes_pl,
                "pkt_size_mean_wire": "",
                "pkt_size_mean_payload": round(bytes_pl / pkts, 3),
                "packets_per_s": round(pkts / dur, 6) if dur > 0 else 0.0,
                "bytes_per_s_payload": round(bytes_pl / dur, 6) if dur > 0 else 0.0,
                "fin_count": int(_num(fila, "FIN Flag Cnt")),
                "syn_count": int(_num(fila, "SYN Flag Cnt")),
                "rst_count": int(_num(fila, "RST Flag Cnt")),
                "psh_count": int(_num(fila, "PSH Flag Cnt")),
                "ack_count": int(_num(fila, "ACK Flag Cnt")),
                "urg_count": int(_num(fila, "URG Flag Cnt")),
                "service": heuristic_app_proto(
                    tcp_dport=dport if proto == "TCP" else None,
                    udp_dport=dport if proto == "UDP" else None,
                    tcp_sport=None, udp_sport=None, payload=b""),
            }

            if len(reservorio) < n_muestra:
                reservorio.append(registro)
            else:
                j = rng.randrange(n_benign)
                if j < n_muestra:
                    reservorio[j] = registro

    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ESQUEMA_FLOW)
        w.writeheader()
        w.writerows(reservorio)

    return {
        "csv_origen": csv_in.name,
        "filas_totales": n_total,
        "etiquetas": dict(etiquetas.most_common()),
        "flujos_benign_tcp_udp": n_benign,
        "descartados": n_descartados,
        "protocolos_benign": dict(protos),
        "muestra_escrita": len(reservorio),
        "seed": seed,
        "metodo_muestreo": "reservorio uniforme sobre los flujos Benign TCP/UDP",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Adaptación de CSE-CIC-IDS2018 (exp2)")
    p.add_argument("--csv-in", type=Path, default=CSV_IN)
    p.add_argument("--csv-out", type=Path, default=CSV_OUT)
    p.add_argument("--n-muestra", type=int, default=50_000)
    p.add_argument("--seed", type=int, default=2000)
    args = p.parse_args()

    if not args.csv_in.exists():
        print(f"[ERROR] Falta {args.csv_in}. Ejecuta antes: "
              f"python -m exp2.scripts.fetch_public --solo ids2018")
        return 1

    info = adaptar(args.csv_in, args.csv_out, args.n_muestra, args.seed)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    destino = _ROOT / "exp2" / "aggregated" / "ids2018_adaptacion.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] {info['muestra_escrita']} flujos -> {args.csv_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
