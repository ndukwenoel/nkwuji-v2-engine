
import sys
import datetime
import MetaTrader5 as mt5
from backtester import Backtester

pairs = ['NZDCADz', 'AUDUSDz', 'EURJPYz', 'BTCUSDz', 'XAUUSDz']
end = datetime.datetime.now()
start = end - datetime.timedelta(days=180)

if not mt5.initialize():
    print("MT5 Init Failed")
    sys.exit(1)

for pair in pairs:
    tester = Backtester(pair, start, end, volume=0.02)
    # We already know mt5 is initialized, but tester.connect() is harmless
    if tester.connect():
        if tester.fetch_data():
            tester.run()
            if tester.trades:
                wins = [t for t in tester.trades if t['profit'] > 0]
                win_rate = len(wins) / len(tester.trades) * 100
                total_profit = sum(t['profit'] for t in tester.trades)
                
                # calc drawdown
                balance = tester.initial_balance
                peak = balance
                max_dd = 0.0
                for t in tester.trades:
                    balance = t['balance']
                    if balance > peak: peak = balance
                    dd = (peak - balance) / peak * 100
                    if dd > max_dd: max_dd = dd
                
                print(f"{pair},{win_rate:.1f}%,{len(tester.trades)},${total_profit:.2f},{max_dd:.2f}%")
            else:
                print(f"{pair},0.0%,0,$0.00,0.00%")
        else:
            print(f"{pair},FETCH_FAILED,0,$0.00,0.00%")
    else:
        print(f"{pair},CONNECT_FAILED,0,$0.00,0.00%")
mt5.shutdown()
