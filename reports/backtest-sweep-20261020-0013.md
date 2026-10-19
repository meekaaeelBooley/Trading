# Backtest sweep

runs: auto SAST, spread 120.0pt, slip 10.0pt, risk 3.0%/trade. No historical news calendar, so news gates are off. SL-before-TP inside a bar.

| params | train | test (held out) |
|---|---|---|
| {'tp_r': 2.5, 'sl_atr_mult': 2.0, 'partial_tp': False} | n=26 E=+0.20R win=54% PF=2.02 DD=4.7% ci=(-0.08, 0.47) | n=18 E=-0.15R win=50% PF=0.53 DD=11.8% ci=(-0.43, 0.1) |
| {'tp_r': 3.0, 'sl_atr_mult': 2.0, 'partial_tp': False} | n=26 E=+0.20R win=54% PF=2.02 DD=4.7% ci=(-0.08, 0.47) | n=18 E=-0.15R win=50% PF=0.53 DD=11.8% ci=(-0.43, 0.1) |
| {'tp_r': 2.0, 'sl_atr_mult': 2.0, 'partial_tp': False} | n=26 E=+0.18R win=54% PF=1.92 DD=4.7% ci=(-0.09, 0.44) | n=18 E=-0.15R win=50% PF=0.53 DD=11.8% ci=(-0.43, 0.1) |
| {'tp_r': 2.5, 'sl_atr_mult': 2.0, 'partial_tp': True} | n=26 E=+0.16R win=54% PF=1.84 DD=4.7% ci=(-0.1, 0.41) | n=18 E=-0.15R win=50% PF=0.55 DD=11.8% ci=(-0.42, 0.11) |
| {'tp_r': 3.0, 'sl_atr_mult': 2.0, 'partial_tp': True} | n=26 E=+0.16R win=54% PF=1.84 DD=4.7% ci=(-0.1, 0.41) | n=18 E=-0.15R win=50% PF=0.55 DD=11.8% ci=(-0.42, 0.11) |
| {'tp_r': 2.0, 'sl_atr_mult': 2.0, 'partial_tp': True} | n=26 E=+0.15R win=54% PF=1.79 DD=4.7% ci=(-0.1, 0.4) | n=18 E=-0.15R win=50% PF=0.55 DD=11.8% ci=(-0.42, 0.11) |
| {'tp_r': 1.5, 'sl_atr_mult': 1.0, 'partial_tp': False} | n=22 E=+0.14R win=64% PF=1.48 DD=5.9% ci=(-0.19, 0.5) | n=15 E=-0.21R win=40% PF=0.58 DD=12.9% ci=(-0.62, 0.23) |
| {'tp_r': 2.5, 'sl_atr_mult': 1.0, 'partial_tp': False} | n=25 E=+0.12R win=56% PF=1.44 DD=7.4% ci=(-0.18, 0.47) | n=18 E=-0.07R win=50% PF=0.84 DD=9.5% ci=(-0.45, 0.34) |
| {'tp_r': 3.0, 'sl_atr_mult': 1.0, 'partial_tp': False} | n=25 E=+0.12R win=56% PF=1.44 DD=7.4% ci=(-0.18, 0.47) | n=18 E=-0.07R win=50% PF=0.84 DD=9.5% ci=(-0.45, 0.34) |
| {'tp_r': 1.5, 'sl_atr_mult': 1.0, 'partial_tp': True} | n=22 E=+0.12R win=64% PF=1.42 DD=5.9% ci=(-0.2, 0.46) | n=15 E=-0.22R win=40% PF=0.56 DD=12.9% ci=(-0.62, 0.21) |
| {'tp_r': 2.5, 'sl_atr_mult': 1.0, 'partial_tp': True} | n=25 E=+0.12R win=60% PF=1.43 DD=7.4% ci=(-0.18, 0.45) | n=18 E=-0.09R win=50% PF=0.78 DD=9.5% ci=(-0.45, 0.29) |
| {'tp_r': 3.0, 'sl_atr_mult': 1.0, 'partial_tp': True} | n=25 E=+0.12R win=60% PF=1.43 DD=7.4% ci=(-0.18, 0.45) | n=18 E=-0.09R win=50% PF=0.78 DD=9.5% ci=(-0.45, 0.29) |
| {'tp_r': 2.0, 'sl_atr_mult': 1.5, 'partial_tp': False} | n=26 E=+0.12R win=54% PF=1.47 DD=7.4% ci=(-0.15, 0.41) | n=18 E=-0.22R win=44% PF=0.46 DD=12.1% ci=(-0.52, 0.09) |
| {'tp_r': 2.0, 'sl_atr_mult': 1.5, 'partial_tp': True} | n=26 E=+0.12R win=58% PF=1.46 DD=7.4% ci=(-0.15, 0.39) | n=18 E=-0.21R win=44% PF=0.5 DD=12.1% ci=(-0.52, 0.11) |
| {'tp_r': 1.5, 'sl_atr_mult': 2.0, 'partial_tp': False} | n=19 E=+0.11R win=68% PF=1.73 DD=3.7% ci=(-0.13, 0.35) | n=14 E=-0.02R win=57% PF=0.93 DD=5.3% ci=(-0.38, 0.31) |
| {'tp_r': 2.0, 'sl_atr_mult': 1.0, 'partial_tp': False} | n=26 E=+0.11R win=54% PF=1.35 DD=7.4% ci=(-0.22, 0.46) | n=18 E=-0.08R win=50% PF=0.8 DD=6.7% ci=(-0.47, 0.31) |
| {'tp_r': 1.5, 'sl_atr_mult': 2.0, 'partial_tp': True} | n=19 E=+0.10R win=68% PF=1.68 DD=3.7% ci=(-0.13, 0.33) | n=14 E=-0.02R win=57% PF=0.93 DD=5.3% ci=(-0.38, 0.31) |
| {'tp_r': 2.0, 'sl_atr_mult': 1.0, 'partial_tp': True} | n=26 E=+0.09R win=58% PF=1.3 DD=7.4% ci=(-0.22, 0.43) | n=18 E=-0.11R win=50% PF=0.74 DD=6.7% ci=(-0.47, 0.26) |
| {'tp_r': 2.5, 'sl_atr_mult': 1.5, 'partial_tp': True} | n=26 E=+0.09R win=58% PF=1.35 DD=7.4% ci=(-0.17, 0.36) | n=18 E=-0.21R win=44% PF=0.5 DD=12.1% ci=(-0.52, 0.11) |
| {'tp_r': 3.0, 'sl_atr_mult': 1.5, 'partial_tp': True} | n=26 E=+0.09R win=58% PF=1.35 DD=7.4% ci=(-0.17, 0.36) | n=18 E=-0.21R win=44% PF=0.5 DD=12.1% ci=(-0.52, 0.11) |
| {'tp_r': 2.5, 'sl_atr_mult': 1.5, 'partial_tp': False} | n=26 E=+0.08R win=54% PF=1.32 DD=7.4% ci=(-0.18, 0.37) | n=18 E=-0.22R win=44% PF=0.46 DD=12.1% ci=(-0.52, 0.09) |
| {'tp_r': 3.0, 'sl_atr_mult': 1.5, 'partial_tp': False} | n=26 E=+0.08R win=54% PF=1.32 DD=7.4% ci=(-0.18, 0.37) | n=18 E=-0.22R win=44% PF=0.46 DD=12.1% ci=(-0.52, 0.09) |
| {'tp_r': 1.5, 'sl_atr_mult': 1.5, 'partial_tp': True} | n=21 E=-0.04R win=52% PF=0.87 DD=5.6% ci=(-0.33, 0.25) | n=14 E=+0.05R win=64% PF=1.17 DD=3.6% ci=(-0.33, 0.4) |
| {'tp_r': 1.5, 'sl_atr_mult': 1.5, 'partial_tp': False} | n=21 E=-0.05R win=48% PF=0.83 DD=7.0% ci=(-0.34, 0.24) | n=14 E=+0.05R win=64% PF=1.17 DD=3.6% ci=(-0.33, 0.4) |
