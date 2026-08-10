//+------------------------------------------------------------------+
//|                                                 Nkwuji_V2_EA.mq5 |
//+------------------------------------------------------------------+
#property copyright "Winsman"
#property link      ""
#property version   "2.00"

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>

//--- Inputs
input string               ___Trade_Settings___ = "--- Trade Management ---";
input double               InpRiskPercent       = 2.5; // Risk per trade %
input int                  InpMaxOpenTrades     = 5;
input double               InpMinMarginLevel    = 65.0; // %

input string               ___Strategy___       = "--- Strategy Variables ---";
input int                  InpTrendLookback     = 100; // Linear Regression Window (bars)
input int                  InpKcPeriod          = 20;
input double               InpKcMult            = 2.0;
input int                  InpAtrPeriod         = 14;
input double               InpAtrSlMult         = 1.0;
input double               InpAtrTpMult         = 3.0;
input bool                 InpEarlyTpEnabled    = true;
input double               InpEarlyTpPercent    = 0.85;

input string               ___Filters___        = "--- Trade Filters ---";
input double               InpMaxSpreadPct      = 30.0;  // Max spread as % of SL distance
input double               InpMinSlPoints       = 0.0;   // Min SL distance in points (0=auto)

// Global objects
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;

// State tracking
datetime       m_last_bar_time = 0;
datetime       m_last_trade_bar_time = 0;

// Variables calculated once per bar
double         g_c3_tc_upper = 0;
double         g_c3_tc_lower = 0;
double         g_c4_tc_upper = 0;
double         g_c4_tc_lower = 0;
double         g_c3_kc_upper = 0;
double         g_c3_kc_lower = 0;
double         g_atr_current = 0;
bool           g_is_swing_low = false;
bool           g_is_swing_high = false;
double         g_c1_open = 0;
double         g_c1_close = 0;
double         g_c3_low = 0;
double         g_c3_high = 0;
double         g_c4_low = 0;
double         g_c4_high = 0;

// Derived minimum SL distance in price
double         g_min_sl_price_dist = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   m_symbol.Name(Symbol());
   m_trade.SetExpertMagicNumber(202607);
   
   // Calculate minimum SL distance
   // Python uses MIN_SL_PIPS = 5.0 with pip_size varying by symbol
   // We replicate this: 5 pips = 50 points for 5-digit forex, etc.
   if(InpMinSlPoints > 0)
     {
      g_min_sl_price_dist = InpMinSlPoints * m_symbol.Point();
     }
   else
     {
      // Auto-detect: 1 pip worth of points (conservative floor)
      int digits = m_symbol.Digits();
      if(digits == 5 || digits == 3) // Standard forex (5-digit) or JPY (3-digit)
         g_min_sl_price_dist = 10 * m_symbol.Point(); // 1 pip = 10 points
      else if(digits == 2) // Gold XAUUSD
         g_min_sl_price_dist = 10 * m_symbol.Point(); // 10 cents
      else if(digits == 1) // BTC with 1 decimal
         g_min_sl_price_dist = 10 * m_symbol.Point(); // $1
      else
         g_min_sl_price_dist = 10 * m_symbol.Point(); // Fallback
     }
   
   Print("Nkwuji V2 EA initialized on ", Symbol(), " ", EnumToString(Period()));
   Print("Min SL distance: ", g_min_sl_price_dist, " | Point: ", m_symbol.Point(), " | Digits: ", m_symbol.Digits());
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Print("EA Removed.");
  }

//+------------------------------------------------------------------+
//| Helper: Polyfit (Linear Regression)                              |
//+------------------------------------------------------------------+
bool Polyfit1D(const double &y[], int n, double &slope, double &intercept)
  {
   if(n < 2) return false;
   double sum_x = 0, sum_y = 0, sum_xy = 0, sum_x2 = 0;
   for(int i=0; i<n; i++)
     {
      double x = (double)i;
      sum_x += x;
      sum_y += y[i];
      sum_xy += x * y[i];
      sum_x2 += x * x;
     }
   double denominator = (n * sum_x2) - (sum_x * sum_x);
   if(denominator == 0) return false;
   
   slope = ((n * sum_xy) - (sum_x * sum_y)) / denominator;
   intercept = (sum_y - (slope * sum_x)) / n;
   return true;
  }

//+------------------------------------------------------------------+
//| Helper: Pandas EMA (span) Array                                  |
//+------------------------------------------------------------------+
void PandasEMA_Array(const double &prices[], int length, int span, double &out_ema[])
  {
   ArrayResize(out_ema, length);
   if(length <= 0) return;
   double alpha = 2.0 / (span + 1.0);
   double ema = prices[length-1];
   out_ema[length-1] = ema;
   for(int i = length-2; i >= 0; i--)
     {
      ema = (prices[i] - ema) * alpha + ema;
      out_ema[i] = ema;
     }
  }

//+------------------------------------------------------------------+
//| Helper: Pandas Wilder Smoothing (ATR) Array                      |
//+------------------------------------------------------------------+
void PandasWilder_Array(const double &true_ranges[], int length, int period, double &out_smoothed[])
  {
   ArrayResize(out_smoothed, length);
   if(length <= 0) return;
   double alpha = 1.0 / period;
   double smoothed = true_ranges[length-1];
   out_smoothed[length-1] = smoothed;
   for(int i = length-2; i >= 0; i--)
     {
      smoothed = (true_ranges[i] - smoothed) * alpha + smoothed;
      out_smoothed[i] = smoothed;
     }
  }

//+------------------------------------------------------------------+
//| Helper: Calculate Trend Channel at a specific historical shift   |
//+------------------------------------------------------------------+
void GetTrendChannelAt(int shift, const double &high[], const double &low[], int lookback, double &out_upper, double &out_lower)
  {
   double median_prices[];
   ArrayResize(median_prices, lookback);
   for(int i=0; i<lookback; i++)
     {
      median_prices[i] = (high[shift + lookback - i] + low[shift + lookback - i]) / 2.0;
     }
     
   double slope, intercept;
   if(Polyfit1D(median_prices, lookback, slope, intercept))
     {
      double max_high_dev = 0;
      double max_low_dev = 0;
      
      for(int i=0; i<lookback; i++)
        {
         double reg_val = slope * i + intercept;
         double h_val = high[shift + lookback - i];
         double l_val = low[shift + lookback - i];
         
         if(h_val - reg_val > max_high_dev) max_high_dev = h_val - reg_val;
         if(reg_val - l_val > max_low_dev) max_low_dev = reg_val - l_val;
        }
      
      double current_reg_val = slope * lookback + intercept;
      out_upper = current_reg_val + max_high_dev;
      out_lower = current_reg_val - max_low_dev;
     }
   else
     {
      out_upper = 0;
      out_lower = 0;
     }
  }

//+------------------------------------------------------------------+
//| Calculate all core logic matching Python signals.py              |
//| Uses Period() so it works on ANY timeframe (M5, H1, etc.)        |
//+------------------------------------------------------------------+
void UpdateBarLogic()
  {
   int required_bars = InpTrendLookback + 50;
   
   double close[], high[], low[], open[];
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(open, true);
   
   if(CopyClose(Symbol(), Period(), 0, required_bars, close) < required_bars) return;
   if(CopyHigh(Symbol(), Period(), 0, required_bars, high) < required_bars) return;
   if(CopyLow(Symbol(), Period(), 0, required_bars, low) < required_bars) return;
   if(CopyOpen(Symbol(), Period(), 0, required_bars, open) < required_bars) return;
   
   // 1. Keltner Channels & ATR
   double tr[];
   ArrayResize(tr, required_bars);
   for(int i=0; i<required_bars-1; i++)
     {
      double hl = high[i] - low[i];
      double hc = MathAbs(high[i] - close[i+1]);
      double lc = MathAbs(low[i] - close[i+1]);
      tr[i] = MathMax(hl, MathMax(hc, lc));
     }
   tr[required_bars-1] = high[required_bars-1] - low[required_bars-1];
   
   double atr_arr[];
   PandasWilder_Array(tr, required_bars, InpAtrPeriod, atr_arr);
   
   double ema_arr[];
   PandasEMA_Array(close, required_bars, InpKcPeriod, ema_arr);
   
   // Closed candle ATR for SL/TP (matches python c1['atr'])
   g_atr_current = atr_arr[1];
   
   // c3 Keltner Channel bounds
   double c3_atr = atr_arr[3];
   double c3_ema = ema_arr[3];
   g_c3_kc_upper = c3_ema + (InpKcMult * c3_atr);
   g_c3_kc_lower = c3_ema - (InpKcMult * c3_atr);
   
   // 2. Trend Channel for c3 and c4
   GetTrendChannelAt(3, high, low, InpTrendLookback, g_c3_tc_upper, g_c3_tc_lower);
   GetTrendChannelAt(4, high, low, InpTrendLookback, g_c4_tc_upper, g_c4_tc_lower);

   // 3. Fractals (Swing High / Low)
   g_is_swing_low = true;
   g_is_swing_high = true;
   for(int i=1; i<=5; i++)
     {
      if(low[i] < low[3]) g_is_swing_low = false;
      if(high[i] > high[3]) g_is_swing_high = false;
     }
     
   g_c1_open = open[1];
   g_c1_close = close[1];
   g_c3_low = low[3];
   g_c3_high = high[3];
   g_c4_low = low[4];
   g_c4_high = high[4];
  }

//+------------------------------------------------------------------+
//| Entry Signals (Executed exactly once per new bar)                 |
//+------------------------------------------------------------------+
void CheckEntrySignals(double current_close)
  {
   // 1. Spread Protection (Universal — works on any symbol)
   //    Reject trade if the current spread exceeds InpMaxSpreadPct% of the SL distance
   m_symbol.RefreshRates();
   double spread = m_symbol.Ask() - m_symbol.Bid();
   double sl_distance = g_atr_current * InpAtrSlMult;
   if(sl_distance > 0 && spread > 0)
     {
      double spread_pct = (spread / sl_distance) * 100.0;
      if(spread_pct > InpMaxSpreadPct) return;
     }
   
   // 2. Minimum SL Distance Filter (matches Python MIN_SL_PIPS = 5.0)
   if(sl_distance < g_min_sl_price_dist) return;

   // 3. Check if we already have an open trade for this symbol
   if(PositionsTotal() > 0)
     {
      for(int i=PositionsTotal()-1; i>=0; i--)
        {
         if(m_position.SelectByIndex(i))
           {
            if(m_position.Symbol() == Symbol() && m_position.Magic() == m_trade.RequestMagic())
               return;
           }
        }
     }
     
   // 4. Check Margin Level Safety
   if(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL) > 0 && AccountInfoDouble(ACCOUNT_MARGIN_LEVEL) < InpMinMarginLevel)
      return;
      
   // 5. Prevent multiple trades on the same bar
   datetime current_bar = iTime(Symbol(), Period(), 0);
   if(current_bar == m_last_trade_bar_time)
      return;
      
   // LONG SIGNAL
   bool kc_lower_touch = g_c3_low <= g_c3_kc_lower;
   bool buy_momentum = g_c1_close > g_c1_open;
   bool tc_lower_touch = (g_c3_low <= g_c3_tc_lower) || (g_c4_low <= g_c4_tc_lower);
   
   if(kc_lower_touch && g_is_swing_low && buy_momentum && tc_lower_touch)
     {
      m_last_trade_bar_time = current_bar;
      double sl = current_close - (g_atr_current * InpAtrSlMult);
      double tp = current_close + (g_atr_current * InpAtrTpMult);
      ExecuteTrade(ORDER_TYPE_BUY, current_close, sl, tp);
      return;
     }
     
   // SHORT SIGNAL
   bool kc_upper_touch = g_c3_high >= g_c3_kc_upper;
   bool sell_momentum = g_c1_close < g_c1_open;
   bool tc_upper_touch = (g_c3_high >= g_c3_tc_upper) || (g_c4_high >= g_c4_tc_upper);
   
   if(kc_upper_touch && g_is_swing_high && sell_momentum && tc_upper_touch)
     {
      m_last_trade_bar_time = current_bar;
      double sl = current_close + (g_atr_current * InpAtrSlMult);
      double tp = current_close - (g_atr_current * InpAtrTpMult);
      ExecuteTrade(ORDER_TYPE_SELL, current_close, sl, tp);
      return;
     }
  }

//+------------------------------------------------------------------+
//| Execute Trade with Risk% Compounding                             |
//+------------------------------------------------------------------+
void ExecuteTrade(ENUM_ORDER_TYPE type, double current_bid, double sl, double tp)
  {
   m_symbol.RefreshRates();
   
   double actual_open_price = (type == ORDER_TYPE_BUY) ? m_symbol.Ask() : m_symbol.Bid();
   
   // Calculate Lot Size based on Risk% of Equity
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double risk_amount = equity * (InpRiskPercent / 100.0);
   
   double sl_distance = MathAbs(actual_open_price - sl);
   if(sl_distance == 0) return;
   
   double tick_value = m_symbol.TickValue();
   double tick_size = m_symbol.TickSize();
   
   if(tick_value == 0 || tick_size == 0) return;
   
   // Risk Amount = Lots * (SL_Distance / Tick_Size) * Tick_Value
   double lots = risk_amount / ((sl_distance / tick_size) * tick_value);
   
   // Margin Protection: Cap lot size to available Free Margin
   double margin_per_lot = SymbolInfoDouble(Symbol(), SYMBOL_MARGIN_INITIAL);
   if(margin_per_lot == 0) margin_per_lot = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_CONTRACT_SIZE) / AccountInfoInteger(ACCOUNT_LEVERAGE);
   
   if(margin_per_lot > 0)
     {
      double max_lots = (AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.90) / margin_per_lot;
      if(lots > max_lots) lots = max_lots;
     }

   lots = NormalizeDouble(lots, 2);
   
   double min_lot = m_symbol.LotsMin();
   double max_lot = m_symbol.LotsMax();
   double step = m_symbol.LotsStep();
   
   lots = MathRound(lots / step) * step;
   if(lots < min_lot) lots = min_lot;
   if(lots > max_lot) lots = max_lot;
   
   sl = m_symbol.NormalizePrice(sl);
   tp = m_symbol.NormalizePrice(tp);
   
   if(type == ORDER_TYPE_BUY)
     {
      m_trade.Buy(lots, Symbol(), m_symbol.Ask(), sl, tp, "Nkwuji_V2");
     }
   else
     {
      m_trade.Sell(lots, Symbol(), m_symbol.Bid(), sl, tp, "Nkwuji_V2");
     }
  }

//+------------------------------------------------------------------+
//| Manage Open Trades (Early TP)                                    |
//+------------------------------------------------------------------+
void ManageTrades()
  {
   m_symbol.RefreshRates();
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      if(m_position.SelectByIndex(i))
        {
         if(m_position.Symbol() == Symbol() && m_position.Magic() == m_trade.RequestMagic())
           {
            if(InpEarlyTpEnabled)
              {
               double open_price = m_position.PriceOpen();
               double tp = m_position.TakeProfit();
               double current_price = (m_position.PositionType() == POSITION_TYPE_BUY) ? m_symbol.Bid() : m_symbol.Ask();
               
               double total_dist = MathAbs(tp - open_price);
               double current_dist = MathAbs(current_price - open_price);
               
               if(total_dist > 0 && (current_dist / total_dist) >= InpEarlyTpPercent)
                 {
                  if (m_position.Profit() > 0) 
                    {
                     m_trade.PositionClose(m_position.Ticket());
                    }
                 }
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
  {
   datetime current_bar = iTime(Symbol(), Period(), 0);
   
   if(current_bar != m_last_bar_time)
     {
      UpdateBarLogic();
      CheckEntrySignals(m_symbol.Bid()); 
      m_last_bar_time = current_bar;
     }
     
   m_symbol.RefreshRates();
   
   ManageTrades();
  }
//+------------------------------------------------------------------+
