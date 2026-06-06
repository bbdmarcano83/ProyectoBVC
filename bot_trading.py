import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
import logging
from threading import Thread
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Configuración de Exchange
exchange = ccxt.deribit({
    'apiKey': os.getenv('DERIBIT_CLIENT_ID'),
    'secret': os.getenv('DERIBIT_CLIENT_SECRET'),
})
exchange.load_markets()

ASSETS = [
    'BTC_USDC-PERPETUAL', 'ETH_USDC-PERPETUAL', 'SOL_USDC-PERPETUAL', 
    'XRP_USDC-PERPETUAL', 'ADA_USDC-PERPETUAL', 'AVAX_USDC-PERPETUAL', 
    'DOGE_USDC-PERPETUAL', 'DOT_USDC-PERPETUAL', 'LINK_USDC-PERPETUAL', 'TRX_USDC-PERPETUAL'
]

# Configuración Estrategia
RIESGO_POR_OPERACION = 0.02
APALANCAMIENTO = 5
MAX_OPERACIONES = 2
posiciones_abiertas = {} # Estado: {symbol: {'tipo': 'LONG/SHORT', 'entrada': price, 'sl': sl, 'be': False}}

def get_data(symbol, timeframe, limit=200):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    return pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

def ejecutar_estrategia():
    balance = exchange.fetch_balance()['total']['USDC']
    monto_riesgo = balance * RIESGO_POR_OPERACION
    
    for symbol in ASSETS:
        try:
            # Análisis de datos
            df_1h = get_data(symbol, '1h')
            ema200 = ta.ema(df_1h['close'], length=200).iloc[-1]
            close_1h = df_1h['close'].iloc[-1]
            
            df_5m = get_data(symbol, '5m')
            rsi = ta.rsi(df_5m['close'], length=14).iloc[-1]
            wma = ta.wma(df_5m['close'], length=14).iloc[-1]
            price = df_5m['close'].iloc[-1]

            print(f"[{symbol}] RSI: {rsi:.2f} | Precio: {price:.2f} | WMA: {wma:.2f}")

            # --- GESTIÓN DE POSICIONES ABIERTAS ---
            if symbol in posiciones_abiertas:
                pos = posiciones_abiertas[symbol]
                # 1. Break Even (Ratio 1:1)
                dist_inicial = abs(pos['entrada'] - pos['sl'])
                if not pos['be']:
                    if (pos['tipo'] == 'LONG' and price >= pos['entrada'] + dist_inicial) or \
                       (pos['tipo'] == 'SHORT' and price <= pos['entrada'] - dist_inicial):
                        pos['be'] = True
                        logging.info(f"[{symbol}] BE activado. SL movido a {pos['entrada']}")
                
                # 2. Cierre por RSI (Salida)
                if (pos['tipo'] == 'LONG' and rsi > 60 and price < wma) or \
                   (pos['tipo'] == 'SHORT' and rsi < 40 and price > wma):
                    logging.info(f"[{symbol}] Cierre de posición por RSI. Precio: {price}")
                    del posiciones_abiertas[symbol]
                    continue

            # --- NUEVAS ENTRADAS ---
            if symbol not in posiciones_abiertas and len(posiciones_abiertas) < MAX_OPERACIONES:
                # LONG
                if close_1h > ema200 and rsi < 40 and price > wma:
                    sl = df_5m['low'].iloc[-2]
                    dist = abs(price - sl)
                    if dist > 0:
                        pos_size = (monto_riesgo / dist) * APALANCAMIENTO
                        posiciones_abiertas[symbol] = {'tipo': 'LONG', 'entrada': price, 'sl': sl, 'be': False}
                        logging.info(f"SEÑAL LONG en {symbol} | Apalancado {APALANCAMIENTO}x | Tamaño: {pos_size:.4f}")
                
                # SHORT
                elif close_1h < ema200 and rsi > 60 and price < wma:
                    sl = df_5m['high'].iloc[-2]
                    dist = abs(price - sl)
                    if dist > 0:
                        pos_size = (monto_riesgo / dist) * APALANCAMIENTO
                        posiciones_abiertas[symbol] = {'tipo': 'SHORT', 'entrada': price, 'sl': sl, 'be': False}
                        logging.info(f"SEÑAL SHORT en {symbol} | Apalancado {APALANCAMIENTO}x | Tamaño: {pos_size:.4f}")

        except Exception as e:
            print(f"Error analizando {symbol}: {e}")

def main():
    print("Bot Iniciado en modo Vigilancia Continua...")
    while True:
        try:
            ejecutar_estrategia()
            print(f"Ciclo completado. Esperando 60 segundos...")
            time.sleep(60)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error en el ciclo: {e}")
            time.sleep(30)

# --- SERVIDOR WEB RENDER ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot de Deribit activo y operando"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()
    main()