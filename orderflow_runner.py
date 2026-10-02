#!/usr/bin/env python3
"""
Shared public order-flow gate for AGENT 001/002/003.
Uses Binance public market-data endpoints only (no account, API key, or real orders).
It approximates the same microstructure concepts commonly inspected in ATAS:
top-of-book bid/ask imbalance + aggressive trade delta.
Existing exit/risk logic remains untouched; the gate only vetoes weak BUY entries.
"""
import importlib, json, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = "https://data-api.binance.vision"
FLOW = {}

def jget(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent":"paper-orderflow-gate/1.0"})
    with urllib.request.urlopen(req, timeout=12) as f:
        return json.loads(f.read().decode())

def flow_for(symbol):
    pair = symbol.upper() + "USDT"
    try:
        depth = jget("/api/v3/depth", {"symbol":pair, "limit":100})
        trades = jget("/api/v3/aggTrades", {"symbol":pair, "limit":500})
        bid = sum(float(p)*float(q) for p,q in depth.get("bids",[]))
        ask = sum(float(p)*float(q) for p,q in depth.get("asks",[]))
        book = (bid-ask)/(bid+ask) if bid+ask else 0.0
        buy = sell = 0.0
        for t in trades:
            notion = float(t["p"])*float(t["q"])
            # m=True => buyer is maker => aggressive seller; False => aggressive buyer.
            if t.get("m"): sell += notion
            else: buy += notion
        delta = (buy-sell)/(buy+sell) if buy+sell else 0.0
        score = 0.55*delta + 0.45*book
        return {"ok": score >= -0.08 and not (delta < -0.18 and book < -0.10),
                "score":score, "delta":delta, "book":book,
                "trades":len(trades), "source":"Binance public depth+aggTrades",
                "timestamp":datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        # Fail open: a data outage must not silently disable the original strategy.
        return {"ok":True, "score":0.0, "delta":0.0, "book":0.0,
                "trades":0, "source":"unavailable/fail-open", "error":str(e),
                "timestamp":datetime.now(timezone.utc).isoformat()}

def getflow(symbol):
    if symbol not in FLOW: FLOW[symbol]=flow_for(symbol)
    return FLOW[symbol]

def run(agent_id):
    name={"001":"agent001","002":"agent002","003":"agent003"}[agent_id]
    mod=importlib.import_module(name)
    if agent_id=="001":
        original=mod.signal
        def gated_signal(sym,h,cfg):
            sig,edge=original(sym,h,cfg)
            if sig=="BUY":
                f=getflow(sym)
                if not f["ok"]: return "HOLD",edge
            return sig,edge
        mod.signal=gated_signal
    else:
        original=mod.metrics
        def gated_metrics(sym,h,cfg):
            m=original(sym,h,cfg)
            # Entry requires breakout in both agents; veto only that entry gate.
            if m.get("ready") and m.get("breakout"):
                f=getflow(sym)
                if not f["ok"]:
                    m=dict(m); m["breakout"]=False; m["orderflow_veto"]=True
                else:
                    m=dict(m); m["orderflow_confirmed"]=True
                m["orderflow_score"]=f["score"]
                m["orderflow_delta"]=f["delta"]
                m["orderbook_imbalance"]=f["book"]
            return m
        mod.metrics=gated_metrics
    mod.main()
    with open(f"orderflow{agent_id}.json","w",encoding="utf-8") as f:
        json.dump({"agent_id":agent_id,"generated_at":datetime.now(timezone.utc).isoformat(),
                   "method":"public Binance order-flow entry gate","symbols":FLOW},f,indent=2)

if __name__=="__main__":
    if len(sys.argv)!=2 or sys.argv[1] not in {"001","002","003"}:
        raise SystemExit("usage: orderflow_runner.py 001|002|003")
    run(sys.argv[1])
