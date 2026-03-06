# ======================== USO DEL SCRIPT ========================
# Ejecución básica:
#   python pcap_stats.py captura.pcap
#
# Mostrar más elementos en las estadísticas (Top N):
#   python pcap_stats.py captura.pcap --top 20
#
# Generar resumen en formato JSON:
#   python pcap_stats.py captura.pcap --json resumen.json
#
# Generar gráficos (PNG) de las estadísticas:
#   python pcap_stats.py captura.pcap --plots
#
# Especificar directorio de salida de los gráficos:
#   python pcap_stats.py captura.pcap --plots --outdir graficas_resultados
#
# Ejecutar en servidores sin entorno gráfico (solo guardar gráficas):
#   python pcap_stats.py captura.pcap --plots --no-show
#
# Ejecución completa (JSON + gráficas + Top personalizado):
#   python pcap_stats.py captura.pcap --top 15 --json resultados.json --plots --outdir salidas_graficas --no-show
# ================================================================

# pcap_stats.py
import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional, Tuple

# --- Evita problemas en servidores sin display (no es necesario en Windows, pero no molesta)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from scapy.all import (
    RawPcapReader, Ether, IP, IPv6, TCP, UDP, DNS,
    ICMP, ICMPv6EchoRequest, ICMPv6EchoReply
)

# ======================== Utilidades ========================

def human_bytes(n: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"

def ts_seconds(md) -> float:
    """
    Convierte el metadata de RawPcapReader (pcap o pcapng) a segundos (float).
    - En PCAP suele haber sec/usec
    - En PCAPNG puede venir sec/nsec (o sec/usec)
    """
    if isinstance(md, (int, float)):
        return float(md)

    sec = getattr(md, "sec", None)
    if sec is not None:
        if hasattr(md, "usec") and md.usec is not None:
            return sec + (md.usec / 1e6)
        if hasattr(md, "nsec") and md.nsec is not None:
            return sec + (md.nsec / 1e9)
        return float(sec)

    t = getattr(md, "time", None)
    if t is not None:
        return float(t)

    return 0.0

def proto_name(ipver: Optional[str], proto_num: Optional[int]) -> str:
    if ipver == 'IPv4':
        mapping = {1: 'ICMP', 6: 'TCP', 17: 'UDP'}
        return mapping.get(proto_num, str(proto_num))
    if ipver == 'IPv6':
        mapping = {58: 'ICMPv6', 6: 'TCP', 17: 'UDP'}
        return mapping.get(proto_num, str(proto_num))
    return 'N/A'

def tcp_flags_str(t: TCP) -> str:
    flags = []
    if t.flags & 0x02: flags.append('SYN')
    if t.flags & 0x10: flags.append('ACK')
    if t.flags & 0x04: flags.append('RST')
    if t.flags & 0x01: flags.append('FIN')
    if t.flags & 0x08: flags.append('PSH')
    if t.flags & 0x20: flags.append('URG')
    return '+'.join(flags) if flags else 'NONE'

def ensure_outdir(path: str):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def plot_bar(counter: Counter, title: str, xlabel: str, outpath: Optional[str], topn: int, show: bool):
    items = counter.most_common(topn)
    if not items:
        return
    labels = [str(k) for k, _ in items]
    values = [v for _, v in items]

    plt.figure()
    plt.bar(range(len(values)), values)
    plt.xticks(range(len(labels)), labels, rotation=45, ha='right')
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("Conteo")
    plt.tight_layout()
    if outpath:
        plt.savefig(outpath, dpi=150)
    if show:
        plt.show()
    plt.close()

def plot_time_series(times: list, values: list, title: str, xlabel: str, ylabel: str,
                     outpath: Optional[str], show: bool):
    if not times or not values:
        return
    plt.figure()
    plt.plot(times, values)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    if outpath:
        plt.savefig(outpath, dpi=150)
    if show:
        plt.show()
    plt.close()

# ======================== Lógica principal ========================

def main():
    ap = argparse.ArgumentParser(description="Estadísticas y gráficos de un PCAP/PCAPNG (streaming con RawPcapReader)")
    ap.add_argument("pcap", help="Ruta al archivo .pcap o .pcapng")
    ap.add_argument("--top", type=int, default=10, help="Top N elementos a mostrar (default 10)")
    ap.add_argument("--json", dest="json_out", help="Ruta para guardar resumen JSON")
    ap.add_argument("--plots", action="store_true", help="Genera gráficos (PNG)")
    ap.add_argument("--outdir", default="pcap_plots", help="Carpeta para guardar gráficos (default: pcap_plots)")
    ap.add_argument("--no-show", action="store_true", help="No mostrar ventanas de gráficos (solo guardar PNG)")
    args = ap.parse_args()

    show_plots = args.plots and not args.no_show
    if args.plots:
        ensure_outdir(args.outdir)

    total_pkts = 0
    total_bytes = 0
    first_ts = None
    last_ts = None

    # Contadores
    eth_types = Counter()
    ip_versions = Counter()
    ip_proto = Counter()
    src_ips = Counter()
    dst_ips = Counter()
    pairs = Counter()
    flows = Counter()  # 5-tuplas (dirigidas)
    tcp_src_ports = Counter()
    tcp_dst_ports = Counter()
    udp_src_ports = Counter()
    udp_dst_ports = Counter()
    tcp_flag_counts = Counter()
    dns_queries = Counter()
    icmp_counts = Counter()
    sizes = []

    # Serie temporal de bytes/segundo
    # guardamos un bucket por segundo relativo al inicio
    bytes_per_second = Counter()

    # Errores de parseo
    bad_frames = 0

    for (raw_pkt, md) in RawPcapReader(args.pcap):
        ts = ts_seconds(md)
        total_pkts += 1
        plen = len(raw_pkt)
        total_bytes += plen
        sizes.append(plen)

        if first_ts is None:
            first_ts = ts
        last_ts = ts

        # Buckets por segundo para throughput
        sec_bucket = int(ts - first_ts) if first_ts is not None else 0
        bytes_per_second[sec_bucket] += plen

        try:
            eth = Ether(raw_pkt)
        except Exception:
            bad_frames += 1
            continue

        eth_types[hex(eth.type)] += 1

        # IP/IPv6/parsing
        ipver = None
        prnum = None
        s_ip = d_ip = None

        if IP in eth:
            ip = eth[IP]
            ipver = 'IPv4'
            prnum = ip.proto
            s_ip = ip.src
            d_ip = ip.dst
        elif IPv6 in eth:
            ip6 = eth[IPv6]
            ipver = 'IPv6'
            prnum = ip6.nh
            s_ip = ip6.src
            d_ip = ip6.dst

        if ipver:
            ip_versions[ipver] += 1
            pname = proto_name(ipver, prnum)
            ip_proto[pname] += 1
            if s_ip: src_ips[s_ip] += 1
            if d_ip: dst_ips[d_ip] += 1
            if s_ip and d_ip:
                pairs[(s_ip, d_ip)] += 1

        # TCP / UDP / Flows
        if TCP in eth:
            t = eth[TCP]
            sport, dport = t.sport, t.dport
            tcp_src_ports[sport] += 1
            tcp_dst_ports[dport] += 1
            tcp_flag_counts[tcp_flags_str(t)] += 1

            if s_ip and d_ip:
                flows[(ipver, s_ip, d_ip, 'TCP', sport, dport)] += 1

        elif UDP in eth:
            u = eth[UDP]
            sport, dport = u.sport, u.dport
            udp_src_ports[sport] += 1
            udp_dst_ports[dport] += 1
            if s_ip and d_ip:
                flows[(ipver, s_ip, d_ip, 'UDP', sport, dport)] += 1

        # DNS
        if DNS in eth and (UDP in eth or TCP in eth):
            d = eth[DNS]
            if getattr(d, "qr", 0) == 0 and d.qd is not None:
                try:
                    qname = d.qd.qname.decode() if isinstance(d.qd.qname, (bytes, bytearray)) else str(d.qd.qname)
                except Exception:
                    qname = str(d.qd.qname)
                qname = qname.rstrip('.')
                dns_queries[qname] += 1

        # ICMP/ICMPv6
        if ICMP in eth:
            icmp = eth[ICMP]
            icmp_counts[f"ICMP {icmp.type}/{icmp.code}"] += 1
        if ICMPv6EchoRequest in eth or ICMPv6EchoReply in eth:
            if ICMPv6EchoRequest in eth:
                icmp_counts["ICMPv6 Echo Request"] += 1
            if ICMPv6EchoReply in eth:
                icmp_counts["ICMPv6 Echo Reply"] += 1

    duration = 0.0
    if first_ts is not None and last_ts is not None:
        duration = max(0.0, last_ts - first_ts)
    bps = (total_bytes * 8 / duration) if duration > 0 else 0.0

    # ======================== Salida en consola ========================
    print("="*70)
    print("RESUMEN DEL PCAP")
    print("="*70)
    try:
        start_dt = datetime.fromtimestamp(first_ts) if first_ts else None
        end_dt = datetime.fromtimestamp(last_ts) if last_ts else None
    except (OverflowError, OSError, ValueError):
        start_dt = end_dt = None

    if start_dt and end_dt:
        print(f"Inicio captura: {start_dt} | Fin: {end_dt} | Duración: {duration:.3f} s")
    else:
        print(f"Duración (s): {duration:.3f}")

    if sizes:
        avg_sz = sum(sizes)/len(sizes)
        print(f"Paquetes: {total_pkts:,} | Tamaño total: {human_bytes(total_bytes)} | Media pqt: {avg_sz:.1f} B")
    else:
        print(f"Paquetes: {total_pkts:,} | Tamaño total: {human_bytes(total_bytes)}")

    print(f"Throughput aprox.: {bps/1e6:.3f} Mbps")
    if bad_frames:
        print(f"Paquetes no parseados: {bad_frames}")
    print()

    def show_counter(title, counter, topn):
        print(f"--- {title} (Top {topn}) ---")
        for item, cnt in counter.most_common(topn):
            print(f"{str(item):>25} : {cnt:,}")
        print()

    show_counter("EtherTypes", eth_types, args.top)
    show_counter("Versiones IP", ip_versions, args.top)
    show_counter("Protocolos IP", ip_proto, args.top)
    show_counter("IPs de origen", src_ips, args.top)
    show_counter("IPs de destino", dst_ips, args.top)

    print(f"--- Pares IP (Top {args.top}) ---")
    for (sip, dip), cnt in pairs.most_common(args.top):
        print(f"{sip} -> {dip:>15} : {cnt:,}")
    print()

    show_counter("Puertos TCP origen", tcp_src_ports, args.top)
    show_counter("Puertos TCP destino", tcp_dst_ports, args.top)
    show_counter("Puertos UDP origen", udp_src_ports, args.top)
    show_counter("Puertos UDP destino", udp_dst_ports, args.top)
    show_counter("Flags TCP", tcp_flag_counts, args.top)
    show_counter("Consultas DNS", dns_queries, args.top)
    show_counter("ICMP/ICMPv6", icmp_counts, args.top)

    # ======================== Resumen JSON opcional ========================
    if args.json_out:
        out = {
            "packets": total_pkts,
            "bytes": total_bytes,
            "duration_seconds": duration,
            "throughput_bps": bps,
            "start_ts": first_ts,
            "end_ts": last_ts,
            "avg_packet_size": (sum(sizes)/len(sizes)) if sizes else 0,
            "eth_types": eth_types.most_common(args.top),
            "ip_versions": ip_versions.most_common(args.top),
            "ip_protocols": ip_proto.most_common(args.top),
            "top_src_ips": src_ips.most_common(args.top),
            "top_dst_ips": dst_ips.most_common(args.top),
            "top_ip_pairs": [ (f"{a}->{b}", c) for (a,b),c in pairs.most_common(args.top) ],
            "top_tcp_src_ports": tcp_src_ports.most_common(args.top),
            "top_tcp_dst_ports": tcp_dst_ports.most_common(args.top),
            "top_udp_src_ports": udp_src_ports.most_common(args.top),
            "top_udp_dst_ports": udp_dst_ports.most_common(args.top),
            "tcp_flags": tcp_flag_counts.most_common(args.top),
            "dns_queries": dns_queries.most_common(args.top),
            "icmp": icmp_counts.most_common(args.top),
            "bad_frames": bad_frames
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"Resumen JSON guardado en: {args.json_out}")

    # ======================== Gráficos ========================
    if args.plots:
        # Barras: protocolos/IPs/puertos
        plot_bar(ip_proto, "Protocolos IP (Top)", "Protocolo",
                 os.path.join(args.outdir, "top_protocolos.png"), args.top, show_plots)
        plot_bar(src_ips, "IPs de origen (Top)", "IP origen",
                 os.path.join(args.outdir, "top_src_ips.png"), args.top, show_plots)
        plot_bar(dst_ips, "IPs de destino (Top)", "IP destino",
                 os.path.join(args.outdir, "top_dst_ips.png"), args.top, show_plots)
        plot_bar(tcp_dst_ports, "Puertos TCP destino (Top)", "Puerto TCP dst",
                 os.path.join(args.outdir, "top_tcp_dst_ports.png"), args.top, show_plots)
        plot_bar(udp_dst_ports, "Puertos UDP destino (Top)", "Puerto UDP dst",
                 os.path.join(args.outdir, "top_udp_dst_ports.png"), args.top, show_plots)
        plot_bar(tcp_flag_counts, "Flags TCP (Top)", "Flags",
                 os.path.join(args.outdir, "top_tcp_flags.png"), args.top, show_plots)

        # Serie temporal: throughput (Mbps) por segundo
        if bytes_per_second:
            times = sorted(bytes_per_second.keys())
            values_bps = [bytes_per_second[t] * 8 / 1e6 for t in times]  # Mbps
            plot_time_series(times, values_bps, "Throughput por segundo", "Segundos desde inicio", "Mbps",
                             os.path.join(args.outdir, "throughput_por_segundo.png"), show_plots)

        print(f"Gráficos guardados en: {os.path.abspath(args.outdir)}")

if __name__ == "__main__":
    main()
