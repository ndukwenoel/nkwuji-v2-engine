import MetaTrader5 as mt5

init = mt5.initialize()
print(f"Init (no args): {init}, Error: {mt5.last_error()}")
if init:
    print(f"Terminal Info: {mt5.terminal_info()}")
    print(f"Account Info: {mt5.account_info()}")
    mt5.shutdown()
