import MetaTrader5 as mt5
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.connection import MT5ConnectionManager

def analyze():
    if not MT5ConnectionManager.initialize():
        print("Failed to connect")
        return

    date_to = datetime.now()
    date_from = date_to - timedelta(days=3)

    orders = mt5.history_orders_get(date_from, date_to)
    if not orders:
        print("No orders found.")
        MT5ConnectionManager.shutdown()
        return

    btc_orders = [o for o in orders if "BTC" in o.symbol and o.magic == 100100]
    if not btc_orders:
        print("No BTC orders found.")
        MT5ConnectionManager.shutdown()
        return

    # Take the last executed order that has SL/TP
    target_order = None
    for o in reversed(btc_orders):
        if o.sl > 0 and o.tp > 0:
            target_order = o
            break

    if not target_order:
        print("Could not find a BTC order with SL and TP set.")
        MT5ConnectionManager.shutdown()
        return

    sym_info = mt5.symbol_info(target_order.symbol)
    tick_size = sym_info.trade_tick_size
    tick_value = sym_info.trade_tick_value
    
    # Calculate dollar values
    # Point multiplier: how much 1 point of price movement is worth in USD for this volume
    if tick_value == 0 or tick_size == 0:
        print("Symbol tick info not available.")
        MT5ConnectionManager.shutdown()
        return
        
    point_mult = tick_value / tick_size * target_order.volume_initial
    
    entry = target_order.price_open
    sl = target_order.sl
    tp = target_order.tp
    
    if target_order.type == mt5.ORDER_TYPE_BUY:
        risk_usd = (entry - sl) * point_mult
        reward_usd = (tp - entry) * point_mult
    else:
        risk_usd = (sl - entry) * point_mult
        reward_usd = (entry - tp) * point_mult

    print(f"--- Trade Analysis for {target_order.symbol} ---")
    print(f"Volume: {target_order.volume_initial}")
    print(f"Entry Price: {entry}")
    print(f"Stop Loss: {sl}")
    print(f"Take Profit: {tp}")
    print(f"Calculated Risk (SL hit): ${risk_usd:.2f}")
    print(f"Calculated Reward (TP hit): ${reward_usd:.2f}")
    
    if reward_usd > 0:
        percent_of_tp = (170.0 / reward_usd) * 100
        print(f"\nA $170 floating profit was exactly {percent_of_tp:.2f}% of the way to the Take Profit target.")

    MT5ConnectionManager.shutdown()

if __name__ == "__main__":
    analyze()
