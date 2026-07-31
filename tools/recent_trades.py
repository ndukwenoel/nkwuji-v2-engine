import MetaTrader5 as mt5
from datetime import datetime, timedelta

if not mt5.initialize():
    print("Failed to initialize MT5")
    quit()

from_date = datetime.now() - timedelta(hours=2)
to_date = datetime.now()
deals = mt5.history_deals_get(from_date, to_date)

if deals is None or len(deals) == 0:
    print("No deals found in the last 2 hours.")
else:
    print("--- RECENT CLOSED TRADES (LAST 2 HOURS) ---")
    sorted_deals = sorted(deals, key=lambda x: x.time, reverse=True)
    
    count = 0
    for d in sorted_deals:
        if d.entry == mt5.DEAL_ENTRY_OUT:
            pos_id = d.position_id
            orders = mt5.history_orders_get(position=pos_id)
            if orders:
                # The first order in the history for this position is usually the opening order
                open_order = orders[0]
                sl = open_order.sl
                tp = open_order.tp
                price_open = open_order.price_open
            else:
                sl = 0.0
                tp = 0.0
                price_open = 0.0
                
            time_str = datetime.fromtimestamp(d.time).strftime('%Y-%m-%d %H:%M:%S')
            action = "SELL" if d.type == mt5.DEAL_TYPE_SELL else "BUY"
            print(f"Time: {time_str} | Symbol: {d.symbol} | Volume: {d.volume} | Profit: ${d.profit}")
            print(f"   -> Entry Price: {price_open} | SL: {sl} | TP: {tp}")
            count += 1
            if count >= 10:
                break
                
mt5.shutdown()
