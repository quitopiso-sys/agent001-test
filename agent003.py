#!/usr/bin/env python3
import csv, json, urllib.request
from pathlib import Path
from datetime import datetime, timezone

B = Path(__file__).resolve().parent
CFG = B / "config003.json"
STATE = B / "state003.json"
HIST = B / "price_history003.json"
CYC = B / "cycles003.csv"
TR = B / "trades003.csv"
SUM = B / "summary003.json"
PAGE = B / "agent003.html"

def now():
    return datetime.now(timezone.utc).isoformat()

def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

def save(path, obj):
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AGENT-003-paper/1.0"})
    with urllib.request.urlopen(req, timeout=20) as f:
        return json.loads(f.read().decode())

def prices_chf(symbols):
    usd_chf = float(get_json("https://api.coinbase.com/v2/exchange-rates?currency=USD")["data"]["rates"]["CHF"])
    out = {}
    for symbol in symbols:
        try:
            ticker = get_json(f"https://api.exchange.coinbase.com/products/{symbol}-USD/ticker")
            out[symbol] = float(ticker["price"]) * usd_chf
        except Exception:
            pass
    return out

def pct(a, b):
    return (a / b - 1) * 100 if b else 0.0

def equity(st, prices):
    return st["cash"] + sum(v["qty"] * prices.get(s, 0) for s, v in st["pos"].items())

def exposure(st, prices):
    return sum(v["qty"] * prices.get(s, 0) for s, v in st["pos"].items())

def open_count(st):
    return sum(v["qty"] > 0 for v in st["pos"].values())

def ensure_csv(path, header):
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def tail_csv(path, n):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))[-n:]

def metrics(symbol, history, cfg):
    values = [float(x[symbol]) for x in history if symbol in x]
    need = max(cfg["long_period"], cfg["breakout_lookback"]) + 1
    if len(values) < need:
        return {"ready": False, "fast": 0.0, "medium": 0.0, "long": 0.0, "breakout": False, "score": -999.0}
    cur = values[-1]
    fast = pct(cur, values[-1 - cfg["fast_period"]])
    medium = pct(cur, values[-1 - cfg["medium_period"]])
    long = pct(cur, values[-1 - cfg["long_period"]])
    prior = values[-1 - cfg["breakout_lookback"]:-1]
    breakout_level = max(prior) * (1 + cfg["breakout_buffer_pct"] / 100)
    breakout = cur >= breakout_level
    score = (cfg["score_fast_weight"] * fast + cfg["score_medium_weight"] * medium + cfg["score_long_weight"] * long + (cfg["breakout_bonus"] if breakout else 0.0))
    return {"ready": True, "fast": fast, "medium": medium, "long": long, "breakout": breakout, "score": score}

def log_trade(st, prices, symbol, side, notional, fee, reason):
    ensure_csv(TR, ["timestamp", "symbol", "side", "notional_chf", "fee_chf", "equity_after_chf", "reason"])
    with TR.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([now(), symbol, side, f"{notional:.8f}", f"{fee:.8f}", f"{equity(st, prices):.8f}", reason])

def buy(st, prices, cfg, symbol, reason):
    if st["pos"][symbol]["qty"] > 0 or open_count(st) >= cfg["max_positions"]:
        return "BLOCKED"
    eq = equity(st, prices)
    room = max(0.0, eq * cfg["max_total_exposure_pct"] - exposure(st, prices))
    budget = min(eq * cfg["position_size_pct"], room, st["cash"])
    if budget < cfg["min_order_chf"]:
        return "BLOCKED"
    fee_rate = cfg["fee_rate"]
    slip = cfg["slippage_bps"] / 10000
    notional = budget / (1 + fee_rate)
    fee = notional * fee_rate
    execution = prices[symbol] * (1 + slip)
    qty = notional / execution
    st["cash"] -= notional + fee
    st["pos"][symbol] = {"qty": qty, "entry": execution, "peak": prices[symbol]}
    st["fees"] += fee
    st["trades"] += 1
    log_trade(st, prices, symbol, "BUY", notional, fee, reason)
    return f"BUY CHF {notional:.2f}"

def sell(st, prices, cfg, symbol, reason):
    pos = st["pos"][symbol]
    if pos["qty"] <= 0:
        return "BLOCKED"
    fee_rate = cfg["fee_rate"]
    slip = cfg["slippage_bps"] / 10000
    execution = prices[symbol] * (1 - slip)
    notional = pos["qty"] * execution
    fee = notional * fee_rate
    st["cash"] += notional - fee
    st["pos"][symbol] = {"qty": 0.0, "entry": 0.0, "peak": 0.0}
    st["fees"] += fee
    st["trades"] += 1
    log_trade(st, prices, symbol, "SELL", notional, fee, reason)
    return f"SELL CHF {notional:.2f}"

def render(summary, st, all_metrics):
    trades = tail_csv(TR, 25)
    trade_rows = "".join(
        f"<tr><td>{r['timestamp'][:19]}</td><td>{r['symbol']}</td><td>{r['side']}</td><td>CHF {float(r['notional_chf']):.2f}</td><td>CHF {float(r['fee_chf']):.3f}</td><td>{r['reason']}</td></tr>"
        for r in reversed(trades)
    ) or "<tr><td colspan='6'>Sin operaciones todavía.</td></tr>"
    radar_rows = "".join(
        f"<tr><td>{s}</td><td>{m.get('fast', 0):+.2f}%</td><td>{m.get('medium', 0):+.2f}%</td><td>{m.get('long', 0):+.2f}%</td><td>{'YES' if m.get('breakout') else 'NO'}</td><td>{m.get('score', -999):+.2f}</td></tr>"
        for s, m in sorted(all_metrics.items(), key=lambda kv: kv[1].get("score", -999), reverse=True)
    )
    position_rows = "".join(
        f"<tr><td>{s}</td><td>{v['qty']:.8f}</td><td>CHF {v['entry']:.4f}</td><td>CHF {summary['prices'].get(s, 0):.4f}</td><td>{pct(summary['prices'].get(s, 0), v['entry']):+.2f}%</td></tr>"
        for s, v in st["pos"].items() if v["qty"] > 0
    ) or "<tr><td colspan='5'>Sin posiciones abiertas.</td></tr>"
    html = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta http-equiv="refresh" content="60"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AGENT #003</title>
<style>body{{margin:0;padding:22px;background:radial-gradient(circle at top,#2b0710,#090506 52%);color:#fff7f7;font-family:system-ui}}.w{{max-width:1120px;margin:auto}}.top{{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}}h1{{margin:0;font-size:36px}}.sub{{color:#d39aa6;margin-top:6px}}.badge{{padding:9px 13px;border:1px solid #a52c46;border-radius:999px;color:#ff6f91;background:#290b12}}.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:18px}}.c,.box{{background:#1b0b0f;border:1px solid #5e1e2e;border-radius:16px;padding:14px}}.v{{font-size:28px;font-weight:850;margin-top:5px}}.l{{font-size:11px;color:#bf8190;text-transform:uppercase}}h2{{margin-top:28px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #4d1a27;text-align:left;font-size:13px}}th{{color:#d19aaa}}.note{{margin-top:14px;padding:12px;border-radius:12px;background:#2a0b13;border:1px solid #7f2039;color:#ffb1c1}}@media(max-width:700px){{body{{padding:12px}}h1{{font-size:29px}}}}</style></head><body><div class="w">
<div class="top"><div><h1>AGENT #003 · NO FEAR</h1><div class="sub">Paper trading agresivo · compite por beneficio neto</div></div><div class="badge">{summary['status']}</div></div>
<div class="g"><div class="c"><div class="l">Patrimonio</div><div class="v">CHF {summary['equity_chf']:.2f}</div></div><div class="c"><div class="l">Resultado</div><div class="v">CHF {summary['pnl_chf']:+.2f}</div></div><div class="c"><div class="l">Ciclos</div><div class="v">{summary['cycle_count']}</div></div><div class="c"><div class="l">Trades</div><div class="v">{summary['trade_count']}</div></div><div class="c"><div class="l">Exposición</div><div class="v">{summary['exposure_pct']:.0f}%</div></div><div class="c"><div class="l">Fees</div><div class="v">CHF {summary['fees_paid_chf']:.3f}</div></div></div>
<div class="note">Misión: crecer. Sin modo defensivo ni fecha límite. Puede usar hasta {summary['max_total_exposure_pct']*100:.0f}% del patrimonio y seguirá buscando oportunidades mientras conserve capital operativo.</div>
<h2>Radar de velocidad</h2><div class="box"><table><tr><th>Activo</th><th>Rápido</th><th>Medio</th><th>Largo</th><th>Breakout</th><th>Score</th></tr>{radar_rows}</table></div>
<h2>Posiciones</h2><div class="box"><table><tr><th>Activo</th><th>Cantidad</th><th>Entrada</th><th>Precio</th><th>Bruto</th></tr>{position_rows}</table></div>
<h2>Operaciones</h2><div class="box"><table><tr><th>UTC</th><th>Activo</th><th>Lado</th><th>Importe</th><th>Fee</th><th>Motivo</th></tr>{trade_rows}</table></div></div></body></html>'''
    PAGE.write_text(html, encoding="utf-8")

def main():
    cfg = load(CFG, {})
    if cfg.get("real_money_enabled"):
        raise SystemExit("REAL MONEY BLOCKED")
    symbols = cfg["symbols"]
    st = load(STATE, {"cash": cfg["initial_capital_chf"], "pos": {s: {"qty": 0.0, "entry": 0.0, "peak": 0.0} for s in symbols}, "fees": 0.0, "trades": 0, "cycles": 0})
    for s in symbols:
        st["pos"].setdefault(s, {"qty": 0.0, "entry": 0.0, "peak": 0.0})
    history = load(HIST, [])
    prices = prices_chf(symbols)
    if len(prices) < 3:
        raise SystemExit("Not enough market prices")
    history.append({"timestamp": now(), **prices})
    history = history[-10000:]
    st["cycles"] += 1
    all_metrics = {s: metrics(s, history, cfg) for s in prices}
    actions = {s: "HOLD" for s in symbols}

    for s in symbols:
        if s not in prices or st["pos"][s]["qty"] <= 0:
            continue
        pos = st["pos"][s]
        pos["peak"] = max(pos["peak"], prices[s])
        gross = pct(prices[s], pos["entry"])
        trail = pct(prices[s], pos["peak"])
        m = all_metrics.get(s, {})
        if gross >= cfg["take_profit_pct"]:
            actions[s] = sell(st, prices, cfg, s, f"TAKE PROFIT {gross:+.2f}%")
        elif gross <= -cfg["hard_stop_pct"]:
            actions[s] = sell(st, prices, cfg, s, f"HARD STOP {gross:+.2f}%")
        elif gross >= cfg["trailing_activation_pct"] and trail <= -cfg["trailing_stop_pct"]:
            actions[s] = sell(st, prices, cfg, s, f"TRAIL {trail:+.2f}%")
        elif m.get("ready") and m.get("fast", 0) <= -cfg["exit_fast_reversal_pct"]:
            actions[s] = sell(st, prices, cfg, s, f"FAST REVERSAL {m['fast']:+.2f}%")

    candidates = []
    for s, m in all_metrics.items():
        if st["pos"][s]["qty"] > 0 or not m.get("ready"):
            continue
        if (m["fast"] >= cfg["min_fast_momentum_pct"] and m["medium"] >= cfg["min_medium_momentum_pct"] and m["long"] >= cfg["min_long_momentum_pct"] and m["breakout"] and m["score"] >= cfg["min_entry_score"]):
            candidates.append((m["score"], s, m))

    for _, s, m in sorted(candidates, reverse=True):
        if open_count(st) >= cfg["max_positions"]:
            break
        actions[s] = buy(st, prices, cfg, s, f"VELOCITY score {m['score']:+.2f}; fast {m['fast']:+.2f}%; med {m['medium']:+.2f}%; long {m['long']:+.2f}%")

    eq = equity(st, prices)
    exposure_pct = (exposure(st, prices) / eq * 100) if eq > 0 else 0.0
    status = "DEAD" if eq < cfg["min_operating_equity_chf"] else "WINNING" if eq > cfg["initial_capital_chf"] else "HUNTING"
    ensure_csv(CYC, ["timestamp", "cycle", "equity_chf", "pnl_chf", "status", "exposure_pct", "actions"])
    with CYC.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([now(), st["cycles"], f"{eq:.8f}", f"{eq-cfg['initial_capital_chf']:.8f}", status, f"{exposure_pct:.2f}", json.dumps(actions, separators=(",", ":"))])

    summary = {"timestamp": now(), "agent_id": "AGENT-003", "status": status, "initial_capital_chf": cfg["initial_capital_chf"], "equity_chf": eq, "pnl_chf": eq - cfg["initial_capital_chf"], "cycle_count": st["cycles"], "trade_count": st["trades"], "fees_paid_chf": st["fees"], "exposure_pct": exposure_pct, "max_total_exposure_pct": cfg["max_total_exposure_pct"], "symbols": symbols, "prices": prices, "actions": actions, "metrics": all_metrics, "real_money_enabled": False}
    save(HIST, history); save(STATE, st); save(SUM, summary); render(summary, st, all_metrics)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
