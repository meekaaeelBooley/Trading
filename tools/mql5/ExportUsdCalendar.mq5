//+------------------------------------------------------------------+
//| ExportUsdCalendar.mq5 - dump the MetaQuotes economic calendar    |
//| (all events of one currency, with actual / forecast / previous)  |
//| to a CSV in the terminal's Common\Files folder.                  |
//| Read-only: no orders, no trading calls. Used by tools/calendar.py|
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

input datetime InpFrom     = D'2014.01.01';
input int      InpDaysAhead= 120;
input string   InpCurrency = "USD";
input string   InpFile     = "usd_calendar.csv";

string Clean(string s)
{
   StringReplace(s, ",", ";");
   StringReplace(s, "\"", "");
   StringReplace(s, "\r", " ");
   StringReplace(s, "\n", " ");
   return s;
}

string Num(const bool has, const long raw, const int digits, const long mult)
{
   if(!has || raw == LONG_MIN) return "";
   return DoubleToString((double)raw / 1000000.0, MathMax(digits, 0));
}

void OnStart()
{
   // first call may trigger a sync with the calendar server: retry a few times
   MqlCalendarValue probe[];
   for(int k = 0; k < 20; k++)
   {
      if(CalendarValueHistory(probe, TimeTradeServer() - 86400 * 7, TimeTradeServer(), NULL, InpCurrency) > 0) break;
      Sleep(1500);
   }

   int h = FileOpen(InpFile, FILE_WRITE | FILE_ANSI | FILE_TXT | FILE_COMMON);
   if(h == INVALID_HANDLE) { Print("cannot open ", InpFile, " err=", GetLastError()); return; }
   FileWriteString(h, "ts_server,period_ts,event_id,event_code,name,importance,sector,frequency,actual,forecast,prev,revised_prev,impact\n");

   datetime end = TimeTradeServer() + (datetime)(InpDaysAhead * 86400);
   long total = 0;
   // one year per request keeps each call small
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
            Num(v[i].HasActualValue(),   v[i].actual_value,   dg, 0),
            Num(v[i].HasForecastValue(), v[i].forecast_value, dg, 0),
            Num(v[i].HasPreviousValue(), v[i].prev_value,     dg, 0),
            Num(v[i].HasRevisedValue(),  v[i].revised_prev_value, dg, 0),
            (int)v[i].impact_type);
         FileWriteString(h, line + "\n");
         total++;
      }
      PrintFormat("calendar %s..%s: %d values", TimeToString(a), TimeToString(b), n);
      a = b;
   }
   FileClose(h);

   int hm = FileOpen(InpFile + ".meta", FILE_WRITE | FILE_ANSI | FILE_TXT | FILE_COMMON);
   if(hm != INVALID_HANDLE)
   {
      FileWriteString(hm, StringFormat("rows=%I64d\nserver_now=%I64d\ngmt_now=%I64d\nserver=%s\nfrom=%I64d\n", total,
                      (long)TimeTradeServer(), (long)TimeGMT(), AccountInfoString(ACCOUNT_SERVER), (long)InpFrom));
      FileClose(hm);
   }
   PrintFormat("ExportUsdCalendar: %I64d rows -> Common/Files/%s", total, InpFile);
}
