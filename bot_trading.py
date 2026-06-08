import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
import logging
import requests
from flask import Flask
from threading import Thread

# Configuración de logs para auditoría total en Render
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

exchange = ccxt.deribit({
    'apiKey': os.getenv('DERIBIT_TESTNET_CLIENT_ID'),
    'secret': os.getenv('DERIBIT_TESTNET_CLIENT_SECRET'),
    'sandbox': True
})
exchange.load_markets()

ASSETS = ['BTC_USDC-PERPETUAL', 'ETH_USDC-PERPETUAL', 'SOL_USDC-PERPETUAL', 'XRP_USDC-PERPETUAL', 
          'ADA_USDC-PERPETUAL', 'AVAX_USDC-PERPETUAL', 'DOGE_USDC-PERPETUAL', 'DOT_USDC-PERPETUAL', 
          'LINK_USDC-PERPETUAL', 'TRX_USDC-PERPETUAL']

# Parámetros estrictos
RIESGO_FIJO = 0.02 
APALANCAMIENTO = 2
PORCENTAJE_SL = 0.02 

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/sendMessage"
        requests.get(url, params={'chat_id': os.getenv('TELEGRAM_CHAT_ID'), 'text': mensaje}, timeout=5)
    except Exception as e:
        logging.error(f"Error Telegram: {e}")

def patrulla_emergencia():
    """Vigilante: Cierra cualquier pérdida > 2.05% inmediatamente."""
    for symbol in ASSETS:
        try:
            posiciones = exchange.fetch_positions([symbol])
            for pos in posiciones:
                if float(pos['contracts']) > 0:
                    entry = float(pos['entry_price'])
                    mark = float(pos['mark_price'])
                    pnl_pct = (mark - entry) / entry
                    if pos['side'] == 'short': pnl_pct = -pnl_pct
                    
                    if pnl_pct <= -0.0205: # Stop de emergencia
                        side_to_close = 'sell' if pos['side'] == 'long' else 'buy'
                        exchange.create_order(symbol, 'market', side_to_close, float(pos['contracts']))
                        msg = f"🚨 EMERGENCIA: Cierre forzado en {symbol}. Pérdida real: {pnl_pct:.2%}"
                        logging.warning(msg)
                        enviar_telegram(msg)
        except Exception as e:
            logging.error(f"Error en patrulla {symbol}: {e}")

def ejecutar_estrategia():
    balance = exchange.fetch_balance()['total']['USDC']
    monto_riesgo = balance * RIESGO_FIJO

    for symbol in ASSETS:
        try:
            # 1. FILTRO DE POSICIÓN ÚNICA: Bloqueo de entrada si ya hay algo abierto
            # Esta es la capa que evita el "bucle de entrada"
            posiciones = exchange.fetch_positions([symbol])
            if any(float(p['contracts']) > 0 for p in posiciones):
                logging.info(f"Omitiendo {symbol}: Posición ya abierta. Protegiendo capital.")
                continue 

            # 2. Análisis técnico
            df_1h = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', limit=200), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            df_5m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '5m', limit=50), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            
            ema200 = ta.ema(df_1h['c'], length=200).iloc[-1]
            rsi = ta.rsi(df_5m['c'], length=14).iloc[-1]
            wma = ta.wma(df_5m['c'], length=14).iloc[-1]
            price = df_5m['c'].iloc[-1]
            close_1h = df_1h['c'].iloc[-1]

            # 3. Take Profit dinámico (RSI 70/30)
            for pos in posiciones:
                if float(pos['contracts']) > 0:
                    pnl = (float(pos['mark_price']) - float(pos['entry_price'])) / float(pos['entry_price'])
                    if pos['side'] == 'short': pnl = -pnl
                    if (pos['side'] == 'long' and rsi < 30 and pnl > 0) or (pos['side'] == 'short' and rsi > 70 and pnl > 0):
                        side_close = 'sell' if pos['side'] == 'long' else 'buy'
                        exchange.create_order(symbol, 'market', side_close, float(pos['contracts']))
                        enviar_telegram(f"✅ TAKE PROFIT RSI en {symbol} | Ganancia: {pnl:.2%}")

            # 4. Entrada estricta (Solo si no hubo continue antes)
            side = 'buy' if (close_1h > ema200 and rsi < 30 and price > wma) else \
                   'sell' if (close_1h < ema200 and rsi > 70 and price < wma) else None
            
            if side:
                pos_size = (monto_riesgo / (price * PORCENTAJE_SL)) * APALANCAMIENTO
                exchange.create_order(symbol, 'market', side, pos_size, params={'leverage': APALANCAMIENTO})
                logging.info(f"🚀 ENTRADA ÚNICA: {side.upper()} en {symbol} con 2x")
                enviar_telegram(f"🚀 Entrada única {side.upper()} en {symbol}")

        except Exception as e:
            logging.error(f"Error analizando {symbol}: {e}")

if __name__ == "__main__":
    Thread(target=lambda: Flask(__name__).run(host='0.0.0.0', port=8080), daemon=True).start()
    while True:
        patrulla_emergencia()
        ejecutar_estrategia()
        time.sleep(30)