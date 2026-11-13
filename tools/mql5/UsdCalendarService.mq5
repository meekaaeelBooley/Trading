//+------------------------------------------------------------------+
//| UsdCalendarService.mq5 - keeps Common\Files\usd_calendar.csv    |
//| fresh (re-exports the whole MetaQuotes USD calendar every 3 h). |
//| Start once: MT5 Navigator > Services > UsdCalendarService >      |
//| right click > Start. Services restart with the terminal.        |
//| Read-only: no orders, no trading calls.                          |
//+------------------------------------------------------------------+
#property service
#property strict

input datetime InpFrom      = D'2014.01.01';
input int      InpDaysAhead = 120;
input int      InpEveryMin  = 180;
input string   InpCurrency  = "USD";
input string   InpFile      = "usd_calendar.csv";

string Clean(string s)
{
   StringReplace(s, ",", ";");
   StringReplace(s, "\"", "");
   StringReplace(s, "\r", " ");
   StringReplace(s, "\n", " ");
   return s;
}

string Num(const bool has, const long raw, const int digits)
{
   if(!has || raw == LONG_MIN) return "";
   return DoubleToString((double)raw / 1000000.0, MathMax(digits, 0));
}

bool Export()
{
   string tmp = InpFile + ".tmp";
   int h = FileOpen(tmp, FILE_WRITE | FILE_ANSI | FILE_TXT | FILE_COMMON);
   if(h == INVALID_HANDLE) return false;
   FileWriteString(h, "ts_server,period_ts,event_id,event_code,name,importance,sector,frequency,actual,forecast,prev,revised_prev,impact\n");
   datetime end = TimeTradeServer() + (datetime)(InpDaysAhead * 86400);
   long total = 0;
   for(datetime a = InpFrom; a < end; )
   {
      datetime b = a + (datetime)(365 * 86400);
      if(b > end) b = end;
      MqlCalendarValue v[];
      int n = CalendarValueHistory(v, a, b, NULL, InpCurrency);
      for(int i = 0; i < n; i++)
      {
         MqlCalendarEvent ev;
         if(!CalendarEventById(v[i].event_id, ev)) continue;
         int dg = (int)ev.digits;
         string line = StringFormat("%I64d,%I64d,%I64u,%s,%s,%d,%d,%d,%s,%s,%s,%s,%d",
            (long)v[i].time, (long)v[i].period, v[i].event_id, Clean(ev.event_code), Clean(ev.name),
            (int)ev.importance, (int)ev.sector, (int)ev.frequency,
            Num(v[i].HasActualValue(), v[i].actual_value, dg), Num(v[i].HasForecastValue(), v[i].forecast_value, dg),
            Num(v[i].HasPreviousValue(), v[i].prev_value, dg), Num(v[i].HasRevisedValue(), v[i].revised_prev_value, dg),
            (int)v[i].impact_type);
         FileWriteString(h, line + "\n");
         total++;
      }
      a = b;
   }
   FileClose(h);
   if(total < 1000) { FileDelete(tmp, FILE_COMMON); return false; }   // never replace a good file with an empty one
   FileDelete(InpFile, FILE_COMMON);
   FileMove(tmp, FILE_COMMON, InpFile, FILE_COMMON | FILE_REWRITE);
   int hm = FileOpen(InpFile + ".meta", FILE_WRITE | FILE_ANSI | FILE_TXT | FILE_COMMON);
   if(hm != INVALID_HANDLE)
   {
      FileWriteString(hm, StringFormat("rows=%I64d\nserver_now=%I64d\ngmt_now=%I64d\nserver=%s\nfrom=%I64d\n", total,
                      (long)TimeTradeServer(), (long)TimeGMT(), AccountInfoString(ACCOUNT_SERVER), (long)InpFrom));
      FileClose(hm);
   }
   return true;
}

void OnStart()
{
   while(!IsStopped())
   {
      bool ok = Export();
      PrintFormat("UsdCalendarService: export %s", ok ? "ok" : "FAILED (kept the previous file)");
      for(int s = 0; s < InpEveryMin * 60 && !IsStopped(); s++) Sleep(1000);
   }
}
