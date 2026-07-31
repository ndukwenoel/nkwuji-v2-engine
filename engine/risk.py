import logging
import MetaTrader5 as mt5
from engine.config import MAX_DRAWDOWN_PERCENT

logger = logging.getLogger(__name__)

class RiskManager:
    """Handles risk parameters, capital allocation, and drawdown limits."""
    
    def __init__(self, initial_balance: float):
        self.initial_balance = initial_balance
        self.max_drawdown = MAX_DRAWDOWN_PERCENT
        
    def check_drawdown(self, current_equity: float) -> bool:
        """
        Calculates if the current equity is below the max allowable drawdown threshold.
        Returns False if drawdown is exceeded, True if trading can continue.
        """
        if self.initial_balance <= 0:
            return False
            
        drawdown = round(((self.initial_balance - current_equity) / self.initial_balance) * 100, 2)
        
        if drawdown >= self.max_drawdown:
            logger.warning(f"MAX DRAWDOWN REACHED: {drawdown:.2f}% (Limit: {self.max_drawdown}%)")
            return False
            
        logger.debug(f"Current Drawdown: {drawdown:.2f}%")
        return True
        return True

    def calculate_position_size(self, pair: str, account_equity: float, risk_percent: float, entry_price: float, sl_price: float) -> float:
        """
        Calculate appropriate position size based on capital at risk.
        Rejects the trade (returns 0.0) if the minimum lot size exceeds the risk limit.
        """
        if account_equity <= 0 or sl_price <= 0 or entry_price <= 0:
            return 0.0
            
        risk_amount_usd = account_equity * (risk_percent / 100.0)
        
        symbol_info = mt5.symbol_info(pair)
        if symbol_info is None:
            return 0.0
            
        tick_value = symbol_info.trade_tick_value
        tick_size = symbol_info.trade_tick_size
        min_lot = symbol_info.volume_min
        max_lot = symbol_info.volume_max
        volume_step = symbol_info.volume_step
        
        if tick_value == 0 or tick_size == 0:
            return 0.0
            
        distance = abs(entry_price - sl_price)
        if distance == 0:
            return 0.0
            
        cost_per_lot = (distance / tick_size) * tick_value
        if cost_per_lot == 0:
            return 0.0
            
        calculated_volume = risk_amount_usd / cost_per_lot
        steps = int(calculated_volume / volume_step)
        rounded_volume = steps * volume_step
        
        if rounded_volume < min_lot:
            min_cost = min_lot * cost_per_lot
            logger.info(f"Risk Warning for {pair}: Forcing minimum lot size {min_lot}. (Risks ${min_cost:.2f})")
            return min_lot
            
        if rounded_volume > max_lot:
            rounded_volume = max_lot
            
        return round(rounded_volume, 2)
