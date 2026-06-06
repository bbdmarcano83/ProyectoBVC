import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

# --- CONFIGURACIÓN TÉCNICA ---
MODO_REAL = False 
APALANCAMIENTO = 5
RIESGO_POR_OPERACION = 0.02
MAX_POSICIONES = 2  # <--- LÍMITE DE SEGURIDAD

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
        
        # 1. GESTIÓN DE SALIDA (RSI Dinámico)
        for pos in posiciones:
            df_5m = get_data(pos['symbol'], '5m')
            rsi = ta.rsi(df_5m['close'], length=14).iloc[-1]
            rsi_ant = ta.rsi(df_5m['close'], length=14).iloc[-2]
            
            if (pos['side'] == 'long' and rsi_ant > 60 and rsi < 60) or \
               (pos['side'] == 'short' and rsi_ant < 40 and rsi > 40):
                print(f"SALIDA TÉCNICA: {pos['symbol']} por RSI.")
                if MODO_REAL: exchange.create_order(pos['symbol'], 'market', 'sell' if pos['side'] == 'long' else 'buy', pos['contracts'])

        # 2. ANÁLISIS Y ENTRADA (Validando límite de 2 posiciones)
        if len(posiciones) < MAX_POSICIONES:
            print(f"Posiciones abiertas: {len(posiciones)}/{MAX_POSICIONES}. Buscando oportunidades...")
            
            for symbol in ASSETS:
                # Comprobar si ya tenemos posición en este activo
                if any(p['symbol'] == symbol for p in posiciones): continue
                
                df_1h, df_5m = get_data(symbol, '1h'), get_data(symbol, '5m')
                ema200 = ta.ema(df_1h['close'], length=200).iloc[-1]
                rsi, price, wma = ta.rsi(df_5m['close'], length=14).iloc[-1], df_5m['close'].iloc[-1], ta.wma(df_5m['close'], length=14).iloc[-1]
                
                print(f"Analizando: {symbol} | RSI: {rsi:.2f} | Precio: {price:.2f}")
                
                exchange.set_leverage(APALANCAMIENTO, symbol)
                
                # LÓGICA LONG
                if df_1h['close'].iloc[-1] > ema200 and rsi < 40 and price > wma:
                    sl = df_5m['low'].iloc[-2]
                    pos_size = monto_riesgo / abs(price - sl)
                    print(f"DISPARO LONG {symbol} | Tamaño: {pos_size:.4f}")
                    if MODO_REAL: exchange.create_order(symbol, 'market', 'buy', pos_size)
                    # Actualizamos posiciones para no superar el límite en este mismo ciclo
                    posiciones.append({'symbol': symbol})
                    if len(posiciones) >= MAX_POSICIONES: break
                
                # LÓGICA SHORT
                elif df_1h['close'].iloc[-1] < ema200 and rsi > 60 and price < wma:
                    sl = df_5m['high'].iloc[-2]
                    pos_size = monto_riesgo / abs(price - sl)
                    print(f"DISPARO SHORT {symbol} | Tamaño: {pos_size:.4f}")
                    if MODO_REAL: exchange.create_order(symbol, 'market', 'sell', pos_size)
                    posiciones.append({'symbol': symbol})
                    if len(posiciones) >= MAX_POSICIONES: break
        else:
            print(f"Límite de {MAX_POSICIONES} posiciones alcanzado. Esperando salida...")

    except Exception as e:
        print(f"Error en ejecución: {e}")

# Servidor Flask para Render
app = Flask(__name__)
@app.route('/')
def home(): return "Bot activo"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()
    while True:
        ejecutar_estrategia()
        time.sleep(60)