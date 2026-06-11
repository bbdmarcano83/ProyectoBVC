import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
import logging
import requests
import datetime
from flask import Flask
from threading import Thread

# Configuración de logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Inicialización del Exchange
exchange = ccxt.deribit({
    'apiKey': os.getenv('DERIBIT_TESTNET_CLIENT_ID'),
    'secret': os.getenv('DERIBIT_TESTNET_CLIENT_SECRET'),
    'sandbox': True,
    'enableRateLimit': True 
})
exchange.load_markets()

ASSETS = [
    'BTC_USDC-PERPETUAL', 'ETH_USDC-PERPETUAL', 'SOL_USDC-PERPETUAL', 'XRP_USDC-PERPETUAL', 
    'ADA_USDC-PERPETUAL', 'AVAX_USDC-PERPETUAL', 'DOGE_USDC-PERPETUAL', 'DOT_USDC-PERPETUAL', 
    'LINK_USDC-PERPETUAL', 'TRX_USDC-PERPETUAL'
]

# Parámetros Rígidos
RIESGO_FIJO = 0.02 
APALANCAMIENTO = 2
PORCENTAJE_SL = 0.02
TAKE_PROFIT_PCT = 0.06
MAX_VOLATILIDAD = 0.05
COOLDOWN_MINUTOS = 30

ultima_operacion = {}
trailing_stops = {}

app = Flask(__name__)

@app.route('/')
def keep_alive():
    return "Bot is running perfectly", 200

def enviar_telegram(mensaje):
    try:
        token = os.getenv('TELEGRAM_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': mensaje}
        # Usamos post con timeout para mayor estabilidad
        response = requests.post(url, json=payload, timeout=5)
        
        if response.status_code != 200:
            logging.error(f"Telegram respondió con error {response.status_code}: {response.text}")
        else:
            logging.info("Mensaje enviado a Telegram correctamente.")
            
    except Exception as e:
        logging.error(f"Error de red enviando Telegram: {e}")

import datetime
# Diccionario para controlar el cooldown por símbolo
ultima_operacion = {symbol: datetime.datetime.min for symbol in ASSETS}

def puede_operar(symbol):
    """Verifica si han pasado X minutos desde la última operación en este símbolo."""
    # Si el símbolo no ha operado nunca, devuelve True (puede operar)
    if symbol not in ultima_operacion:
        return True
    
    # Si ha operado, calcula el tiempo transcurrido
    tiempo_transcurrido = (datetime.datetime.now() - ultima_operacion[symbol]).total_seconds()
    
    return tiempo_transcurrido > (COOLDOWN_MINUTOS * 60)

def calcular_tamaño_posicion(symbol, balance_disponible, price):
    try:
        market = exchange.market(symbol)
        min_size = market['limits']['amount']['min']
        
        # 2% de riesgo sobre el disponible
        monto_riesgo = balance_disponible * RIESGO_FIJO
        
        # Cálculo de contratos
        pos_size = (monto_riesgo / (price * PORCENTAJE_SL)) * APALANCAMIENTO
        
        # Seguridad: Máximo 80% del disponible para dejar margen de fees
        max_size_seguro = (balance_disponible * 0.80) / price
        pos_size = min(pos_size, max_size_seguro)
        
        # Límites del exchange
        max_exch = market['limits']['amount']['max']
        if max_exch: 
            pos_size = min(pos_size, max_exch * 0.95)
        
        if pos_size < min_size: return 0
        return float(exchange.amount_to_precision(symbol, pos_size))
    except Exception as e:
        logging.error(f"Error calculando posición: {e}")
        return 0

def ejecutar_operacion(symbol, side, pos_size, price):
    """Ejecuta orden con TP/SL nativo de Deribit integrado."""
    try:
        is_long = (side == 'buy')
        tp_price = float(exchange.price_to_precision(symbol, price * (1 + TAKE_PROFIT_PCT if is_long else 1 - TAKE_PROFIT_PCT)))
        sl_price = float(exchange.price_to_precision(symbol, price * (1 - PORCENTAJE_SL if is_long else 1 + PORCENTAJE_SL)))
        amount = float(exchange.amount_to_precision(symbol, pos_size))

        params = {
            'leverage': APALANCAMIENTO,
            'stop_loss_price': sl_price,
            'take_profit_price': tp_price,
            'trigger': 'mark_price' 
        }
        
        logging.info(f"🚀 Enviando {side} {symbol} | SL: {sl_price} | TP: {tp_price}")
        order = exchange.create_order(symbol, 'market', side, amount, params=params)
        
        if order:
            return True, order
        return False, None
    except Exception as e:
        logging.error(f"Error crítico en apertura con TP/SL: {e}")
        return False, None

def ajustar_sl_nativo(symbol, nuevo_sl):
    try:
        open_orders = exchange.fetch_open_orders(symbol)
        for order in open_orders:
            if order.get('type') == 'stop_market' or order.get('stopPrice') is not None:
                exchange.edit_order(order['id'], symbol, 'stop_market', None, None, {'stopPrice': nuevo_sl})
                logging.info(f"🚀 Trailing aplicado en {symbol} a {nuevo_sl}")
                break
    except Exception as e:
        logging.debug(f"Ajuste SL omitido para {symbol}: {e}")

def actualizar_trailing_stop(symbol, pos):
    try:
        # Usamos mark_price del exchange si no está en el objeto pos
        mark_price = float(pos.get('mark_price') or exchange.fetch_ticker(symbol).get('mark', last_price)
        entry = float(pos.get('entry_price', 0))
        side = 'long' if float(pos.get('size', 0)) > 0 else 'short'
        
        umbral_cambio = 0.001 
        
        if side == 'long' and mark_price > entry * 1.01:
            nuevo_sl = mark_price * (1 - PORCENTAJE_SL)
            if symbol not in trailing_stops or nuevo_sl > (trailing_stops[symbol] * (1 + umbral_cambio)):
                trailing_stops[symbol] = nuevo_sl
        
        elif side == 'short' and mark_price < entry * 0.99:
            nuevo_sl = mark_price * (1 + PORCENTAJE_SL)
            if symbol not in trailing_stops or nuevo_sl < (trailing_stops[symbol] * (1 - umbral_cambio)):
                trailing_stops[symbol] = nuevo_sl
                
    except Exception as e:
        logging.error(f"Error cálculo trailing {symbol}: {e}")

def patrulla_emergencia():
    """El Corazón Centinela: Vigila posiciones, limpia huérfanas y cierra si falla el TP/SL nativo."""
    try:
        # 1. Obtener posiciones actuales
        posiciones = exchange.fetch_positions(params={'currency': 'USDC'})
        simbolos_con_posicion = [p['symbol'] for p in posiciones if abs(float(p.get('contracts', 0) or p.get('size', 0))) > 0]

        # 2. LIMPIEZA: Si no hay posición activa, eliminamos órdenes huérfanas
        for symbol in ASSETS:
            if symbol not in simbolos_con_posicion:
                limpiar_ordenes_huerfanas(symbol)

       # 3. MONITOREO y GESTIÓN DE POSICIONES
        for pos in posiciones:
            contratos = abs(float(pos.get('contracts', 0) or pos.get('size', 0)))
            if contratos <= 0: continue
            
            symbol = pos['symbol']
            side = pos['side']
            
            # Obtener datos de mercado
            ticker = exchange.fetch_ticker(symbol)
            last_price = float(ticker.get('last', 0))
            if last_price <= 0: continue
            
            # Obtener precio de entrada
            entry = float(pos.get('entry_price', 0) or pos.get('average_price', 0))
            if entry <= 0:
                orders = exchange.fetch_closed_orders(symbol, limit=1)
                if orders: entry = float(orders[0]['price'])
                else: continue

            # --- GESTIÓN DE TRAILING STOP ---
            # Actualiza el precio SL en memoria y lo aplica al Exchange
            actualizar_trailing_stop(symbol, pos)
            if symbol in trailing_stops:
                ajustar_sl_nativo(symbol, trailing_stops[symbol])

            # --- MONITOREO DE SEGURIDAD (Cierre Emergencia) ---
            pnl_pct = ((last_price - entry) / entry) * (1 if side == 'long' else -1)
            
            # Cierre de emergencia si se toca el TP/SL nativo o fallo
            if pnl_pct >= TAKE_PROFIT_PCT or pnl_pct <= -PORCENTAJE_SL:
                msg_tipo = "💰 TAKE PROFIT" if pnl_pct >= TAKE_PROFIT_PCT else "🚨 STOP LOSS"
                side_to_close = 'sell' if side == 'long' else 'buy'
                
                try:
                    order = exchange.create_order(symbol, 'market', side_to_close, contratos)
                    if order:
                        enviar_telegram(f"{msg_tipo} (Centinela) EJECUTADO\nActivo: {symbol}\nPnL: {pnl_pct:.2%}")
                        if symbol in trailing_stops: del trailing_stops[symbol] # Limpiar memoria
                        time.sleep(2)
                except Exception as e:
                    logging.error(f"Fallo cierre patrulla {symbol}: {e}")
    except Exception as e:
        logging.error(f"Error crítico en patrulla_emergencia: {e}")
    

def limpiar_ordenes_huerfanas(symbol):
    """Elimina órdenes pendientes de activos que no tienen posición abierta."""
    try:
        open_orders = exchange.fetch_open_orders(symbol)
        for order in open_orders:
            # Cancelamos si son órdenes trigger (nativas del exchange)
            if order.get('type') in ['stop_market', 'stop', 'take_profit'] or 'trigger' in str(order):
                exchange.cancel_order(order['id'], symbol)
                logging.info(f"🧹 Limpieza: Cancelada orden huérfana {order['id']} de {symbol}")
    except Exception as e:
        logging.error(f"Error en limpieza de {symbol}: {e}")

def validar_datos_tecnicos(df_1h, df_5m, symbol):
    if len(df_1h) < 200: return False
    if len(df_5m) < 80: return False
    return True

def filtrar_por_volatilidad(df_5m, price):
    try:
        atr = ta.atr(df_5m['h'], df_5m['l'], df_5m['c'], length=14).iloc[-1]
        vol_pct = atr / price
        return (vol_pct <= MAX_VOLATILIDAD), f"Volatilidad: {vol_pct:.2%}"
    except: return False, "Error Volatilidad"

def ejecutar_estrategia():
    # 1. CONTEO DE SEGURIDAD (Con corrección para Shorts y USDC)
    try:
        todas_las_posiciones = exchange.fetch_positions(params={'currency': 'USDC'})
        
        simbolos_activos = []
        for p in todas_las_posiciones:
            # CRÍTICO: Usamos abs() para que los Shorts (números negativos) se cuenten como activos
            cant = abs(float(p.get('contracts', 0) or p.get('size', 0)))
            if cant > 0:
                sym = p['symbol']
                if sym not in simbolos_activos:
                    simbolos_activos.append(sym)
        
        num_activos = len(simbolos_activos)
        logging.info(f"--- STATUS --- Activos Detectados: {num_activos} | Lista: {simbolos_activos}")
        
        # Bloqueo si ya hay 2 activos abiertos
        if num_activos >= 2:
            logging.info("Cupo lleno. Monitoreando posiciones existentes...")
            return 
            
    except Exception as e:
        logging.error(f"Error en fase de conteo: {e}")
        return

    # 2. BALANCE DISPONIBLE (Dinero líquido)
    try:
        full_balance = exchange.fetch_balance()
        balance_free = full_balance.get('free', {}).get('USDC', 0)
        logging.info(f"💰 Balance USDC Disponible: ${balance_free:.2f}")
        if balance_free <= 5: 
            return
    except Exception as e:
        logging.error(f"Error obteniendo balance: {e}")
        return

    # 3. BUCLE DE ANÁLISIS POR ACTIVO
    for symbol in ASSETS:
        # Si ya tenemos este activo abierto, saltar al siguiente
        if symbol in simbolos_activos: 
            continue

        try:
            # Descarga de datos (200 velas 1h, 100 velas 5m para evitar RSI NaN)
            df_1h = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', limit=200), columns=['t','o','h','l','c','v'])
            df_5m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '5m', limit=100), columns=['t','o','h','l','c','v'])
            
            if not validar_datos_tecnicos(df_1h, df_5m, symbol): 
                continue
            
            # Indicadores
            ema200 = ta.ema(df_1h['c'], length=200).iloc[-1]
            rsi = ta.rsi(df_5m['c'], length=14).iloc[-1]
            wma = ta.wma(df_5m['c'], length=14).iloc[-1]
            price = df_5m['c'].iloc[-1]
            close_1h = df_1h['c'].iloc[-1]

            # Auditoría técnica para Render
            logging.info(f"AUDITORÍA: {symbol} | Precio: {price} | RSI: {rsi:.2f} | EMA200: {ema200:.2f}")

            # Filtros de seguridad
            if not puede_operar(symbol): 
                continue
            if pd.isna(rsi) or pd.isna(ema200): 
                continue

            # Lógica de señales
            long_sig = (close_1h > ema200 and rsi < 30 and price > wma)
            short_sig = (close_1h < ema200 and rsi > 70 and price < wma)
            
            side = 'buy' if long_sig else 'sell' if short_sig else None
            if not side: 
                continue

            # 4. DOBLE CHECK FINAL (Antes de disparar la orden)
            check_final = exchange.fetch_positions(params={'currency': 'USDC'})
            # Buscamos si el símbolo apareció mágicamente en el último segundo
            ya_esta = any(p['symbol'] == symbol and abs(float(p.get('contracts', 0) or p.get('size', 0))) > 0 for p in check_final)
            if ya_esta: 
                continue

            # 5. EJECUCIÓN
            pos_size = calcular_tamaño_posicion(symbol, balance_free, price)
            
            if pos_size > 0:
                logging.warning(f"🚀 SEÑAL CONFIRMADA: {side} {symbol} Cant: {pos_size}")
                # AHORA SÍ pasamos el precio actual para que la orden lleve TP/SL nativo
                success, order = ejecutar_operacion(symbol, side, pos_size, price) 
                
                if success:
                    enviar_telegram(f"✅ ORDEN EXITOSA: {side.upper()} {symbol}\n📊 RSI: {rsi:.2f}")
                    ultima_operacion[symbol] = datetime.datetime.now()
                    
                    # Pausa obligatoria
                    logging.info("Esperando 20s para que Deribit actualice saldos...")
                    time.sleep(20)
                    return

        except Exception as e:
            logging.error(f"Error procesando {symbol}: {e}")
            time.sleep(2)

def limpiar_datos_antiguos():
    try:
        ahora = datetime.datetime.now()
        to_rem = [s for s, t in ultima_operacion.items() if (ahora - t).total_seconds() > 86400]
        for s in to_rem:
            if s in ultima_operacion: del ultima_operacion[s]
            if s in trailing_stops: del trailing_stops[s]
    except Exception as e:
        logging.error(f"Error limpiando datos antiguos: {e}")
         
def enviar_reporte_salud():
    try:
        balance = exchange.fetch_balance()
        usdc_free = balance.get('free', {}).get('USDC', 0)
        posiciones = exchange.fetch_positions(params={'currency': 'USDC'})
        num_pos = len([p for p in posiciones if float(p.get('size', 0)) > 0])
        
        mensaje = f"🤖 Bot Saludable\n💰 Balance Libre: {usdc_free:.2f} USDC\n📊 Posiciones: {num_pos}"
        enviar_telegram(mensaje)
    except Exception as e:
        logging.error(f"Error en reporte salud: {e}")

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True).start()
    logging.info("🤖 Bot iniciado. Patrulla con Last Price activa.")
    
    contador_salud = 0
    
    while True:
        try:
            # 1. Patrulla de emergencia (TP/SL)
            patrulla_emergencia()
            
            # 2. Ejecutar estrategia (Cuando esta abra operación, usa enviar_telegram)
            ejecutar_estrategia()
            
            # 3. Reporte de salud (Cada hora aprox: 240 ciclos * 15s = 3600s)
            contador_salud += 1
            if contador_salud >= 240: 
                enviar_reporte_salud()
                contador_salud = 0
            
            time.sleep(15)
        except Exception as e:
            logging.error(f"Error en bucle principal: {e}")
            time.sleep(60)