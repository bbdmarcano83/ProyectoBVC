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


SCORING_ENGINE_V3_ENABLED = lambda: flag_enabled("SCORING_ENGINE_V3_ENABLED")
PORTFOLIO_ENGINE_V4_ENABLED = lambda: flag_enabled("PORTFOLIO_ENGINE_V4_ENABLED")
SECURITY_HARDENING_V1_ENABLED = lambda: flag_enabled("SECURITY_HARDENING_V1_ENABLED")
