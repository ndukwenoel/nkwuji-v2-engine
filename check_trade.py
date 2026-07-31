import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

def check_open_trades():
    if not mt5.initialize():
        print(f"initialize() failed, error code = {mt5.last_error()}")
        return

    positions = mt5.positions_get()
    if positions is None:
        print(f"No positions, error code = {mt5.last_error()}")
    elif len(positions) == 0:
        print("No open positions found.")
    else:
        print(f"Found {len(positions)} open positions.")
        for pos in positions:
            if "NZDCAD" in pos.symbol:
                time_open = datetime.fromtimestamp(pos.time).strftime('%Y-%m-%d %H:%M:%S')
                pos_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
                print(f"--- NZDCAD POSITION ---")
                print(f"Ticket: {pos.ticket}")
                print(f"Symbol: {pos.symbol}")
                print(f"Type: {pos_type}")
                print(f"Volume: {pos.volume}")
                print(f"Price Open: {pos.price_open}")
                print(f"Current Price: {pos.price_current}")
                print(f"Profit: {pos.profit}")
                print(f"Magic Number: {pos.magic}")
                print(f"Comment: '{pos.comment}'")
                print(f"Time Opened: {time_open}")
                print("-----------------------")

    mt5.shutdown()

if __name__ == '__main__':
    check_open_trades()
