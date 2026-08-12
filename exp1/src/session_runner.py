# -*- coding: utf-8 -*-
"""
session_runner.py — Ejecuta UNA sesión del perfil regular_user con el planner
indicado (Experimento 1). Lo lanza el orquestador como subproceso; también se
puede ejecutar a mano:

  python -m exp1.src.session_runner --planner random --seed 1001 \
      --duration 300 --run-dir exp1/random/run_01 --run-id random_run01

Escribe en run-dir:
  actions.csv       una fila por acción (y por intento LLM rechazado)
  llm_trace.jsonl   traza completa prompt/respuesta del LLM (solo planner=llm)
  manifest.json     (actualiza los campos de la sesión)

El pipeline de ejecución es EXACTAMENTE el de agentev7.py (validación,
dispatcher del navegador, simulación de actividad); solo cambia el planner.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def cargar_dotenv(path: Path) -> None:
    """Carga KEY=VALUE de .env en os.environ sin pisar variables ya definidas.
    Parser mínimo para no añadir dependencias (no hay python-dotenv en el repo)."""
    import os
    if not path.is_file():
        return
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


# .env ANTES de importar agentev7 (lee GROQ_API_KEY etc. al importar)
cargar_dotenv(_ROOT / ".env")

import agentev7  # noqa: E402
from exp1.src.planners import AccionPlanificada, crear_planner  # noqa: E402
from exp1.src.manifest import actualizar_manifest  # noqa: E402

CSV_CAMPOS = [
    "idx", "ts_iso", "run_id", "planner", "seed", "tipo", "params_json",
    "source", "validada", "motivo_rechazo", "ejecutada", "error_ejecucion",
    "delay_s", "exec_s", "llm_model", "llm_temperature", "llm_prompt",
    "llm_respuesta",
]

PAGE_LOAD_TIMEOUT_S = 60  # evita que un driver.get() colgado consuma la sesión


def _params_de(accion: dict) -> str:
    return json.dumps(
        {k: v for k, v in accion.items() if k not in ("tipo", "delay")},
        ensure_ascii=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Runner de una sesión exp1")
    parser.add_argument("--planner", required=True, choices=["llm", "random", "rule"])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--duration", type=int, required=True, help="segundos")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--perfil", default="regular_user")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    actions_path = run_dir / "actions.csv"
    trace_path = run_dir / "llm_trace.jsonl"
    if trace_path.is_file():
        trace_path.unlink()  # se escribe en append: evita mezclar trazas de un re-run

    # Seed global: hace deterministas simular_actividad, los defaults de
    # _validar_accion y (para llm) la elección local de perfil/intención.
    # RandomPlanner/RuleBasedPlanner usan además su random.Random(seed) propio.
    random.seed(args.seed)

    planner = crear_planner(args.planner, args.seed)

    contadores = {
        "emitidas": 0,               # acciones finales entregadas por el planner
        "validas": 0,
        "rechazadas_validacion": 0,  # tras el planner (debería ser 0 en random/rule)
        "llm_intentos_rechazados": 0,
        "fallbacks": 0,
        "ejecutadas_ok": 0,
        "ejecutadas_fallo": 0,
    }
    errores: list[str] = []
    llm_config: dict | None = None
    inicio = time.time()

    csv_f = open(actions_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_f, fieldnames=CSV_CAMPOS)
    writer.writeheader()
    csv_f.flush()

    def fila_base(idx: int) -> dict:
        return {
            "idx": idx,
            "ts_iso": datetime.now().astimezone().isoformat(),
            "run_id": args.run_id,
            "planner": args.planner,
            "seed": args.seed,
        }

    driver = None
    exit_code = 0
    idx = 0
    try:
        driver = agentev7.crear_driver()
        try:
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_S)
        except Exception:
            pass

        fin = inicio + args.duration
        while time.time() < fin:
            print(f"🕒 [{args.run_id}] Nueva acción ({datetime.now().strftime('%H:%M:%S')})")
            try:
                planificada: AccionPlanificada = planner.next_action()
            except Exception as e:
                errores.append(f"planner: {type(e).__name__}: {e}")
                print(f"❌ Error del planner: {e}")
                time.sleep(5)
                continue

            # ── Traza LLM: intentos rechazados y fallback ──
            for reg in planificada.trace:
                with open(trace_path, "a", encoding="utf-8") as tf:
                    tf.write(json.dumps(reg, ensure_ascii=False) + "\n")
                if llm_config is None and reg.get("model"):
                    llm_config = {
                        "modelo": reg["model"],
                        "temperaturas": [0.2, 0.3],
                        "prompt_base": reg.get("prompt"),
                        "api": "groq/chat.completions",
                    }
                if reg.get("error"):
                    contadores["llm_intentos_rechazados"] += 1
                    idx += 1
                    acc_i = reg.get("accion") or {}
                    writer.writerow({
                        **fila_base(idx),
                        "tipo": acc_i.get("tipo", ""),
                        "params_json": _params_de(acc_i) if acc_i else "",
                        "source": "llm_intento",
                        "validada": "rechazada",
                        "motivo_rechazo": reg["error"],
                        "ejecutada": "no",
                        "error_ejecucion": "",
                        "delay_s": "",
                        "exec_s": "",
                        "llm_model": reg.get("model", ""),
                        "llm_temperature": reg.get("temperature", ""),
                        "llm_prompt": reg.get("prompt", ""),
                        "llm_respuesta": reg.get("respuesta_cruda", ""),
                    })
                    csv_f.flush()

            accion = planificada.accion
            contadores["emitidas"] += 1
            if planificada.source == "fallback":
                contadores["fallbacks"] += 1

            # ── Validación (la MISMA para los tres planners) ──
            validada = agentev7._validar_accion(dict(accion))
            idx += 1
            fila = fila_base(idx)
            fila.update({
                "tipo": accion.get("tipo", ""),
                "params_json": _params_de(accion),
                "source": planificada.source,
                "llm_model": "", "llm_temperature": "",
                "llm_prompt": "", "llm_respuesta": "",
            })
            reg_ok = next((r for r in planificada.trace if r.get("accion") and not r.get("error") and not r.get("fallback")), None)
            if reg_ok is not None:
                fila["llm_model"] = reg_ok.get("model", "")
                fila["llm_temperature"] = reg_ok.get("temperature", "")
                fila["llm_prompt"] = reg_ok.get("prompt", "")
                fila["llm_respuesta"] = reg_ok.get("respuesta_cruda", "")

            if validada is None:
                contadores["rechazadas_validacion"] += 1
                fila.update({
                    "validada": "rechazada",
                    "motivo_rechazo": "tipo fuera de catálogo o formato inválido (_validar_accion)",
                    "ejecutada": "no", "error_ejecucion": "",
                    "delay_s": "", "exec_s": "",
                })
                writer.writerow(fila); csv_f.flush()
                continue

            contadores["validas"] += 1
            print(f"🔎 [{planner.nombre}] Acción decidida: {validada}")

            # ── Ejecución (dispatcher intacto de agentev7) ──
            t0 = time.time()
            try:
                ok = agentev7.ejecutar_accion_browser(validada, driver)
            except Exception as e:  # por si el dispatcher lanza algo inesperado
                ok = False
                errores.append(f"ejecutar_accion_browser: {type(e).__name__}: {e}")
            exec_s = round(time.time() - t0, 2)

            if ok:
                contadores["ejecutadas_ok"] += 1
            else:
                contadores["ejecutadas_fallo"] += 1

            fila.update({
                "validada": "ok",
                "motivo_rechazo": "",
                "ejecutada": "ok" if ok else "fallo",
                "error_ejecucion": "" if ok else "ver session.log",
                "delay_s": validada.get("delay", ""),
                "exec_s": exec_s,
            })
            writer.writerow(fila); csv_f.flush()

            # ── Actividad simulada (idéntica al bucle original) ──
            delay = validada.get("delay", random.randint(8, 10))
            restante = fin - time.time()
            if restante <= 0:
                break
            print(f"⏳ Simulando actividad {delay}s…")
            try:
                agentev7.simular_actividad(driver, min(delay, max(1, restante)))
            except Exception as e:
                errores.append(f"simular_actividad: {type(e).__name__}: {e}")

    except Exception as e:
        errores.append(f"sesion: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        print(f"❌ Error fatal de la sesión: {e}")
        exit_code = 1
    finally:
        csv_f.close()
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        duracion_real = round(time.time() - inicio, 1)
        try:
            actualizar_manifest(
                run_dir,
                fin=datetime.now().astimezone().isoformat(),
                duracion_real_s=duracion_real,
                llm=llm_config,
                acciones=contadores,
                errores=errores,
                rutas={
                    "actions_csv": str(actions_path),
                    "llm_trace": str(trace_path) if trace_path.is_file() else None,
                },
            )
        except Exception as e:
            print(f"⚠️ No se pudo actualizar el manifest: {e}")
            exit_code = exit_code or 1

    print(f"✅ Sesión terminada: {contadores} | errores={len(errores)}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
