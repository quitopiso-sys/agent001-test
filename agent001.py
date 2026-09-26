#!/usr/bin/env python3
import csv, json, math, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
STATE=BASE/'state.json'; CONFIG=BASE/'config.json'; HIST=BASE/'price_history.json'; CYCLES=BASE/'cycles.csv'; TRADES=BASE/'trades.csv'; INDEX=BASE/'index.html'; SUMMARY=BASE/'summary.json'

def now(): return datetime.now(timezone.utc).isoformat()
def load(p,d): return json.loads(p.read_text()) if p.exists() else d
def save(p,x): p.write_text(json.dumps(x,indent=2),encoding='utf-8')
def get_json(url):
    r=urllib.request.Request(url,headers={'User-Agent':'AGENT-001-paper/1.0'})
    with urllib.request.urlopen(r,timeout=15) as f: return json.loads(f.read().decode())

def prices_chf():
    rates=get_json('https://api.coinbase.com/v2/exchange-rates?currency=EUR')['data']['rates']
    eur_chf=float(rates['CHF'])
    out={}
    for s in ('BTC','ETH'):
        t=get_json(f'https://api.exchange.coinbase.com/products/{s}-EUR/ticker')
        out[s]=float(t['price'])*eur_chf
    return out

def status(eq):
    if eq<=5: return 'DEAD'
    if eq<10: return 'CRITICAL'
    if eq<20: return 'SURVIVAL'
    if eq<35: return 'DEFENSIVE'
    return 'NORMAL'

def equity(st,p): return st['cash_chf']+sum(st['positions'][s]*p[s] for s in ('BTC','ETH'))
def exposure(st,p): return sum(st['positions'][s]*p[s] for s in ('BTC','ETH'))
def mean(a): return sum(a)/len(a)

def signal(sym,h,cfg):
    n1,n2=cfg['fast_ma_period'],cfg['slow_ma_period']
    if len(h)<n2: return 'HOLD',0.0
    a=[x[sym] for x in h]
    edge=(mean(a[-n1:])/mean(a[-n2:])-1)*100
    th=cfg['signal_threshold_pct']
    return ('BUY' if edge>=th else 'SELL' if edge<=-th else 'HOLD'),edge

def ensure_csv(path,header):
    if not path.exists():
        with path.open('w',newline='',encoding='utf-8') as f: csv.writer(f).writerow(header)

def add_trade(st,p,cfg,sym,side,reason):
    ensure_csv(TRADES,['timestamp','symbol','side','notional_chf','fee_chf','equity_after_chf','reason'])
    fee=cfg['fee_rate']; slip=cfg['slippage_bps']/10000
    if side=='BUY':
        eq=equity(st,p); maxexp=eq*cfg['max_total_exposure_pct']; room=max(0,maxexp-exposure(st,p)); budget=min(eq*cfg['max_buy_pct'],room,st['cash_chf'])
        if budget<0.50: return 'BLOCKED'
        notional=budget/(1+fee); cost=notional*(1+fee); px=p[sym]*(1+slip); qty=notional/px
        st['cash_chf']-=cost; st['positions'][sym]+=qty; fee_amt=notional*fee
    else:
        qty=st['positions'][sym]
        if qty<=0: return 'BLOCKED'
        px=p[sym]*(1-slip); notional=qty*px; fee_amt=notional*fee; st['cash_chf']+=notional-fee_amt; st['positions'][sym]=0
    st['fees_paid_chf']+=fee_amt; st['trade_count']+=1
    with TRADES.open('a',newline='',encoding='utf-8') as f: csv.writer(f).writerow([now(),sym,side,f'{notional:.8f}',f'{fee_amt:.8f}',f'{equity(st,p):.8f}',reason])
    return f'{side} CHF {notional:.2f}'

def tail(path,n=20):
    if not path.exists(): return []
    with path.open(encoding='utf-8') as f: return list(csv.DictReader(f))[-n:]

def page(sumry):
    rows=''.join(f"<tr><td>{r['timestamp'][:19].replace('T',' ')}</td><td>#{r['cycle']}</td><td>{r['btc_signal']} / {r['btc_action']}</td><td>{r['eth_signal']} / {r['eth_action']}</td><td>CHF {float(r['equity_chf']):.2f}</td><td>{r['status']}</td></tr>" for r in reversed(tail(CYCLES,25))) or "<tr><td colspan=6>Esperando ciclo</td></tr>"
    trs=''.join(f"<tr><td>{r['timestamp'][:19].replace('T',' ')}</td><td>{r['symbol']}</td><td>{r['side']}</td><td>CHF {float(r['notional_chf']):.2f}</td><td>CHF {float(r['fee_chf']):.4f}</td><td>CHF {float(r['equity_after_chf']):.2f}</td></tr>" for r in reversed(tail(TRADES,20))) or "<tr><td colspan=6>Sin operaciones todavía</td></tr>"
    html=f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta http-equiv="refresh" content="60"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AGENT #001</title><style>body{{font-family:system-ui;background:#0b0e13;color:#eef;padding:22px}}.wrap{{max-width:1050px;margin:auto}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}}.card,table{{background:#151a23;border:1px solid #293140;border-radius:12px}}.card{{padding:14px}}.v{{font-size:24px;font-weight:700}}.l{{opacity:.65;font-size:12px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #293140;text-align:left;font-size:13px}}.live{{padding:7px 10px;border:1px solid #2b3544;border-radius:999px;display:inline-block}}</style></head><body><div class="wrap"><h1>AGENT #001</h1><p class="live">● TEST MODE — {sumry['status']}</p><div class="grid"><div class="card"><div class="l">Patrimonio</div><div class="v">CHF {sumry['equity_chf']:.2f}</div></div><div class="card"><div class="l">Resultado</div><div class="v">CHF {sumry['pnl_chf']:+.2f}</div></div><div class="card"><div class="l">Ciclos</div><div class="v">{sumry['cycle_count']}</div></div><div class="card"><div class="l">Trades</div><div class="v">{sumry['trade_count']}</div></div><div class="card"><div class="l">BTC</div><div class="v">CHF {sumry['prices']['BTC']:,.0f}</div><div>{sumry['signals']['BTC']} / {sumry['actions']['BTC']}</div></div><div class="card"><div class="l">ETH</div><div class="v">CHF {sumry['prices']['ETH']:,.0f}</div><div>{sumry['signals']['ETH']} / {sumry['actions']['ETH']}</div></div></div><h2>Actividad de cada ciclo</h2><div style="overflow:auto"><table><tr><th>UTC</th><th>Ciclo</th><th>BTC</th><th>ETH</th><th>Patrimonio</th><th>Estado</th></tr>{rows}</table></div><h2>Operaciones simuladas</h2><div style="overflow:auto"><table><tr><th>UTC</th><th>Activo</th><th>Lado</th><th>Importe</th><th>Fee</th><th>Patrimonio</th></tr>{trs}</table></div><p>Dinero real BLOQUEADO · Coinbase privado NO conectado · 0 CHF gastados</p></div></body></html>'''
    INDEX.write_text(html,encoding='utf-8')

def main():
    cfg=load(CONFIG,{})
    if cfg.get('real_money_enabled'): raise SystemExit('REAL MONEY BLOCKED')
    st=load(STATE,{})
    h=load(HIST,[])
    p=prices_chf(); h.append({'timestamp':now(),'BTC':p['BTC'],'ETH':p['ETH']}); h=h[-10000:]
    st['cycle_count']=st.get('cycle_count',0)+1; actions={}; sigs={}
    for s in ('BTC','ETH'):
        sig,edge=signal(s,h,cfg); prev=st.get('last_signal',{}).get(s,'HOLD'); sigs[s]=sig
        if sig in ('BUY','SELL') and sig!=prev: actions[s]=add_trade(st,p,cfg,s,sig,f'MA edge {edge:+.3f}%')
        else: actions[s]='HOLD' if sig=='HOLD' else 'WAIT'
        st.setdefault('last_signal',{})[s]=sig
    eq=equity(st,p); st['status']=status(eq); st['last_update']=now(); st['last_prices_chf']=p
    ensure_csv(CYCLES,['timestamp','cycle','btc_signal','btc_action','eth_signal','eth_action','equity_chf','status'])
    with CYCLES.open('a',newline='',encoding='utf-8') as f: csv.writer(f).writerow([now(),st['cycle_count'],sigs['BTC'],actions['BTC'],sigs['ETH'],actions['ETH'],f'{eq:.8f}',st['status']])
    save(STATE,st); save(HIST,h)
    sm={'timestamp':now(),'status':st['status'],'equity_chf':eq,'pnl_chf':eq-50,'cycle_count':st['cycle_count'],'trade_count':st['trade_count'],'prices':p,'signals':sigs,'actions':actions,'fees_paid_chf':st['fees_paid_chf']}
    save(SUMMARY,sm); page(sm)
    print(f"Cycle #{st['cycle_count']} | BTC {sigs['BTC']}/{actions['BTC']} | ETH {sigs['ETH']}/{actions['ETH']} | CHF {eq:.2f} | {st['status']}")

if __name__=='__main__': main()
