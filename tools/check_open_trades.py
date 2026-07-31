import MetaTrader5 as mt5
import sys
import os
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.connection import MT5ConnectionManager

def check_live_trades_history():
    if not MT5ConnectionManager.initialize():
        print("Failed to connect")
        return

    positions = mt5.positions_get()
    if not positions:
        print("No open positions found.")
        MT5ConnectionManager.shutdown()
        return

    for pos in positions:
        print(f"\n--- TRADE {pos.ticket} ({pos.symbol}) ---")
        
        time_opened = datetime.fromtimestamp(pos.time)
        
        print(f"Trade Opened At: {time_opened}")
        print(f"Type: {'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL'}")
        print(f"Entry Price: {pos.price_open}")
        print(f"Take Profit (TP): {pos.tp}")
        print(f"Current Price: {pos.price_current}")
        print(f"Floating Profit: ${pos.profit}")
        
        # Fetch 1-minute candles from open time to now
        rates = mt5.copy_rates_range(pos.symbol, mt5.TIMEFRAME_M1, time_opened, datetime.now())
        
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            lowest_low = df['low'].min()
            highest_high = df['high'].max()
            lowest_low_time = pd.to_datetime(df.loc[df['low'].idxmin(), 'time'], unit='s')
            highest_high_time = pd.to_datetime(df.loc[df['high'].idxmax(), 'time'], unit='s')
            
            print(f"--- HISTORICAL DATA SINCE OPEN ---")
            if pos.type == mt5.ORDER_TYPE_SELL:
                print(f"Lowest Price Reached: {lowest_low} (at {lowest_low_time})")
                if lowest_low <= pos.tp:
                    print(">>> YES! The physical chart price mathematically crossed the Take Profit line.")
                else:
                    diff = lowest_low - pos.tp
                    print(f">>> NO. The chart price came within {diff:.5f} of the Take Profit, but never crossed it.")
            else:
                print(f"Highest Price Reached: {highest_high} (at {highest_high_time})")
                if highest_high >= pos.tp and pos.tp > 0:
                    print(">>> YES! The physical chart price mathematically crossed the Take Profit line.")
                else:
                    if pos.tp > 0:
                        diff = pos.tp - highest_high
                        print(f">>> NO. The chart price came within {diff:.5f} of the Take Profit, but never crossed it.")
        else:
            print("Could not fetch historical candles.")
        
    MT5ConnectionManager.shutdown()

if __name__ == "__main__":
    check_live_trades_history()
