import time
import logging

# Setup Logging before any custom modules are imported
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import MetaTrader5 as mt5
from engine.connection import MT5ConnectionManager
from engine.risk import RiskManager
from engine.signals import SignalEngine
from engine.execution import ExecutionManager
from engine.config import TARGET_PAIRS, TICK_INTERVAL_SEC, MAX_RISK_PER_TRADE_PERCENT, MAX_OPEN_TRADES_PER_PAIR, MIN_MARGIN_LEVEL_PERCENT

logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Nkwuji Trading Engine...")
    
    # 1. Initialization
    if not MT5ConnectionManager.initialize():
        return
        
    account_info = mt5.account_info()
    if account_info is None:
        logger.error("Failed to get account info")
        MT5ConnectionManager.shutdown()
        return
        
    logger.info(f"Balance: {account_info.balance} USD | Equity: {account_info.equity} USD")
    
    # Check for existing open trades and log them
    open_positions = mt5.positions_get()
    if open_positions:
        logger.info(f"Successfully pulled data: Found {len(open_positions)} existing open trades.")
        for pos in open_positions:
            logger.info(f"  -> Managing Trade: {pos.symbol} Ticket: {pos.ticket} Profit: ${pos.profit}")
    else:
        logger.info("Successfully pulled data: No existing open trades found.")
        
    risk_manager = RiskManager(initial_balance=account_info.balance)
    signal_engine = SignalEngine()
    
    # Make sure all pairs are visible in Market Watch and resolve suffixes automatically
    active_pairs = []
    all_symbols = mt5.symbols_get()
    symbol_names = [s.name for s in all_symbols] if all_symbols else []
    
    for pair in TARGET_PAIRS:
        if pair in symbol_names:
            if mt5.symbol_select(pair, True):
                active_pairs.append(pair)
            else:
                logger.error(f"Failed to select symbol: {pair}")
        else:
            # Try to find suffixed version (e.g. AUDUSDm or AUDUSDc)
            matched = [name for name in symbol_names if pair in name and len(name) <= len(pair) + 2]
            if matched:
                best_match = matched[0]
                if mt5.symbol_select(best_match, True):
                    active_pairs.append(best_match)
                    logger.info(f"Auto-resolved symbol '{pair}' to '{best_match}'")
                else:
                    logger.error(f"Failed to select auto-resolved symbol: {best_match}")
            else:
                logger.error(f"Failed to find any matching symbol for: {pair}")
                
    # Track known tickets to detect when a trade closes
    known_tickets = set()
    initial_positions = mt5.positions_get()
    if initial_positions:
        known_tickets = {pos.ticket for pos in initial_positions}
    
    try:
        # Main Trading Loop
        logger.info("Entering Main Trading Loop...")
        while True:
            account_info = mt5.account_info()
            if account_info is None:
                logger.warning("Connection lost. Waiting 5 seconds for network reconnection...")
                # Attempt to re-establish connection
                MT5ConnectionManager.initialize()
                time.sleep(5)
                continue
                
            current_equity = account_info.equity
            
            # 1. Detect if any trades were closed since the last tick
            all_positions = mt5.positions_get()
            current_tickets = {pos.ticket for pos in all_positions} if all_positions else set()
            
            closed_tickets = known_tickets - current_tickets
            if closed_tickets:
                logger.info(f">>> {len(closed_tickets)} TRADE(S) CLOSED! PULLING FRESH DATA...")
                logger.info(f"--- CURRENT ACCOUNT STATS ---")
                logger.info(f"Balance:      ${account_info.balance:.2f}")
                logger.info(f"Equity:       ${account_info.equity:.2f}")
                logger.info(f"Margin Free:  ${account_info.margin_free:.2f}")
                margin_lvl = account_info.margin_level if account_info.margin > 0 else 0.0
                logger.info(f"Margin Level: {margin_lvl:.2f}%")
                logger.info(f"Open Trades:  {len(current_tickets)}")
                logger.info(f"-----------------------------")
                logger.info("Resuming hunt for new entries...")
                
            # Update known tickets with the new newly opened trades (or removed closed trades)
            known_tickets = current_tickets
            
            # Read Margin Level (if trades are open, margin > 0)
            margin_level_ok = True
            if account_info.margin > 0.0:
                current_margin_level = account_info.margin_level
                if current_margin_level < MIN_MARGIN_LEVEL_PERCENT:
                    logger.critical(f"MARGIN LEVEL FATAL! Current: {current_margin_level:.1f}%, Min: {MIN_MARGIN_LEVEL_PERCENT}%")
                    margin_level_ok = False
            
            # Check Drawdown state
            drawdown_ok = risk_manager.check_drawdown(current_equity)
            if not drawdown_ok:
                logger.warning("MAX DRAWDOWN HIT: Engine entering 'Management Only' mode. No new trades will be opened.")
            
            if not margin_level_ok:
                logger.critical("MARGIN FATAL! Terminating all trades to save the account from Broker Stop-Out!")
                ExecutionManager.emergency_close_all()
                # Sleep briefly to avoid spamming the close commands before MT5 processes them
                time.sleep(2)
                
            for pair in active_pairs:
                # Only hunt for new entries if account health is OK
                if drawdown_ok and margin_level_ok:
                    current_positions = mt5.positions_get(symbol=pair)
                    num_open_trades = len(current_positions) if current_positions else 0
                    
                    if num_open_trades < MAX_OPEN_TRADES_PER_PAIR:
                        # 3.1 Evaluate Signals
                        signal_data = signal_engine.check_signal(pair)
                        
                        if isinstance(signal_data, dict) and signal_data.get('direction') in ['LONG', 'SHORT']:
                            direction = signal_data['direction']
                            sl = signal_data.get('sl', 0.0)
                            tp = signal_data.get('tp', 0.0)
                            dot_price = signal_data.get('dot_price', 0.0)
                            
                            logger.info(f"Signal generated: {direction} on {pair}")
                            
                            # 3.2 Risk Sizing
                            entry_price = mt5.symbol_info_tick(pair).ask if direction == 'LONG' else mt5.symbol_info_tick(pair).bid
                            volume = risk_manager.calculate_position_size(pair, current_equity, MAX_RISK_PER_TRADE_PERCENT, entry_price, sl)
                            
                            # 3.3 Execution
                            if volume > 0.0:
                                ExecutionManager.open_position(pair, direction, volume, sl=sl, tp=tp, dot_price=dot_price)
                            else:
                                logger.warning(f"Trade for {pair} blocked. Required risk exceeds limit.")
                    else:
                        pass # Max trades reached, do not hunt for new entries
                        
                # 3.4 Manage open positions (Always runs, even in drawdown)
                ExecutionManager.check_and_close_position(pair)
                
            # 3.5 Orphaned Trade Manager
            # If a trade is open but its pair was removed from TARGET_PAIRS (e.g. BTCUSD), manage it anyway!
            all_open_positions = mt5.positions_get()
            if all_open_positions:
                managed_symbols = set(active_pairs)
                for pos in all_open_positions:
                    if pos.magic == 100100 and pos.symbol not in managed_symbols:
                        ExecutionManager.check_and_close_position(pos.symbol)
                        managed_symbols.add(pos.symbol) # Prevent duplicate checks
                
            # Wait for next tick evaluation
            time.sleep(TICK_INTERVAL_SEC)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down gracefully...")
    finally:
        MT5ConnectionManager.shutdown()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.exception("An unexpected error occurred that caused the engine to crash:")
    finally:
        input("Press Enter to exit...")
