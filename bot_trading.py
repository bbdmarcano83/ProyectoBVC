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
        url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/sendMessage"
        requests.get(url, params={'chat_id': os.getenv('TELEGRAM_CHAT_ID'), 'text': mensaje}, timeout=5)
    except Exception as e:
        logging.error(f"Error enviando Telegram: {e}")

def puede_operar(symbol):
    if symbol in ultima_operacion:
        tiempo_transcurrido = datetime.datetime.now() - ultima_operacion[symbol]
        return tiempo_transcurrido.total_seconds() > (COOLDOWN_MINUTOS * 60)
    return True

def calcular_tamaño_posicion(symbol, balance, price):
    try:
        market = exchange.market(symbol)
        min_size = market['limits']['amount']['min']
        max_size_exch = market['limits']['amount']['max']
        
        monto_riesgo = balance * RIESGO_FIJO
        pos_size = (monto_riesgo / (price * PORCENTAJE_SL)) * APALANCAMIENTO
        
        if max_size_exch:
            pos_size = min(pos_size, max_size_exch * 0.95)
            
        max_size_balance = (balance * 0.25) / price
        pos_size = min(pos_size, max_size_balance)
        
        if pos_size < min_size: return 0
        
        return float(exchange.amount_to_precision(symbol, pos_size))
    except Exception as e:
        logging.error(f"Error calculando posición {symbol}: {e}")
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
    for symbol in ASSETS:
        try:
            posiciones = exchange.fetch_positions([symbol])
            for pos in posiciones:
                if float(pos.get('contracts', 0)) > 0:
                    entry, mark, side = float(pos['entry_price']), float(pos['mark_price']), pos['side']
                    side_mult = 1 if side == 'long' else -1
                    pnl_pct = ((mark - entry) / entry) * side_mult
                    
                    actualizar_trailing_stop(symbol, pos)
                    
                    if pnl_pct >= TAKE_PROFIT_PCT:
                        side_close = 'sell' if side == 'long' else 'buy'
                        if ejecutar_operacion(symbol, side_close, float(pos['contracts']))[0]:
                            enviar_telegram(f"💰 TP: {symbol} {pnl_pct:.2%}")
                            if symbol in trailing_stops: del trailing_stops[symbol]
                        continue
                    
                    stop_triggered = False
                    if pnl_pct <= -0.0205:
                        stop_triggered, msg = True, "🚨 EMERGENCIA"
                    elif symbol in trailing_stops:
                        if (side == 'long' and mark <= trailing_stops[symbol]) or \
                           (side == 'short' and mark >= trailing_stops[symbol]):
                            stop_triggered, msg = True, "📉 TRAILING"
                    
                    if stop_triggered:
                        side_close = 'sell' if side == 'long' else 'buy'
                        if ejecutar_operacion(symbol, side_close, float(pos['contracts']))[0]:
                            enviar_telegram(f"{msg}: {symbol} {pnl_pct:.2%}")
                            if symbol in trailing_stops: del trailing_stops[symbol]
        except Exception as e: logging.error(f"Error patrulla {symbol}: {e}")

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
    pos_activas = 0
    for s in ASSETS:
        try:
            if any(float(p.get('contracts', 0)) > 0 for p in exchange.fetch_positions([s])): pos_activas += 1
        except: continue
    
    if pos_activas >= 2: return 

    try:
        balance = exchange.fetch_balance()['total']['USDC']
        if balance <= 10: return
    except: return

    for symbol in ASSETS:
        try:
            if not puede_operar(symbol): continue
            
            df_1h = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', limit=200), columns=['t','o','h','l','c','v'])
            df_5m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '5m', limit=100), columns=['t','o','h','l','c','v'])
            
            if not validar_datos_tecnicos(df_1h, df_5m, symbol): continue
            
            ema200 = ta.ema(df_1h['c'], length=200).iloc[-1]
            rsi = ta.rsi(df_5m['c'], length=14).iloc[-1]
            wma = ta.wma(df_5m['c'], length=14).iloc[-1]
            price, close_1h = df_5m['c'].iloc[-1], df_1h['c'].iloc[-1]

            logging.info(f"AUDITORÍA: {symbol} -> Precio: {price}, RSI: {rsi}, EMA: {ema200}")

            if pd.isna(rsi) or pd.isna(ema200): continue

            vol_ok, vol_msg = filtrar_por_volatilidad(df_5m, price)
            if not vol_ok: continue

            long_signal = (close_1h > ema200 and rsi < 30 and price > wma)
            short_signal = (close_1h < ema200 and rsi > 70 and price < wma)
            
            if long_signal: side, strength = 'buy', "LONG (RSI < 30)"
            elif short_signal: side, strength = 'sell', "SHORT (RSI > 70)"
            else: continue
            
            pos_size = calcular_tamaño_posicion(symbol, balance, price)
            if pos_size > 0:
                success, order = ejecutar_operacion(symbol, side, pos_size)
                if success:
                    enviar_telegram(f"🚀 ENTRADA: {side.upper()} {symbol}\n📊 {strength}\n📈 {vol_msg}")
                    time.sleep(10)
        except Exception as e: logging.error(f"Error analizando {symbol}: {e}")

def limpiar_datos_antiguos():
    ahora = datetime.datetime.now()
    to_rem = [s for s, t in ultima_operacion.items() if (ahora - t).total_seconds() > 86400]
    for s in to_rem:
        del ultima_operacion[s]
        if s in trailing_stops: del trailing_stops[s]

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True).start()
    logging.info("🤖 Bot iniciado con todas las capas originales + correcciones.")
    
    ciclos = 0
    while True:
        try:
            patrulla_emergencia()
            ejecutar_estrategia()
            ciclos += 1
            if ciclos % 100 == 0: limpiar_datos_antiguos()
            time.sleep(30)
        except Exception as e:
            logging.critical(f"Error bucle: {e}")
            time.sleep(60)