# -*- coding: utf-8 -*-
"""
orchestrate.py — Orquestador del Experimento 1 (LLM vs Random vs Rule).

Lanza N runs por planner (por defecto 10) de forma SECUENCIAL (una NIC y un
Chrome: nunca se solapan runs) e INTERCALADA por índice de run (llm, random,
rule, llm, ...) para repartir posibles efectos temporales (hora del día, carga
de red) entre las tres variantes.

Por cada run:
  1. crea exp1/<planner>/run_XX/ y el manifest inicial (seed, commit, red...)
  2. arranca tshark (reutiliza captura_combinada.iniciar_tshark)
  3. lanza session_runner como subproceso (stdout+stderr → session.log)
  4. espera con timeout duro (duración + margen); si cuelga, mata el árbol
  5. para tshark, extrae métricas del PCAP → metrics.json
  6. marca el manifest como completed/failed

Idempotente: los runs con manifest status=completed se saltan (--force repite).

Uso:
  python -m exp1.src.orchestrate --smoke              # 1 run × planner, 120 s
  python -m exp1.src.orchestrate --runs 10 --duration 300
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import captura_combinada  # noqa: E402  (reutiliza tshark helpers)
from exp1.src.manifest import (  # noqa: E402
    actualizar_manifest, cargar_manifest, guardar_manifest, manifest_inicial,
)
from exp1.src.traffic_metrics import extraer_metricas  # noqa: E402

PERFIL = "regular_user"
MARGEN_TIMEOUT_S = 240   # margen sobre la duración para matar sesiones colgadas
PAUSA_ENTRE_RUNS_S = 10  # deja cerrar conexiones TIME_WAIT entre runs

_LOG_PATH: Path | None = None


def _guid_ruta_por_defecto() -> str:
    """GUID del adaptador con la ruta por defecto (0.0.0.0/0), vía PowerShell.
    Devuelve '' si no se puede determinar (p.ej. no-Windows)."""
    ps = (
        "$i=(Get-NetRoute -DestinationPrefix 0.0.0.0/0 | "
        "Sort-Object RouteMetric | Select-Object -First 1).InterfaceIndex; "
        "(Get-NetAdapter -InterfaceIndex $i).InterfaceGuid"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip()
    except Exception:
        return ""


def detectar_iface_activa() -> str:
    """Interfaz tshark cuya GUID coincide con la ruta por defecto (la que lleva
    tráfico real). Cae en captura_combinada._autodetect_iface() si no hay match.

    Corrige el fallo observado en el smoke: el autodetect genérico elegía el
    primer adaptador no-loopback (uno virtual sin tráfico) → PCAP vacío."""
    guid = _guid_ruta_por_defecto()
    if guid:
        try:
            r = subprocess.run([captura_combinada.TSHARK, "-D"],
                              capture_output=True, text=True, timeout=15)
            for line in r.stdout.splitlines():
                if guid.lower() in line.lower():
                    idx = line.split(".")[0].strip()
                    if idx.isdigit():
                        log(f"Interfaz activa detectada por ruta por defecto: {line.strip()}")
                        return idx
        except Exception as e:
            log(f"AVISO: no se pudo mapear GUID→tshark: {e}")
    log("AVISO: usando autodetección genérica de interfaz (puede fallar)")
    return captura_combinada._autodetect_iface()


def log(msg: str) -> None:
    linea = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(linea, flush=True)
    if _LOG_PATH is not None:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(linea + "\n")


def _matar_arbol(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                   capture_output=True)


def ejecutar_run(planner: str, i: int, seed: int, duracion: int,
                 out_dir: Path, force: bool) -> str:
    """Ejecuta un run completo. Devuelve 'completed' | 'failed' | 'skipped'."""
    run_dir = out_dir / planner / f"run_{i:02d}"
    existente = cargar_manifest(run_dir)
    if existente and existente.get("status") == "completed" and not force:
        log(f"[{planner} run_{i:02d}] ya completado — se salta (usa --force para repetir)")
        return "skipped"

    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{planner}_run{i:02d}"
    pcap_path = run_dir / "capture.pcap"
    session_log = run_dir / "session.log"

    # captura_combinada.IFACE_WINDOWS se fija una vez en main() y es la misma
    # interfaz para los 30 runs (constante entre variantes).
    iface = captura_combinada.IFACE_WINDOWS

    guardar_manifest(run_dir, manifest_inicial(
        perfil=PERFIL, planner=planner, run_id=run_id, seed=seed,
        duracion_s=duracion, repo_dir=str(_ROOT), iface_captura=str(iface),
        pcap_path=str(pcap_path),
    ))

    log(f"[{run_id}] seed={seed} dur={duracion}s → {run_dir}")

    # 1. Captura
    proc_tshark = captura_combinada.iniciar_tshark(str(pcap_path))
    if proc_tshark is None:
        actualizar_manifest(run_dir, status="failed",
                            errores=["tshark no arrancó (¿permisos/Npcap?)"])
        return "failed"
    time.sleep(2)

    # 2. Sesión del agente
    exit_code: int | None = None
    try:
        with open(session_log, "w", encoding="utf-8") as slog:
            p = subprocess.Popen(
                [sys.executable, "-m", "exp1.src.session_runner",
                 "--planner", planner, "--seed", str(seed),
                 "--duration", str(duracion), "--run-dir", str(run_dir),
                 "--run-id", run_id, "--perfil", PERFIL],
                cwd=str(_ROOT), stdout=slog, stderr=subprocess.STDOUT,
                env={**__import__("os").environ,
                     "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
            )
            try:
                exit_code = p.wait(timeout=duracion + MARGEN_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                log(f"[{run_id}] TIMEOUT — matando árbol de procesos (pid={p.pid})")
                _matar_arbol(p.pid)
                exit_code = -9
    finally:
        # 3. Parar captura SIEMPRE
        captura_combinada.detener_tshark(proc_tshark)

    # 4. Métricas
    metrics_path = run_dir / "metrics.json"
    metricas_ok = False
    if pcap_path.is_file() and pcap_path.stat().st_size > 0:
        try:
            import json
            metricas = extraer_metricas(pcap_path)
            metrics_path.write_text(
                json.dumps(metricas, ensure_ascii=False, indent=2),
                encoding="utf-8")
            metricas_ok = True
            log(f"[{run_id}] métricas: {metricas['packets']} pkts, "
                f"{metricas['flows_total']} flows, {metricas['bytes']} bytes")
        except Exception as e:
            log(f"[{run_id}] ERROR extrayendo métricas: {e}")
            actualizar_manifest(run_dir, errores=[f"metricas: {e}"])
    else:
        log(f"[{run_id}] AVISO: PCAP vacío o inexistente")

    # 5. Estado final
    ok = (exit_code == 0) and metricas_ok
    status = "completed" if ok else "failed"
    actualizar_manifest(
        run_dir,
        status=status,
        session_exit_code=exit_code,
        rutas={
            "pcap": str(pcap_path),
            "session_log": str(session_log),
            "metrics_json": str(metrics_path) if metricas_ok else None,
        },
    )
    log(f"[{run_id}] → {status} (exit={exit_code})")
    return status


def main() -> int:
    global _LOG_PATH
    parser = argparse.ArgumentParser(description="Orquestador Experimento 1")
    parser.add_argument("--runs", type=int, default=10,
                        help="runs por planner (default 10; fallback documentado: 5)")
    parser.add_argument("--duration", type=int, default=300,
                        help="duración de cada sesión en segundos (default 300)")
    parser.add_argument("--planners", default="llm,random,rule")
    parser.add_argument("--base-seed", type=int, default=1000,
                        help="seed del run i = base_seed + i")
    parser.add_argument("--out", default=str(_ROOT / "exp1"),
                        help="directorio raíz de salida")
    parser.add_argument("--smoke", action="store_true",
                        help="modo prueba: 1 run × planner, 120 s, en <out>/smoke")
    parser.add_argument("--force", action="store_true",
                        help="repite también los runs ya completados")
    parser.add_argument("--iface", default="",
                        help="interfaz tshark (nº de 'tshark -D'); "
                             "vacío = autodetectar por ruta por defecto")
    args = parser.parse_args()

    planners = [p.strip() for p in args.planners.split(",") if p.strip()]
    out_dir = Path(args.out)
    runs, duracion = args.runs, args.duration
    if args.smoke:
        out_dir = out_dir / "smoke"
        runs, duracion = 1, min(duracion, 120)

    out_dir.mkdir(parents=True, exist_ok=True)
    _LOG_PATH = out_dir / "orchestrator.log"

    # Interfaz de captura fijada UNA vez para todos los runs (constante).
    iface = args.iface.strip() or detectar_iface_activa()
    captura_combinada.IFACE_WINDOWS = iface

    log("═" * 60)
    log(f"Experimento 1 — planners={planners} runs={runs} duración={duracion}s "
        f"base_seed={args.base_seed} iface={iface} out={out_dir}")
    log("═" * 60)

    resultados: dict[str, list[str]] = {p: [] for p in planners}
    t0 = time.time()
    for i in range(1, runs + 1):
        seed = args.base_seed + i
        for planner in planners:
            estado = ejecutar_run(planner, i, seed, duracion, out_dir, args.force)
            resultados[planner].append(estado)
            if estado != "skipped":
                time.sleep(PAUSA_ENTRE_RUNS_S)

    log("═" * 60)
    for planner, estados in resultados.items():
        c = estados.count
        log(f"{planner}: completed={c('completed')} failed={c('failed')} "
            f"skipped={c('skipped')}")
    log(f"Tiempo total: {(time.time() - t0) / 60:.1f} min")
    fallos = sum(e.count("failed") for e in resultados.values())
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
