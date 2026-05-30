
    from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import json
import os

app = FastAPI()
CONFIG_FILE = 'config.json'

def cargar_config():
    if not os.path.exists('config.json'):
        # Crea el archivo con un valor inicial si no existe
        with open('config.json', 'w') as f: json.dump({"tasa": 0.0}, f)
    with open('config.json', 'r') as f: 
        return json.load(f)

def cargar_portafolio():
    if not os.path.exists('portafolio.json'):
        # Crea el archivo con un diccionario vacío si no existe
        with open('portafolio.json', 'w') as f: json.dump({}, f)
    with open('portafolio.json', 'r') as f: 
        return json.load(f)

def guardar_config(tasa):
    with open(CONFIG_FILE, 'w') as f: json.dump({"tasa": tasa}, f)

# Funciones de datos (sin cambios)
def cargar_portafolio():
    if os.path.exists('portafolio.json'):
        with open('portafolio.json', 'r') as f: return json.load(f)
    return {}

def guardar_portafolio(data):
    with open('portafolio.json', 'w') as f: json.dump(data, f)

import httpx
async def obtener_datos_bvc():
    try:
        url = "https://www.bolsadecaracas.com/wp-admin/admin-ajax.php"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data={'action': 'get_cotizaciones'}, headers={"User-Agent": "Mozilla/5.0"})
            return resp.json().get('response', [])
    except: return []

CSS_STYLE = """
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f4f7f6; padding: 20px; }
    .container { max-width: 1200px; margin: auto; background: white; padding: 25px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .stats { display: flex; gap: 20px; background: #34495e; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; font-weight: bold; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th { background: #34495e; color: white; padding: 12px; font-size: 13px; }
    td { padding: 10px; border-bottom: 1px solid #ddd; text-align: center; font-size: 13px; }
    .btn { padding: 8px 16px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; }
    .overlay { display: none; position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.5); justify-content: center; align-items: center; }
    .modal { background: white; padding: 30px; border-radius: 8px; position: relative; width: 400px; }
    .close-btn { position: absolute; top: 10px; right: 15px; cursor: pointer; font-size: 20px; }
</style>
"""

@app.post("/configurar")
async def configurar(tasa: float = Form(...)):
    guardar_config(tasa)
    return RedirectResponse(url="/portafolio", status_code=303)

@app.post("/agregar")
async def agregar(simb: str = Form(...), cant: float = Form(...), precio: float = Form(...), com: float = Form(0), reg: float = Form(0), iva: float = Form(16)):
    portafolio = cargar_portafolio()
    portafolio[simb.upper()] = {"cantidad": cant, "precio_promedio": precio, "comision": com, "registro": reg, "iva": iva}
    guardar_portafolio(portafolio)
    return RedirectResponse(url="/portafolio", status_code=303)

@app.get("/")
async def root():
    datos = await obtener_datos_bvc()
    html = f"<html><head>{CSS_STYLE}</head><body><div class='container'><h1>Pizarra Profesional BVC</h1><a href='/portafolio' class='btn'>Ir a Portafolio</a>"
    html += "<table><tr><th>Símbolo</th><th>Precio Cmp</th><th>Precio Vta</th><th>Precio Ult</th><th>Vol. Transado</th><th>Var.</th></tr>"
    for item in datos:
        var = float(item.get('VAR_REL') or item.get('VAR_DIARIA', 0) or 0)
        html += f"<tr><td><b>{item.get('COD_SIMB')}</b></td><td>{item.get('PRE_CMP_1')}</td><td>{item.get('PRE_VTA_1')}</td><td>{item.get('PRE_ULT')}</td><td>{item.get('MONTO_EFECTIVO')}</td><td style='color:{'green' if var > 0 else 'red'}'>{var:.2f}%</td></tr>"
    html += "</table></div></body></html>"
    return HTMLResponse(html)

@app.get("/portafolio")
async def ver_portafolio():
    datos_bolsa = await obtener_datos_bvc()
    portafolio = cargar_portafolio()
    config = cargar_config()
    tasa = config['tasa']
    
    total_inv = sum(d['cantidad'] * d['precio_promedio'] for d in portafolio.values())
    total_mkt = sum(d['cantidad'] * float(next((i for i in datos_bolsa if i.get('COD_SIMB') == simb), {}).get('PRE_ULT', d['precio_promedio'])) for simb, d in portafolio.items())
    
    gan_bs = total_mkt - total_inv
    rend = (gan_bs / total_inv * 100) if total_inv > 0 else 0
    
    html = f"<html><head>{CSS_STYLE}<script src='https://cdn.jsdelivr.net/npm/chart.js'></script></head><body><div class='container'><h1>Mi Portafolio</h1>"
    html += "<a href='/' class='btn' style='background:#95a5a6;'>« Volver a Pizarra</a>"
    html += f"<form action='/configurar' method='post' style='margin-top:10px;'>Tasa BCV Manual: <input type='number' name='tasa' value='{tasa}' step='any' required> <button type='submit' class='btn'>Fijar Tasa</button></form>"
    html += f"<div class='stats' style='margin-top:15px;'><div>Val. Mkt: {total_mkt:,.2f} Bs</div><div>Ganancia: {gan_bs:,.2f} Bs</div><div>Rend: {rend:.2f}%</div></div>"
    
    html += "<button class='btn' onclick=\"document.getElementById('modal').style.display='flex'\">+ Agregar Activo</button>"
    html += "<div id='modal' class='overlay' onclick=\"if(event.target==this) this.style.display='none'\"><div class='modal'><span class='close-btn' onclick=\"document.getElementById('modal').style.display='none'\">&times;</span><h3>Nuevo Activo</h3><form action='/agregar' method='post'><input type='text' name='simb' placeholder='Símbolo' required><br><input type='number' name='cant' placeholder='Cantidad' step='any' required><br><input type='number' name='precio' placeholder='Precio' step='any' required><br><button type='submit' class='btn'>Guardar</button></form></div></div>"
    
    html += "<table><tr><th>Símbolo</th><th>% Port.</th><th>Ganancia Bs.</th><th>Ganancia USD</th></tr>"
    for simb, d in portafolio.items():
        act = next((i for i in datos_bolsa if i.get('COD_SIMB') == simb), {})
        val = d['cantidad'] * float(act.get('PRE_ULT') or d['precio_promedio'])
        gan = val - (d['cantidad'] * d['precio_promedio'])
        peso = (val / total_mkt * 100) if total_mkt > 0 else 0
        html += f"<tr><td>{simb}</td><td>{peso:.1f}%</td><td style='color:{'green' if gan>=0 else 'red'}'>{gan:,.2f}</td><td>{(gan/tasa) if tasa>0 else 0:,.2f}</td></tr>"
    
    html += "</table><div style='width:500px; margin:20px auto;'><canvas id='chart'></canvas></div>"
    html += f"<script>new Chart(document.getElementById('chart'), {{type:'bar', data:{{labels:['Invertido', 'Mercado'], datasets:[{{label:'Bs', data:[{total_inv}, {total_mkt}], backgroundColor:['#34495e', '#3498db']}}]}}}});</script></div></body></html>"
    return HTMLResponse(html)

if __name__ == "__main__":
    # Render asigna el puerto automáticamente
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("servidor:app", host="0.0.0.0", port=port)