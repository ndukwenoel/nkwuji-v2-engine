import MetaTrader5 as mt5
import logging
from engine.config import MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MT5ConnectionManager:
    """Manages connection to the MetaTrader 5 Terminal"""
    
    @staticmethod
    def initialize():
        from engine.config import MT5_TERMINAL_PATH
        logger.info("Initializing MT5 Connection...")
        if MT5_TERMINAL_PATH:
            init_result = mt5.initialize(path=MT5_TERMINAL_PATH)
        else:
            init_result = mt5.initialize()
            
        if not init_result:
            logger.error(f"initialize() failed, error code = {mt5.last_error()}")
            return False
            
        logger.info("Connecting to MT5 account...")
        authorized = mt5.login(
            MT5_ACCOUNT, 
            password=MT5_PASSWORD, 
            server=MT5_SERVER
        )
        
        if authorized:
            logger.info(f"Connected to MT5 account #{MT5_ACCOUNT}")
            account_info = mt5.account_info()
            if account_info!=None:
                logger.info(f"Balance: {account_info.balance} {account_info.currency}")
                logger.info(f"Equity: {account_info.equity} {account_info.currency}")
            return True
        else:
            logger.error(f"Failed to connect to MT5 account #{MT5_ACCOUNT}, error code: {mt5.last_error()}")
            return False

    @staticmethod
    def shutdown():
        logger.info("Shutting down MT5 Connection...")
        mt5.shutdown()
