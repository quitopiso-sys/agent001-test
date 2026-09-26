#!/usr/bin/env python3
import csv, json, math, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from string import Template

BASE=Path(__file__).resolve().parent
STATE=BASE/'state.json'; CONFIG=BASE/'config.json'; HIST=BASE/'price_history.json'; CYCLES=BASE/'cycles.csv'; TRADES=BASE/'trades.csv'; INDEX=BASE/'index.html'; SUMMARY=BASE/'summary.json'

def now(): return datetime.now(timezone.utc).isoformat()
def load(p,d): return json.loads(p.read_text()) if p.exists() else d
def save(p,x): p.write_text(json.dumps(x,indent=2),encoding='utf-8')
def get_json(url):
    r=urllib.request.Request(url,headers={'User-Agent':'AGENT-001-paper/2.0'})
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

def spark(values,w=420,h=100):
    vals=[float(v) for v in values]
    if not vals: vals=[0.0,0.0]
    if len(vals)==1: vals=[vals[0],vals[0]]
    lo,hi=min(vals),max(vals)
    if hi==lo:
        pad=max(abs(hi)*0.002,1.0); lo-=pad; hi+=pad
    pts=[]
    for i,v in enumerate(vals):
        x=i*w/max(1,len(vals)-1)
        y=h-8-(v-lo)/(hi-lo)*(h-16)
        pts.append(f'{x:.1f},{y:.1f}')
    line=' '.join(pts)
    area=f'0,{h} {line} {w},{h}'
    return f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" preserveAspectRatio="none"><defs><linearGradient id="fillg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#57e3d0" stop-opacity=".32"/><stop offset="100%" stop-color="#57e3d0" stop-opacity=".02"/></linearGradient></defs><polygon points="{area}" fill="url(#fillg)"/><polyline points="{line}" fill="none" stroke="#57e3d0" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>'

def badge_class(s):
    return {'NORMAL':'normal','DEFENSIVE':'defensive','SURVIVAL':'survival','CRITICAL':'critical','DEAD':'dead'}.get(s,'normal')

def page(sumry):
    cycles=tail(CYCLES,30)
    trades=tail(TRADES,20)
    hist=load(HIST,[])[-30:]
    cycle_rows=''.join(
        f"<tr><td>{r['timestamp'][:19].replace('T',' ')}</td><td>#{r['cycle']}</td><td><b>{r['btc_signal']}</b><span>{r['btc_action']}</span></td><td><b>{r['eth_signal']}</b><span>{r['eth_action']}</span></td><td>CHF {float(r['equity_chf']):.2f}</td><td><em class='{badge_class(r['status'])}'>{r['status']}</em></td></tr>"
        for r in reversed(cycles)
    ) or '<tr><td colspan="6">Esperando ciclo</td></tr>'
    trade_rows=''.join(
        f"<tr><td>{r['timestamp'][:19].replace('T',' ')}</td><td>{r['symbol']}</td><td>{r['side']}</td><td>CHF {float(r['notional_chf']):.2f}</td><td>CHF {float(r['fee_chf']):.4f}</td><td>CHF {float(r['equity_after_chf']):.2f}</td></tr>"
        for r in reversed(trades)
    ) or '<tr><td colspan="6">Todavía no ha ejecutado ninguna operación.</td></tr>'
    eq_vals=[float(r['equity_chf']) for r in cycles] or [sumry['equity_chf']]
    btc_vals=[float(r['BTC']) for r in hist if 'BTC' in r] or [sumry['prices']['BTC']]
    eth_vals=[float(r['ETH']) for r in hist if 'ETH' in r] or [sumry['prices']['ETH']]
    tpl=Template('''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta http-equiv="refresh" content="60"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AGENT #001</title>
<style>*{box-sizing:border-box}:root{color-scheme:dark}body{margin:0;padding:24px;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:#eef4fa;background:radial-gradient(circle at top,#122239 0,#090e16 48%,#060a10 100%)}.wrap{max-width:1180px;margin:auto}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap;margin-bottom:20px}h1{margin:0;font-size:38px;letter-spacing:-.04em}.sub{color:#92a1b7;margin-top:8px}.live,.badge,em{display:inline-flex;align-items:center;border:1px solid #2b3850;background:#0d1520;border-radius:999px}.live,.badge{padding:9px 13px;gap:9px;font-weight:700}.dot{width:9px;height:9px;border-radius:50%;background:#56e39a;box-shadow:0 0 12px #56e39a}.normal{color:#74efaa}.defensive{color:#ffd166}.survival{color:#ffb454}.critical,.dead{color:#ff7777}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}.card,.chart,.tablebox{background:rgba(18,26,40,.88);border:1px solid #253248;border-radius:18px;box-shadow:0 18px 40px rgba(0,0,0,.18)}.card{padding:16px}.hero{grid-column:span 2}.label{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:#8493aa}.value{font-size:30px;font-weight:800;margin-top:6px;letter-spacing:-.03em}.small{font-size:13px;color:#94a5bb;margin-top:4px}.section{display:flex;justify-content:space-between;gap:12px;align-items:end;margin:28px 0 12px}.section h2{margin:0;font-size:22px}.two{display:grid;grid-template-columns:1.2fr .8fr;gap:14px}.twoeq{display:grid;grid-template-columns:1fr 1fr;gap:14px}.chart{padding:16px}.tablebox{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:12px 10px;text-align:left;border-bottom:1px solid #253248;font-size:13px;vertical-align:top}th{color:#8796ab;font-weight:600}td span{display:block;color:#8697ad;margin-top:3px;font-size:12px}em{font-style:normal;padding:4px 8px;font-size:11px;font-weight:800}.foot{margin:18px 0 4px;color:#6f8097;font-size:12px;text-align:right}@media(max-width:850px){.two,.twoeq{grid-template-columns:1fr}.hero{grid-column:span 1}h1{font-size:30px}}</style></head><body><div class="wrap">
<div class="top"><div><h1>AGENT #001</h1><div class="sub">Simulación en tiempo real · actualización automática cada ~15 min</div></div><div style="display:flex;gap:10px;flex-wrap:wrap"><div class="live"><span class="dot"></span>LIVE TEST</div><div class="badge $status_class">$status</div></div></div>
<div class="grid"><div class="card hero"><div class="label">Patrimonio</div><div class="value">CHF $equity</div><div class="small">Última actualización: $updated UTC</div></div><div class="card"><div class="label">Resultado</div><div class="value">CHF $pnl</div></div><div class="card"><div class="label">Ciclos</div><div class="value">$cycles</div></div><div class="card"><div class="label">Trades</div><div class="value">$trades</div></div><div class="card"><div class="label">Fees</div><div class="value">CHF $fees</div></div></div>
<div class="section"><h2>Rendimiento</h2><div class="small">evolución reciente del patrimonio</div></div><div class="two"><div class="chart"><div class="label">Patrimonio reciente</div>$eq_chart</div><div class="chart"><div class="label">Mercado y decisión actual</div><div class="grid" style="margin-top:12px"><div class="card"><div class="label">BTC</div><div class="value" style="font-size:23px">CHF $btc_price</div><div class="small">Señal: $btc_signal · Acción: $btc_action</div></div><div class="card"><div class="label">ETH</div><div class="value" style="font-size:23px">CHF $eth_price</div><div class="small">Señal: $eth_signal · Acción: $eth_action</div></div></div></div></div>
<div class="section"><h2>Movimiento del mercado</h2><div class="small">últimos ciclos registrados</div></div><div class="twoeq"><div class="chart"><div class="label">BTC</div>$btc_chart</div><div class="chart"><div class="label">ETH</div>$eth_chart</div></div>
<div class="section"><h2>Actividad de cada ciclo</h2><div class="small">incluye ciclos sin operación</div></div><div class="tablebox"><table><tr><th>UTC</th><th>Ciclo</th><th>BTC</th><th>ETH</th><th>Patrimonio</th><th>Estado</th></tr>$cycle_rows</table></div>
<div class="section"><h2>Operaciones simuladas</h2><div class="small">solo aparece cuando ejecuta trades</div></div><div class="tablebox"><table><tr><th>UTC</th><th>Activo</th><th>Lado</th><th>Importe</th><th>Fee</th><th>Patrimonio</th></tr>$trade_rows</table></div><div class="foot">AGENT #001 · Dashboard público</div></div></body></html>''')
    html=tpl.safe_substitute(
        status_class=badge_class(sumry['status']), status=sumry['status'], equity=f"{sumry['equity_chf']:.2f}", pnl=f"{sumry['pnl_chf']:+.2f}",
        updated=sumry['timestamp'][:19].replace('T',' '), cycles=sumry['cycle_count'], trades=sumry['trade_count'], fees=f"{sumry['fees_paid_chf']:.4f}",
        eq_chart=spark(eq_vals,430,115), btc_price=f"{sumry['prices']['BTC']:,.2f}", eth_price=f"{sumry['prices']['ETH']:,.2f}",
        btc_signal=sumry['signals']['BTC'], eth_signal=sumry['signals']['ETH'], btc_action=sumry['actions']['BTC'], eth_action=sumry['actions']['ETH'],
        btc_chart=spark(btc_vals,430,90), eth_chart=spark(eth_vals,430,90), cycle_rows=cycle_rows, trade_rows=trade_rows
    )
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
