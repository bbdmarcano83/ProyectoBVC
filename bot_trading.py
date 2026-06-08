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

# Configuración
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# MODO: Cambia a False para operar en Real
MODO_SIMULACION = True 

exchange = ccxt.deribit({
    'apiKey': os.getenv('DERIBIT_TESTNET_CLIENT_ID') if MODO_SIMULACION else os.getenv('DERIBIT_CLIENT_ID'),
    'secret': os.getenv('DERIBIT_TESTNET_CLIENT_SECRET') if MODO_SIMULACION else os.getenv('DERIBIT_CLIENT_SECRET'),
    'sandbox': MODO_SIMULACION
})
exchange.load_markets()

# LOS 10 ACTIVOS LÍQUIDOS CONFIGURADOS
ASSETS = ['BTC_USDC-PERPETUAL', 'ETH_USDC-PERPETUAL', 'SOL_USDC-PERPETUAL', 'XRP_USDC-PERPETUAL', 'ADA_USDC-PERPETUAL', 
          'AVAX_USDC-PERPETUAL', 'DOGE_USDC-PERPETUAL', 'DOT_USDC-PERPETUAL', 'LINK_USDC-PERPETUAL', 'TRX_USDC-PERPETUAL']

RIESGO_FIJO = 0.02 
APALANCAMIENTO = 2
PORCENTAJE_SL = 0.02 # 2% Rígido

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/sendMessage?chat_id={os.getenv('TELEGRAM_CHAT_ID')}&text={mensaje}"
        requests.get(url)
    except Exception as e:
        logging.error(f"Error Telegram: {e}")

def gestionar_posiciones():
    for symbol in ASSETS:
        try:
            positions = exchange.fetch_positions([symbol])
            df_5m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '5m', limit=50), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            rsi = ta.rsi(df_5m['c'], length=14).iloc[-1]
            
            for pos in positions:
                contracts = float(pos['contracts'])
                if contracts > 0:
                    entry_price = float(pos['entry_price'])
                    current_price = float(pos['mark_price'])
                    pnl_pct = (current_price - entry_price) / entry_price
                    if pos['side'] == 'short': pnl_pct = -pnl_pct
                    
                    # 1. Take Profit Técnico (Cruce de RSI)
                    if (pos['side'] == 'long' and rsi < 60 and pnl_pct > 0) or \
                       (pos['side'] == 'short' and rsi > 40 and pnl_pct > 0):
                        side_to_close = 'sell' if pos['side'] == 'long' else 'buy'
                        exchange.create_order(symbol, 'market', side_to_close, contracts)
                        enviar_telegram(f"✅ TAKE PROFIT RSI en {symbol} | Ganancia: {pnl_pct:.2%}")
        except Exception as e:
            logging.error(f"Error gestión {symbol}: {e}")

def ejecutar_estrategia():
    try:
        balance = exchange.fetch_balance()['total']['USDC']
        if balance < 10: return
        monto_riesgo = balance * RIESGO_FIJO

        for symbol in ASSETS:
            # Análisis de Tendencia (1H)
            df_1h = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', limit=200), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            ema200 = ta.ema(df_1h['c'], length=200).iloc[-1]
            close_1h = df_1h['c'].iloc[-1]

            # Análisis de Gatillo (5M)
            df_5m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '5m', limit=50), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            rsi = ta.rsi(df_5m['c'], length=14).iloc[-1]
            wma = ta.wma(df_5m['c'], length=14).iloc[-1]
            price = df_5m['c'].iloc[-1]

            if any(float(p['contracts']) > 0 for p in exchange.fetch_positions([symbol])): continue

            side = 'buy' if (close_1h > ema200 and rsi < 40 and price > wma) else 'sell' if (close_1h < ema200 and rsi > 60 and price < wma) else None
            
            if side:
                sl_price = price * (1 - PORCENTAJE_SL) if side == 'buy' else price * (1 + PORCENTAJE_SL)
                pos_size = (monto_riesgo / (price * PORCENTAJE_SL)) * APALANCAMIENTO
                
                # Orden con Stop Loss Adjunto en el Exchange
                exchange.create_order(symbol, 'market', side, pos_size, params={
                    'leverage': APALANCAMIENTO,
                    'stop_loss': {'type': 'stop_market', 'stop_price': sl_price, 'reduce_only': True}
                })
                enviar_telegram(f"🚀 Entrada {side.upper()} {symbol} | SL Adjunto 2% en {sl_price:.4f}")
    except Exception as e:
        logging.error(f"Error ciclo: {e}")

app = Flask(__name__)
@app.route('/')
def home(): return "Bot Operativo - Modo Autogestión RSI + SL 2%"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()
    while True:
        ejecutar_estrategia()
        gestionar_posiciones()
        time.sleep(60)