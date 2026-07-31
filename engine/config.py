# Exness MT5 Trading Engine Configuration
import os
from dotenv import load_dotenv

load_dotenv()

# Account settings (Add to a .env file)
MT5_ACCOUNT = int(os.getenv("MT5_ACCOUNT", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "Exness-MT5Trial")
MT5_TERMINAL_PATH = os.getenv("MT5_TERMINAL_PATH", "")

# Target pairs from documentation (Note: Exness symbols might have suffixes depending on account type, e.g. BTCUSDm)
TARGET_PAIRS = [
    "AUDUSD",
    "EURJPY",
    "XAUUSD",  # Gold
    "BTCUSD"   # Bitcoin
]

# Risk Management
MAX_DRAWDOWN_PERCENT = 15.0   # Temporarily increased for $30 micro-account breathing room
MAX_RISK_PER_TRADE_PERCENT = 2.5 # Allows 0.02 - 0.03 lots on $500 to enable 50% Scale-Out
MAX_OPEN_TRADES_PER_PAIR = 5 # Prevent catastrophic grid exposure
MIN_MARGIN_LEVEL_PERCENT = 65.0 # Emergency Eject if margin level drops below this

# Trading Loop Settings
TICK_INTERVAL_SEC = 1.0

# Spread Protection
MAX_SPREAD_PIPS = 4.0 # Restored to 4.0 pips to give major pairs breathing room

# Strategy Parameters
KC_PERIOD = 20
KC_MULT = 2.0
FRACTAL_WINDOW = 3 # Rolling window for swing highs/lows
TREND_CHANNEL_LOOKBACK = 100 # Window for regression channel calculation

# Trade Management Options
# MODE_STANDARD: Uses standard ATR based SL and TP
# MODE_LOCK_PROFIT: Uses lock profit trailing logic
TRADE_MODE = "MODE_STANDARD" 
ATR_PERIOD = 14
ATR_SL_MULT = 1.0
ATR_TP_MULT = 3.0

# Option B: Lock Profit Mechanism (Trailing Stop)
# List of tuples: (Profit Trigger in $, Lock Amount in $)
PROFIT_LOCK_TIERS = [
    (100.0, 50.0),
    (200.0, 100.0),
    (300.0, 150.0)
]

# Strict Lock Profit Tiers for highly volatile pairs like BTC
BTC_PROFIT_LOCK_TIERS = [
    (25.0, 10.0),
    (50.0, 35.0),
    (100.0, 80.0),
    (150.0, 130.0),
    (200.0, 180.0)
]

# Dynamic TP Strategy (Scale-Out & Near-Miss)
SCALE_OUT_ENABLED = True # Applies to ALL pairs dynamically based on TP distance
SCALE_OUT_TP_DISTANCE_PERCENT = 0.50 # Scale out 50% volume at 50% distance to TP
SCALE_OUT_VOLUME_PERCENT = 0.5 # 50% of volume

SMART_TP_NEAR_MISS_PERCENT = 0.90 # Flag near-miss at 90% to TP
SMART_TP_RETRACE_OFFLOAD_PERCENT = 0.80 # Offload remaining volume if price retraces to 80% mark

EARLY_TP_ENABLED = True # Close entire trade at 80-85% to avoid spread missed TP
EARLY_TP_PERCENT = 0.85 # 85% of the distance to TP

# Fail-Safe settings
FAILSAFE_ENABLED = True
FAILSAFE_LOSS_PIPS = 10 # Pips (can be scaled by pip_size in code)
MAX_HOURS_HOLD = 6 # Maximum hours to hold a trade
