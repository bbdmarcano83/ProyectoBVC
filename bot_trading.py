import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
import logging
import requests
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

def patrulla_emergencia():
    for symbol in ASSETS:
        try:
            posiciones = exchange.fetch_positions([symbol])
            for pos in posiciones:
                if float(pos.get('contracts', 0)) > 0:
                    entry = float(pos['entry_price'])
                    mark = float(pos['mark_price'])
                    side_multiplier = 1 if pos['side'] == 'long' else -1
                    pnl_pct = ((mark - entry) / entry) * side_multiplier
                    
                    if pnl_pct <= -0.0205:
                        side_to_close = 'sell' if pos['side'] == 'long' else 'buy'
                        exchange.create_order(symbol, 'market', side_to_close, float(pos['contracts']))
                        msg = f"🚨 EMERGENCIA: Cierre forzado en {symbol}. Pérdida: {pnl_pct:.2%}"
                        logging.warning(msg)
                        enviar_telegram(msg)
        except Exception as e:
            logging.error(f"Error en patrulla {symbol}: {e}")

def ejecutar_estrategia():
    # --- MODIFICACIÓN QUIRÚRGICA: SEMÁFORO DE SEGURIDAD ---
    posiciones_abiertas = 0
    for symbol in ASSETS:
        try:
            p_list = exchange.fetch_positions([symbol])
            if any(float(p.get('contracts', 0)) > 0 for p in p_list):
                posiciones_abiertas += 1
        except: continue
    
    if posiciones_abiertas >= 2:
        logging.info(f"BLINDAJE: {posiciones_abiertas} operaciones activas. Máximo permitido alcanzado. OMITIENDO.")
        return 
    # -----------------------------------------------------

    try:
        balance = exchange.fetch_balance()['total']['USDC']
        monto_riesgo = balance * RIESGO_FIJO
    except Exception as e:
        logging.error(f"Error obteniendo balance: {e}")
        return

    for symbol in ASSETS:
        try:
            # Re-verificar posición individual
            posiciones = exchange.fetch_positions([symbol])
            if any(float(p.get('contracts', 0)) > 0 for p in posiciones):
                continue 

            df_1h = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', limit=200), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            df_5m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '5m', limit=50), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            
            if len(df_5m) < 14: continue
            
            ema200 = ta.ema(df_1h['c'], length=200).iloc[-1]
            rsi = ta.rsi(df_5m['c'], length=14).iloc[-1]
            wma = ta.wma(df_5m['c'], length=14).iloc[-1]
            price = df_5m['c'].iloc[-1]
            close_1h = df_1h['c'].iloc[-1]

            if pd.isna(rsi): continue

            side = 'buy' if (close_1h > ema200 and rsi < 30 and price > wma) else \
                   'sell' if (close_1h < ema200 and rsi > 70 and price < wma) else None
            
            if side:
                pos_size = (monto_riesgo / (price * PORCENTAJE_SL)) * APALANCAMIENTO
                exchange.create_order(symbol, 'market', side, pos_size, params={'leverage': APALANCAMIENTO})
                msg = f"🚀 ENTRADA ÚNICA: {side.upper()} en {symbol} | Tamaño: {pos_size:.4f}"
                logging.info(msg)
                enviar_telegram(msg)
                time.sleep(10) # Pausa estratégica tras abrir orden

        except Exception as e:
            logging.error(f"Error analizando {symbol}: {e}")

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True).start()
    logging.info("Bot iniciado. Monitoreando mercado...")
    while True:
        try:
            patrulla_emergencia()
            ejecutar_estrategia()
            time.sleep(30)
        except Exception as e:
            logging.critical(f"ERROR EN BUCLE PRINCIPAL: {e}")
            time.sleep(60)