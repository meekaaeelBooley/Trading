# Calendar event study (USD tier-1 releases)

Calendar: 1504 tier-1 release moments 2014-2027 (MT5/MetaQuotes). Families: adp=157, cpi=155, fomc=106, gdp=152, ism=312, nfp=155, pce=154, ppi=155, retail=158
XAU M5: 674669 bars 2014-01-14 -> 2026-11-04 (continuous from 2017-04; 2014-16 is sparse, excluded; spread recorded only from 2023: earlier bars use the median of recorded spreads)
USTEC M5: 168103 bars from 2023-06-26; holes 2023-07..2024-03 and 2026-07..10

## T1 - live news_drift rule on XAU (thr 2.5 ATR, body 0.6, minutes 08:30/10:00 NY; 14:00 excluded by the closure rule)
```
2017-04 .. 2024-12  HOLD-OUT (never tuned on)  n= 211 E=-0.259R win=9% PF=0.64 t=-1.9 CI=(-0.51,+0.04) ctrl=-0.289 edge=+0.031
2025-01 .. 2026-11  (the tuning window)        n=  35 E=+0.838R win=17% PF=2.48 t=+1.3 CI=(-0.27,+2.21) ctrl=+0.492 edge=+0.346
all                                            n= 246 E=-0.103R win=10% PF=0.85 t=-0.7 CI=(-0.39,+0.23) ctrl=-0.178 edge=+0.075
```
  2017: n=  24 E=-0.219R win=8% PF=0.71 t=-0.5 CI=(-0.92,+0.79) ctrl=-0.534 edge=+0.315
  2018: n=  16 E=-0.897R win=0% PF=0.00 t=-8.8 CI=(-1.09,-0.70) ctrl=+0.804 edge=-1.701
  2019: n=  36 E=-0.632R win=6% PF=0.17 t=-4.3 CI=(-0.88,-0.34) ctrl=-0.144 edge=-0.488
  2020: n=  13 E=-0.737R win=0% PF=0.00 t=-5.5 CI=(-0.97,-0.50) ctrl=-0.589 edge=-0.148
  2021: n=  22 E=-0.094R win=9% PF=0.87 t=-0.2 CI=(-0.86,+1.03) ctrl=-0.441 edge=+0.347
  2022: n=  34 E=-0.069R win=12% PF=0.89 t=-0.2 CI=(-0.73,+0.68) ctrl=-0.113 edge=+0.044
  2023: n=  28 E=+0.119R win=14% PF=1.18 t=+0.2 CI=(-0.66,+1.38) ctrl=-0.438 edge=+0.557
  2024: n=  38 E=-0.041R win=13% PF=0.94 t=-0.1 CI=(-0.63,+0.75) ctrl=-0.590 edge=+0.550

## T2 - same rule on EVERY tier-1 release (real calendar times) on XAU
```
2017-04 .. 2024-12 hold-out                    n= 232 E=-0.223R win=9% PF=0.69 t=-1.6 CI=(-0.47,+0.04) ctrl=-0.286 edge=+0.063
2025-01 .. 2026-11                             n=  38 E=+0.841R win=18% PF=2.53 t=+1.4 CI=(-0.27,+2.08) ctrl=+0.373 edge=+0.469
all                                            n= 270 E=-0.073R win=10% PF=0.90 t=-0.5 CI=(-0.36,+0.22) ctrl=-0.193 edge=+0.120
```

## T3 - exploratory: threshold surface and per-family (XAU, all years; read as a surface, not as picks)
```
thr 1.0 body 0.0                               n= 927 E=-0.070R win=15% PF=0.90 t=-1.0 CI=(-0.21,+0.07) ctrl=-0.227 edge=+0.157
thr 1.0 body 0.6                               n= 369 E=-0.069R win=14% PF=0.90 t=-0.6 CI=(-0.29,+0.19) ctrl=-0.240 edge=+0.171
thr 1.5 body 0.0                               n= 832 E=-0.061R win=14% PF=0.91 t=-0.8 CI=(-0.21,+0.09) ctrl=-0.229 edge=+0.168
thr 1.5 body 0.6                               n= 345 E=-0.063R win=13% PF=0.91 t=-0.5 CI=(-0.30,+0.20) ctrl=-0.219 edge=+0.156
thr 2.0 body 0.0                               n= 705 E=-0.066R win=13% PF=0.90 t=-0.8 CI=(-0.22,+0.10) ctrl=-0.219 edge=+0.152
thr 2.0 body 0.6                               n= 306 E=-0.113R win=11% PF=0.84 t=-0.8 CI=(-0.36,+0.15) ctrl=-0.197 edge=+0.084
thr 2.5 body 0.0                               n= 586 E=-0.100R win=12% PF=0.86 t=-1.1 CI=(-0.28,+0.07) ctrl=-0.194 edge=+0.093
thr 2.5 body 0.6                               n= 270 E=-0.073R win=10% PF=0.90 t=-0.5 CI=(-0.36,+0.22) ctrl=-0.193 edge=+0.120
thr 3.0 body 0.0                               n= 484 E=-0.096R win=11% PF=0.86 t=-0.9 CI=(-0.29,+0.11) ctrl=-0.226 edge=+0.130
thr 3.0 body 0.6                               n= 231 E=-0.111R win=10% PF=0.84 t=-0.7 CI=(-0.39,+0.21) ctrl=-0.315 edge=+0.204
thr 4.0 body 0.0                               n= 351 E=-0.047R win=11% PF=0.93 t=-0.4 CI=(-0.28,+0.22) ctrl=-0.174 edge=+0.126
thr 4.0 body 0.6                               n= 179 E=-0.117R win=9% PF=0.83 t=-0.7 CI=(-0.44,+0.23) ctrl=-0.249 edge=+0.132
--- per family at thr 1.5 body 0.5 (many cells: expect a few false positives) ---
family nfp                                     n=  63 E=+0.158R win=11% PF=1.22 t=+0.4 CI=(-0.52,+1.02) ctrl=-0.525 edge=+0.683
family cpi                                     n=  60 E=-0.022R win=12% PF=0.97 t=-0.1 CI=(-0.52,+0.51) ctrl=-0.431 edge=+0.409
family fomc                                    n=1
family pce                                     n=  36 E=-0.087R win=8% PF=0.89 t=-0.2 CI=(-0.86,+0.87) ctrl=-0.559 edge=+0.472
family adp                                     n=  51 E=+0.181R win=16% PF=1.27 t=+0.5 CI=(-0.50,+1.02) ctrl=-0.199 edge=+0.379
family ism                                     n=  86 E=-0.078R win=22% PF=0.88 t=-0.4 CI=(-0.45,+0.37) ctrl=-0.205 edge=+0.127
family retail                                  n=  55 E=-0.192R win=11% PF=0.74 t=-0.7 CI=(-0.66,+0.37) ctrl=+0.126 edge=-0.318
family ppi                                     n=  46 E=-0.118R win=13% PF=0.78 t=-0.5 CI=(-0.51,+0.35) ctrl=+0.041 edge=-0.160
family gdp                                     n=  50 E=+0.272R win=14% PF=1.39 t=+0.6 CI=(-0.48,+1.20) ctrl=+0.242 edge=+0.030
```

## T4 - exploratory: the same rule on USTEC
```
USTEC thr 1.5 body 0.6 all releases            n=  89 E=-0.155R win=8% PF=0.76 t=-0.6 CI=(-0.56,+0.39) ctrl=-0.439 edge=+0.284
USTEC thr 2.0 body 0.6 all releases            n=  78 E=-0.112R win=8% PF=0.82 t=-0.4 CI=(-0.58,+0.59) ctrl=-0.461 edge=+0.349
USTEC thr 2.5 body 0.6 all releases            n=  69 E=-0.094R win=7% PF=0.85 t=-0.3 CI=(-0.60,+0.60) ctrl=-0.536 edge=+0.442
USTEC thr 3.0 body 0.6 all releases            n=  60 E=-0.042R win=7% PF=0.93 t=-0.1 CI=(-0.63,+0.79) ctrl=-0.509 edge=+0.468
USTEC thr 2.5 body 0.6 minutes 08:30/10:00     n=  61 E=-0.115R win=7% PF=0.82 t=-0.3 CI=(-0.67,+0.66) ctrl=-0.481 edge=+0.366
```
