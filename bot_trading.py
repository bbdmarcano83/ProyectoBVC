import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os
import logging
import requests
import datetime
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
TAKE_PROFIT_PCT = 0.06  # 6% take profit
MAX_VOLATILIDAD = 0.05  # 5% máximo ATR
COOLDOWN_MINUTOS = 30   # 30 minutos entre operaciones del mismo activo

# Variables globales para tracking
ultima_operacion = {}
trailing_stops = {}

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

def puede_operar(symbol):
    """Verifica si ha pasado suficiente tiempo desde la última operación"""
    if symbol in ultima_operacion:
        tiempo_transcurrido = datetime.datetime.now() - ultima_operacion[symbol]
        return tiempo_transcurrido.total_seconds() > (COOLDOWN_MINUTOS * 60)
    return True

def calcular_tamaño_posicion(balance, price, porcentaje_sl):
    """Calcula el tamaño de posición con validaciones mejoradas"""
    try:
        monto_riesgo = balance * RIESGO_FIJO
        pos_size = (monto_riesgo / (price * porcentaje_sl)) * APALANCAMIENTO
        
        # Validar tamaño mínimo (ajustar según Deribit)
        min_size = 0.001
        max_size = balance * 0.1  # Máximo 10% del balance
        
        pos_size = max(pos_size, min_size)
        pos_size = min(pos_size, max_size)
        
        return round(pos_size, 6)
    except Exception as e:
        logging.error(f"Error calculando posición: {e}")
        return 0

def ejecutar_operacion(symbol, side, pos_size):
    """Ejecuta operación con validaciones mejoradas"""
    try:
        order = exchange.create_order(
            symbol, 'market', side, pos_size, 
            params={'leverage': APALANCAMIENTO}
        )
        
        # Verificar estado de la orden
        if order.get('status') in ['closed', 'filled']:
            ultima_operacion[symbol] = datetime.datetime.now()
            return True, order
        else:
            logging.error(f"Orden no ejecutada correctamente: {order}")
            return False, None
            
    except Exception as e:
        logging.error(f"Error ejecutando orden {symbol} {side}: {e}")
        return False, None

def actualizar_trailing_stop(symbol, pos):
    """Actualiza trailing stop loss"""
    try:
        mark_price = float(pos['mark_price'])
        side = pos['side']
        
        if side == 'long':
            nuevo_sl = mark_price * (1 - PORCENTAJE_SL)
            if symbol not in trailing_stops or nuevo_sl > trailing_stops[symbol]:
                trailing_stops[symbol] = nuevo_sl
        else:  # short
            nuevo_sl = mark_price * (1 + PORCENTAJE_SL)
            if symbol not in trailing_stops or nuevo_sl < trailing_stops[symbol]:
                trailing_stops[symbol] = nuevo_sl
                
    except Exception as e:
        logging.error(f"Error actualizando trailing stop {symbol}: {e}")

def patrulla_emergencia():
    """Patrullaje con trailing stops y take profit mejorados"""
    for symbol in ASSETS:
        try:
            posiciones = exchange.fetch_positions([symbol])
            for pos in posiciones:
                if float(pos.get('contracts', 0)) > 0:
                    entry = float(pos['entry_price'])
                    mark = float(pos['mark_price'])
                    side = pos['side']
                    side_multiplier = 1 if side == 'long' else -1
                    pnl_pct = ((mark - entry) / entry) * side_multiplier
                    
                    # Actualizar trailing stop
                    actualizar_trailing_stop(symbol, pos)
                    
                    # Check Take Profit
                    if pnl_pct >= TAKE_PROFIT_PCT:
                        side_to_close = 'sell' if side == 'long' else 'buy'
                        success, order = ejecutar_operacion(symbol, side_to_close, float(pos['contracts']))
                        if success:
                            msg = f"💰 TAKE PROFIT: Cierre en {symbol}. Ganancia: {pnl_pct:.2%}"
                            logging.info(msg)
                            enviar_telegram(msg)
                            # Limpiar trailing stop
                            if symbol in trailing_stops:
                                del trailing_stops[symbol]
                        continue
                    
                    # Check Stop Loss (incluyendo trailing)
                    stop_loss_triggered = False
                    
                    # Stop Loss fijo de emergencia
                    if pnl_pct <= -0.0205:
                        stop_loss_triggered = True
                        msg_tipo = "🚨 EMERGENCIA"
                    
                    # Trailing Stop Loss
                    elif symbol in trailing_stops:
                        if (side == 'long' and mark <= trailing_stops[symbol]) or \
                           (side == 'short' and mark >= trailing_stops[symbol]):
                            stop_loss_triggered = True
                            msg_tipo = "📉 TRAILING STOP"
                    
                    if stop_loss_triggered:
                        side_to_close = 'sell' if side == 'long' else 'buy'
                        success, order = ejecutar_operacion(symbol, side_to_close, float(pos['contracts']))
                        if success:
                            msg = f"{msg_tipo}: Cierre en {symbol}. PnL: {pnl_pct:.2%}"
                            logging.warning(msg)
                            enviar_telegram(msg)
                            # Limpiar trailing stop
                            if symbol in trailing_stops:
                                del trailing_stops[symbol]
                                
        except Exception as e:
            logging.error(f"Error en patrulla {symbol}: {e}")

def validar_datos_tecnicos(df_1h, df_5m, symbol):
    """Valida que los datos técnicos sean suficientes"""
    if len(df_1h) < 200:
        logging.warning(f"Datos 1h insuficientes para {symbol}: {len(df_1h)}/200")
        return False
    
    if len(df_5m) < 50:
        logging.warning(f"Datos 5m insuficientes para {symbol}: {len(df_5m)}/50")
        return False
    
    return True

def filtrar_por_volatilidad(df_5m, price):
    """Filtra operaciones por alta volatilidad"""
    try:
        atr = ta.atr(df_5m['h'], df_5m['l'], df_5m['c'], length=14).iloc[-1]
        volatilidad_pct = atr / price
        
        if volatilidad_pct > MAX_VOLATILIDAD:
            return False, f"Alta volatilidad: {volatilidad_pct:.2%}"
        
        return True, f"Volatilidad OK: {volatilidad_pct:.2%}"
    except Exception as e:
        logging.error(f"Error calculando volatilidad: {e}")
        return False, "Error en cálculo de volatilidad"

def ejecutar_estrategia():
    """Estrategia principal con todas las mejoras"""
    # Semáforo de seguridad
    posiciones_abiertas = 0
    for symbol in ASSETS:
        try:
            p_list = exchange.fetch_positions([symbol])
            if any(float(p.get('contracts', 0)) > 0 for p in p_list):
                posiciones_abiertas += 1
        except: 
            continue
    
    if posiciones_abiertas >= 2:
        logging.info(f"BLINDAJE: {posiciones_abiertas} operaciones activas. Máximo permitido alcanzado.")
        return 

    try:
        balance = exchange.fetch_balance()['total']['USDC']
        if balance <= 10:  # Validar balance mínimo
            logging.error(f"Balance insuficiente: ${balance}")
            return
    except Exception as e:
        logging.error(f"Error obteniendo balance: {e}")
        return

    for symbol in ASSETS:
        try:
            # Verificar cooldown
            if not puede_operar(symbol):
                continue
            
            # Re-verificar posición individual
            posiciones = exchange.fetch_positions([symbol])
            if any(float(p.get('contracts', 0)) > 0 for p in posiciones):
                continue 

            # Obtener datos históricos
            df_1h = pd.DataFrame(exchange.fetch_ohlcv(symbol, '1h', limit=200), 
                               columns=['t', 'o', 'h', 'l', 'c', 'v'])
            df_5m = pd.DataFrame(exchange.fetch_ohlcv(symbol, '5m', limit=50), 
                               columns=['t', 'o', 'h', 'l', 'c', 'v'])
            
            # Validar datos suficientes
            if not validar_datos_tecnicos(df_1h, df_5m, symbol):
                continue
            
            # Calcular indicadores técnicos
            ema200 = ta.ema(df_1h['c'], length=200).iloc[-1]
            rsi = ta.rsi(df_5m['c'], length=14).iloc[-1]
            wma = ta.wma(df_5m['c'], length=14).iloc[-1]
            price = df_5m['c'].iloc[-1]
            close_1h = df_1h['c'].iloc[-1]

            # Validar indicadores
            if pd.isna(rsi) or pd.isna(ema200) or pd.isna(wma):
                logging.warning(f"Indicadores inválidos para {symbol}")
                continue

            # Filtro de volatilidad
            volatilidad_ok, vol_msg = filtrar_por_volatilidad(df_5m, price)
            if not volatilidad_ok:
                logging.info(f"{symbol}: {vol_msg} - Saltando")
                continue

            # Lógica de señales mejorada
            # Señal LONG: Tendencia alcista + RSI sobreventa + precio sobre WMA
            long_signal = (close_1h > ema200 and rsi < 30 and price > wma)
            
            # Señal SHORT: Tendencia bajista + RSI sobrecompra + precio bajo WMA
            short_signal = (close_1h < ema200 and rsi > 70 and price < wma)
            
            if long_signal:
                side = 'buy'
                signal_strength = f"Long: EMA200({ema200:.2f}) < Close1h({close_1h:.2f}), RSI({rsi:.1f}) < 30, Price({price:.2f}) > WMA({wma:.2f})"
            elif short_signal:
                side = 'sell'
                signal_strength = f"Short: EMA200({ema200:.2f}) > Close1h({close_1h:.2f}), RSI({rsi:.1f}) > 70, Price({price:.2f}) < WMA({wma:.2f})"
            else:
                continue
            
            # Calcular tamaño de posición
            pos_size = calcular_tamaño_posicion(balance, price, PORCENTAJE_SL)
            if pos_size <= 0:
                logging.error(f"Tamaño de posición inválido para {symbol}: {pos_size}")
                continue

            # Ejecutar operación
            success, order = ejecutar_operacion(symbol, side, pos_size)
            
            if success:
                msg = f"🚀 ENTRADA: {side.upper()} en {symbol}\n"
                msg += f"💰 Tamaño: {pos_size:.6f} | Precio: ${price:.4f}\n"
                msg += f"📊 {signal_strength}\n"
                msg += f"📈 {vol_msg}"
                
                logging.info(f"Operación exitosa: {side.upper()} {symbol} - {pos_size:.6f}")
                enviar_telegram(msg)
                
                # Pausa estratégica tras abrir orden
                time.sleep(10)
            else:
                logging.error(f"Falló ejecución: {side.upper()} {symbol}")

        except Exception as e:
            logging.error(f"Error analizando {symbol}: {e}")

def limpiar_datos_antiguos():
    """Limpia datos de tracking antiguos"""
    try:
        ahora = datetime.datetime.now()
        # Limpiar operaciones antiguas (más de 24 horas)
        symbols_to_remove = []
        for symbol, timestamp in ultima_operacion.items():
            if (ahora - timestamp).total_seconds() > 86400:  # 24 horas
                symbols_to_remove.append(symbol)
        
        for symbol in symbols_to_remove:
            del ultima_operacion[symbol]
            if symbol in trailing_stops:
                del trailing_stops[symbol]
        
        if symbols_to_remove:
            logging.info(f"Limpiados datos antiguos: {symbols_to_remove}")
            
    except Exception as e:
        logging.error(f"Error limpiando datos: {e}")

if __name__ == "__main__":
    # Iniciar Flask en thread separado
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True).start()
    
    logging.info("🤖 Bot iniciado con mejoras completas. Monitoreando mercado...")
    enviar_telegram("🤖 Bot iniciado con todas las mejoras activadas")
    
    ciclos = 0
    while True:
        try:
            # Patrullaje de emergencia
            patrulla_emergencia()
            
            # Ejecutar estrategia principal
            ejecutar_estrategia()
            
            # Limpiar datos antiguos cada 100 ciclos (~50 min)
            ciclos += 1
            if ciclos % 100 == 0:
                limpiar_datos_antiguos()
                logging.info(f"Ciclo #{ciclos} completado. Posiciones activas: {len(trailing_stops)}")
            
            # Pausa entre ciclos
            time.sleep(30)
            
        except KeyboardInterrupt:
            logging.info("Bot detenido por usuario")
            enviar_telegram("🛑 Bot detenido manualmente")
            break
        except Exception as e:
            logging.critical(f"ERROR CRÍTICO EN BUCLE PRINCIPAL: {e}")
            enviar_telegram(f"⚠️ Error crítico: {str(e)[:100]}...")
            time.sleep(60)
