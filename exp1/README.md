# Experimento 1 — LLM planner vs Random vs Rule-based (perfil regular user)

Compara el valor añadido del planner LLM frente a dos baselines sin
"inteligencia", cambiando **solo el planner**. Todo lo demás es constante:
perfil (`regular_user` = agente web `agentev7.py`), máquina, red, duración de
sesión, validación de acciones, dispatcher del navegador, captura (tshark) y
extractor de métricas.

## Variantes

| Planner  | Descripción | Reproducibilidad |
|----------|-------------|------------------|
| `llm`    | El actual: Groq / `meta-llama/llama-4-scout-17b-16e-instruct`, temperatura 0.2 (reintento 0.3) | no determinista (API); seed fija la parte local (fallbacks, scrolls) |
| `random` | Muestreo uniforme del mismo catálogo (`ALLOWED_TIPOS` de agentev7) con parámetros de pools fijos | total, por `seed` |
| `rule`   | Guion cíclico fijo de 8 pasos (`SECUENCIA_RULE`); la seed solo jitterea el delay | total, por `seed` |

Los tres emiten acciones del mismo formato `{"tipo", "delay", ...}` y pasan por
la **misma** `_validar_accion()` y el **mismo** `ejecutar_accion_browser()` de
`agentev7.py`.

## Reproducir

```bash
# 0) Requisitos: Wireshark (tshark), Chrome, Python con scapy/matplotlib/pandas/
#    selenium/undetected_chromedriver, y un .env en la raíz del repo con
#    GROQ_API_KEY (y opcionalmente GMAIL_*/TWITTER_USERNAME para esas acciones).

# 1) Tests rápidos de los planners (sin red)
python -m exp1.src.test_planners

# 2) Smoke test: 1 run × planner, 120 s, escribe en exp1/smoke/
python -m exp1.src.orchestrate --smoke

# 3) Experimento completo: 10 runs × 3 planners, 900 s (15 min) por sesión (~8 h)
python -m exp1.src.orchestrate --runs 10 --duration 900

# 4) Agregación + gráficas
python -m exp1.src.analyze
```

La interfaz de captura se detecta automáticamente (adaptador con la ruta por
defecto) o se fija con `--iface N` (número de `tshark -D`). El brazo LLM
requiere una `GROQ_API_KEY` válida en `.env`.

El orquestador es **idempotente**: si se interrumpe, al relanzarlo salta los
runs con `status=completed` y repite solo los pendientes/fallidos (`--force`
para repetir todo). Los runs se ejecutan en serie e intercalados por índice
(llm, random, rule, llm, ...) para repartir efectos temporales.

Seeds: `seed = base_seed (1000) + índice_de_run`; el run i de cada planner
comparte seed. Todo queda registrado en el `manifest.json` de cada run
(commit hash, SO, red, seed, config LLM, rutas, errores).

## Estructura de salida

```
exp1/
  llm/     run_01/ ... run_10/     # capture.pcap, actions.csv, llm_trace.jsonl,
  random/  run_01/ ... run_10/     #   manifest.json, metrics.json, session.log
  rule/    run_01/ ... run_10/
  smoke/                           # smoke test (misma estructura)
  summary_por_sesion.csv           # una fila por run: tráfico + acciones
  actions_agregado.csv             # todas las acciones (sin prompts)
  plots/                           # boxplots comparativos
  orchestrator.log
  NOTA_errores.md                  # incidencias y decisiones de diseño
```

## Ficheros de código (`exp1/src/`)

- `planners.py` — puerto `PlannerPort` + `LLMPlanner` / `RandomPlanner` / `RuleBasedPlanner`
- `session_runner.py` — ejecuta una sesión (subproceso); escribe actions.csv y traza LLM
- `orchestrate.py` — orquestador de runs (captura tshark + sesión + métricas + manifest)
- `traffic_metrics.py` — extractor de métricas por PCAP (común a los tres planners)
- `manifest.py` — provenance por run
- `analyze.py` — summary CSV + gráficas
- `test_planners.py` — reproducibilidad y validación del catálogo
