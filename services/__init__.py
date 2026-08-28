"""ProyectoBVC service package bootstrap."""
import os

# Render expone RENDER=true. Si APP_ENV no fue definido, endurecemos el runtime
# automáticamente en lugar de arrancar con defaults de desarrollo.
if os.environ.get("RENDER", "").strip().lower() == "true" and not os.environ.get("APP_ENV"):
    os.environ["APP_ENV"] = "production"

from services.security_runtime import install_fastapi_security_bootstrap
from services.secret_guard import install_secret_guard

install_fastapi_security_bootstrap()
install_secret_guard()
