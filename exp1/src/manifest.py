# -*- coding: utf-8 -*-
"""
manifest.py — Provenance por run (Experimento 1).

Cada run tiene un manifest.json con todo lo necesario para reproducirlo y
auditarlo: perfil, planner, run_id, seed, duración, commit hash, entorno,
config de red, config del LLM (si aplica), rutas de artefactos y errores.

El manifest se escribe en varias fases (orquestador → session_runner →
orquestador), por eso hay helpers de carga/actualización con merge superficial.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MANIFEST_NOMBRE = "manifest.json"


def _git(args: list[str], cwd: str) -> str:
    try:
        out = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=15
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def info_git(repo_dir: str) -> dict:
    porcelain = _git(["status", "--porcelain"], repo_dir)
    return {
        "commit_hash": _git(["rev-parse", "HEAD"], repo_dir),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_dir),
        "dirty": bool(porcelain),
        "dirty_files": porcelain.splitlines()[:50] if porcelain else [],
    }


def info_entorno() -> dict:
    return {
        "os": platform.platform(),
        "hostname": socket.gethostname(),
        "python": sys.version.split()[0],
        "maquina": platform.machine(),
    }


def ip_local() -> str:
    """IP local de salida (truco del socket UDP; no envía nada)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def manifest_inicial(
    *,
    perfil: str,
    planner: str,
    run_id: str,
    seed: int,
    duracion_s: int,
    repo_dir: str,
    iface_captura: str,
    pcap_path: str,
) -> dict:
    return {
        "schema_version": 1,
        "experimento": "exp1_planner_comparison",
        "perfil": perfil,
        "planner": planner,
        "run_id": run_id,
        "seed": seed,
        "duracion_solicitada_s": duracion_s,
        "inicio": datetime.now().astimezone().isoformat(),
        "fin": None,
        "duracion_real_s": None,
        "entorno": info_entorno(),
        "git": info_git(repo_dir),
        "red": {
            "iface_captura": iface_captura,
            "ip_local": ip_local(),
        },
        "llm": None,  # lo rellena el session_runner solo si planner == "llm"
        "rutas": {
            "pcap": pcap_path,
            "actions_csv": None,
            "llm_trace": None,
            "session_log": None,
            "metrics_json": None,
        },
        "acciones": None,  # contadores; los rellena el session_runner
        "errores": [],
        "status": "running",
    }


def ruta_manifest(run_dir: str | Path) -> Path:
    return Path(run_dir) / MANIFEST_NOMBRE


def guardar_manifest(run_dir: str | Path, data: dict) -> None:
    path = ruta_manifest(run_dir)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def cargar_manifest(run_dir: str | Path) -> dict | None:
    path = ruta_manifest(run_dir)
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def actualizar_manifest(run_dir: str | Path, **campos) -> dict:
    """Merge superficial de campos sobre el manifest existente (o vacío)."""
    data = cargar_manifest(run_dir) or {}
    for k, v in campos.items():
        if isinstance(v, dict) and isinstance(data.get(k), dict):
            data[k].update(v)
        else:
            data[k] = v
    guardar_manifest(run_dir, data)
    return data
