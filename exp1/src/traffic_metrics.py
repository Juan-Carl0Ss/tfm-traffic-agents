# -*- coding: utf-8 -*-
"""
traffic_metrics.py — Extractor de métricas de tráfico por PCAP (Experimento 1).

Es el MISMO extractor para los tres planners. Reutiliza los helpers de
estadisticas4.py (ts_seconds, heuristic_app_proto, entropía, percentiles,
FlowKey/FlowStats) con el bucle de paquetes correcto (la regresión de
indentación de estadisticas4 se corrigió como parte de este experimento).

Uso como módulo:   from exp1.src.traffic_metrics import extraer_metricas
Uso como script:   python -m exp1.src.traffic_metrics --pcap x.pcap --json-out m.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scapy.all import (  # noqa: E402
    RawPcapReader, Ether, IP, IPv6, TCP, UDP, DNS, ICMP,
)

from estadisticas4 import (  # noqa: E402
    FlowKey, FlowStats, entropy_from_counter, heuristic_app_proto,
    percentile, proto_name, ts_seconds,
)


def _resumen_dist(valores: list[float]) -> dict:
    """mean/mediana/p95/std/min/max de una distribución (0s si vacía)."""
    if not valores:
        return {"n": 0, "mean": 0.0, "median": 0.0, "p95": 0.0, "std": 0.0,
                "min": 0.0, "max": 0.0}
    return {
        "n": len(valores),
        "mean": float(sum(valores) / len(valores)),
        "median": float(statistics.median(valores)),
        "p95": float(percentile(valores, 95)),
        "std": float(statistics.pstdev(valores)) if len(valores) > 1 else 0.0,
        "min": float(min(valores)),
        "max": float(max(valores)),
    }


def extraer_metricas(pcap_path: str | Path, top: int = 20) -> dict:
    """Analiza un PCAP y devuelve el dict de métricas del experimento."""
    pcap_path = str(pcap_path)

    total_pkts = 0
    total_bytes = 0
    sizes: list[int] = []
    packet_ts: list[float] = []
    bad_frames = 0

    ip_proto = Counter()
    app_proto = Counter()
    dst_ips = Counter()
    tcp_dst_ports = Counter()
    udp_dst_ports = Counter()
    dns_queries = Counter()

    flows: dict[FlowKey, FlowStats] = {}
    new_flow_ts: list[float] = []

    # Tolerancia a PCAP truncado: si tshark se detuvo antes de vaciar el último
    # bloque pcapng, scapy lanza al llegar a él. Se procesan todos los paquetes
    # completos y se deja constancia del truncamiento (dato honesto, no se pierde
    # la sesión entera por unos bytes finales).
    truncado = False
    lector = RawPcapReader(pcap_path)
    while True:
        try:
            item = next(lector)
        except StopIteration:
            break
        except Exception as e:
            truncado = True
            print(f"[AVISO] PCAP truncado tras {total_pkts} pkts: {e}")
            break
        pkt_data, md = item
        total_pkts += 1
        ts = ts_seconds(md)
        plen = len(pkt_data)
        if ts > 0:
            packet_ts.append(ts)
        sizes.append(plen)
        total_bytes += plen

        try:
            eth = Ether(pkt_data)
        except Exception:
            bad_frames += 1
            continue

        ipver = src = dst = None
        proto_num = None
        if eth.haslayer(IP):
            ip = eth[IP]
            ipver, src, dst, proto_num = "IPv4", ip.src, ip.dst, ip.proto
        elif eth.haslayer(IPv6):
            ip6 = eth[IPv6]
            ipver, src, dst, proto_num = "IPv6", ip6.src, ip6.dst, ip6.nh

        proto = proto_name(ipver, proto_num)
        ip_proto[proto] += 1

        if not (ipver and src and dst):
            continue
        dst_ips[dst] += 1

        sport = dport = None
        tcp = udp = None
        payload = b""
        if eth.haslayer(TCP):
            tcp = eth[TCP]
            sport, dport = int(tcp.sport), int(tcp.dport)
            tcp_dst_ports[dport] += 1
            payload = bytes(tcp.payload) if tcp.payload else b""
        elif eth.haslayer(UDP):
            udp = eth[UDP]
            sport, dport = int(udp.sport), int(udp.dport)
            udp_dst_ports[dport] += 1
            payload = bytes(udp.payload) if udp.payload else b""

        if eth.haslayer(DNS):
            dns = eth[DNS]
            if getattr(dns, "qr", 1) == 0 and getattr(dns, "qdcount", 0) > 0:
                try:
                    qname = dns.qd.qname.decode("utf-8", errors="ignore").strip(".")
                    dns_queries[qname] += 1
                except Exception:
                    pass

        ap = heuristic_app_proto(
            tcp_dport=dport if tcp is not None else None,
            udp_dport=dport if udp is not None else None,
            tcp_sport=sport if tcp is not None else None,
            udp_sport=sport if udp is not None else None,
            payload=payload,
        )
        app_proto[ap] += 1

        if sport is not None and dport is not None and proto in ("TCP", "UDP"):
            fk = FlowKey(ipver=ipver, src=src, dst=dst, sport=sport, dport=dport, proto=proto)
            fs = flows.get(fk)
            if fs is None:
                flows[fk] = FlowStats(start_ts=ts, end_ts=ts, bytes=plen, packets=1)
                if ts > 0:
                    new_flow_ts.append(ts)
            else:
                if fs.start_ts == 0.0:
                    fs.start_ts = ts
                if ts > 0:
                    fs.end_ts = max(fs.end_ts, ts)
                fs.bytes += plen
                fs.packets += 1

    # ── Derivadas ──
    duracion = (max(packet_ts) - min(packet_ts)) if len(packet_ts) >= 2 else 0.0

    flow_dur, flow_bytes, flow_pkts = [], [], []
    for fs in flows.values():
        d = fs.end_ts - fs.start_ts if (fs.start_ts and fs.end_ts >= fs.start_ts) else 0.0
        flow_dur.append(d)
        flow_bytes.append(fs.bytes)
        flow_pkts.append(fs.packets)

    ts_sorted = sorted(packet_ts)
    pkt_iat = [b - a for a, b in zip(ts_sorted, ts_sorted[1:])]

    dns_domains = Counter()
    for q, n in dns_queries.items():
        partes = q.split(".")
        dns_domains[".".join(partes[-2:]) if len(partes) >= 2 else q] += n

    # Distribución de protocolos de aplicación normalizada a las columnas del paper
    def _app(label_prefixes: tuple[str, ...]) -> int:
        return sum(v for k, v in app_proto.items() if k.startswith(label_prefixes))

    return {
        "pcap": pcap_path,
        "packets": total_pkts,
        "bytes": total_bytes,
        "duration_s": round(duracion, 3),
        "bad_frames": bad_frames,
        "pcap_truncado": truncado,

        "packet_size": _resumen_dist([float(s) for s in sizes]),
        "packet_iat_s": _resumen_dist(pkt_iat),

        "flows_total": len(flows),
        "flow_duration_s": _resumen_dist(flow_dur),
        "flow_bytes": _resumen_dist([float(b) for b in flow_bytes]),
        "flow_packets": _resumen_dist([float(p) for p in flow_pkts]),

        "ip_protocols": dict(ip_proto),
        "pkts_tcp": ip_proto.get("TCP", 0),
        "pkts_udp": ip_proto.get("UDP", 0),
        "pkts_icmp": ip_proto.get("ICMP", 0) + ip_proto.get("ICMPv6", 0),

        "app_protocols": dict(app_proto),
        "pkts_dns": _app(("DNS",)),
        "pkts_http": _app(("HTTP",)) - _app(("HTTPS",)),  # HTTP plano
        "pkts_https": _app(("HTTPS",)),
        "pkts_quic": _app(("QUIC",)),

        "top_tcp_dst_ports": tcp_dst_ports.most_common(top),
        "top_udp_dst_ports": udp_dst_ports.most_common(top),

        "unique_dst_ips": len(dst_ips),
        "entropy_dst_ips": round(entropy_from_counter(dst_ips), 4),
        "unique_dns_domains": len(dns_domains),
        "entropy_dns_domains": round(entropy_from_counter(dns_domains), 4),
        "top_dns_domains": dns_domains.most_common(top),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Métricas de tráfico exp1")
    parser.add_argument("--pcap", required=True)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    metricas = extraer_metricas(args.pcap)
    texto = json.dumps(metricas, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(texto, encoding="utf-8")
        print(f"[OK] Métricas guardadas en {args.json_out}")
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
