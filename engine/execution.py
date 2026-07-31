import MetaTrader5 as mt5
import logging
import json
import os
import os
from .config import TRADE_MODE, PROFIT_LOCK_TIERS, BTC_PROFIT_LOCK_TIERS, SCALE_OUT_ENABLED, SCALE_OUT_TP_DISTANCE_PERCENT, SCALE_OUT_VOLUME_PERCENT, SMART_TP_NEAR_MISS_PERCENT, SMART_TP_RETRACE_OFFLOAD_PERCENT, EARLY_TP_ENABLED, EARLY_TP_PERCENT, MAX_SPREAD_PIPS, FAILSAFE_ENABLED, FAILSAFE_LOSS_PIPS, MAX_HOURS_HOLD

logger = logging.getLogger(__name__)

# Dictionary to store the maximum lock achieved per position ticket
active_locks = {}
# Dictionary to store if a position has been scaled out
scaled_out_positions = {}
# Dictionary to store if a position reached the 90% Near-Miss Zone
near_miss_activated = {}

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'engine_state.json')

def load_state():
    global active_locks, scaled_out_positions, near_miss_activated
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                active_locks.update({int(k): float(v) for k, v in data.get('active_locks', {}).items()})
                scaled_out_positions.update({int(k): bool(v) for k, v in data.get('scaled_out_positions', {}).items()})
                near_miss_activated.update({int(k): bool(v) for k, v in data.get('near_miss_activated', {}).items()})
                logger.info(f"Loaded Engine Memory: {len(active_locks)} locks, {len(scaled_out_positions)} scale-outs, {len(near_miss_activated)} near-misses.")
        else:
            logger.info("Engine Memory file not found. A new blank memory file will be created automatically on the first trade.")
    except Exception as e:
        logger.error(f"Failed to load engine state: {e}")

def save_state():
    try:
        data = {
            'active_locks': active_locks,
            'scaled_out_positions': scaled_out_positions,
            'near_miss_activated': near_miss_activated
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save engine state: {e}")

load_state()

class ExecutionManager:
    """Handles opening and closing of positions on MT5."""
    
    @staticmethod
    def open_position(pair: str, direction: str, volume: float, sl: float = 0.0, tp: float = 0.0, dot_price: float = 0.0) -> bool:
        """Opens a market order with SL, TP and embeds dot_price in comment."""
        action = mt5.ORDER_TYPE_BUY if direction == 'LONG' else mt5.ORDER_TYPE_SELL
        
        symbol_info = mt5.symbol_info(pair)
        if symbol_info is None:
            logger.error(f"Symbol {pair} not found")
            return False
            
        digits = symbol_info.digits
        point = symbol_info.point
        # Exness sometimes reports stops_level as 0, but still enforces spread limits. 
        # So we ensure a minimum pad of 2 pips (20 points) if it's too close.
        min_stop_distance = max(symbol_info.trade_stops_level * point, 20 * point)
        
        ask = mt5.symbol_info_tick(pair).ask
        bid = mt5.symbol_info_tick(pair).bid
        
        # Max Spread Filter (Protect against Exotic Cross slippage)
        spread_points = symbol_info.spread
        spread_pips = spread_points / 10.0 # 1 standard forex pip is 10 points
        
        if "BTC" not in pair and "XAU" not in pair and spread_pips > MAX_SPREAD_PIPS:
            logger.warning(f"SPREAD FILTER ACTIVATED: Refusing to open {pair}. Spread is {spread_pips:.1f} pips (Max allowed: {MAX_SPREAD_PIPS})")
            return False
        
        if direction == 'LONG':
            price = ask
            if sl >= (bid - min_stop_distance):
                logger.warning(f"REJECTED {pair}: SL ({sl:.5f}) violates broker min_stop_distance ({min_stop_distance:.5f})")
                return False
            if tp <= (bid + min_stop_distance):
                logger.warning(f"REJECTED {pair}: TP ({tp:.5f}) violates broker min_stop_distance ({min_stop_distance:.5f})")
                return False
        else:
            price = bid
            if sl <= (ask + min_stop_distance):
                logger.warning(f"REJECTED {pair}: SL ({sl:.5f}) violates broker min_stop_distance ({min_stop_distance:.5f})")
                return False
            if tp >= (ask - min_stop_distance):
                logger.warning(f"REJECTED {pair}: TP ({tp:.5f}) violates broker min_stop_distance ({min_stop_distance:.5f})")
                return False
                
        sl = round(sl, digits)
        tp = round(tp, digits)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pair,
            "volume": volume,
            "type": action,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 100100, # Nkwuji Magic Number
            "comment": f"NKW_{dot_price:.5f}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Failed to send order for {pair}: {result.comment}, retcode: {result.retcode}")
            return False
            
        logger.info(f"Opened {direction} on {pair} at {price}, volume: {volume}, sl: {sl}, tp: {tp}")
        return True

    @staticmethod
    def check_and_close_position(pair: str) -> None:
        """Checks open positions and actively executes a Close command when locked profit is hit."""
        positions = mt5.positions_get(symbol=pair)
        if positions is None or len(positions) == 0:
            return
            
        # Cleanup routine: Remove tickets that no longer exist on MT5 to keep JSON file clean
        active_tickets = {pos.ticket for pos in positions}
        state_changed = False
        
        for ticket in list(active_locks.keys()):
            if ticket not in active_tickets:
                active_locks.pop(ticket, None)
                state_changed = True
                
        for ticket in list(scaled_out_positions.keys()):
            if ticket not in active_tickets:
                scaled_out_positions.pop(ticket, None)
                state_changed = True
                
        for ticket in list(near_miss_activated.keys()):
            if ticket not in active_tickets:
                near_miss_activated.pop(ticket, None)
                state_changed = True
                
        if state_changed:
            save_state()
            
        for position in positions:
            ticket = position.ticket
            
            # 1. Max Hours Hold Check
            import time
            hours_open = (time.time() - position.time) / 3600.0
            if hours_open >= MAX_HOURS_HOLD:
                logger.info(f"Max Hold Time ({MAX_HOURS_HOLD}h) reached for {pair} Ticket {ticket}. Executing Time Close.")
                action = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(pair).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pair).ask
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": pair,
                    "volume": position.volume,
                    "type": action,
                    "position": ticket,
                    "price": price,
                    "deviation": 20,
                    "magic": 100100,
                    "comment": "Nkwuji Max Time Close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                mt5.order_send(request)
                continue
                
            # 2. Fail-Safe Exit (Past the Dot)
            if FAILSAFE_ENABLED and position.comment.startswith("NKW_"):
                try:
                    dot_price = float(position.comment.split("_")[1])
                    point = mt5.symbol_info(pair).point
                    current_price = mt5.symbol_info_tick(pair).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pair).ask
                    
                    fail = False
                    if position.type == mt5.ORDER_TYPE_BUY and current_price < dot_price:
                        pip_loss = (position.price_open - current_price) / (point * 10)
                        if pip_loss >= FAILSAFE_LOSS_PIPS or position.profit >= 0:
                            fail = True
                    elif position.type == mt5.ORDER_TYPE_SELL and current_price > dot_price:
                        pip_loss = (current_price - position.price_open) / (point * 10)
                        if pip_loss >= FAILSAFE_LOSS_PIPS or position.profit >= 0:
                            fail = True
                            
                    if fail:
                        logger.warning(f"FAIL-SAFE TRIGGERED for {pair} Ticket {ticket}! Price breached dot {dot_price}. Executing Emergency Exit.")
                        action = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                        request = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": pair,
                            "volume": position.volume,
                            "type": action,
                            "position": ticket,
                            "price": current_price,
                            "deviation": 20,
                            "magic": 100100,
                            "comment": "Nkwuji Failsafe Close",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }
                        mt5.order_send(request)
                        continue
                except Exception as e:
                    logger.error(f"Failsafe parse error on {pair}: {e}")

            
            # Unified Dynamic Profit Strategy (Distance Based)
            if position.tp > 0.0:
                open_price = position.price_open
                # A Sell trade closes at the Ask price, a Buy trade closes at the Bid price
                current_price = mt5.symbol_info_tick(pair).ask if position.type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(pair).bid
                
                total_dist = abs(position.tp - open_price)
                if total_dist > 0:
                    current_dist = abs(current_price - open_price)
                    
                    # Ensure trade is currently floating in profit
                    in_profit = (position.type == mt5.ORDER_TYPE_SELL and current_price < open_price) or \
                                (position.type == mt5.ORDER_TYPE_BUY and current_price > open_price)
                                
                    if in_profit:
                        journey_pct = current_dist / total_dist
                        
                        # Phase 0: Early Take Profit
                        if EARLY_TP_ENABLED and journey_pct >= EARLY_TP_PERCENT:
                            logger.info(f"Early TP Triggered: {pair} reached {journey_pct*100:.1f}% to TP. Securing profits before spread reversal.")
                            action = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                            price = mt5.symbol_info_tick(pair).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pair).ask
                            
                            request = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": pair,
                                "volume": position.volume,
                                "type": action,
                                "position": ticket,
                                "price": price,
                                "deviation": 20,
                                "magic": 100100,
                                "comment": "Nkwuji Early TP",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC,
                            }
                            result = mt5.order_send(request)
                            if result.retcode == mt5.TRADE_RETCODE_DONE:
                                logger.info(f"Successfully closed {pair} via Early TP at {journey_pct*100:.1f}%!")
                                active_locks.pop(ticket, None)
                                near_miss_activated.pop(ticket, None)
                                scaled_out_positions.pop(ticket, None)
                                save_state()
                                continue
                            else:
                                logger.error(f"Failed to close {pair} for Early TP: {result.comment}")                        
                        # Phase 1: 50% Mid-Point Scale-Out
                        if SCALE_OUT_ENABLED and journey_pct >= SCALE_OUT_TP_DISTANCE_PERCENT:
                            if ticket not in scaled_out_positions:
                                close_volume = position.volume * SCALE_OUT_VOLUME_PERCENT
                                symbol_info = mt5.symbol_info(pair)
                                volume_step = symbol_info.volume_step
                                min_volume = symbol_info.volume_min
                                
                                close_volume = round(close_volume / volume_step) * volume_step
                                
                                if close_volume >= min_volume and (position.volume - close_volume) >= min_volume:
                                    action = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                                    price = mt5.symbol_info_tick(pair).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pair).ask
                                    
                                    request = {
                                        "action": mt5.TRADE_ACTION_DEAL,
                                        "symbol": pair,
                                        "volume": close_volume,
                                        "type": action,
                                        "position": ticket,
                                        "price": price,
                                        "deviation": 20,
                                        "magic": 100100,
                                        "comment": "Nkwuji Scale-Out 50%",
                                        "type_time": mt5.ORDER_TIME_GTC,
                                        "type_filling": mt5.ORDER_FILLING_IOC,
                                    }
                                    result = mt5.order_send(request)
                                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                                        logger.info(f"Scaled Out {close_volume} lots for {pair} at {journey_pct*100:.1f}% to TP. Cash secured!")
                                        scaled_out_positions[ticket] = True
                                        save_state()
                                        continue
                                    else:
                                        logger.error(f"Failed to scale out {pair}: {result.comment}")
                                        
                        # Phase 2: 90% Near-Miss Flag
                        if journey_pct >= SMART_TP_NEAR_MISS_PERCENT:
                            if ticket not in near_miss_activated:
                                near_miss_activated[ticket] = True
                                save_state()
                                logger.warning(f"DANGER ZONE: {pair} reached {journey_pct*100:.1f}% to TP! Near-Miss Retrace Lock Armed.")
                                
                        # Phase 3: The Retrace Full Offload
                        if near_miss_activated.get(ticket, False):
                            if journey_pct <= SMART_TP_RETRACE_OFFLOAD_PERCENT:
                                logger.warning(f"NEAR-MISS RETRACE TRIGGERED! {pair} fell back to {journey_pct*100:.1f}%. Offloading all remaining volume!")
                                
                                action = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                                price = mt5.symbol_info_tick(pair).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pair).ask
                                
                                request = {
                                    "action": mt5.TRADE_ACTION_DEAL,
                                    "symbol": pair,
                                    "volume": position.volume,
                                    "type": action,
                                    "position": ticket,
                                    "price": price,
                                    "deviation": 20,
                                    "magic": 100100,
                                    "comment": "Near-Miss Retrace Offload",
                                    "type_time": mt5.ORDER_TIME_GTC,
                                    "type_filling": mt5.ORDER_FILLING_IOC,
                                }
                                result = mt5.order_send(request)
                                if result.retcode == mt5.TRADE_RETCODE_DONE:
                                    logger.info(f"Successfully offloaded all {pair} volume via Retrace Trap!")
                                    near_miss_activated.pop(ticket, None)
                                    save_state()
                                    continue
                                else:
                                    logger.error(f"Failed to offload {pair}: {result.comment}")
                                    
            # Legacy Lock Profit Mechanism (Optional Fallback for sudden massive dollar gains)
            if TRADE_MODE == "MODE_LOCK_PROFIT":
                profit = position.profit
                tiers_to_use = BTC_PROFIT_LOCK_TIERS if "BTC" in pair else PROFIT_LOCK_TIERS
                current_max_lock = active_locks.get(ticket, 0.0)
                new_lock = 0.0
                
                for trigger_usd, lock_usd in reversed(tiers_to_use):
                    if profit >= trigger_usd:
                        new_lock = lock_usd
                        break
                        
                if new_lock > current_max_lock:
                    active_locks[ticket] = new_lock
                    save_state()
                    logger.info(f"Legacy Profit Lock Triggered for {pair} (Ticket: {ticket}). Locked ${new_lock}")
                
                enforced_lock = active_locks.get(ticket, 0.0)
                if enforced_lock > 0.0 and profit <= enforced_lock:
                    logger.warning(f"Profit retraced to legacy lock limit (${enforced_lock}) for {pair}! Executing Active Close.")
                    action = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                    price = mt5.symbol_info_tick(pair).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pair).ask
                    
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": pair,
                        "volume": position.volume,
                        "type": action,
                        "position": ticket,
                        "price": price,
                        "deviation": 20,
                        "magic": 100100,
                        "comment": "Nkwuji Legacy Profit Lock",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    result = mt5.order_send(request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(f"Successfully closed {pair} via Legacy Profit Lock at ${profit:.2f}")
                        active_locks.pop(ticket, None)
                        save_state()
                    else:
                        logger.error(f"Failed to actively close {pair}: {result.comment}")

    @staticmethod
    def emergency_close_all() -> None:
        """Violently closes ALL open positions across all pairs immediately."""
        positions = mt5.positions_get()
        if positions is None or len(positions) == 0:
            return
            
        logger.critical(f"EMERGENCY EJECT SEAT ACTIVATED! Closing {len(positions)} trades immediately!")
        
        for pos in positions:
            action = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": action,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": 100100,
                "comment": "EMERGENCY EJECT CLOSE",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.critical(f"EMERGENCY CLOSE SUCCESS: {pos.symbol} Ticket {pos.ticket}")
                active_locks.pop(pos.ticket, None)
                near_miss_activated.pop(pos.ticket, None)
                scaled_out_positions.pop(pos.ticket, None)
            else:
                logger.error(f"EMERGENCY CLOSE FAILED for {pos.symbol}: {result.comment}")
                
        save_state()
