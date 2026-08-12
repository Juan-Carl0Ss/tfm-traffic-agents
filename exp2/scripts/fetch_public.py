# -*- coding: utf-8 -*-
"""
fetch_public.py — Descarga los baselines públicos del Experimento 2 y registra
su procedencia (URL, tamaño, SHA-256, fecha) en exp2/public/procedencia.json.

Dos fuentes, ambas con descarga directa y sin registro (verificado 2026-07-14):

  ctu      Stratosphere CTU-Normal-7 (PCAP, ~417 MB). Captura REAL de un portátil
           Debian con actividad humana (Chrome: Twitter/YouTube, jabber, P2P).
           Se procesa con NUESTRO extractor -> es el baseline público que permite
           afirmar "mismo extractor para todas las fuentes".

  ids2018  CSE-CIC-IDS2018, Wednesday-14-02-2018, CSV de CICFlowMeter (~358 MB),
           alojado por el CIC en AWS Open Data. Se filtra la clase Benign. Viene
           en features de flujo, NO en PCAP: lo alinea `adapt_ids2018.py`.

CIC-IDS2017 se descartó: su servidor (cicresearch.ca) redirige toda descarga
directa al formulario de UNB, así que no es automatizable. Ver DATASET_publico.md.

Uso:
  python -m exp2.scripts.fetch_public              # las dos
  python -m exp2.scripts.fetch_public --solo ctu
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
PUBLIC = _ROOT / "exp2" / "public"

FUENTES = {
    "ctu": {
        "url": "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Normal-7/2013-12-17_capture1.pcap",
        "destino": PUBLIC / "ctu_normal_7.pcap",
        "descripcion": "Stratosphere IPS CTU-Normal-7 (portátil Debian, tráfico normal real)",
    },
    "ids2018": {
        "url": ("https://cse-cic-ids2018.s3.amazonaws.com/Processed%20Traffic%20Data%20for"
                "%20ML%20Algorithms/Wednesday-14-02-2018_TrafficForML_CICFlowMeter.csv"),
        "destino": PUBLIC / "ids2018_wednesday-14-02-2018.csv",
        "descripcion": "CSE-CIC-IDS2018 Wednesday-14-02-2018, flujos CICFlowMeter (clase Benign)",
    },
}


def descargar(url: str, destino: Path) -> dict:
    """Descarga con reanudación y devuelve metadatos de procedencia."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        print(f"[SKIP] {destino.name} ya existe ({destino.stat().st_size:,} B)")
    else:
        tmp = destino.with_suffix(destino.suffix + ".part")
        t0, leidos = time.time(), 0
        req = urllib.request.Request(url, headers={"User-Agent": "tfm-exp2/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r, tmp.open("wb") as fh:
            total = int(r.headers.get("Content-Length", 0))
            while chunk := r.read(1 << 20):
                fh.write(chunk)
                leidos += len(chunk)
                pct = f"{100 * leidos / total:5.1f}%" if total else "  ?  "
                print(f"\r  {destino.name}: {pct} ({leidos / 1e6:8.1f} MB)", end="")
        tmp.rename(destino)
        print(f"\r  {destino.name}: 100.0% ({leidos / 1e6:.1f} MB en {time.time() - t0:.0f}s)")

    h = hashlib.sha256()
    with destino.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return {
        "url": url,
        "fichero": destino.name,
        "bytes": destino.stat().st_size,
        "sha256": h.hexdigest(),
        "descargado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Descarga de baselines públicos (exp2)")
    p.add_argument("--solo", nargs="*", default=list(FUENTES), choices=list(FUENTES))
    args = p.parse_args()

    proc_path = PUBLIC / "procedencia.json"
    proc = json.loads(proc_path.read_text(encoding="utf-8")) if proc_path.exists() else {}

    for clave in args.solo:
        cfg = FUENTES[clave]
        print(f"[{clave}] {cfg['descripcion']}")
        meta = descargar(cfg["url"], cfg["destino"])
        meta["descripcion"] = cfg["descripcion"]
        proc[clave] = meta
        print(f"  sha256={meta['sha256']}")

    proc_path.write_text(json.dumps(proc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] procedencia -> {proc_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
