import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
import logging
import requests
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

load_dotenv()

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# --- CONFIGURACIÓN MODO SIMULACIÓN ---
MODO_SIMULACION = True 

exchange = ccxt.deribit({
    'apiKey': os.getenv('DERIBIT_TESTNET_CLIENT_ID') if MODO_SIMULACION else os.getenv('DERIBIT_CLIENT_ID'),
    'secret': os.getenv('DERIBIT_TESTNET_CLIENT_SECRET') if MODO_SIMULACION else os.getenv('DERIBIT_CLIENT_SECRET'),
    'sandbox': MODO_SIMULACION
})
exchange.load_markets()

# Variables de Control
ASSETS = ['BTC_USDC-PERPETUAL', 'ETH_USDC-PERPETUAL', 'SOL_USDC-PERPETUAL', 'XRP_USDC-PERPETUAL', 'ADA_USDC-PERPETUAL', 'AVAX_USDC-PERPETUAL', 'DOGE_USDC-PERPETUAL', 'DOT_USDC-PERPETUAL', 'LINK_USDC-PERPETUAL', 'TRX_USDC-PERPETUAL']
RIESGO_FIJO = 0.02 # 2% de Riesgo Fijo
APALANCAMIENTO = 2
PORCENTAJE_SL = 0.02 # Stop Loss fijo al 2%

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/sendMessage?chat_id={os.getenv('TELEGRAM_CHAT_ID')}&text={mensaje}"
        requests.get(url)
    except Exception as e:
        logging.error(f"Error Telegram: {e}")

def tiene_posicion_abierta(symbol):
    try:
        positions = exchange.fetch_positions([symbol])
        return any(float(pos['contracts']) > 0 for pos in positions)
    except: return True

def ejecutar_estrategia():
    try:
        balance = exchange.fetch_balance()['total']['USDC']
        if balance < 10: return
        monto_riesgo = balance * RIESGO_FIJO

        for symbol in ASSETS:
            # 1. TENDENCIA (1 Hora)
            df_1h = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', limit=200), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            ema200 = ta.ema(df_1h['c'], length=200).iloc[-1]
            close_1h = df_1h['c'].iloc[-1]

            # 2. GATILLO (5 Minutos)
            df_5m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '5m', limit=50), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            rsi = ta.rsi(df_5m['c'], length=14).iloc[-1]
            wma = ta.wma(df_5m['c'], length=14).iloc[-1]
            price = df_5m['c'].iloc[-1]

            # 3. SEGURIDAD (No sobre-operar)
            if tiene_posicion_abierta(symbol): continue

            # 4. LÓGICA DE ENTRADA
            side = None
            if close_1h > ema200 and rsi < 40 and price > wma: # LONG
                side = 'buy'
            elif close_1h < ema200 and rsi > 60 and price < wma: # SHORT
                side = 'sell'

            if side:
                # Gestión de Riesgo: SL al 2% fijo
                # Distancia SL = Precio * 0.02
                dist_sl = price * PORCENTAJE_SL
                pos_size = (monto_riesgo / dist_sl) * APALANCAMIENTO
                
                order = exchange.create_order(symbol, 'market', side, pos_size, params={'leverage': APALANCAMIENTO})
                enviar_telegram(f"🚀 Entrada {side.upper()} en {symbol} | SL al 2% | Tamaño: {pos_size:.4f}")
                logging.info(f"Orden ejecutada: {symbol}")
    except Exception as e:
        logging.error(f"Error ciclo: {e}")

app = Flask(__name__)
@app.route('/')
def home(): return "Bot Operativo - Tendencia + SL Fijo 2%"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()
    while True:
        ejecutar_estrategia()
        time.sleep(60)