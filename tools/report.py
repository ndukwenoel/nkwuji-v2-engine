import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path so we can import engine modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.connection import MT5ConnectionManager

def generate_report(days=30):
    print(f"--- Goldenburg Digital Performance Report (Last {days} Days) ---")
    
    if not MT5ConnectionManager.initialize():
        print("Failed to connect to MT5.")
        return

    # Set the time range
    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)

    # Fetch all deals in the history
    deals = mt5.history_deals_get(date_from, date_to)
    if deals is None or len(deals) == 0:
        print("No trades found in the specified time period.")
        MT5ConnectionManager.shutdown()
        return

    # Filter for our specific algorithm's trades (Magic Number 100100) and only EXIT deals (where profit is realized)
    # MT5 deals: DEAL_ENTRY_IN (0) = Open, DEAL_ENTRY_OUT (1) = Close
    algo_deals = [d for d in deals if d.magic == 100100 and d.entry == 1]

    if not algo_deals:
        print("No algorithm trades have been closed yet.")
        MT5ConnectionManager.shutdown()
        return

    # Aggregate Data
    total_trades = len(algo_deals)
    winning_trades = [d for d in algo_deals if d.profit > 0]
    losing_trades = [d for d in algo_deals if d.profit < 0]
    
    gross_profit = sum(d.profit for d in winning_trades)
    gross_loss = sum(d.profit for d in losing_trades)
    net_profit = gross_profit + gross_loss
    
    win_rate = (len(winning_trades) / total_trades) * 100
    profit_factor = gross_profit / abs(gross_loss) if gross_loss != 0 else float('inf')

    print(f"Total Trades: {total_trades}")
    print(f"Net Profit: ${net_profit:.2f}")
    print(f"Win Rate: {win_rate:.2f}% ({len(winning_trades)} winners, {len(losing_trades)} losers)")
    print(f"Gross Profit: ${gross_profit:.2f}")
    print(f"Gross Loss: ${gross_loss:.2f}")
    print(f"Profit Factor: {profit_factor:.2f}")
    
    print("\n--- Asset Breakdown ---")
    
    # Calculate per symbol
    symbols = set(d.symbol for d in algo_deals)
    for sym in symbols:
        sym_deals = [d for d in algo_deals if d.symbol == sym]
        sym_trades = len(sym_deals)
        sym_gross_prof = sum(d.profit for d in sym_deals if d.profit > 0)
        sym_gross_loss = sum(d.profit for d in sym_deals if d.profit < 0)
        sym_net = sym_gross_prof + sym_gross_loss
        sym_pf = sym_gross_prof / abs(sym_gross_loss) if sym_gross_loss != 0 else float('inf')
        
        print(f"{sym}: {sym_trades} Trades | Net: ${sym_net:.2f} | PF: {sym_pf:.2f}")

    MT5ConnectionManager.shutdown()

if __name__ == "__main__":
    generate_report(days=30)
