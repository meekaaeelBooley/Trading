# Deep-history re-test of the classic families

XAUUSDm from 2017-04 (9.6 y), USTECm from 2024-04 (2.6 y, two data holes).
Gold spread is only recorded from 2023: earlier bars use the median recorded spread (conservative for the pre-2023 gold market).

## XAUUSDm
```
ORB NY start 9:30 n=3 tp2R                   ALL  n=1899 E=-0.025R win=42% PF=0.95 t=-1.0 CI=(-0.07,+0.03) ctrl=-0.085 edge=+0.060
                                             first60% n=1139 E=-0.015R win=43% PF=0.97 t=-0.5 CI=(-0.08,+0.04) ctrl=-0.125 edge=+0.110
                                             last40%  n= 760 E=-0.039R win=41% PF=0.92 t=-1.0 CI=(-0.11,+0.04) ctrl=-0.024 edge=-0.015
ORB NY start 9:30 n=6 tp2R                   ALL  n=1811 E=-0.032R win=44% PF=0.92 t=-1.5 CI=(-0.07,+0.01) ctrl=-0.063 edge=+0.031
                                             first60% n=1086 E=-0.038R win=44% PF=0.90 t=-1.4 CI=(-0.09,+0.01) ctrl=-0.095 edge=+0.057
                                             last40%  n= 725 E=-0.022R win=44% PF=0.95 t=-0.6 CI=(-0.08,+0.04) ctrl=-0.016 edge=-0.006
ORB NY start 8:00 n=3 tp2R                   ALL  n=1723 E=-0.135R win=32% PF=0.80 t=-4.4 CI=(-0.19,-0.08) ctrl=+0.006 edge=-0.142
                                             first60% n=1033 E=-0.120R win=33% PF=0.82 t=-3.0 CI=(-0.19,-0.05) ctrl=+0.004 edge=-0.124
                                             last40%  n= 690 E=-0.158R win=31% PF=0.77 t=-3.2 CI=(-0.25,-0.06) ctrl=+0.010 edge=-0.168
London range break (00-08 UTC-ish) tp2R      ALL  n=1439 E=-0.029R win=43% PF=0.93 t=-1.1 CI=(-0.08,+0.03) ctrl=-0.059 edge=+0.030
                                             first60% n= 863 E=-0.019R win=43% PF=0.96 t=-0.6 CI=(-0.08,+0.04) ctrl=-0.084 edge=+0.065
                                             last40%  n= 576 E=-0.044R win=42% PF=0.90 t=-1.1 CI=(-0.12,+0.02) ctrl=-0.022 edge=-0.022
London/Asian sweep fade                      ALL  n=1381 E=-0.408R win=22% PF=0.52 t=-11.8 CI=(-0.48,-0.34) ctrl=-0.341 edge=-0.067
                                             first60% n= 828 E=-0.399R win=23% PF=0.54 t=-8.7 CI=(-0.50,-0.30) ctrl=-0.430 edge=+0.031
                                             last40%  n= 553 E=-0.422R win=21% PF=0.50 t=-7.9 CI=(-0.53,-0.30) ctrl=-0.207 edge=-0.214
session momentum 09:30+30min -> 15:30 (stop 3 ATR) ALL  n=2374 E=-0.132R win=37% PF=0.49 t=-13.6 CI=(-0.15,-0.11) ctrl=-0.126 edge=-0.006
                                             first60% n=1424 E=-0.151R win=35% PF=0.45 t=-11.7 CI=(-0.18,-0.13) ctrl=-0.173 edge=+0.023
                                             last40%  n= 950 E=-0.103R win=40% PF=0.55 t=-7.1 CI=(-0.13,-0.08) ctrl=-0.055 edge=-0.049
session momentum 09:30+30min -> 11:00..16:00 (the trend_day recipe) ALL  n= 960 E=-0.081R win=40% PF=0.81 t=-2.6 CI=(-0.14,-0.02) ctrl=-0.042 edge=-0.038
                                             first60% n= 576 E=-0.108R win=37% PF=0.75 t=-2.8 CI=(-0.18,-0.03) ctrl=-0.067 edge=-0.041
                                             last40%  n= 384 E=-0.040R win=43% PF=0.90 t=-0.8 CI=(-0.14,+0.05) ctrl=-0.005 edge=-0.034
gap fade (2 ATR stop)                        ALL  n=2212 E=-0.084R win=40% PF=0.86 t=-3.1 CI=(-0.14,-0.02) ctrl=-0.035 edge=-0.050
                                             first60% n=1327 E=-0.104R win=40% PF=0.83 t=-3.0 CI=(-0.17,-0.04) ctrl=-0.064 edge=-0.040
                                             last40%  n= 885 E=-0.054R win=40% PF=0.91 t=-1.2 CI=(-0.13,+0.03) ctrl=+0.010 edge=-0.064
gap follow                                   ALL  n=2212 E=-0.012R win=32% PF=0.98 t=-0.3 CI=(-0.09,+0.07) ctrl=-0.101 edge=+0.088
                                             first60% n=1327 E=-0.035R win=32% PF=0.95 t=-0.7 CI=(-0.12,+0.06) ctrl=-0.111 edge=+0.076
                                             last40%  n= 885 E=+0.022R win=32% PF=1.03 t=+0.4 CI=(-0.10,+0.14) ctrl=-0.085 edge=+0.107
```

## USTECm
```
ORB NY start 9:30 n=3 tp2R                   ALL  n= 542 E=+0.026R win=48% PF=1.06 t=+0.6 CI=(-0.06,+0.11) ctrl=-0.089 edge=+0.115
                                             first60% n= 325 E=+0.058R win=49% PF=1.13 t=+1.0 CI=(-0.05,+0.17) ctrl=-0.172 edge=+0.231
                                             last40%  n= 217 E=-0.023R win=46% PF=0.95 t=-0.3 CI=(-0.17,+0.10) ctrl=+0.036 edge=-0.059
ORB NY start 9:30 n=6 tp2R                   ALL  n= 497 E=+0.052R win=52% PF=1.15 t=+1.3 CI=(-0.02,+0.13) ctrl=-0.094 edge=+0.146
                                             first60% n= 298 E=+0.064R win=51% PF=1.18 t=+1.2 CI=(-0.04,+0.16) ctrl=-0.128 edge=+0.193
                                             last40%  n= 199 E=+0.032R win=53% PF=1.10 t=+0.5 CI=(-0.09,+0.13) ctrl=-0.043 edge=+0.075
ORB NY start 8:00 n=3 tp2R                   ALL  n= 369 E=-0.193R win=28% PF=0.73 t=-2.8 CI=(-0.33,-0.05) ctrl=-0.086 edge=-0.108
                                             first60% n= 221 E=-0.199R win=28% PF=0.72 t=-2.2 CI=(-0.37,-0.04) ctrl=-0.039 edge=-0.160
                                             last40%  n= 148 E=-0.184R win=29% PF=0.75 t=-1.7 CI=(-0.41,+0.07) ctrl=-0.155 edge=-0.029
London range break (00-08 UTC-ish) tp2R      ALL  n= 352 E=-0.114R win=37% PF=0.81 t=-1.8 CI=(-0.24,+0.01) ctrl=-0.035 edge=-0.079
                                             first60% n= 211 E=-0.115R win=35% PF=0.81 t=-1.4 CI=(-0.28,+0.04) ctrl=-0.030 edge=-0.085
                                             last40%  n= 141 E=-0.112R win=40% PF=0.79 t=-1.2 CI=(-0.27,+0.06) ctrl=-0.043 edge=-0.070
London/Asian sweep fade                      ALL  n= 354 E=-0.304R win=26% PF=0.63 t=-4.2 CI=(-0.44,-0.15) ctrl=-0.307 edge=+0.003
                                             first60% n= 212 E=-0.316R win=26% PF=0.63 t=-3.3 CI=(-0.52,-0.14) ctrl=-0.466 edge=+0.150
                                             last40%  n= 142 E=-0.287R win=25% PF=0.64 t=-2.6 CI=(-0.52,-0.06) ctrl=-0.071 edge=-0.217
session momentum 09:30+30min -> 15:30 (stop 3 ATR) ALL  n= 585 E=-0.098R win=42% PF=0.68 t=-3.8 CI=(-0.15,-0.05) ctrl=-0.044 edge=-0.055
                                             first60% n= 351 E=-0.086R win=42% PF=0.71 t=-2.5 CI=(-0.15,-0.03) ctrl=-0.086 edge=-0.001
                                             last40%  n= 234 E=-0.117R win=41% PF=0.62 t=-3.0 CI=(-0.20,-0.03) ctrl=+0.019 edge=-0.136
session momentum 09:30+30min -> 11:00..16:00 (the trend_day recipe) ALL  n= 310 E=+0.070R win=48% PF=1.17 t=+1.1 CI=(-0.05,+0.19) ctrl=-0.199 edge=+0.268
                                             first60% n= 186 E=+0.033R win=47% PF=1.08 t=+0.4 CI=(-0.12,+0.19) ctrl=-0.223 edge=+0.256
                                             last40%  n= 124 E=+0.125R win=49% PF=1.32 t=+1.2 CI=(-0.08,+0.31) ctrl=-0.161 edge=+0.287
gap fade (2 ATR stop)                        ALL  n= 559 E=+0.029R win=34% PF=1.04 t=+0.4 CI=(-0.13,+0.18) ctrl=-0.108 edge=+0.137
                                             first60% n= 335 E=+0.052R win=37% PF=1.08 t=+0.5 CI=(-0.14,+0.21) ctrl=-0.103 edge=+0.155
                                             last40%  n= 224 E=-0.006R win=29% PF=0.99 t=-0.0 CI=(-0.26,+0.26) ctrl=-0.117 edge=+0.111
gap follow                                   ALL  n= 559 E=+0.055R win=19% PF=1.07 t=+0.5 CI=(-0.17,+0.27) ctrl=+0.022 edge=+0.033
                                             first60% n= 335 E=+0.061R win=19% PF=1.07 t=+0.4 CI=(-0.17,+0.34) ctrl=-0.040 edge=+0.101
                                             last40%  n= 224 E=+0.045R win=19% PF=1.05 t=+0.3 CI=(-0.24,+0.38) ctrl=+0.114 edge=-0.068
```

