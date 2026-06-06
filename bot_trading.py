import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
from dotenv import load_dotenv

load_dotenv()

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

RIESGO_POR_OPERACION = 0.02  # 2% de riesgo fijo

def get_data(symbol, timeframe, limit=200):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def ejecutar_estrategia():
    balance = exchange.fetch_balance()['total']['USDC']
    monto_riesgo = balance * RIESGO_POR_OPERACION
    
    for symbol in ASSETS:
        print(f"Analizando: {symbol}...")
        try:
            # 1. Filtro Macro (1H)
            df_1h = get_data(symbol, '1h')
            ema200 = ta.ema(df_1h['close'], length=200).iloc[-1]
            close_1h = df_1h['close'].iloc[-1]
            
            # 2. Análisis Ejecución (5m)
            df_5m = get_data(symbol, '5m')
            rsi = ta.rsi(df_5m['close'], length=14).iloc[-1]
            wma = ta.wma(df_5m['close'], length=14).iloc[-1] # Media Móvil Ponderada
            price = df_5m['close'].iloc[-1]

            print(f"[{symbol}] RSI: {rsi:.2f} | Precio: {price:.2f} | WMA: {wma:.2f}")
            # 3. Lógica de Disparo
            # LONG: Tendencia Alcista + RSI < 40 + Precio > WMA
            if close_1h > ema200 and rsi < 40 and price > wma:
                sl = df_5m['low'].iloc[-2] # Mínimo anterior
                dist = abs(price - sl)
                if dist > 0:
                    pos_size = monto_riesgo / dist
                    print(f"SEÑAL LONG en {symbol} | Precio: {price} | Tamaño: {pos_size:.4f}")
            
            # SHORT: Tendencia Bajista + RSI > 60 + Precio < WMA
            elif close_1h < ema200 and rsi > 60 and price < wma:
                sl = df_5m['high'].iloc[-2] # Máximo anterior
                dist = abs(price - sl)
                if dist > 0:
                    pos_size = monto_riesgo / dist
                    print(f"SEÑAL SHORT en {symbol} | Precio: {price} | Tamaño: {pos_size:.4f}")
        
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
            print("\nBot detenido manualmente.")
            break
        except Exception as e:
            print(f"Error en el ciclo: {e}")
            time.sleep(30)

# --- BLOQUE PARA MANTENER EL BOT VIVO EN RENDER (Gratuito) ---
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot de Deribit activo y operando"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # Iniciamos el servidor Flask en un hilo separado
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    
    # Iniciamos la lógica principal del bot
    main()