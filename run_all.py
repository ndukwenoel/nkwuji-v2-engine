import datetime
import MetaTrader5 as mt5
from backtester import Backtester

pairs = ["NZDCADm", "AUDUSDm", "EURJPYm", "BTCUSDm", "XAUUSDm"]
end = datetime.datetime.now()
start = end - datetime.timedelta(days=180)

print("Pair,Win Rate,Total Trades,Net Profit")
for pair in pairs:
    tester = Backtester(pair, start, end, volume=0.02)
    if tester.connect():
        if tester.fetch_data():
            tester.run()
            # Calculate summary instead of full print
            if tester.trades:
                wins = [t for t in tester.trades if t['profit'] > 0]
                win_rate = len(wins) / len(tester.trades) * 100
                total_profit = sum(t['profit'] for t in tester.trades)
                print(f"{pair},{win_rate:.1f}%,{len(tester.trades)},${total_profit:.2f}")
            else:
                print(f"{pair},0.0%,0,$0.00")
        else:
            print(f"{pair},FAILED TO FETCH,0,$0.00")
mt5.shutdown()
