import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd

if not mt5.initialize():
    print("Failed to initialize MT5")
    quit()

# Fetch deals from the last 4 hours (since the bot restart)
from_date = datetime.now() - timedelta(hours=4)
to_date = datetime.now()
deals = mt5.history_deals_get(from_date, to_date)

if deals is None or len(deals) == 0:
    print("No deals found.")
else:
    lot_performance = {}
    
    for deal in deals:
        if deal.entry == mt5.DEAL_ENTRY_OUT and deal.profit != 0.0:
            lot_size = deal.volume
            if lot_size not in lot_performance:
                lot_performance[lot_size] = {'trades': 0, 'profit': 0.0, 'wins': 0, 'losses': 0}
            
            lot_performance[lot_size]['trades'] += 1
            lot_performance[lot_size]['profit'] += deal.profit
            if deal.profit > 0:
                lot_performance[lot_size]['wins'] += 1
            else:
                lot_performance[lot_size]['losses'] += 1
                
    print("\n--- HISTORICAL PERFORMANCE BY LOT SIZE ---")
    for lot, data in sorted(lot_performance.items()):
        win_rate = (data['wins'] / data['trades']) * 100 if data['trades'] > 0 else 0.0
        print(f"Lot Size: {lot:.2f} | Trades: {data['trades']} | Net Profit: ${data['profit']:.2f} | Win Rate: {win_rate:.1f}% ({data['wins']}W / {data['losses']}L)")

mt5.shutdown()
