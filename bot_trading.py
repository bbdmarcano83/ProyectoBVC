import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

# Configuración de Exchange
exchange = ccxt.deribit({
    'apiKey': os.getenv('DERIBIT_CLIENT_ID'),
    'secret': os.getenv('DERIBIT_CLIENT_SECRET'),
})
exchange.load_markets()

ASSETS = ['BTC_USDC-PERPETUAL', 'ETH_USDC-PERPETUAL', 'SOL_USDC-PERPETUAL', 
          'XRP_USDC-PERPETUAL', 'ADA_USDC-PERPETUAL', 'AVAX_USDC-PERPETUAL', 
          'DOGE_USDC-PERPETUAL', 'DOT_USDC-PERPETUAL', 'LINK_USDC-PERPETUAL', 'TRX_USDC-PERPETUAL']

MAX_POSICIONES = 2
RIESGO_POR_OPERACION = 0.02

def get_data(symbol, timeframe, limit=200):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    return pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

def ejecutar_estrategia():
    balance = exchange.fetch_balance()['total']['USDC']
    monto_riesgo = balance * RIESGO_POR_OPERACION
    posiciones = exchange.fetch_positions()
    posiciones_abiertas = [p for p in posiciones if float(p['contracts']) > 0]
    
    # Lógica de Salida (Take Profit / Cambio de tendencia)
    for pos in posiciones_abiertas:
        symbol = pos['symbol']
        df_5m = get_data(symbol, '5m')
        rsi = ta.rsi(df_5m['close'], length=14).iloc[-1]
        
        # Cerrar LONG si RSI > 60, Cerrar SHORT si RSI < 40
        if (pos['side'] == 'long' and rsi > 60) or (pos['side'] == 'short' and rsi < 40):
            exchange.create_order(symbol, 'market', 'sell' if pos['side'] == 'long' else 'buy', pos['contracts'])
            print(f"Cerrada posición en {symbol} por cruce RSI.")

    # Lógica de Entrada
    if len(posiciones_abiertas) < MAX_POSICIONES:
        for symbol in ASSETS:
            if any(p['symbol'] == symbol for p in posiciones_abiertas): continue
            
            df_1h = get_data(symbol, '1h')
            ema200 = ta.ema(df_1h['close'], length=200).iloc[-1]
            df_5m = get_data(symbol, '5m')
            rsi = ta.rsi(df_5m['close'], length=14).iloc[-1]
            price = df_5m['close'].iloc[-1]
            wma = ta.wma(df_5m['close'], length=14).iloc[-1]

            # LONG
            if df_1h['close'].iloc[-1] > ema200 and rsi < 40 and price > wma:
                sl = df_5m['low'].iloc[-2]
                pos_size = monto_riesgo / abs(price - sl)
                exchange.create_order(symbol, 'market', 'buy', pos_size)
                print(f"LONG ejecutado en {symbol}")
            
            # SHORT
            elif df_1h['close'].iloc[-1] < ema200 and rsi > 60 and price < wma:
                sl = df_5m['high'].iloc[-2]
                pos_size = monto_riesgo / abs(price - sl)
                exchange.create_order(symbol, 'market', 'sell', pos_size)
                print(f"SHORT ejecutado en {symbol}")

# Bloque Flask para mantener vivo
app = Flask(__name__)
@app.route('/')
def home(): return "Bot activo"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()
    while True:
        ejecutar_estrategia()
        time.sleep(60)