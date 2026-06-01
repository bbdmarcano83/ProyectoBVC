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
def formatear_numero(valor):
    try:
        # Convertimos a float, luego a string con formato de miles y 2 decimales
        # El :.2f asegura 2 decimales, el : , añade separador de miles
        num = float(valor)
        return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return valor  # Si no es un número (como el guion), lo devuelve igual

async def obtener_detalle_especifico(simbolo):
    url = "https://www.bolsadecaracas.com/wp-admin/admin-ajax.php"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    async with httpx.AsyncClient() as client:
        # Replicamos la misma estructura exacta que la pizarra
        # Primero pedimos el detalle específico
        r = await client.post(url, data={'action': 'get_detalle_simbolo', 'simbolo': simbolo}, headers=headers)
        
        # Si la bolsa nos devuelve 0, es que el símbolo está cerrado o no existe el detalle extendido
        # Entonces, devolvemos al menos lo básico que sí tenemos en la pizarra
        data = r.json()
        
        # Aquí está el truco: si la bolsa devuelve 0, intentamos recuperar al menos 
        # la info básica desde la pizarra general
        if data == 0:
            datos_pizarra = await obtener_datos_bvc()
            # Buscamos en los datos de la pizarra si el símbolo existe allí
            for item in datos_pizarra:
                if item.get('COD_SIMB') == simbolo:
                    return item # Devolvemos lo que sí sabemos de la pizarra
        return data

async def obtener_datos_bvc():
    url = "https://www.bolsadecaracas.com/wp-admin/admin-ajax.php"
    headers = {"User-Agent": "Mozilla/5.0"} # Añadimos cabecera básica por seguridad
    
    async with httpx.AsyncClient() as client:
        # 1. Traemos el resumen (Precio, Monto, Variación)
        r1 = await client.post(url, data={'action': 'resumenMercadoRentaVariable'}, headers=headers)
        datos_resumen = r1.json()
        
        # 2. Traemos el detalle (Compra, Venta, Volúmenes)
        r2 = await client.post(url, data={'action': 'get_cotizaciones'}, headers=headers)
        datos_detalle = r2.json().get('response', [])
        
        # 3. Creamos un diccionario para buscar rápido el detalle por símbolo
        mapa_detalle = {item['COD_SIMB']: item for item in datos_detalle}
        
        # 4. Fusionamos los datos
        for item in datos_resumen:
            simbolo = item.get('COD_SIMB')
            if simbolo in mapa_detalle:
                # Esto añade los datos de compra/venta al item del resumen
                item.update(mapa_detalle[simbolo])
        
        return datos_resumen

async def obtener_historico(simbolo: str):
    url = "https://www.bolsadecaracas.com/wp-admin/admin-ajax.php"
    async with httpx.AsyncClient() as client:
        # Hacemos la petición igualita a la de la página
        r = await client.post(url, data={'action': 'getHistoricoSimbolo', 'simbolo': simbolo})
        datos = r.json()
        return datos.get('cur_hist_mov_emisora', [])

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
async def ver_pizarra():
    datos_bolsa = await obtener_datos_bvc()
    
    # CSS profesional
    style = """
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f4f4f4; }
        table { width: 100%; border-collapse: collapse; background: white; margin-top: 10px; }
        th { background: #2c3e50; color: white; padding: 10px; }
        td { padding: 10px; border-bottom: 1px solid #ddd; text-align: center; }
        .simbolo-col { background: #f9f9f9; font-weight: bold; text-align: left; }
        .ticker-wrap { position: fixed; bottom: 0; width: 100%; background: #2c3e50; color: white; padding: 10px; overflow: hidden; white-space: nowrap; }
    </style>
    """
    
    html = f"<html><head>{style}</head><body>"
    
    # BOTÓN INTEGRADO
    html += """
    <div style='padding: 15px;'>
        <a href='/portafolio' style='text-decoration: none; background: #2c3e50; color: white; padding: 10px 20px; border-radius: 5px; font-weight: bold;'>
            💼 Ir a mi Portafolio
        </a>
    </div>
    """
    
    # TABLA
    html += "<table><tr><th>Activo</th><th>Vol. Compra</th><th>Precio Compra (Bs)</th><th>Precio Venta (Bs)</th>"
    html += "<th>Vol. Venta</th><th>Último Precio (Bs)</th><th>Títulos</th><th>Vol. Transado (Bs)</th><th>Var. %</th><th>Var. Bs</th></tr>"
    
    for item in datos_bolsa:
        simb = item.get('COD_SIMB')
        
        # Usamos una función auxiliar para asegurar que siempre sea un número
        def limpiar_num(val):
            try:
                if val is None: return 0.0
                return float(str(val).replace(',', '.'))
            except:
                return 0.0

        p_compra = limpiar_num(item.get('PRE_CMP_1'))
        p_venta = limpiar_num(item.get('PRE_VTA_1'))
        v_compra = item.get('VOL_CMP_1') or 0
        v_venta = item.get('VOL_VTA_1') or 0
        p_ult = limpiar_num(item.get('PRECIO'))
        tit = item.get('VOLUMEN') or 0
        vol_trans = limpiar_num(item.get('MONTO_EFECTIVO'))
        var_porc = limpiar_num(item.get('VAR_REL'))
        var_bs = limpiar_num(item.get('VAR_ABS'))
        logo_url = item.get('ICON', '')

        if var_porc > 0: icono, color = "▲", "green"
        elif var_porc < 0: icono, color = "▼", "red"
        else: icono, color = "▬", "blue"
            
        html += f"""<tr>
            <td class='simbolo-col'>
                <a href='/detalle/{simb}' style='text-decoration:none; color: #2c3e50; font-weight:bold;'>
                    <img src='{logo_url}' width='25' onerror="this.style.display='none'"> {simb}
                </a>
            </td>
            <td>{v_compra}</td>
            <td style='color:green; font-weight:bold;'>{p_compra:,.2f} Bs</td>
            <td style='color:red; font-weight:bold;'>{p_venta:,.2f} Bs</td>
            <td>{v_venta}</td>
            <td>{p_ult:,.2f} Bs</td>
            <td>{tit}</td>
            <td>{vol_trans:,.2f} Bs</td>
            <td style='color:{color}'>{icono} {var_porc:.2f}%</td>
            <td style='color:{color}'>{icono} {var_bs:,.2f} Bs</td>
        </tr>"""
    
    html += "</table>"
    
    # CARRUSEL
    html += "<div class='ticker-wrap'><marquee scrollamount='5'>"
    for item in datos_bolsa:
        simb_c = item.get('COD_SIMB', 'N/A')
        p_ult_c = float(item.get('PRECIO', 0))
        var_p_c = float(item.get('VAR_REL', 0))
        col_c = "#2ecc71" if var_p_c > 0 else ("#ff7675" if var_p_c < 0 else "#3498db")
        html += f"<span style='margin-right:60px;'><b style='color:#ecf0f1;'>{simb_c}</b>: {p_ult_c:,.2f} Bs <span style='color:{col_c};'>{var_p_c:.2f}%</span></span>"
    html += "</marquee></div></body></html>"
    
    return HTMLResponse(html)
    
@app.get("/portafolio")
@app.get("/portafolio")
async def ver_portafolio():
    datos_bolsa = await obtener_datos_bvc()
    portafolio = cargar_portafolio()
    config = cargar_config()
    tasa = config['tasa']
    
    # Cálculos totales
    total_inv = sum(d['cantidad'] * d['precio_promedio'] for d in portafolio.values())
    total_mkt = sum(d['cantidad'] * float(next((i for i in datos_bolsa if i.get('COD_SIMB') == simb), {}).get('PRECIO', d['precio_promedio'])) for simb, d in portafolio.items())
    
    gan_bs = total_mkt - total_inv
    rend = (gan_bs / total_inv * 100) if total_inv > 0 else 0
    
    # Inicio del HTML
    html = f"<html><head>{CSS_STYLE}<script src='https://cdn.jsdelivr.net/npm/chart.js'></script></head><body><div class='container'><h1>Mi Portafolio</h1>"
    html += "<a href='/' class='btn' style='background:#95a5a6;'>« Volver a Pizarra</a>"
    html += f"<form action='/configurar' method='post' style='margin-top:10px;'>Tasa BCV Manual: <input type='number' name='tasa' value='{tasa}' step='any' required> <button type='submit' class='btn'>Fijar Tasa</button></form>"
    html += f"<div class='stats' style='margin-top:15px;'><div>Val. Mkt: {total_mkt:,.2f} Bs</div><div>Ganancia: {gan_bs:,.2f} Bs</div><div>Rend: {rend:.2f}%</div></div>"
    html += "<button class='btn' onclick=\"document.getElementById('modal').style.display='flex'\">+ Agregar Activo</button>"
    
    # Modal (se queda igual)
    html += "<div id='modal' class='overlay' onclick=\"if(event.target==this) this.style.display='none'\"><div class='modal'><span class='close-btn' onclick=\"document.getElementById('modal').style.display='none'\">&times;</span><h3>Nuevo Activo</h3><form action='/agregar' method='post'><input type='text' name='simb' placeholder='Símbolo' required><br><input type='number' name='cant' placeholder='Cantidad' step='any' required><br><input type='number' name='precio' placeholder='Precio' step='any' required><br><button type='submit' class='btn'>Guardar</button></form></div></div>"
    
    # 1. Ajusta los encabezados de la tabla
    html += """
    <table><tr>
        <th>Símbolo</th><th>Cantidad</th><th>Precio Prom.</th>
        <th>Precio Mercado</th><th>Val. Portafolio</th><th>% Port.</th>
        <th>Ganancia Bs.</th><th>Ganancia USD</th>
    </tr>"""
    
    # 2. Ajusta el cálculo y la fila
    for simb, d in portafolio.items():
        act = next((i for i in datos_bolsa if i.get('COD_SIMB') == simb), {})
        precio_actual = float(act.get('PRECIO') or d['precio_promedio'])
        
        cant = d['cantidad']
        prom = d['precio_promedio']
        
        # VALOR DE PORTAFOLIO: Multiplicación de Cantidad * Precio Mercado
        val_port = cant * precio_actual 
        
        # Ganancia: Lo que vale hoy vs. Lo que costó
        gan = val_port - (cant * prom)
        gan_usd = (gan / tasa) if tasa > 0 else 0
        peso = (val_port / total_mkt * 100) if total_mkt > 0 else 0
        
        # Definimos colores para USD
        color_usd = "green" if gan_usd > 0 else ("red" if gan_usd < 0 else "blue")
        
        html += f"""<tr>
            <td>{simb}</td><td>{cant}</td><td>{prom:,.2f}</td>
            <td>{precio_actual:,.2f}</td><td>{val_port:,.2f}</td><td>{peso:.1f}%</td>
            <td style='color:{'green' if gan>=0 else 'red'}'>{gan:,.2f}</td>
            <td style='color:{color_usd}'>{gan_usd:,.2f}</td>
        </tr>"""
    html += "</table>"
    html += "<div style='width:500px; margin:20px auto;'><canvas id='chart'></canvas></div>"
    html += f"<script>new Chart(document.getElementById('chart'), {{type:'bar', data:{{labels:['Invertido', 'Mercado'], datasets:[{{label:'Bs', data:[{total_inv}, {total_mkt}], backgroundColor:['#34495e', '#3498db']}}]}}}});</script></div></body></html>"
    return HTMLResponse(html)
    
@app.get("/detalle/{simbolo}")
async def ver_detalle(simbolo: str):
    activo = await obtener_detalle_especifico(simbolo)
    
    # Protección anti-error 500
    if not isinstance(activo, dict) or 'cur_encab_simb_rv' not in activo:
        print(f"DEBUG: El activo {simbolo} devolvió: {activo}") # ESTO ES LO QUE NECESITAMOS VER
        return HTMLResponse(f"<h1>Sin datos. Contenido recibido: {activo}</h1><a href='/'>Volver</a>")
    # Extracción segura
    encab = activo.get('cur_encab_simb_rv', [{}])[0]
    cap = activo.get('cur_cap_simb_rv', [{}])[0]
    lib = activo.get('cur_con_lib_ord_rv', [{}])[0]
    
    # Extracción segura del IBC
    ibc_data = activo.get('CUR_IBC', [])
    ultimo_ibc = ibc_data[-1].get('PRECIO', '---') if ibc_data else "---"
    
    # Limpieza de datos técnicos
    def safe_get(dic, key, default="-"):
        return dic.get(key) if dic.get(key) is not None else default

    var_val = float(str(activo.get('VAR_REL', '0')).replace(',', '.'))
    col = "green" if var_val > 0 else ("red" if var_val < 0 else "blue")
    
    historico = await obtener_historico(simbolo)
    # Aquí están tus 60 velas:
    series_data = [{"x": m.get('FEC'), "y": [float(m.get('PRECIO_APERT', '0').replace('.', '').replace(',', '.')), float(m.get('PRECIO_MAX', '0').replace('.', '').replace(',', '.')), float(m.get('PRECIO_MIN', '0').replace('.', '').replace(',', '.')), float(m.get('PRECIO_CIE', '0').replace('.', '').replace(',', '.'))]} for m in historico[:60]]
    series_data.append({"x": "HOY", "y": [float(str(activo.get('PRECIO', '0')).replace('.', '').replace(',', '.').replace(' ', ''))]*4})

    html = f"""
    <html><head>{CSS_STYLE}<script src='https://cdn.jsdelivr.net/npm/apexcharts'></script>
    <style>
        .ibc-bar {{ background: #000; color: #fff; padding: 15px; text-align: center; font-size: 18px; font-weight: bold; border-bottom: 3px solid #f1c40f; margin-bottom: 20px; }}
        .card {{ background: #1e1e1e; padding: 20px; border-radius: 15px; border: 1px solid #444; color: white; }}
        .bid {{ color: #2ecc71; }} .ask {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; background: #1a1a1a; color: white; }}
        td {{ padding: 10px; border: 1px solid #333; text-align: center; }}
    </style></head><body>
    
    <div class='ibc-bar'>ÍNDICE BURSÁTIL CARACAS (IBC): {ultimo_ibc}</div>
    <div class='container'>
        <a href='/' class='btn'>« Volver a Pizarra</a>
        <div class='card'>
            <h2>{encab.get('DESC_SIMB', simbolo)} ({simbolo})</h2>
            <p>Precio: <b>{activo.get('PRECIO')}</b> | Var: <span style='color:{col}'>{activo.get('VAR_REL')}%</span></p>
            <p>Cap. Bs: {float(str(cap.get('CAPITALI_BS', 0)) or 0):,.2f}</p>
        </div>
        <div id='chart' style='background:white; padding:15px; border-radius:12px; margin:20px 0;'></div>
        <div class='card'>
            <h3>Libro de Órdenes</h3>
            <table>
                <tr><th>Vol. Compra</th><th>Precio Compra</th><th>Precio Venta</th><th>Vol. Venta</th></tr>
                {''.join([f"<tr><td class='bid'>{lib.get(f'VOL_CMP_{i+1}', '-')}</td><td class='bid'>{lib.get(f'PRE_CMP_{i+1}', '-')}</td><td class='ask'>{lib.get(f'PRE_VTA_{i+1}', '-')}</td><td class='ask'>{lib.get(f'VOL_VTA_{i+1}', '-')}</td></tr>" for i in range(6)])}
            </table>
        </div>
    </div>
    <script>
        var options = {{ series: [{{ data: {series_data} }}], chart: {{ type: 'candlestick', height: 350 }}, xaxis: {{ type: 'datetime' }} }};
        var chart = new ApexCharts(document.querySelector("#chart"), options);
        chart.render();
    </script>
    </body></html>
    """
    return HTMLResponse(html)

     
if __name__ == "__main__":
    # Render asigna el puerto automáticamente
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("servidor:app", host="0.0.0.0", port=port)