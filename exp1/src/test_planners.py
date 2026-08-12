# -*- coding: utf-8 -*-
"""
test_planners.py — Tests rápidos de los planners del Experimento 1 (sin red).

  python -m exp1.src.test_planners
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import agentev7  # noqa: E402
from exp1.src.planners import (  # noqa: E402
    CATALOGO, RandomPlanner, RuleBasedPlanner, SECUENCIA_RULE, crear_planner,
)

N = 50


def test_random_reproducible() -> None:
    # secuencias completas con la misma seed → idénticas
    p1, p2 = RandomPlanner(seed=42), RandomPlanner(seed=42)
    s1 = [p1.next_action().accion for _ in range(N)]
    s2 = [p2.next_action().accion for _ in range(N)]
    assert s1 == s2, "RandomPlanner no es reproducible con la misma seed"
    # seed distinta → secuencia distinta
    p3 = RandomPlanner(seed=43)
    s3 = [p3.next_action().accion for _ in range(N)]
    assert s1 != s3, "RandomPlanner ignora la seed"
    print("✅ RandomPlanner reproducible por seed")


def test_rule_reproducible() -> None:
    p1, p2 = RuleBasedPlanner(seed=7), RuleBasedPlanner(seed=7)
    s1 = [p1.next_action().accion for _ in range(N)]
    s2 = [p2.next_action().accion for _ in range(N)]
    assert s1 == s2, "RuleBasedPlanner no es reproducible con la misma seed"
    # la secuencia de tipos es el guion fijo, independiente de la seed
    tipos = [a["tipo"] for a in s1]
    esperado = [SECUENCIA_RULE[i % len(SECUENCIA_RULE)]["tipo"] for i in range(N)]
    assert tipos == esperado, "RuleBasedPlanner no sigue la secuencia fija"
    print("✅ RuleBasedPlanner reproducible y fiel al guion")


def test_validacion_catalogo() -> None:
    """Todas las acciones de random/rule pasan la MISMA validación que el LLM."""
    for planner in (RandomPlanner(seed=1), RuleBasedPlanner(seed=1)):
        for _ in range(N):
            plan = planner.next_action()
            assert plan.accion["tipo"] in CATALOGO
            validada = agentev7._validar_accion(dict(plan.accion))
            assert validada is not None, f"acción rechazada: {plan.accion}"
            assert 8 <= validada["delay"] <= 25
    print("✅ Acciones de random/rule válidas según _validar_accion de agentev7")


def test_factoria() -> None:
    assert crear_planner("random", 1).nombre == "random"
    assert crear_planner("rule", 1).nombre == "rule"
    assert crear_planner("llm", 1).nombre == "llm"
    try:
        crear_planner("foo", 1)
        raise AssertionError("la factoría aceptó un planner desconocido")
    except ValueError:
        pass
    print("✅ Factoría de planners")


if __name__ == "__main__":
    test_random_reproducible()
    test_rule_reproducible()
    test_validacion_catalogo()
    test_factoria()
    print("\nTodos los tests OK")
