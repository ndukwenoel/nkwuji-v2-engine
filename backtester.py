import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import datetime
import logging

# Import V1 config parameters
from engine.config import (
    KC_PERIOD, KC_MULT, ATR_PERIOD, ATR_SL_MULT, ATR_TP_MULT, 
    PROFIT_LOCK_TIERS, TRADE_MODE, MT5_TERMINAL_PATH, MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER,
    TREND_CHANNEL_LOOKBACK, EARLY_TP_ENABLED, EARLY_TP_PERCENT
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Backtester:
    def __init__(self, pair, start_date, end_date, initial_balance=500.0, volume=0.01):
        self.pair = pair
        self.start_date = start_date
        self.end_date = end_date
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.volume = volume
        self.df = pd.DataFrame()
        self.trades = []
        
    def _calculate_atr(self, df, period=14):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.ewm(alpha=1/period, adjust=False).mean()
        return atr

    def _calculate_trend_channel(self, df, lookback=100):
        upper_channel = pd.Series(index=df.index, dtype=float)
        lower_channel = pd.Series(index=df.index, dtype=float)
        
        x = np.arange(lookback)
        for i in range(lookback, len(df)):
            window = df.iloc[i - lookback : i]
            median_prices = (window['high'] + window['low']) / 2.0
            
            slope, intercept = np.polyfit(x, median_prices.values, 1)
            regression_line = slope * x + intercept
            
            max_high_dev = np.max(window['high'].values - regression_line)
            max_low_dev = np.max(regression_line - window['low'].values)
            
            current_reg_val = slope * lookback + intercept
            upper_channel.iloc[i] = current_reg_val + max_high_dev
            lower_channel.iloc[i] = current_reg_val - max_low_dev
            
        return upper_channel, lower_channel

    def connect(self):
        logger.info("Initializing MT5...")
        if MT5_TERMINAL_PATH:
            mt5.initialize(path=MT5_TERMINAL_PATH)
        else:
            mt5.initialize()
            
        authorized = mt5.login(MT5_ACCOUNT, password=MT5_PASSWORD, server=MT5_SERVER)
        if not authorized:
            logger.error("Failed to connect to MT5.")
            return False
        return True

    def fetch_data(self):
        logger.info(f"Fetching M5 data for {self.pair} from {self.start_date.date()} to {self.end_date.date()}...")
        utc_from = self.start_date.replace(tzinfo=datetime.timezone.utc)
        utc_to = self.end_date.replace(tzinfo=datetime.timezone.utc)
        
        rates = mt5.copy_rates_range(self.pair, mt5.TIMEFRAME_M5, utc_from, utc_to)
        if rates is None or len(rates) == 0:
            logger.error("Failed to fetch data.")
            return False
            
        self.df = pd.DataFrame(rates)
        self.df['time'] = pd.to_datetime(self.df['time'], unit='s')
        
        # Calculate Indicators (Vectorized)
        self.df['ema'] = self.df['close'].ewm(span=KC_PERIOD, adjust=False).mean()
        self.df['atr'] = self._calculate_atr(self.df, ATR_PERIOD)
        self.df['kc_upper'] = self.df['ema'] + (KC_MULT * self.df['atr'])
        self.df['kc_lower'] = self.df['ema'] - (KC_MULT * self.df['atr'])
        
        # Linear Regression Trend Channel
        self.df['tc_upper'], self.df['tc_lower'] = self._calculate_trend_channel(self.df, TREND_CHANNEL_LOOKBACK)
        
        # Fractals
        self.df['local_high'] = self.df['high'].rolling(window=5).max()
        self.df['local_low'] = self.df['low'].rolling(window=5).min()
        self.df['is_swing_high'] = self.df['high'] == self.df['local_high'].shift(-2)
        self.df['is_swing_low'] = self.df['low'] == self.df['local_low'].shift(-2)
        
        logger.info(f"Prepared {len(self.df)} candles for simulation.")
        return True

    def run(self):
        if self.df.empty:
            return
            
        symbol_info = mt5.symbol_info(self.pair)
        if symbol_info is None:
            logger.error(f"Symbol {self.pair} not found.")
            return
            
        logger.info("Starting simulation loop...")
        open_trade = None
        
        for i in range(10, len(self.df)):
            current_candle = self.df.iloc[i]
            
            # --- MANAGE OPEN TRADE ---
            if open_trade is not None:
                high = current_candle['high']
                low = current_candle['low']
                close = current_candle['close']
                
                # Check standard SL/TP
                if open_trade['direction'] == 'LONG':
                    if low <= open_trade['sl']:
                        self._close_trade(open_trade, open_trade['sl'], current_candle['time'], "SL Hit")
                        open_trade = None
                        continue
                    elif high >= open_trade['tp']:
                        self._close_trade(open_trade, open_trade['tp'], current_candle['time'], "TP Hit")
                        open_trade = None
                        continue
                else: # SHORT
                    if high >= open_trade['sl']:
                        self._close_trade(open_trade, open_trade['sl'], current_candle['time'], "SL Hit")
                        open_trade = None
                        continue
                    elif low <= open_trade['tp']:
                        self._close_trade(open_trade, open_trade['tp'], current_candle['time'], "TP Hit")
                        open_trade = None
                        continue
                        
                # Check V2 Early TP
                total_dist = abs(open_trade['tp'] - open_trade['open_price'])
                current_dist = abs(high - open_trade['open_price']) if open_trade['direction'] == 'LONG' else abs(open_trade['open_price'] - low)
                if total_dist > 0:
                    journey_pct = current_dist / total_dist
                    if EARLY_TP_ENABLED and journey_pct >= EARLY_TP_PERCENT:
                        self._close_trade(open_trade, high if open_trade['direction'] == 'LONG' else low, current_candle['time'], "V2 Early TP (85%)")
                        open_trade = None
                        continue
                        
                # Check Option B Profit Lock
                if TRADE_MODE == "MODE_LOCK_PROFIT":
                    # Estimate floating profit at high/low extremum
                    if open_trade['direction'] == 'LONG':
                        max_price = high
                        min_price = low
                    else:
                        max_price = low # For short, lowest price is highest profit
                        min_price = high
                        
                    # Calculate max possible profit in this candle
                    profit_at_max = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY if open_trade['direction'] == 'LONG' else mt5.ORDER_TYPE_SELL, 
                                                          self.pair, self.volume, open_trade['open_price'], max_price)
                                                          
                    # Check if max profit triggered a new lock
                    for trigger_usd, lock_usd in reversed(PROFIT_LOCK_TIERS):
                        if profit_at_max is not None and profit_at_max >= trigger_usd:
                            if lock_usd > open_trade['locked_profit']:
                                open_trade['locked_profit'] = lock_usd
                            break
                            
                    # Calculate profit at worst price in this candle
                    profit_at_min = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY if open_trade['direction'] == 'LONG' else mt5.ORDER_TYPE_SELL, 
                                                          self.pair, self.volume, open_trade['open_price'], min_price)
                                                          
                    # If profit dipped below the locked amount, we get stopped out at the locked amount
                    if open_trade['locked_profit'] > 0.0 and profit_at_min is not None and profit_at_min <= open_trade['locked_profit']:
                        self._close_trade(open_trade, close, current_candle['time'], f"Lock ${open_trade['locked_profit']}", forced_profit=open_trade['locked_profit'])
                        open_trade = None
                        continue

            # --- CHECK FOR NEW SIGNALS ---
            if open_trade is None:
                # Signal logic evaluates candles matching the live bot's delay (c3 is the signal candle)
                c1 = self.df.iloc[i-1] 
                c3 = self.df.iloc[i-3]
                
                # Buy Signal
                kc_lower_touch = c3['low'] <= c3['kc_lower']
                swing_low_present = self.df['is_swing_low'].iloc[i-3]
                buy_momentum = c1['close'] > c1['open']
                tc_lower_touch = (c3['low'] <= c3['tc_lower']) or (self.df.iloc[i-4]['low'] <= self.df.iloc[i-4]['tc_lower'])
                
                if kc_lower_touch and swing_low_present and buy_momentum and tc_lower_touch:
                    open_price = current_candle['open'] # Enter at open of current candle
                    sl = open_price - (c1['atr'] * ATR_SL_MULT)
                    tp = open_price + (c1['atr'] * ATR_TP_MULT)
                    
                    open_trade = {
                        'direction': 'LONG',
                        'open_price': open_price,
                        'open_time': current_candle['time'],
                        'sl': sl,
                        'tp': tp,
                        'locked_profit': 0.0
                    }
                    continue
                    
                # Sell Signal
                kc_upper_touch = c3['high'] >= c3['kc_upper']
                swing_high_present = self.df['is_swing_high'].iloc[i-3]
                sell_momentum = c1['close'] < c1['open']
                tc_upper_touch = (c3['high'] >= c3['tc_upper']) or (self.df.iloc[i-4]['high'] >= self.df.iloc[i-4]['tc_upper'])
                
                if kc_upper_touch and swing_high_present and sell_momentum and tc_upper_touch:
                    open_price = current_candle['open']
                    sl = open_price + (c1['atr'] * ATR_SL_MULT)
                    tp = open_price - (c1['atr'] * ATR_TP_MULT)
                    
                    open_trade = {
                        'direction': 'SHORT',
                        'open_price': open_price,
                        'open_time': current_candle['time'],
                        'sl': sl,
                        'tp': tp,
                        'locked_profit': 0.0
                    }

    def _close_trade(self, trade, close_price, close_time, reason, forced_profit=None):
        if forced_profit is not None:
            profit = forced_profit
        else:
            action = mt5.ORDER_TYPE_BUY if trade['direction'] == 'LONG' else mt5.ORDER_TYPE_SELL
            profit = mt5.order_calc_profit(action, self.pair, self.volume, trade['open_price'], close_price)
            if profit is None: profit = 0.0
            
        self.balance += profit
        
        self.trades.append({
            'direction': trade['direction'],
            'open_time': trade['open_time'],
            'close_time': close_time,
            'open_price': trade['open_price'],
            'close_price': close_price,
            'profit': profit,
            'reason': reason,
            'balance': self.balance
        })

    def print_results(self):
        if not self.trades:
            print("No trades taken in the specified period.")
            return
            
        trades_df = pd.DataFrame(self.trades)
        wins = trades_df[trades_df['profit'] > 0]
        losses = trades_df[trades_df['profit'] <= 0]
        
        win_rate = len(wins) / len(trades_df) * 100
        total_profit = trades_df['profit'].sum()
        
        print("\n" + "="*50)
        print(" BACKTEST RESULTS: NKWUJI V2")
        print("="*50)
        print(f"Pair: {self.pair}")
        print(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        print(f"Volume per trade: {self.volume} lots")
        print("-" * 50)
        print(f"Total Trades: {len(trades_df)}")
        print(f"Win Rate: {win_rate:.1f}% ({len(wins)} wins / {len(losses)} losses)")
        print(f"Total Net Profit: ${total_profit:.2f}")
        print(f"Final Balance: ${self.balance:.2f} (Start: ${self.initial_balance:.2f})")
        print("="*50)
        
        print("\nLast 10 Trades:")
        print(trades_df.tail(10)[['open_time', 'direction', 'profit', 'reason']].to_string(index=False))

if __name__ == "__main__":
    # Test for the last 30 days
    end = datetime.datetime.now()
    start = end - datetime.timedelta(days=180)
    
    # User target pair
    tester = Backtester("BTCUSDm", start, end, volume=0.02)
    if tester.connect():
        if tester.fetch_data():
            tester.run()
            tester.print_results()
        mt5.shutdown()
