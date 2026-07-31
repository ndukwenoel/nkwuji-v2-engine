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
    losses = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT and d.profit < 0]
    
    print(f"Total Losing Trades: {len(losses)}")
    
    exit_reasons = {
        "Full SL Hit": 0,
        "Broker Stop-Out (Margin Call)": 0,
        "Emergency Eject (Failsafe)": 0,
        "Scale-Out Residual Loss": 0,
        "Manual / Unknown": 0
    }
    
    profits_by_reason = {k: 0.0 for k in exit_reasons.keys()}
    
    for w in losses:
        comment = w.comment.lower()
        if "[sl" in comment:
            reason = "Full SL Hit"
        elif "[so" in comment:
            reason = "Broker Stop-Out (Margin Call)"
        elif "emergency eject" in comment:
            reason = "Emergency Eject (Failsafe)"
        elif "scale-out" in comment or "[tp" in comment: # Sometime residual scale outs hit TP but result in net loss due to spread/swaps? Wait, if [tp is hit but profit < 0, it's spread/swap trap.
            if "[tp" in comment:
                reason = "Spread/Swap Trap (Hit TP but lost money)"
                if reason not in exit_reasons:
                    exit_reasons[reason] = 0
                    profits_by_reason[reason] = 0.0
            else:
                reason = "Scale-Out Residual Loss"
        else:
            reason = "Manual / Unknown"
            
        exit_reasons[reason] += 1
        profits_by_reason[reason] += w.profit
        
    print("\n--- LOSING TRADE ANALYSIS ---")
    for reason in exit_reasons:
        count = exit_reasons[reason]
        if count > 0:
            avg_loss = profits_by_reason[reason] / count
            print(f"{reason}: {count} trades | Total Loss: ${profits_by_reason[reason]:.2f} | Avg Loss per Trade: ${avg_loss:.2f}")
            
mt5.shutdown()
