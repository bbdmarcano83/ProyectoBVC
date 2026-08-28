"""ProyectoBVC service package bootstrap."""

from services.security_runtime import install_fastapi_security_bootstrap
from services.secret_guard import install_secret_guard

install_fastapi_security_bootstrap()
install_secret_guard()
