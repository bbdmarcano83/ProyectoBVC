import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_USER     = os.environ.get("GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")

def enviar_email(destinatario: str, asunto: str, html: str) -> bool:
    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("[Email] No configurado")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = f"Caracas Bull <{GMAIL_USER}>"
        msg["To"]      = destinatario
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, destinatario, msg.as_string())
        return True
    except Exception as e:
        print(f"[Email] Error: {e}")
        return False

def email_recuperar_password(destinatario: str, nombre: str, token: str, app_url: str) -> bool:
    url = f"{app_url}/recuperar/{token}"
    html = f"<div style='font-family:sans-serif;max-width:520px;margin:auto;background:#0f1a1a;color:#e8f0f0;padding:40px;border-radius:12px;'><h2>Recuperar contrasena</h2><p>Hola {nombre}, haz clic para restablecer tu contrasena:</p><a href='{url}' style='display:block;text-align:center;background:#00c896;color:#080f0f;padding:14px;border-radius:8px;font-weight:700;text-decoration:none;margin:20px 0;'>Restablecer contrasena</a><p style='color:#6b9090;font-size:13px;'>Expira en 30 minutos.</p></div>"
    return enviar_email(destinatario, "Recuperar contrasena - Caracas Bull", html)

def email_bienvenida(destinatario: str, nombre: str) -> bool:
    html = f"<div style='font-family:sans-serif;max-width:520px;margin:auto;background:#0f1a1a;color:#e8f0f0;padding:40px;border-radius:12px;'><h2>Bienvenido {nombre}!</h2><p>Tu cuenta esta activa con 14 dias de prueba gratis.</p><a href='https://caracasbull.com' style='display:block;text-align:center;background:#00c896;color:#080f0f;padding:14px;border-radius:8px;font-weight:700;text-decoration:none;margin:20px 0;'>Ir a Caracas Bull</a></div>"
    return enviar_email(destinatario, "Bienvenido a Caracas Bull!", html)
