# -*- coding: utf-8 -*-
"""
planners.py — Puerto del planner y sus tres adaptadores (Experimento 1).

El "puerto" replica el contrato de facto del sistema actual: el planner devuelve
un dict-acción {"tipo": str, "delay": int, ["termino"|"url"|"busqueda"]} del
catálogo ALLOWED_TIPOS de agentev7.py. Los tres adaptadores emiten acciones del
mismo tipo y formato; el resto del pipeline (validación, dispatcher del
navegador, captura) no cambia.

- LLMPlanner:       envuelve obtener_accion_json_llm() de agentev7 (con traza).
- RandomPlanner:    muestreo uniforme del catálogo, reproducible por seed.
- RuleBasedPlanner: secuencia cíclica fija con parámetros deterministas;
                    la seed solo afecta al jitter del delay.
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# Repo root en sys.path para importar agentev7 (los scripts del repo son planos)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import agentev7  # noqa: E402

# ── Pools de parámetros fijos ────────────────────────────────────────────────
# Derivados de los valores que ya usa agentev7 en _validar_accion() y
# generar_accion_fallback(), ampliados mínimamente para que los baselines no
# queden limitados a un único valor por parámetro. Registrados aquí (no hay
# valores "mágicos" fuera del repo).
POOL_TERMINOS: list[str] = [
    "últimas noticias de IA",
    "tendencias ciberseguridad 2025",
    "python asyncio tutorial",
    "últimas noticias tecnología",
    "ciberseguridad hoy",
    "mejores frameworks python 2025",
    "inteligencia artificial hoy",
    "noticias tecnología",
]
POOL_URLS: list[str] = [
    "https://www.bbc.com/mundo",
    "https://elpais.com",
    "https://www.elmundo.es",
    "https://www.xataka.com",
    "https://www.genbeta.com",
]
POOL_BUSQUEDAS_YT: list[str] = [
    "noticias tecnología",
    "ciberseguridad",
    "tutorial python",
    "programación en vivo",
    "noticias en vivo",
    "música en vivo",
]

DELAY_MIN, DELAY_MAX = 8, 25  # mismo rango que impone _validar_accion()

# Catálogo ordenado (ALLOWED_TIPOS es un set; el orden de iteración de sets de
# strings varía entre procesos por el hash aleatorio → se ordena para que la
# seed produzca siempre la misma secuencia)
CATALOGO: list[str] = sorted(agentev7.ALLOWED_TIPOS)


@dataclass
class AccionPlanificada:
    """Acción emitida por un planner + metadatos de trazabilidad."""
    accion: dict
    source: str                      # "llm" | "fallback" | "random" | "rule"
    trace: list = field(default_factory=list)  # solo LLM: intentos/prompt/respuesta


class PlannerPort(Protocol):
    """Puerto del planner: cualquier adaptador debe emitir AccionPlanificada."""
    nombre: str

    def next_action(self) -> AccionPlanificada: ...


def _completar_params(tipo: str, rng: random.Random) -> dict:
    """Parámetros del pool fijo para los tipos que los requieren."""
    if tipo == "buscar_google":
        return {"termino": rng.choice(POOL_TERMINOS)}
    if tipo == "abrir_url":
        return {"url": rng.choice(POOL_URLS)}
    if tipo == "mirar_youtube":
        return {"busqueda": rng.choice(POOL_BUSQUEDAS_YT)}
    return {}


class LLMPlanner:
    """Adaptador del planner actual (Groq / Llama 4 Scout) con traza completa."""
    nombre = "llm"

    def next_action(self) -> AccionPlanificada:
        trace: list = []
        accion = agentev7.obtener_accion_json_llm(trace=trace)
        uso_fallback = any(t.get("fallback") for t in trace)
        return AccionPlanificada(
            accion=accion,
            source="fallback" if uso_fallback else "llm",
            trace=trace,
        )


class RandomPlanner:
    """Muestreo uniforme del mismo catálogo que usa el LLM. Reproducible por seed."""
    nombre = "random"

    def __init__(self, seed: int):
        self.seed = seed
        self._rng = random.Random(seed)

    def next_action(self) -> AccionPlanificada:
        tipo = self._rng.choice(CATALOGO)
        accion = {"tipo": tipo, "delay": self._rng.randint(DELAY_MIN, DELAY_MAX)}
        accion.update(_completar_params(tipo, self._rng))
        return AccionPlanificada(accion=accion, source="random")


# Secuencia fija del planner basado en reglas: un "guion" plausible de usuario
# regular, sin inteligencia. Se recorre cíclicamente; parámetros deterministas.
SECUENCIA_RULE: list[dict] = [
    {"tipo": "buscar_google", "termino": "últimas noticias tecnología"},
    {"tipo": "abrir_url", "url": "https://www.bbc.com/mundo"},
    {"tipo": "mirar_youtube", "busqueda": "noticias tecnología"},
    {"tipo": "revisar_correo"},
    {"tipo": "buscar_google", "termino": "ciberseguridad hoy"},
    {"tipo": "usar_twitter"},
    {"tipo": "abrir_url", "url": "https://elpais.com"},
    {"tipo": "ver_streaming"},
]


class RuleBasedPlanner:
    """Secuencia predefinida cíclica. La seed solo introduce jitter en el delay."""
    nombre = "rule"

    def __init__(self, seed: int):
        self.seed = seed
        self._rng = random.Random(seed)
        self._idx = 0

    def next_action(self) -> AccionPlanificada:
        base = dict(SECUENCIA_RULE[self._idx % len(SECUENCIA_RULE)])
        self._idx += 1
        base["delay"] = self._rng.randint(DELAY_MIN, DELAY_MAX)
        return AccionPlanificada(accion=base, source="rule")


def crear_planner(nombre: str, seed: int) -> "PlannerPort":
    """Factoría: nombre ∈ {llm, random, rule}."""
    if nombre == "llm":
        return LLMPlanner()
    if nombre == "random":
        return RandomPlanner(seed)
    if nombre == "rule":
        return RuleBasedPlanner(seed)
    raise ValueError(f"Planner desconocido: {nombre!r} (usa llm|random|rule)")
