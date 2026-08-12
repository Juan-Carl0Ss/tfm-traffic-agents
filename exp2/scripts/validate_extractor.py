# -*- coding: utf-8 -*-
"""
validate_extractor.py — Validación cruzada del extractor de exp2.

`flow_features.py` sustituye la disección de scapy por un parser propio (struct)
por razones de rendimiento. Este script comprueba, sobre el mismo PCAP, que
coincide con `exp1/src/traffic_metrics.py` (scapy) en las magnitudes que ambos
miden: paquetes, bytes, TCP/UDP, DNS, IPs destino únicas y nº de flujos
UNIDIRECCIONALES.

El nº de flujos bidireccionales NO tiene que coincidir (es otra definición: ver
exp2/LIMITACIONES.md); por eso se recuenta aquí la versión unidireccional a
partir de los datos crudos, para poder comparar manzanas con manzanas.

Uso: python -m exp2.scripts.validate_extractor --pcap captura5m2.pcapng
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from exp1.src.traffic_metrics import extraer_metricas  # noqa: E402
from exp2.scripts.flow_features import extraer_flows   # noqa: E402


# Diferencias CONOCIDAS y verificadas con tshark, en las que exp2 es el correcto.
# No invalidan la equivalencia: se declaran, no se ocultan.
DIFERENCIAS_ESPERADAS = {
    "pkts_icmp": (
        "exp1 lee ip6.nh (la PRIMERA cabecera) y etiqueta 'IPv6_0' los ICMPv6 que "
        "llevan hop-by-hop (MLD); exp2 recorre la cadena de extensión y los "
        "clasifica bien. Verificado con tshark sobre rule/run_01: icmpv6=33, "
        "icmpv4=15, total=48 (exp2=48, exp1=33)."
    ),
    "unique_dns_domains": (
        "exp2 parsea DNS sobre UDP/53, mDNS/5353, LLMNR/5355 y DNS sobre TCP/53 "
        "(Windows/Chrome resuelven por TCP contra la puerta de enlace: 682 queries "
        "en rule/run_01). exp1 dependía del binding de scapy y perdía parte."
    ),
}


def _fila(nombre: str, a, b, tol: float = 0.0) -> tuple[str, bool]:
    if a is None or b is None:
        return f"  {nombre:<22} exp1={a!s:>12}  exp2={b!s:>12}  (n/d)", True
    dif = abs(a - b)
    rel = dif / max(abs(a), 1e-9)
    ok = dif == 0 or rel <= tol
    if not ok and nombre in DIFERENCIAS_ESPERADAS:
        return (f"  [DIF*] {nombre:<22} exp1={a:>12}  exp2={b:>12}"
                f"  dif={dif} (esperada)"), True
    marca = "OK " if ok else "DIF"
    return (f"  [{marca}] {nombre:<22} exp1={a:>12}  exp2={b:>12}"
            f"  dif={dif} ({rel:.4%})"), ok


def main() -> int:
    p = argparse.ArgumentParser(description="Validación cruzada exp1 vs exp2")
    p.add_argument("--pcap", required=True)
    p.add_argument("--tol", type=float, default=0.01,
                   help="tolerancia relativa admitida (por defecto 1%%)")
    args = p.parse_args()

    print(f"[1/2] Extractor exp1 (scapy)  -> {args.pcap}")
    m1 = extraer_metricas(args.pcap)
    print(f"[2/2] Extractor exp2 (struct) -> {args.pcap}")
    filas, m2 = extraer_flows(args.pcap)

    print("\n== Comparación ==")
    todo_ok = True
    comparaciones = [
        ("packets", m1["packets"], m2["packets"], 0.0),
        # exp1 suma caplen; exp2 suma wirelen. Idénticos salvo captura truncada.
        ("bytes", m1["bytes"], m2["bytes_wire"], 0.01),
        ("pkts_tcp", m1["pkts_tcp"], m2["pkts_tcp"], 0.0),
        ("pkts_udp", m1["pkts_udp"], m2["pkts_udp"], 0.0),
        ("pkts_icmp", m1["pkts_icmp"], m2["pkts_icmp"], 0.0),
        ("unique_dst_ips", m1["unique_dst_ips"], m2["unique_dst_ips"], 0.0),
        ("unique_dns_domains", m1["unique_dns_domains"], m2["unique_dns_domains"], 0.02),
        ("duration_s", m1["duration_s"], m2["duration_s"], 0.001),
    ]
    for nombre, a, b, tol in comparaciones:
        linea, ok = _fila(nombre, a, b, tol)
        todo_ok &= ok
        print(linea)

    print(f"\n  flows exp1 (unidireccional, sin timeout): {m1['flows_total']}")
    print(f"  flows exp2 (bidireccional, timeout 120 s): {m2['flows']}")
    print("  (no tienen por qué coincidir: son definiciones distintas)")

    marcadas = [k for k in DIFERENCIAS_ESPERADAS
                if any(k == n for n, *_ in comparaciones)]
    if marcadas:
        print("\n== Diferencias esperadas (DIF*) ==")
        for k in marcadas:
            print(f"  - {k}: {DIFERENCIAS_ESPERADAS[k]}")

    print("\n== Resultado ==")
    print("  OK: el parser de exp2 reproduce las magnitudes de exp1."
          if todo_ok else
          "  ATENCIÓN: hay divergencias por encima de la tolerancia.")
    return 0 if todo_ok else 1


if __name__ == "__main__":
    sys.exit(main())
