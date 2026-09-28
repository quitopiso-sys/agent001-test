#!/usr/bin/env python3
import csv,json,urllib.request
from pathlib import Path
from datetime import datetime,timezone

B=Path(__file__).resolve().parent
CFG=B/'config002.json'; STATE=B/'state002.json'; HIST=B/'price_history002.json'
CYC=B/'cycles002.csv'; TR=B/'trades002.csv'; SUM=B/'summary002.json'; PAGE=B/'agent002.html'

def now(): return datetime.now(timezone.utc).isoformat()
def load(p,d): return json.loads(p.read_text()) if p.exists() else d
def save(p,x): p.write_text(json.dumps(x,indent=2),encoding='utf-8')
def jget(u):
    r=urllib.request.Request(u,headers={'User-Agent':'AGENT-002-paper/1.0'})
    with urllib.request.urlopen(r,timeout=20) as f:return json.loads(f.read().decode())
def prices(symbols):
    fx=float(jget('https://api.coinbase.com/v2/exchange-rates?currency=USD')['data']['rates']['CHF'])
    out={}
    for s in symbols:
        try: out[s]=float(jget(f'https://api.exchange.coinbase.com/products/{s}-USD/ticker')['price'])*fx
        except Exception: pass
    return out
def pct(a,b): return (a/b-1)*100 if b else 0
def eq(st,p): return st['cash']+sum(v['qty']*p.get(s,0) for s,v in st['pos'].items())
def exp(st,p): return sum(v['qty']*p.get(s,0) for s,v in st['pos'].items())
def opened(st): return sum(v['qty']>0 for v in st['pos'].values())
def csv_init(p,h):
    if not p.exists():
        with p.open('w',newline='') as f: csv.writer(f).writerow(h)
def log_trade(st,p,cfg,s,side,notional,fee,reason):
    csv_init(TR,['timestamp','symbol','side','notional_chf','fee_chf','equity_after_chf','reason'])
    with TR.open('a',newline='') as f: csv.writer(f).writerow([now(),s,side,f'{notional:.8f}',f'{fee:.8f}',f'{eq(st,p):.8f}',reason])
def metrics(s,h,c):
    vals=[float(x[s]) for x in h if s in x]
    need=max(c['slow_period'],c['breakout_lookback'])+1
    if len(vals)<need:return {'ready':False,'fast':0,'slow':0,'breakout':False,'score':-999}
    cur=vals[-1]; mf=pct(cur,vals[-1-c['fast_period']]); ms=pct(cur,vals[-1-c['slow_period']])
    level=max(vals[-1-c['breakout_lookback']:-1])*(1+c['breakout_buffer_pct']/100)
    return {'ready':True,'fast':mf,'slow':ms,'breakout':cur>=level,'score':mf+.55*ms}
def buy(st,p,c,s,reason):
    if st['pos'][s]['qty']>0 or opened(st)>=c['max_positions']: return 'BLOCKED'
    equity=eq(st,p); room=max(0,equity*c['max_total_exposure_pct']-exp(st,p))
    budget=min(equity*c['position_size_pct'],room,st['cash'])
    if budget<1:return 'BLOCKED'
    fee=c['fee_rate']; slip=c['slippage_bps']/10000; n=budget/(1+fee); f=n*fee; px=p[s]*(1+slip)
    st['cash']-=n+f; st['pos'][s]={'qty':n/px,'entry':px,'peak':p[s]}; st['fees']+=f; st['trades']+=1
    log_trade(st,p,c,s,'BUY',n,f,reason); return f'BUY CHF {n:.2f}'
def sell(st,p,c,s,reason):
    q=st['pos'][s]['qty']
    if q<=0:return 'BLOCKED'
    fee=c['fee_rate']; slip=c['slippage_bps']/10000; px=p[s]*(1-slip); n=q*px; f=n*fee
    st['cash']+=n-f; st['pos'][s]={'qty':0,'entry':0,'peak':0}; st['fees']+=f; st['trades']+=1
    log_trade(st,p,c,s,'SELL',n,f,reason); return f'SELL CHF {n:.2f}'

def tail(p,n):
    if not p.exists():return []
    with p.open() as f:return list(csv.DictReader(f))[-n:]
def page(sm,st,mm):
    trades=tail(TR,20); cycles=tail(CYC,30)
    rows=''.join(f"<tr><td>{r['timestamp'][:19]}</td><td>{r['symbol']}</td><td>{r['side']}</td><td>CHF {float(r['notional_chf']):.2f}</td><td>CHF {float(r['fee_chf']):.3f}</td><td>{r['reason']}</td></tr>" for r in reversed(trades)) or "<tr><td colspan=6>Sin trades todavía.</td></tr>"
    radar=''.join(f"<tr><td>{s}</td><td>{mm.get(s,{}).get('fast',0):+.2f}%</td><td>{mm.get(s,{}).get('slow',0):+.2f}%</td><td>{'YES' if mm.get(s,{}).get('breakout') else 'NO'}</td><td>{mm.get(s,{}).get('score',-999):+.2f}</td></tr>" for s in sm['symbols'])
    pos=''.join(f"<tr><td>{s}</td><td>{v['qty']:.8f}</td><td>CHF {v['entry']:.4f}</td><td>CHF {sm['prices'].get(s,0):.4f}</td><td>{pct(sm['prices'].get(s,0),v['entry']):+.2f}%</td></tr>" for s,v in st['pos'].items() if v['qty']>0) or "<tr><td colspan=5>Sin posiciones abiertas.</td></tr>"
    html=f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta http-equiv="refresh" content="60"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AGENT #002</title><style>
body{{margin:0;padding:22px;background:#090705;color:#f8f2eb;font-family:system-ui}}.w{{max-width:1100px;margin:auto}}.top{{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}}h1{{margin:0}}.sub{{color:#b89b82}}.badge{{padding:9px 13px;border:1px solid #76502c;border-radius:999px;color:#ffbd68}}.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:18px}}.c,.box{{background:#1b120d;border:1px solid #54351f;border-radius:16px;padding:14px}}.v{{font-size:28px;font-weight:800;margin-top:5px}}.l{{font-size:11px;color:#ad9078;text-transform:uppercase}}h2{{margin-top:28px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #49301f;text-align:left;font-size:13px}}th{{color:#b99e86}}.note{{margin-top:14px;padding:12px;border-radius:12px;background:#28170b;color:#edc18f}}@media(max-width:700px){{body{{padding:12px}}}}
</style></head><body><div class="w"><div class="top"><div><h1>AGENT #002 · PROFIT HUNTER</h1><div class="sub">Paper trading agresivo · objetivo: beneficio neto</div></div><div class="badge">{sm['status']}</div></div>
<div class="g"><div class="c"><div class="l">Patrimonio</div><div class="v">CHF {sm['equity_chf']:.2f}</div></div><div class="c"><div class="l">Resultado</div><div class="v">CHF {sm['pnl_chf']:+.2f}</div></div><div class="c"><div class="l">Ciclos</div><div class="v">{sm['cycle_count']}</div></div><div class="c"><div class="l">Trades</div><div class="v">{sm['trade_count']}</div></div><div class="c"><div class="l">Fees</div><div class="v">CHF {sm['fees_paid_chf']:.3f}</div></div></div>
<div class="note">Mandato: no basta sobrevivir. Debe superar CHF {sm['initial_capital_chf']:.2f} netos antes del ciclo {sm['profit_deadline_cycles']}; si no, queda FAILED y deja de abrir nuevas posiciones.</div>
<h2>Radar</h2><div class="box"><table><tr><th>Activo</th><th>Mom. rápido</th><th>Mom. lento</th><th>Breakout</th><th>Score</th></tr>{radar}</table></div>
<h2>Posiciones</h2><div class="box"><table><tr><th>Activo</th><th>Cantidad</th><th>Entrada</th><th>Precio</th><th>Bruto</th></tr>{pos}</table></div>
<h2>Operaciones</h2><div class="box"><table><tr><th>UTC</th><th>Activo</th><th>Lado</th><th>Importe</th><th>Fee</th><th>Motivo</th></tr>{rows}</table></div></div></body></html>'''
    PAGE.write_text(html,encoding='utf-8')

def main():
    c=load(CFG,{})
    if c.get('real_money_enabled'):raise SystemExit('REAL MONEY BLOCKED')
    syms=c['symbols']; st=load(STATE,{'cash':c['initial_capital_chf'],'pos':{s:{'qty':0,'entry':0,'peak':0} for s in syms},'fees':0,'trades':0,'cycles':0,'failed':False})
    for s in syms:st['pos'].setdefault(s,{'qty':0,'entry':0,'peak':0})
    h=load(HIST,[]); p=prices(syms)
    if len(p)<2:raise SystemExit('Not enough prices')
    h.append({'timestamp':now(),**p}); h=h[-10000:]; st['cycles']+=1
    mm={s:metrics(s,h,c) for s in p}; acts={s:'HOLD' for s in syms}
    for s in syms:
        if s not in p or st['pos'][s]['qty']<=0:continue
        ps=st['pos'][s]; ps['peak']=max(ps['peak'],p[s]); gross=pct(p[s],ps['entry']); trail=pct(p[s],ps['peak']); m=mm.get(s,{})
        if gross>=c['take_profit_pct']:acts[s]=sell(st,p,c,s,f"TAKE PROFIT {gross:+.2f}%")
        elif gross<=-c['hard_stop_pct']:acts[s]=sell(st,p,c,s,f"HARD STOP {gross:+.2f}%")
        elif gross>c['roundtrip_cost_pct'] and trail<=-c['trailing_stop_pct']:acts[s]=sell(st,p,c,s,f"TRAIL {trail:+.2f}%")
        elif m.get('ready') and m.get('fast',0)<=-c['exit_momentum_pct']:acts[s]=sell(st,p,c,s,f"MOM EXIT {m['fast']:+.2f}%")
    equity=eq(st,p)
    if st['cycles']>=c['profit_deadline_cycles'] and equity<=c['initial_capital_chf']:st['failed']=True
    if not st['failed'] and equity>c['hard_death_equity_chf']:
        cand=[]
        for s,m in mm.items():
            if st['pos'][s]['qty']>0 or not m.get('ready'):continue
            if m['fast']>=c['min_fast_momentum_pct'] and m['slow']>=c['min_slow_momentum_pct'] and m['breakout'] and m['score']>=c['min_entry_score']:cand.append((m['score'],s,m))
        for _,s,m in sorted(cand,reverse=True):
            if opened(st)>=c['max_positions']:break
            acts[s]=buy(st,p,c,s,f"PROFIT GATE score {m['score']:+.2f}; fast {m['fast']:+.2f}%; slow {m['slow']:+.2f}%")
    equity=eq(st,p)
    status='FAILED' if st['failed'] else 'DEAD' if equity<=c['hard_death_equity_chf'] else 'PROFIT' if equity>c['initial_capital_chf'] else 'HUNTING'
    csv_init(CYC,['timestamp','cycle','equity_chf','pnl_chf','status','actions'])
    with CYC.open('a',newline='') as f:csv.writer(f).writerow([now(),st['cycles'],f'{equity:.8f}',f"{equity-c['initial_capital_chf']:.8f}",status,json.dumps(acts,separators=(',',':'))])
    sm={'timestamp':now(),'agent_id':'AGENT-002','status':status,'initial_capital_chf':c['initial_capital_chf'],'equity_chf':equity,'pnl_chf':equity-c['initial_capital_chf'],'cycle_count':st['cycles'],'trade_count':st['trades'],'fees_paid_chf':st['fees'],'profit_deadline_cycles':c['profit_deadline_cycles'],'symbols':syms,'prices':p,'actions':acts,'metrics':mm,'failed':st['failed']}
    save(HIST,h);save(STATE,st);save(SUM,sm);page(sm,st,mm);print(json.dumps(sm,indent=2))
if __name__=='__main__':main()
