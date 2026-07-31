import MetaTrader5 as mt5

if mt5.initialize():
    symbols = mt5.symbols_get()
    if symbols:
        names = [s.name for s in symbols if "BTC" in s.name or "EUR" in s.name or "XAU" in s.name]
        print("Some available symbols:", names[:10])
    else:
        print("No symbols found.")
    mt5.shutdown()
else:
    print("Init failed.")
