"""Build the offline trade view for HTML readers that disable scripts."""

from datetime import datetime, timezone


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%m-%d %H:%M:%S")


def candle_chart(bars, order, expiry):
    index = order["i"]
    interval = bars[1][0] - bars[0][0]
    active = bars[index][0] + interval
    until = order["exit"] or (active + expiry * 60_000 if order["status"] == "Expired"
                              else bars[-1][0] + interval)
    start = max(0, index - 8)
    candles = bars[start:index + 6 + (until - active) // interval]
    low = min(order["stop"], *(bar[3] for bar in candles))
    high = max(order["target"], *(bar[2] for bar in candles))
    step = 320 / len(candles)

    def x(time):
        return 8 + (time - candles[0][0]) / interval * step

    def y(price):
        return 243 - (price - low) / (high - low) * 218

    pieces = ['<svg viewBox="0 0 336 284" role="img" aria-label="BTC candlesticks with entry, stop and target">']
    for idx, (time, opening, hi, lo, close) in enumerate(candles, start):
        center = x(time + interval / 2)
        color = "#7adab5" if close >= opening else "#f29a87"
        pieces.append(f'<path stroke="{color}" d="M{center:.2f} {y(hi):.2f}V{y(lo):.2f}"/>'
                      f'<path stroke="{color}" stroke-width="{max(.5, step*.62):.2f}" '
                      f'd="M{center:.2f} {y(opening):.2f}v{(y(close)-y(opening)) or .7:.2f}"/>')
        if index-2 <= idx <= index:
            pieces.append(f'<text x="{center:.2f}" y="259" text-anchor="middle" fill="white" font-size="10">{idx-index+3}</text>')
    for level, color in (("entry", "#ffdb77"), ("stop", "#ffa18b"), ("target", "#8ee1c0")):
        pieces.append(f'<path stroke="{color}" stroke-dasharray="4 2" d="M{x(active):.2f} {y(order[level]):.2f}H{x(until):.2f}"/>')
    for event, price, mark in (("fill", "entry", "F"), ("exit", "out", "X")):
        if order[event] is not None:
            cx, cy = x(order[event]), y(order[price])
            pieces.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="2.8" fill="white"/>'
                          f'<text x="{cx:.2f}" y="{cy + (14 if mark=="F" else -5):.2f}" fill="white" font-size="12">{mark}</text>')
    pieces.append(f'<text x="8" y="278" fill="white" font-size="11">{utc(candles[0][0])} UTC</text></svg>')
    return "".join(pieces)


def preview(data, expiry):
    pieces = ['<p>Choose a setting, then tap an order to see its chart. F marks the fill and X marks the exit.</p>']
    for idx, run in enumerate(data["runs"]):
        orders = run["orders"]
        net = sum((o["gross"] or 0) - o["fees"] + o.get("funding", 0) for o in orders)
        filled = sum(o["fill"] is not None for o in orders)
        setting = (f'ATR({run["atr_period"]}) · range 2 ≥ 1.5 × ATR' if "atr_period" in run
                   else f'&gt; {run["threshold"]}% range threshold')
        pieces.append(f'<details {"open" if idx == 0 else ""}><summary><b>{setting}'
                      f'</b> · net ${net:,.2f}</summary>'
                      f'<p>{len(orders)} orders · {filled} filled</p>')
        for number, order in enumerate(orders, 1):
            time = utc(data["bars"][order["i"]][0] + data["bars"][1][0] - data["bars"][0][0])
            pnl = "" if order["pnl"] is None else f' · net ${order["pnl"]:,.2f}'
            pieces.append(f'<details {"open" if idx == 0 and number == 1 else ""}><summary>'
                          f'#{number} · {time} UTC · {order["status"]}{pnl}</summary>'
                          f'<p>Entry {order["entry"]:g} · Stop {order["stop"]:g} · Target {order["target"]:g}</p>')
            pieces.append(candle_chart(data["bars"], order, expiry))
            pieces.append('</details>')
        pieces.append('</details>')
    return "".join(pieces)
