import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import logging
from .config import KC_PERIOD, KC_MULT, FRACTAL_WINDOW, ATR_PERIOD, ATR_SL_MULT, ATR_TP_MULT, TRADE_MODE, TREND_CHANNEL_LOOKBACK

logger = logging.getLogger(__name__)

class SignalEngine:
    """Evaluates market data and generates Long/Short signals using Keltner Channels and Fractals."""
    
    def __init__(self):
        pass
        
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

    def check_signal(self, pair: str) -> dict:
        """
        Executes proprietary trading logic to determine if a signal exists.
        Returns: dict with 'direction', 'sl', 'tp'
        """
        # Fetch enough data to calculate indicators (150 candles to accommodate the 100-bar regression)
        rates = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M5, 0, 150)
        if rates is None or len(rates) == 0:
            return {"direction": "NONE"}
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # 1. Keltner Channels
        df['ema'] = df['close'].ewm(span=KC_PERIOD, adjust=False).mean()
        df['atr'] = self._calculate_atr(df, ATR_PERIOD)
        df['kc_upper'] = df['ema'] + (KC_MULT * df['atr'])
        df['kc_lower'] = df['ema'] - (KC_MULT * df['atr'])
        
        # 2. Linear Regression Trend Channel
        df['tc_upper'], df['tc_lower'] = self._calculate_trend_channel(df, TREND_CHANNEL_LOOKBACK)
        
        # 3. Fractals (Swing Highs and Lows) without lookahead bias
        # A swing low is valid if the low is the lowest of the last 5 candles.
        df['local_high'] = df['high'].rolling(window=5).max()
        df['local_low'] = df['low'].rolling(window=5).min()
        
        # Shift the local high/low back by 2 so that the middle of the 5-candle window is checked
        df['is_swing_high'] = df['high'] == df['local_high'].shift(-2)
        df['is_swing_low'] = df['low'] == df['local_low'].shift(-2)
        
        # Note: shift(-2) introduces NaNs for the very last 2 candles, which is exactly how real fractals work 
        # (you need 2 candles to close AFTER the swing to confirm it).
        # We will evaluate signals on the 3rd candle from the end, which is fully confirmed.

        if len(df) < 6:
            return {"direction": "NONE"}
            
        c_confirm = df.iloc[-1] # The live candle (not closed)
        c1 = df.iloc[-2] # 1st candle after swing
        c2 = df.iloc[-3] # 2nd candle after swing
        c3 = df.iloc[-4] # The potential SWING candle (signal candle)
        c4 = df.iloc[-5] # Candle before swing

        current_atr = df.iloc[-1]['atr']
        current_close = df.iloc[-1]['close']
        
        # Buy Signal Logic
        # 1. Agimat (KC) Touch: Swing candle touched lower KC
        kc_lower_touch = c3['low'] <= c3['kc_lower']
        # 2. Dot (Swing Low) is confirmed on c3
        swing_low_present = df['is_swing_low'].iloc[-4]
        # 3. Loosened Candlestick sequence: Just ensure we are now moving up (bullish momentum)
        buy_momentum = c1['close'] > c1['open']
        # 4. AutoTrendChannel Touch: Signal candle (c3) OR previous candle (c4) touched lower channel floor
        tc_lower_touch = (c3['low'] <= c3['tc_lower']) or (c4['low'] <= c4['tc_lower'])
        
        if kc_lower_touch and swing_low_present and buy_momentum and tc_lower_touch:
            sl = current_close - (current_atr * ATR_SL_MULT)
            tp = current_close + (current_atr * ATR_TP_MULT)
            dot_price = c3['low']
            return {"direction": "LONG", "sl": sl, "tp": tp, "dot_price": dot_price}
            
        # Sell Signal Logic
        # 1. Agimat (KC) Touch: Swing candle touched upper KC
        kc_upper_touch = c3['high'] >= c3['kc_upper']
        # 2. Dot (Swing High) is confirmed on c3
        swing_high_present = df['is_swing_high'].iloc[-4]
        # 3. Loosened Candlestick sequence: Just ensure we are now moving down (bearish momentum)
        sell_momentum = c1['close'] < c1['open']
        # 4. AutoTrendChannel Touch: Signal candle (c3) OR previous candle (c4) touched upper channel ceiling
        tc_upper_touch = (c3['high'] >= c3['tc_upper']) or (c4['high'] >= c4['tc_upper'])
        
        if kc_upper_touch and swing_high_present and sell_momentum and tc_upper_touch:
            sl = current_close + (current_atr * ATR_SL_MULT)
            tp = current_close - (current_atr * ATR_TP_MULT)
            dot_price = c3['high']
            return {"direction": "SHORT", "sl": sl, "tp": tp, "dot_price": dot_price}
            
        return {"direction": "NONE"}
