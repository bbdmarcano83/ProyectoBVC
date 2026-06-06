import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- CONFIGURACIÓN ---
MODO_REAL = False  # <--- CAMBIA A True SOLO CUANDO QUIERAS OPERAR EN REAL
APALANCAMIENTO = 5
RIESGO_POR_OPERACION = 0.02
MAX_POSICIONES = 2

load_dotenv()
exchange = ccxt.deribit({
    'apiKey': os.getenv('DERIBIT_CLIENT_ID'),
    'secret': os.getenv('DERIBIT_CLIENT_SECRET'),
})
exchange.load_markets()

ASSETS = ['BTC_USDC-PERPETUAL', 'ETH_USDC-PERPETUAL', 'SOL_USDC-PERPETUAL', 
          'XRP_USDC-PERPETUAL', 'ADA_USDC-PERPETUAL', 'AVAX_USDC-PERPETUAL', 
          'DOGE_USDC-PERPETUAL', 'DOT_USDC-PERPETUAL', 'LINK_USDC-PERPETUAL', 'TRX_USDC-PERPETUAL']

def get_data(symbol, timeframe, limit=200):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    return pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

def ejecutar_estrategia():
    try:
        balance = exchange.fetch_balance()['total']['USDC']
        monto_riesgo = balance * RIESGO_POR_OPERACION
        posiciones = [p for p in exchange.fetch_positions() if float(p['contracts']) > 0]
        
        # SALIDA DINÁMICA (RSI y Break Even)
        for pos in posiciones:
            df_5m = get_data(pos['symbol'], '5m')
            rsi = ta.rsi(df_5m['close'], length=14).iloc[-1]
            rsi_ant = ta.rsi(df_5m['close'], length=14).iloc[-2]
            
            if (pos['side'] == 'long' and rsi_ant > 60 and rsi < 60) or \
               (pos['side'] == 'short' and rsi_ant < 40 and rsi > 40):
                if MODO_REAL: exchange.create_order(pos['symbol'], 'market', 'sell' if pos['side'] == 'long' else 'buy', pos['contracts'])
                print(f"CERRADA posición en {pos['symbol']} por RSI.")

        # ENTRADA
        if len(posiciones) < MAX_POSICIONES:
            for symbol in ASSETS:
                if any(p['symbol'] == symbol for p in posiciones): continue
                df_1h, df_5m = get_data(symbol, '1h'), get_data(symbol, '5m')
                ema200 = ta.ema(df_1h['close'], length=200).iloc[-1]
                rsi, price, wma = ta.rsi(df_5m['close'], length=14).iloc[-1], df_5m['close'].iloc[-1], ta.wma(df_5m['close'], length=14).iloc[-1]
                
                exchange.set_leverage(APALANCAMIENTO, symbol)
                
                # LONG
                if df_1h['close'].iloc[-1] > ema200 and rsi < 40 and price > wma:
                    sl = df_5m['low'].iloc[-2]
                    size = monto_riesgo / abs(price - sl)
                    if MODO_REAL: exchange.create_order(symbol, 'market', 'buy', size)
                    else: print(f"SIMULACIÓN: BUY {size} en {symbol} (5x)")
                
                # SHORT
                elif df_1h['close'].iloc[-1] < ema200 and rsi > 60 and price < wma:
                    sl = df_5m['high'].iloc[-2]
                    size = monto_riesgo / abs(price - sl)
                    if MODO_REAL: exchange.create_order(symbol, 'market', 'sell', size)
                    else: print(f"SIMULACIÓN: SELL {size} en {symbol} (5x)")
    except Exception as e: print(f"Error: {e}")

# Servidor Flask
app = Flask(__name__)
@app.route('/')
def home(): return "Bot activo"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()
    while True:
        ejecutar_estrategia()
        time.sleep(60)