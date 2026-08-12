# -*- coding: utf-8 -*-
"""
flow_features.py — Extractor de features POR FLUJO (Experimento 2).

Es el MISMO extractor para TODAS las fuentes en PCAP: los tres perfiles propios
(regular/gamer/admin), el baseline interno simple (exp1/random) y el baseline
público en PCAP (CTU-Normal). El baseline público en CSV (CSE-CIC-IDS2018) no
puede pasar por aquí (no hay PCAP disponible) y se alinea en `adapt_ids2018.py`;
las diferencias de definición están en `exp2/LIMITACIONES.md`.

Diferencias respecto a `exp1/src/traffic_metrics.py` (que se deja intacto):

1. Emite UNA FILA POR FLUJO (aquel emite un resumen agregado por PCAP).
2. Flujos **bidireccionales** con **timeout de 120 s**, como CICFlowMeter, para
   que la comparación con el dataset público sea justa. exp1 usaba flujos
   unidireccionales sin timeout (un flujo podía durar toda la sesión).
3. Lee **TCP flags** (FIN/SYN/RST/PSH/ACK/URG) y puerto origen.
4. Contabiliza bytes de DOS formas: `bytes_wire` (trama completa) y
   `bytes_payload` (solo payload L4). CICFlowMeter cuenta payload, así que el
   análisis comparativo usa `bytes_payload` y las tablas descriptivas reportan
   ambos.
5. Parser propio (struct) en vez de la disección completa de scapy: hacen falta
   ~5 M de paquetes y scapy tardaría horas. `validate_extractor.py` comprueba
   que ambos coinciden en paquetes/bytes/flujos sobre el mismo PCAP.

Uso como módulo:  from exp2.scripts.flow_features import extraer_flows
Uso como script:  python -m exp2.scripts.flow_features --pcap x.pcap --csv-out f.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import socket
import struct
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scapy.all import RawPcapReader  # noqa: E402

from estadisticas4 import entropy_from_counter, heuristic_app_proto, ts_seconds  # noqa: E402

# ── Parámetros de definición de flujo (alineados con CICFlowMeter) ──
FLOW_TIMEOUT_S = 120.0   # un paquete >120 s después del inicio abre un flujo nuevo
IDLE_TIMEOUT_S = 120.0   # un hueco >120 s sin paquetes también corta el flujo

# ── Flags TCP ──
FIN, SYN, RST, PSH, ACK, URG = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20

# Resolución de nombres: DNS + mDNS + LLMNR (mismo formato de mensaje)
DNS_PORTS = {53, 5353, 5355}

# ── Link types (DLT) soportados ──
DLT_EN10MB, DLT_RAW_BSD, DLT_RAW, DLT_LINUX_SLL, DLT_LINUX_SLL2 = 1, 12, 101, 113, 276

# Esquema del CSV de flujos. Es el contrato común a todas las fuentes: el
# adaptador del dataset público debe rellenar estas mismas columnas (con vacío
# donde el dataset no las provee).
ESQUEMA_FLOW = [
    "source", "profile", "run_id", "flow_id",
    "ip_version", "protocol", "src_ip", "dst_ip", "src_port", "dst_port",
    "duration_s", "packets", "bytes_wire", "bytes_payload",
    "pkt_size_mean_wire", "pkt_size_mean_payload",
    "packets_per_s", "bytes_per_s_payload",
    "fin_count", "syn_count", "rst_count", "psh_count", "ack_count", "urg_count",
    "service",
]

_ETH = struct.Struct("!12sH")
_TCP_PORTS = struct.Struct("!HH")


@dataclass
class _Flujo:
    """Acumulador de un flujo bidireccional en curso."""
    start_ts: float
    last_ts: float
    ipver: str
    proto: str
    src: bytes           # lado que envía el primer paquete (iniciador)
    dst: bytes
    sport: int
    dport: int
    packets: int = 0
    bytes_wire: int = 0
    bytes_payload: int = 0
    flags: Counter = field(default_factory=Counter)
    fin_fwd: bool = False
    fin_bwd: bool = False
    service: str = ""


def _ip_str(raw: bytes) -> str:
    fam = socket.AF_INET if len(raw) == 4 else socket.AF_INET6
    try:
        return socket.inet_ntop(fam, raw)
    except Exception:
        return raw.hex()


def _parse_l3(data: bytes, off: int) -> tuple | None:
    """(ipver, proto_num, src, dst, l4_off) leyendo la cabecera IP en `off`."""
    if len(data) < off + 20:
        return None
    ver = data[off] >> 4
    if ver == 4:
        ihl = (data[off] & 0x0F) * 4
        if ihl < 20 or len(data) < off + ihl:
            return None
        return "IPv4", data[off + 9], data[off + 12:off + 16], data[off + 16:off + 20], off + ihl
    if ver == 6:
        if len(data) < off + 40:
            return None
        nh = data[off + 6]
        pos = off + 40
        # Cadena de cabeceras de extensión (las habituales; sin criptografía)
        for _ in range(8):
            if nh in (0, 43, 60):            # hop-by-hop, routing, dest-opts
                if len(data) < pos + 8:
                    return None
                nh, pos = data[pos], pos + (data[pos + 1] + 1) * 8
            elif nh == 44:                    # fragment
                if len(data) < pos + 8:
                    return None
                nh, pos = data[pos], pos + 8
            else:
                break
        return "IPv6", nh, data[off + 8:off + 24], data[off + 24:off + 40], pos
    return None


def _parse_frame(data: bytes, linktype: int) -> tuple | None:
    """Devuelve (ipver, proto_num, src, dst, l4_off) o None si no es IP."""
    if linktype == DLT_EN10MB:
        if len(data) < 14:
            return None
        _, etype = _ETH.unpack_from(data, 0)
        off = 14
        while etype in (0x8100, 0x88A8, 0x9100):   # VLAN / QinQ
            if len(data) < off + 4:
                return None
            etype = struct.unpack_from("!H", data, off + 2)[0]
            off += 4
        if etype not in (0x0800, 0x86DD):
            return None
        return _parse_l3(data, off)
    if linktype == DLT_LINUX_SLL:
        return _parse_l3(data, 16) if len(data) >= 16 else None
    if linktype == DLT_LINUX_SLL2:
        return _parse_l3(data, 20) if len(data) >= 20 else None
    if linktype in (DLT_RAW, DLT_RAW_BSD):
        return _parse_l3(data, 0)
    return None


def _dns_qname(payload: bytes, base: int = 0) -> str | None:
    """Nombre consultado de una query DNS (qr=0); None si no lo es.

    `base` es el desplazamiento del mensaje DNS dentro del payload: 0 en UDP y 2
    en TCP (RFC 1035 §4.2.2 antepone la longitud del mensaje en 2 bytes).
    """
    if len(payload) < base + 13:
        return None
    flags, qdcount = struct.unpack_from("!HH", payload, base + 2)
    if (flags >> 15) & 1 or qdcount == 0:      # es respuesta, o sin pregunta
        return None
    labels, pos = [], base + 12
    for _ in range(64):
        if pos >= len(payload):
            return None
        n = payload[pos]
        if n == 0:
            break
        if n & 0xC0:                            # puntero de compresión en la query
            return None
        pos += 1
        if pos + n > len(payload):
            return None
        labels.append(payload[pos:pos + n].decode("utf-8", errors="ignore"))
        pos += n
    return ".".join(labels) if labels else None


def _dns_queries_tcp(payload: bytes) -> list[str]:
    """Queries DNS dentro de un payload TCP/53, sin reensamblar la sesión.

    Aparecen en dos formatos, y ambos ocurren de verdad en las capturas:
      (a) prefijo de longitud (2 B) + mensaje, posiblemente varios encadenados;
      (b) mensaje "pelado", porque el cliente envió el prefijo en el segmento
          ANTERIOR (Windows/Chrome lo hacen con las queries).
    """
    nombres: list[str] = []
    pos = 0
    while pos + 2 <= len(payload):
        msg_len = struct.unpack_from("!H", payload, pos)[0]
        if not (12 <= msg_len <= len(payload) - pos - 2):
            break
        q = _dns_qname(payload, base=pos + 2)
        if q:
            nombres.append(q)
        pos += 2 + msg_len
    if nombres:
        return nombres
    q = _dns_qname(payload, base=0)      # caso (b)
    return [q] if q else []


def extraer_flows(
    pcap_path: str | Path,
    source: str = "",
    profile: str = "",
    run_id: str = "",
    flow_timeout_s: float = FLOW_TIMEOUT_S,
    max_seconds: float = 0.0,
    max_packets: int = 0,
) -> tuple[list[dict], dict]:
    """Analiza un PCAP y devuelve (filas_de_flujo, resumen_de_sesión).

    max_seconds / max_packets acotan la lectura (para muestras y para recortar
    ventanas del dataset público). 0 = sin límite.
    """
    pcap_path = str(pcap_path)

    activos: dict[tuple, _Flujo] = {}
    cerrados: list[_Flujo] = []
    total_pkts = total_bytes = pkts_no_ip = pkts_recortados = 0
    ip_proto, servicios, dst_ips, dns_queries = Counter(), Counter(), Counter(), Counter()
    t0 = t_last = 0.0
    truncado = False

    lector = RawPcapReader(pcap_path)
    lt_global = getattr(lector, "linktype", DLT_EN10MB)

    def _cerrar(k: tuple) -> None:
        cerrados.append(activos.pop(k))

    while True:
        try:
            item = next(lector)
        except StopIteration:
            break
        except Exception as e:   # PCAP truncado (ver exp1/NOTA_errores.md)
            truncado = True
            print(f"[AVISO] PCAP truncado tras {total_pkts} pkts: {e}")
            break

        data, md = item
        ts = ts_seconds(md)
        if t0 == 0.0 and ts > 0:
            t0 = ts
        if max_seconds and ts > 0 and (ts - t0) > max_seconds:
            break

        total_pkts += 1
        wirelen = getattr(md, "wirelen", None) or len(data)
        total_bytes += wirelen
        # Capturas con snaplen (el PCAP público puede traerlo): los bytes que
        # faltan son siempre de payload, porque el recorte es por la cola. Se
        # reconstruye la longitud real para no infraestimar bytes_payload.
        recortado = wirelen - len(data)
        if recortado > 0:
            pkts_recortados += 1
        else:
            recortado = 0
        if ts > 0:
            t_last = ts
        if max_packets and total_pkts >= max_packets:
            break

        l3 = _parse_frame(data, getattr(md, "linktype", None) or lt_global)
        if l3 is None:
            pkts_no_ip += 1
            continue
        ipver, proto_num, src, dst, l4 = l3
        proto = {6: "TCP", 17: "UDP", 1: "ICMP", 58: "ICMPv6"}.get(proto_num, f"IP_{proto_num}")
        ip_proto[proto] += 1
        dst_ips[_ip_str(dst)] += 1

        if proto == "TCP":
            if len(data) < l4 + 20:
                continue
            sport, dport = _TCP_PORTS.unpack_from(data, l4)
            doff = (data[l4 + 12] >> 4) * 4
            flags = data[l4 + 13]
            payload = data[l4 + doff:]
            if 53 in (sport, dport) and payload:
                for q in _dns_queries_tcp(payload):
                    dns_queries[q.strip(".").lower()] += 1
        elif proto == "UDP":
            if len(data) < l4 + 8:
                continue
            sport, dport = _TCP_PORTS.unpack_from(data, l4)
            flags = 0
            payload = data[l4 + 8:]
            if DNS_PORTS & {sport, dport}:      # DNS, mDNS (5353) y LLMNR (5355)
                q = _dns_qname(payload)
                if q:
                    dns_queries[q.strip(".").lower()] += 1
        else:
            continue

        # Clave canónica: independiente del sentido del paquete
        a, b = (src, sport), (dst, dport)
        key = (ipver, proto, a, b) if a <= b else (ipver, proto, b, a)

        f = activos.get(key)
        if f is not None and (
            (ts > 0 and ts - f.start_ts > flow_timeout_s)
            or (ts > 0 and ts - f.last_ts > IDLE_TIMEOUT_S)
        ):
            _cerrar(key)
            f = None
        if f is None:
            f = _Flujo(start_ts=ts, last_ts=ts, ipver=ipver, proto=proto,
                       src=src, dst=dst, sport=sport, dport=dport)
            activos[key] = f

        es_fwd = (src, sport) == (f.src, f.sport)
        f.packets += 1
        f.bytes_wire += wirelen
        f.bytes_payload += len(payload) + recortado
        if ts > 0:
            f.last_ts = max(f.last_ts, ts)
        if not f.service or (f.service == "UNKNOWN" and payload):
            f.service = heuristic_app_proto(
                tcp_dport=f.dport if proto == "TCP" else None,
                udp_dport=f.dport if proto == "UDP" else None,
                tcp_sport=f.sport if proto == "TCP" else None,
                udp_sport=f.sport if proto == "UDP" else None,
                payload=payload,
            )
        if flags:
            for bit, nombre in ((FIN, "fin"), (SYN, "syn"), (RST, "rst"),
                                (PSH, "psh"), (ACK, "ack"), (URG, "urg")):
                if flags & bit:
                    f.flags[nombre] += 1
            # Cierre limpio: RST, o FIN en ambos sentidos (como CICFlowMeter)
            if flags & FIN:
                if es_fwd:
                    f.fin_fwd = True
                else:
                    f.fin_bwd = True
            if (flags & RST) or (f.fin_fwd and f.fin_bwd):
                _cerrar(key)

    cerrados.extend(activos.values())

    filas = []
    for i, f in enumerate(cerrados):
        dur = max(0.0, f.last_ts - f.start_ts) if f.start_ts else 0.0
        # Tasas: 0.0 cuando la duración es 0 (un solo paquete). CICFlowMeter
        # emite infinito en ese caso; se normaliza igual en ambos lados.
        rate_p = (f.packets / dur) if dur > 0 else 0.0
        rate_b = (f.bytes_payload / dur) if dur > 0 else 0.0
        servicios[f.service or "UNKNOWN"] += 1
        filas.append({
            "source": source, "profile": profile, "run_id": run_id,
            "flow_id": f"{run_id}_{i}" if run_id else str(i),
            "ip_version": f.ipver, "protocol": f.proto,
            "src_ip": _ip_str(f.src), "dst_ip": _ip_str(f.dst),
            "src_port": f.sport, "dst_port": f.dport,
            "duration_s": round(dur, 6),
            "packets": f.packets,
            "bytes_wire": f.bytes_wire,
            "bytes_payload": f.bytes_payload,
            "pkt_size_mean_wire": round(f.bytes_wire / f.packets, 3),
            "pkt_size_mean_payload": round(f.bytes_payload / f.packets, 3),
            "packets_per_s": round(rate_p, 6),
            "bytes_per_s_payload": round(rate_b, 6),
            "fin_count": f.flags["fin"], "syn_count": f.flags["syn"],
            "rst_count": f.flags["rst"], "psh_count": f.flags["psh"],
            "ack_count": f.flags["ack"], "urg_count": f.flags["urg"],
            "service": f.service or "UNKNOWN",
        })

    n_tcp, n_udp = ip_proto.get("TCP", 0), ip_proto.get("UDP", 0)
    dominios = Counter()
    for q, n in dns_queries.items():
        partes = q.split(".")
        dominios[".".join(partes[-2:]) if len(partes) >= 2 else q] += n

    resumen = {
        "pcap": pcap_path, "source": source, "profile": profile, "run_id": run_id,
        "packets": total_pkts, "bytes_wire": total_bytes,
        "duration_s": round(t_last - t0, 3) if t_last and t0 else 0.0,
        "pkts_no_ip": pkts_no_ip, "pcap_truncado": truncado,
        "pkts_recortados_snaplen": pkts_recortados,
        "flows": len(filas),
        "pkts_tcp": n_tcp, "pkts_udp": n_udp,
        "ratio_tcp_udp": round(n_tcp / n_udp, 4) if n_udp else None,
        "pkts_icmp": ip_proto.get("ICMP", 0) + ip_proto.get("ICMPv6", 0),
        "dns_queries": sum(dns_queries.values()),
        "unique_dns_domains": len(dominios),
        "entropy_dns_domains": round(entropy_from_counter(dominios), 4),
        "unique_dst_ips": len(dst_ips),
        "entropy_dst_ips": round(entropy_from_counter(dst_ips), 4),
        "servicios": dict(servicios.most_common()),
        "ip_protocols": dict(ip_proto),
    }
    return filas, resumen


def escribir_csv(filas: list[dict], destino: str | Path) -> None:
    """Vuelca filas de flujo al CSV con el esquema común (append-safe)."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ESQUEMA_FLOW)
        w.writeheader()
        w.writerows(filas)


def main() -> int:
    p = argparse.ArgumentParser(description="Features por flujo (exp2)")
    p.add_argument("--pcap", required=True)
    p.add_argument("--csv-out", default="")
    p.add_argument("--resumen-out", default="")
    p.add_argument("--source", default="")
    p.add_argument("--profile", default="")
    p.add_argument("--run-id", default="")
    p.add_argument("--max-seconds", type=float, default=0.0)
    p.add_argument("--max-packets", type=int, default=0)
    args = p.parse_args()

    filas, resumen = extraer_flows(
        args.pcap, source=args.source, profile=args.profile, run_id=args.run_id,
        max_seconds=args.max_seconds, max_packets=args.max_packets,
    )
    if args.csv_out:
        escribir_csv(filas, args.csv_out)
        print(f"[OK] {len(filas)} flujos -> {args.csv_out}")
    if args.resumen_out:
        Path(args.resumen_out).write_text(
            json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] resumen -> {args.resumen_out}")
    if not args.csv_out and not args.resumen_out:
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
