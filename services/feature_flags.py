"""Feature flags centralizados para despliegues y rollback operacional.

Los motores de análisis validados están activos por defecto. Un valor explícito
``false`` conserva un rollback inmediato sin modificar ni redesplegar código.
Los flags de shadow y seguridad continúan opt-in.
"""

import os

_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def flag_enabled(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def scoring_v3_enabled() -> bool:
    return flag_enabled("SCORING_ENGINE_V3_ENABLED", default=True)


def scoring_v5_enabled() -> bool:
    return flag_enabled("SCORING_ENGINE_V5_ENABLED", default=True)


def scoring_v3_shadow_enabled() -> bool:
    return flag_enabled("SCORING_ENGINE_V3_SHADOW_ENABLED")


def portfolio_v4_enabled() -> bool:
    return flag_enabled("PORTFOLIO_ENGINE_V4_ENABLED", default=True)


def portfolio_v4_shadow_enabled() -> bool:
    return flag_enabled("PORTFOLIO_ENGINE_V4_SHADOW_ENABLED")


def portfolio_ibc_benchmark_v5_enabled() -> bool:
    """Benchmark Portafolio vs IBC V5, activo con rollback explícito."""
    return flag_enabled("PORTFOLIO_IBC_BENCHMARK_V5_ENABLED", default=True)


def security_hardening_v1_enabled() -> bool:
    return flag_enabled("SECURITY_HARDENING_V1_ENABLED")


# Aliases temporales para compatibilidad con la primera rama V3/V4.
SCORING_ENGINE_V3_ENABLED = scoring_v3_enabled
SCORING_ENGINE_V5_ENABLED = scoring_v5_enabled
PORTFOLIO_ENGINE_V4_ENABLED = portfolio_v4_enabled
PORTFOLIO_IBC_BENCHMARK_V5_ENABLED = portfolio_ibc_benchmark_v5_enabled
SECURITY_HARDENING_V1_ENABLED = security_hardening_v1_enabled
