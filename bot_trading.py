import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
import logging
import requests
from flask import Flask
from threading import Thread

# Configuración de logs: Esto es lo que reemplaza a los 'print' y funciona en Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Inicialización del Exchange
exchange = ccxt.deribit({
    'apiKey': os.getenv('DERIBIT_TESTNET_CLIENT_ID'),
    'secret': os.getenv('DERIBIT_TESTNET_CLIENT_SECRET'),
    'sandbox': True
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

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/sendMessage"
        requests.get(url, params={'chat_id': os.getenv('TELEGRAM_CHAT_ID'), 'text': mensaje}, timeout=5)
    except Exception as e:
        logging.error(f"Error enviando Telegram: {e}")

def patrulla_emergencia():
    """Vigilante: Cierra cualquier pérdida > 2.05%."""
    for symbol in ASSETS:
        try:
            posiciones = exchange.fetch_positions([symbol])
            for pos in posiciones:
                if float(pos.get('contracts', 0)) > 0:
                    entry = float(pos['entry_price'])
                    mark = float(pos['mark_price'])
                    # Si es short, la lógica de pérdida se invierte
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
    try:
        balance = exchange.fetch_balance()['total']['USDC']
        monto_riesgo = balance * RIESGO_FIJO
    except Exception as e:
        logging.error(f"Error obteniendo balance: {e}")
        return

    for symbol in ASSETS:
        try:
            # 1. BLOQUEO DE POSICIÓN ÚNICA (Auditado)
            posiciones = exchange.fetch_positions([symbol])
            if any(float(p.get('contracts', 0)) > 0 for p in posiciones):
                logging.info(f"AUDITORIA: {symbol} tiene posición abierta. OMITIENDO entrada.")
                continue 

            # 2. ANÁLISIS TÉCNICO
            df_1h = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', limit=200), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            df_5m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '5m', limit=50), columns=['t', 'o', 'h', 'l', 'c', 'v'])
            
            ema200 = ta.ema(df_1h['c'], length=200).iloc[-1]
            rsi = ta.rsi(df_5m['c'], length=14).iloc[-1]
            wma = ta.wma(df_5m['c'], length=14).iloc[-1]
            price = df_5m['c'].iloc[-1]
            close_1h = df_1h['c'].iloc[-1]

            # Auditando valores para que sepas qué está pasando
            logging.info(f"AUDITORIA: {symbol} -> Precio: {price:.4f}, RSI: {rsi:.2f}, EMA: {ema200:.4f}")

            # 3. ESTRATEGIA DE ENTRADA
            side = 'buy' if (close_1h > ema200 and rsi < 30 and price > wma) else \
                   'sell' if (close_1h < ema200 and rsi > 70 and price < wma) else None
            
            if side:
                pos_size = (monto_riesgo / (price * PORCENTAJE_SL)) * APALANCAMIENTO
                exchange.create_order(symbol, 'market', side, pos_size, params={'leverage': APALANCAMIENTO})
                msg = f"🚀 ENTRADA ÚNICA: {side.upper()} en {symbol} | Tamaño: {pos_size:.4f}"
                logging.info(msg)
                enviar_telegram(msg)
            else:
                logging.info(f"AUDITORIA: {symbol} sin señal técnica.")

        except Exception as e:
            logging.error(f"Error analizando {symbol}: {e}")

if __name__ == "__main__":
    Thread(target=lambda: Flask(__name__).run(host='0.0.0.0', port=8080), daemon=True).start()
    logging.info("Bot iniciado. Monitoreando mercado...")
    while True:
        patrulla_emergencia()
        ejecutar_estrategia()
        time.sleep(30)