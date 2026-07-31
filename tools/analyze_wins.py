import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

if not mt5.initialize():
    print("Failed to initialize MT5")
    quit()

from_date = datetime.now() - timedelta(hours=48)
to_date = datetime.now()
deals = mt5.history_deals_get(from_date, to_date)

if deals is None or len(deals) == 0:
    print("No deals found.")
else:
    wins = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT and d.profit > 0]
    
    print(f"Total Winning Trades: {len(wins)}")
    
    exit_reasons = {
        "Full TP Hit": 0,
        "Scale-Out 50%": 0,
        "Legacy Lock": 0,
        "Near-Miss Retrace": 0,
        "Manual / Unknown": 0
    }
    
    profits_by_reason = {k: 0.0 for k in exit_reasons.keys()}
    
    for w in wins:
        comment = w.comment.lower()
        if "[tp" in comment:
            reason = "Full TP Hit"
        elif "scale-out" in comment:
            reason = "Scale-Out 50%"
        elif "legacy profit lock" in comment:
            reason = "Legacy Lock"
        elif "near-miss" in comment or "retrace trap" in comment or "retrace offload" in comment:
            reason = "Near-Miss Retrace"
        else:
            reason = "Manual / Unknown"
            
        exit_reasons[reason] += 1
        profits_by_reason[reason] += w.profit
        
    print("\n--- WINNING TRADE ANALYSIS ---")
    for reason in exit_reasons:
        count = exit_reasons[reason]
        if count > 0:
            avg_profit = profits_by_reason[reason] / count
            print(f"{reason}: {count} trades | Total Profit: ${profits_by_reason[reason]:.2f} | Avg per Trade: ${avg_profit:.2f}")
            
mt5.shutdown()
