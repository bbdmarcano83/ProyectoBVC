"""Feature flags centralizados para despliegues progresivos.

Todos los flags son opt-in y por defecto están desactivados para preservar
el comportamiento actual de producción.
"""

import os

_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def flag_enabled(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def scoring_v3_enabled() -> bool:
    return flag_enabled("SCORING_ENGINE_V3_ENABLED")


def scoring_v3_shadow_enabled() -> bool:
    return flag_enabled("SCORING_ENGINE_V3_SHADOW_ENABLED")


def portfolio_v4_enabled() -> bool:
    return flag_enabled("PORTFOLIO_ENGINE_V4_ENABLED")


def portfolio_v4_shadow_enabled() -> bool:
    return flag_enabled("PORTFOLIO_ENGINE_V4_SHADOW_ENABLED")


def security_hardening_v1_enabled() -> bool:
    return flag_enabled("SECURITY_HARDENING_V1_ENABLED")


# Aliases temporales para compatibilidad con la primera rama V3/V4.
SCORING_ENGINE_V3_ENABLED = scoring_v3_enabled
PORTFOLIO_ENGINE_V4_ENABLED = portfolio_v4_enabled
SECURITY_HARDENING_V1_ENABLED = security_hardening_v1_enabled
