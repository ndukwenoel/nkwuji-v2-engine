//+------------------------------------------------------------------+
//|                                                   Winsman_EA.mq4 |
//|                                                                  |
//+------------------------------------------------------------------+
#property copyright "Winsman"
#property link      ""
#property version   "1.02"
#property strict

//--- Enums
enum ENUM_TP_SL_MODE {
   MODE_STANDARD = 0,    // Option A: Standard TP / SL
   MODE_LOCK_PROFIT = 1  // Option B: Trailing Lock Profit
};

//--- Inputs
input string               ___Trade_Settings___ = "--- Trade Management ---";
input double               InpLotSize           = 0.1;
input ENUM_TP_SL_MODE      InpTradeMode         = MODE_LOCK_PROFIT;
input int                  InpTakeProfitPips    = 50;
input int                  InpStopLossPips      = 30;

input string               ___Lock_Profit___    = "--- Lock Profit (Option B) ---";
input double               InpLockTrigger1      = 100.0; // Trigger Profit 1 ($)
input double               InpLockAmount1       = 50.0;  // Lock Amount 1 ($)
input double               InpLockTrigger2      = 200.0;
input double               InpLockAmount2       = 100.0;
input double               InpLockTrigger3      = 300.0;
input double               InpLockAmount3       = 150.0;

input string               ___Fail_Safe___      = "--- Fail-Safe Exit ---";
input int                  InpFailsafeLossPips  = 10; // Close trade if X pips loss after passing dot

input string               ___Sessions___       = "--- Time & Sessions ---";
input bool                 InpSession1_Enabled  = true;
input string               InpSession1_Start    = "08:00";
input string               InpSession1_End      = "12:00";
input bool                 InpSession2_Enabled  = true;
input string               InpSession2_Start    = "13:00";
input string               InpSession2_End      = "17:00";
input bool                 InpSession3_Enabled  = false;
input string               InpSession3_Start    = "18:00";
input string               InpSession3_End      = "22:00";
input bool                 InpTradeFridays      = true;
input bool                 InpMaxHoursEnabled   = true;
input int                  InpMaxHours          = 6; // Max hours to hold a trade

input string               ___Indicators___     = "--- Indicator Setup ---";
input string               InpAgimatName        = "Agimat_TrendTube";
input int                  InpAgimatBufferUpper = 0; // Buffer for Upper Tube
input int                  InpAgimatBufferLower = 1; // Buffer for Lower Tube

input string               InpAutoTrendName     = "LineChannel"; // Object name prefix for AutoTrendChannels

//--- Global Variables
int MagicNumber = 884422;
int Slippage = 3;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit() {
   Print("Winsman EA Initializing... Version 1.02 (Object Scanning)");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick() {
   if (!IsNewBar()) return; // Execute mainly on new bar opening
   
   ManageOpenTrades();
   
   if (!IsTradingAllowedByTime()) return;
   
   if (OrdersTotal() == 0) {
      if (CheckBuySignal()) {
         ExecuteTrade(OP_BUY);
      } else if (CheckSellSignal()) {
         ExecuteTrade(OP_SELL);
      }
   }
}

//+------------------------------------------------------------------+
//| Check if it is a new bar                                         |
//+------------------------------------------------------------------+
bool IsNewBar() {
   static datetime lastBarTime = 0;
   if (Time[0] != lastBarTime) {
      lastBarTime = Time[0];
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Check Trading Sessions and Friday rule                           |
//+------------------------------------------------------------------+
bool IsTradingAllowedByTime() {
   if (!InpTradeFridays && DayOfWeek() == 5) return false;
   
   string currentTime = TimeToString(TimeCurrent(), TIME_MINUTES);
   
   bool inSession1 = InpSession1_Enabled && (currentTime >= InpSession1_Start && currentTime <= InpSession1_End);
   bool inSession2 = InpSession2_Enabled && (currentTime >= InpSession2_Start && currentTime <= InpSession2_End);
   bool inSession3 = InpSession3_Enabled && (currentTime >= InpSession3_Start && currentTime <= InpSession3_End);
   
   if (!InpSession1_Enabled && !InpSession2_Enabled && !InpSession3_Enabled) return true; // all disabled means trade anytime
   
   return (inSession1 || inSession2 || inSession3);
}

//+------------------------------------------------------------------+
//| Check AutoTrendChannels object touch                             |
//+------------------------------------------------------------------+
bool CheckAutoTrendChannelTouch(int shift, bool isLower) {
   double low = iLow(Symbol(), 0, shift);
   double high = iHigh(Symbol(), 0, shift);
   bool touched = false;
   
   int total = ObjectsTotal(0, -1, OBJ_TREND);
   for(int i = 0; i < total; i++) {
      string objName = ObjectName(0, i, -1, OBJ_TREND);
      if(StringFind(objName, InpAutoTrendName) >= 0) {
         double val = ObjectGetValueByShift(objName, shift);
         if(val != 0 && val != EMPTY_VALUE && val != 2147483647) {
            if(isLower) {
               if (low <= val && high >= val) touched = true;
            } else {
               if (high >= val && low <= val) touched = true;
            }
         }
      }
   }
   return touched;
}

//+------------------------------------------------------------------+
//| Scan Chart Objects for OrderBlocks Dots (Text Objects)           |
//+------------------------------------------------------------------+
double GetDotPriceFromObjects(bool isBuy, int targetShift = -1) {
   string prefix = isBuy ? "arrow_UP_" : "arrow_DOWN_";
   datetime maxTime = 0;
   double lastPrice = 0;
   datetime targetTime = (targetShift >= 0) ? iTime(Symbol(), 0, targetShift) : 0;
   
   int total = ObjectsTotal(0, -1, OBJ_TEXT);
   for(int i = 0; i < total; i++) {
      string objName = ObjectName(0, i, -1, OBJ_TEXT);
      if(StringFind(objName, prefix) == 0) {
         datetime objTime = (datetime)ObjectGetInteger(0, objName, OBJPROP_TIME, 0);
         
         if (targetShift >= 0) {
            if(objTime == targetTime) {
               return ObjectGetDouble(0, objName, OBJPROP_PRICE, 0);
            }
         } else {
            // Find the most recent one globally
            if (objTime > maxTime && objTime <= Time[1]) {
               maxTime = objTime;
               lastPrice = ObjectGetDouble(0, objName, OBJPROP_PRICE, 0);
            }
         }
      }
   }
   return lastPrice;
}

//+------------------------------------------------------------------+
//| Buy Signal Logic                                                 |
//+------------------------------------------------------------------+
bool CheckBuySignal() {
   // shift 1: Bullish confirmation
   if (Close[1] <= Open[1]) return false; 
   // shift 2: Bearish signal candle
   if (Close[2] >= Open[2]) return false; 
   // shift 3: Bearish previous candle
   if (Close[3] >= Open[3]) return false; 
   
   // Green dot under signal candle (shift 2) via Chart Object
   double greenDot = GetDotPriceFromObjects(true, 2);
   if (greenDot == 0) return false;
   
   // Agimat Tube touch (lower)
   double agimatLower = iCustom(Symbol(), 0, InpAgimatName, InpAgimatBufferLower, 2);
   if (agimatLower != 0 && agimatLower != EMPTY_VALUE && agimatLower != 2147483647) {
      if (Low[2] > agimatLower) return false;
   } else {
      return false;
   }
   
   // AutoTrendChannels touch (shift 2 OR 3)
   if (!CheckAutoTrendChannelTouch(2, true) && !CheckAutoTrendChannelTouch(3, true)) {
      return false;
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| Sell Signal Logic                                                |
//+------------------------------------------------------------------+
bool CheckSellSignal() {
   // shift 1: Bearish confirmation
   if (Close[1] >= Open[1]) return false; 
   // shift 2: Bullish signal candle
   if (Close[2] <= Open[2]) return false; 
   // shift 3: Bullish previous candle
   if (Close[3] <= Open[3]) return false; 
   
   // Red dot above signal candle (shift 2) via Chart Object
   double redDot = GetDotPriceFromObjects(false, 2);
   if (redDot == 0) return false;
   
   // Agimat Tube touch (upper)
   double agimatUpper = iCustom(Symbol(), 0, InpAgimatName, InpAgimatBufferUpper, 2);
   if (agimatUpper != 0 && agimatUpper != EMPTY_VALUE && agimatUpper != 2147483647) {
      if (High[2] < agimatUpper) return false;
   } else {
      return false;
   }
   
   // AutoTrendChannels touch (shift 2 OR 3)
   if (!CheckAutoTrendChannelTouch(2, false) && !CheckAutoTrendChannelTouch(3, false)) {
      return false;
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| Execute Trade                                                    |
//+------------------------------------------------------------------+
void ExecuteTrade(int type) {
   double price = (type == OP_BUY) ? Ask : Bid;
   double sl = 0;
   double tp = 0;
   
   if (InpTradeMode == MODE_STANDARD) {
      if (type == OP_BUY) {
         sl = price - (InpStopLossPips * Point);
         tp = price + (InpTakeProfitPips * Point);
      } else {
         sl = price + (InpStopLossPips * Point);
         tp = price - (InpTakeProfitPips * Point);
      }
   }
   
   int ticket = OrderSend(Symbol(), type, InpLotSize, price, Slippage, sl, tp, "Winsman EA v1.02", MagicNumber, 0, (type==OP_BUY)?Blue:Red);
   if (ticket < 0) {
      Print("OrderSend failed with error #", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| Manage Open Trades (Lock Profit, Failsafe, Time limit)           |
//+------------------------------------------------------------------+
void ManageOpenTrades() {
   for (int i = OrdersTotal() - 1; i >= 0; i--) {
      if (OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) {
         if (OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber) {
            
            // 1. Max Hours Check
            if (InpMaxHoursEnabled) {
               datetime openTime = OrderOpenTime();
               int hoursOpen = (int)((TimeCurrent() - openTime) / 3600);
               if (hoursOpen >= InpMaxHours) {
                  CloseOrder(OrderTicket());
                  continue;
               }
            }
            
            // 2. Failsafe Exit (Opposite side of dot)
            double dotPrice = GetDotPriceFromObjects(OrderType() == OP_BUY, -1);
            if (dotPrice > 0) {
               if (OrderType() == OP_BUY && Bid < dotPrice) {
                  double pipLoss = (OrderOpenPrice() - Bid) / Point;
                  if (pipLoss >= InpFailsafeLossPips || OrderProfit() >= 0) {
                     CloseOrder(OrderTicket());
                     continue;
                  }
               }
               if (OrderType() == OP_SELL && Ask > dotPrice) {
                  double pipLoss = (Ask - OrderOpenPrice()) / Point;
                  if (pipLoss >= InpFailsafeLossPips || OrderProfit() >= 0) {
                     CloseOrder(OrderTicket());
                     continue;
                  }
               }
            }
            
            // 3. Lock Profit Mechanism (Option B)
            if (InpTradeMode == MODE_LOCK_PROFIT) {
               double profitDollar = OrderProfit() + OrderSwap() + OrderCommission();
               double targetSL = 0;
               double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
               double tickSize = MarketInfo(Symbol(), MODE_TICKSIZE);
               double pointMult = tickSize / (OrderLots() * tickValue);
               
               if (profitDollar >= InpLockTrigger3) {
                  targetSL = CalculateLockSL(OrderType(), OrderOpenPrice(), InpLockAmount3, pointMult);
               } else if (profitDollar >= InpLockTrigger2) {
                  targetSL = CalculateLockSL(OrderType(), OrderOpenPrice(), InpLockAmount2, pointMult);
               } else if (profitDollar >= InpLockTrigger1) {
                  targetSL = CalculateLockSL(OrderType(), OrderOpenPrice(), InpLockAmount1, pointMult);
               }
               
               if (targetSL > 0) {
                  bool modify = false;
                  if (OrderType() == OP_BUY && (OrderStopLoss() < targetSL || OrderStopLoss() == 0)) modify = true;
                  if (OrderType() == OP_SELL && (OrderStopLoss() > targetSL || OrderStopLoss() == 0)) modify = true;
                  
                  if (modify) {
                     targetSL = NormalizeDouble(targetSL, Digits);
                     OrderModify(OrderTicket(), OrderOpenPrice(), targetSL, OrderTakeProfit(), 0, clrNONE);
                  }
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Helper to calculate Lock SL price                                |
//+------------------------------------------------------------------+
double CalculateLockSL(int type, double openPrice, double lockAmount, double mult) {
   if (type == OP_BUY) {
      return openPrice + (lockAmount * mult);
   } else {
      return openPrice - (lockAmount * mult);
   }
}

//+------------------------------------------------------------------+
//| Helper to close an order                                         |
//+------------------------------------------------------------------+
void CloseOrder(int ticket) {
   if (OrderSelect(ticket, SELECT_BY_TICKET)) {
      double closePrice = (OrderType() == OP_BUY) ? Bid : Ask;
      OrderClose(OrderTicket(), OrderLots(), closePrice, Slippage, clrNONE);
   }
}
//+------------------------------------------------------------------+
