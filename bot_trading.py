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
    """Verifica si han pasado al menos 30 minutos desde la última operación en este símbolo"""
    ahora = datetime.datetime.now()
    tiempo_transcurrido = (ahora - ultima_operacion.get(symbol, datetime.datetime.min)).total_seconds()
    return tiempo_transcurrido > 1800 # 1800 segundos = 30 minutos

def puede_operar(symbol):
    if symbol in ultima_operacion:
        tiempo_transcurrido = datetime.datetime.now() - ultima_operacion[symbol]
        return tiempo_transcurrido.total_seconds() > (COOLDOWN_MINUTOS * 60)
    return True

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

def ejecutar_operacion(symbol, side, pos_size):
    try:
        pos_size = float(exchange.amount_to_precision(symbol, pos_size))
        order = exchange.create_order(symbol, 'market', side, pos_size, params={'leverage': APALANCAMIENTO})
        
        if order.get('status') in ['closed', 'filled']:
            ultima_operacion[symbol] = datetime.datetime.now()
            return True, order
        return False, None
    except Exception as e:
        logging.error(f"Error ejecutando orden {symbol} {side}: {e}")
        return False, None

def actualizar_trailing_stop(symbol, pos):
    try:
        mark_price = float(pos['mark_price'])
        side = pos['side']
        if side == 'long':
            nuevo_sl = mark_price * (1 - PORCENTAJE_SL)
            if symbol not in trailing_stops or nuevo_sl > trailing_stops[symbol]:
                trailing_stops[symbol] = nuevo_sl
        else:
            nuevo_sl = mark_price * (1 + PORCENTAJE_SL)
            if symbol not in trailing_stops or nuevo_sl < trailing_stops[symbol]:
                trailing_stops[symbol] = nuevo_sl
    except Exception as e:
        logging.error(f"Error actualizando trailing stop {symbol}: {e}")

def patrulla_emergencia():
    try:
        # 1. Forzamos a Deribit a darnos las posiciones de la billetera USDC
        posiciones = exchange.fetch_positions(params={'currency': 'USDC'})
        
        for pos in posiciones:
            # 2. CRÍTICO: Detectar Shorts (números negativos) y buscar en 'size' si 'contracts' falta
            contratos = abs(float(pos.get('contracts', 0) or pos.get('size', 0)))
            
            if contratos > 0:
                symbol = pos['symbol']
                # Intentamos obtener el precio de entrada de varias formas
                entry = float(pos.get('entry_price', 0) or pos.get('average_price', 0))
                mark = float(pos.get('mark_price', 0))
                side = pos['side']
                
                # --- MEJORA CRÍTICA: Si el precio sigue siendo 0, lo buscamos en el historial ---
                if entry <= 0:
                    try:
                        # Buscamos la última orden cerrada de este símbolo para obtener el precio de ejecución
                        orders = exchange.fetch_closed_orders(symbol, limit=1)
                        if orders:
                            entry = float(orders[0]['price'])
                            logging.info(f"Recuperado precio histórico para {symbol}: {entry}")
                        else:
                            # Si no hay órdenes, avisamos y saltamos
                            logging.warning(f"No se pudo recuperar precio de entrada real para {symbol}")
                            continue
                    except Exception as e:
                        logging.error(f"Error recuperando historial para {symbol}: {e}")
                        continue

                # 3. Cálculo de PnL Porcentual
                side_mult = 1 if side == 'long' else -1
                pnl_pct = ((mark - entry) / entry) * side_mult
                
                # Log de monitoreo constante en Render
                logging.info(f"MONITOR {symbol}: PnL {pnl_pct:.2%} | Entry: {entry:.4f} | Mark: {mark:.4f}")

                # 4. LÓGICA DE CIERRE (Take Profit 6% / Stop Loss 2%)
                should_close = False
                msg_tipo = ""

                if pnl_pct >= 0.06:
                    should_close = True
                    msg_tipo = "💰 TAKE PROFIT"
                elif pnl_pct <= -0.02:
                    should_close = True
                    msg_tipo = "🚨 STOP LOSS"

                if should_close:
                    logging.warning(f"🎯 EJECUTANDO CIERRE {msg_tipo}: {symbol} al {pnl_pct:.2%}")
                    
                    # El lado de cierre es el opuesto al actual
                    side_to_close = 'sell' if side == 'long' else 'buy'
                    
                    # Usamos la cantidad exacta de contratos que tiene la posición
                    success, _ = ejecutar_operacion(symbol, side_to_close, contratos)
                    
                    if success:
                        enviar_telegram(f"{msg_tipo} EXITOSO: {symbol}\n📈 PnL: {pnl_pct:.2%}\n📉 Cantidad: {contratos}")
                        time.sleep(2) # Pausa breve entre cierres
                
    except Exception as e:
        logging.error(f"Error crítico en patrulla de emergencia: {e}")

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
                success, order = ejecutar_operacion(symbol, side, pos_size)
                
                if success:
                    enviar_telegram(f"✅ ORDEN EXITOSA: {side.upper()} {symbol}\n📊 RSI: {rsi:.2f}")
                    ultima_operacion[symbol] = datetime.datetime.now()
                    
                    # Pausa obligatoria para sincronización del exchange
                    logging.info("Esperando 20s para que Deribit actualice saldos...")
                    time.sleep(20)
                    return # Salida forzada para reiniciar el ciclo con datos frescos

        except Exception as e:
            logging.error(f"Error procesando {symbol}: {e}")
            time.sleep(2)

def limpiar_datos_antiguos():
    ahora = datetime.datetime.now()
    to_rem = [s for s, t in ultima_operacion.items() if (ahora - t).total_seconds() > 86400]
    for s in to_rem:
        del ultima_operacion[s]
        if s in trailing_stops: del trailing_stops[s]

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True).start()
    logging.info("🤖 Bot iniciado. Patrulla de alta frecuencia activa.")
    
    while True:
        try:
            # Primero: Protegemos ganancias/controlamos pérdidas
            patrulla_emergencia()
            
            # Segundo: Buscamos nuevas oportunidades
            ejecutar_estrategia()
            
            # Pausa breve para no saturar
            time.sleep(15)
        except Exception as e:
            logging.error(f"Error en bucle principal: {e}")
            time.sleep(30)