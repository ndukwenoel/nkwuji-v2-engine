import MetaTrader5 as mt5
from datetime import datetime, timedelta

if not mt5.initialize():
    print("Failed to initialize MT5")
    quit()

from_date = datetime.now() - timedelta(hours=24)
to_date = datetime.now()
deals = mt5.history_deals_get(from_date, to_date)

if deals is None or len(deals) == 0:
    print("No deals found.")
else:
    print("--- SEARCHING FOR AUDUSD SELL ENTRY AROUND 0.69429 ---")
    sorted_deals = sorted(deals, key=lambda x: x.time, reverse=True)
    
    count = 0
    for d in sorted_deals:
        # A SELL entry is DEAL_ENTRY_IN and DEAL_TYPE_SELL
        if d.entry == mt5.DEAL_ENTRY_IN and "AUDUSD" in d.symbol and d.type == mt5.DEAL_TYPE_SELL:
            time_str = datetime.fromtimestamp(d.time).strftime('%Y-%m-%d %H:%M:%S')
            print(f"Time: {time_str} | Symbol: {d.symbol} | Fill Price: {d.price} | Volume: {d.volume}")
            count += 1
            if count >= 10:
                break
                
mt5.shutdown()
