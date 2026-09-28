#!/usr/bin/env python3
import csv, json, sys
from pathlib import Path
from html import escape

B=Path(__file__).resolve().parent
AGENTS={
 '001':{'name':'AGENT #001','tag':'CONTROL','state':'state.json','summary':'summary.json','trades':'trades.csv','page':'index.html','details':'trade_details001.json','accent':'#57e3d0','bg':'#071019','initial':50.0},
 '002':{'name':'AGENT #002 · PROFIT HUNTER','tag':'PROFIT HUNTER','state':'state002.json','summary':'summary002.json','trades':'trades002.csv','page':'agent002.html','details':'trade_details002.json','accent':'#ffb45e','bg':'#120b06','initial':50.0},
 '003':{'name':'AGENT #003 · NO FEAR','tag':'NO FEAR','state':'state003.json','summary':'summary003.json','trades':'trades003.csv','page':'agent003.html','details':'trade_details003.json','accent':'#ff557d','bg':'#14070b','initial':50.0},
}

def loadj(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def savej(path,obj):path.write_text(json.dumps(obj,indent=2),encoding='utf-8')
def rows(path):
    if not path.exists():return []
    with path.open(encoding='utf-8') as f:return list(csv.DictReader(f))
def fnum(x,d=0.0):
    try:return float(x)
    except Exception:return d

def cash(a,st):return fnum(st.get('cash_chf' if a=='001' else 'cash',0))
def trade_count(a,st):return int(st.get('trade_count' if a=='001' else 'trades',0))
def positions(a,st):
    if a=='001':return {s:{'qty':fnum(q),'entry':0.0,'peak':0.0} for s,q in st.get('positions',{}).items()}
    return {s:{'qty':fnum(v.get('qty')),'entry':fnum(v.get('entry')),'peak':fnum(v.get('peak'))} for s,v in st.get('pos',{}).items()}
def key(r):return '|'.join([r.get('timestamp',''),r.get('symbol',''),r.get('side',''),r.get('notional_chf','')])
def fmtpx(x):
    x=fnum(x)
    if x>=1000:return f"CHF {x:,.2f}"
    if x>=1:return f"CHF {x:,.4f}"
    return f"CHF {x:,.6f}"
def pct(a,b):return (a/b-1)*100 if b else 0.0

def pre(a,c):
    st=loadj(B/c['state'],{})
    savej(B/f'.dashboard_before_{a}.json',{'state':st,'trade_count':trade_count(a,st)})

def capture_new_details(a,c,before,st,trs):
    path=B/c['details']; details=loadj(path,[]); known={d.get('key') for d in details}
    old=int(before.get('trade_count',0)); new=trs[old:]
    bp=positions(a,before.get('state',{})); ap=positions(a,st)
    for r in new:
        s=r.get('symbol',''); side=r.get('side',''); n=fnum(r.get('notional_chf')); q=0.0; px=0.0
        if side=='BUY':
            if a!='001' and ap.get(s,{}).get('entry',0)>0:
                px=ap[s]['entry']; q=n/px if px else 0
            else:
                q=max(0.0,ap.get(s,{}).get('qty',0)-bp.get(s,{}).get('qty',0))
                px=n/q if q else 0
        elif side=='SELL':
            q=bp.get(s,{}).get('qty',0)
            px=n/q if q else 0
        d={'key':key(r),'timestamp':r.get('timestamp'),'symbol':s,'side':side,'notional_chf':n,'fee_chf':fnum(r.get('fee_chf')),'qty':q,'execution_price_chf':px,'reason':r.get('reason','')}
        if d['key'] not in known:details.append(d);known.add(d['key'])
    savej(path,details[-500:])
    return details

def latest_open_buy(trs,details,sym):
    dm={d.get('key'):d for d in details}
    for r in reversed(trs):
        if r.get('symbol')==sym and r.get('side')=='BUY':return r,dm.get(key(r),{})
    return None,{}

def render(a,c,st,sm,trs,details):
    prices={s:fnum(v) for s,v in sm.get('prices',{}).items()}; pos=positions(a,st)
    eq=fnum(sm.get('equity_chf')); pnl=fnum(sm.get('pnl_chf'),eq-c['initial']); fees=fnum(sm.get('fees_paid_chf',st.get('fees_paid_chf',st.get('fees',0))))
    ca=cash(a,st); invested=max(0.0,eq-ca); unreal=0.0; position_rows=[]
    for s,v in pos.items():
        q=v['qty']; cur=prices.get(s,0)
        if q<=0:continue
        entry=v.get('entry',0); br,bd=latest_open_buy(trs,details,s)
        if not entry:entry=fnum(bd.get('execution_price_chf'))
        upnl=(cur-entry)*q if entry else 0.0; unreal+=upnl
        bought=(br or {}).get('timestamp','')[:19].replace('T',' ') if br else 'n/d'
        position_rows.append(f"<tr><td><b>{escape(s)}</b></td><td>{q:.8f}</td><td>{fmtpx(entry) if entry else 'n/d histórico'}</td><td>{fmtpx(cur)}</td><td>CHF {q*cur:.2f}</td><td class={'pos' if upnl>=0 else 'neg'}>CHF {upnl:+.3f}<br><small>{pct(cur,entry):+.2f}%</small></td><td>{bought} UTC</td></tr>")
    if not position_rows:position_rows=["<tr><td colspan='7' class='muted'>Sin posiciones abiertas.</td></tr>"]
    closed_est=pnl-unreal
    market=[]
    syms=list(sm.get('symbols',prices.keys()))
    for s in syms:
        if s not in prices:continue
        action=sm.get('actions',{}).get(s,'HOLD'); signal=sm.get('signals',{}).get(s,'')
        met=sm.get('metrics',{}).get(s,{})
        info=(f"Señal {signal} · {action}" if signal else f"Acción {action} · score {fnum(met.get('score',0)):+.2f}")
        market.append(f"<tr><td><b>{escape(s)}</b></td><td>{fmtpx(prices[s])}</td><td>{escape(info)}</td><td><a target='_blank' rel='noopener' href='https://www.coinbase.com/advanced-trade/spot'>Verificar en Coinbase ↗</a></td></tr>")
    dm={d.get('key'):d for d in details}; trade_rows=[]
    for r in reversed(trs[-40:]):
        d=dm.get(key(r),{}); px=fnum(d.get('execution_price_chf')); q=fnum(d.get('qty'))
        # Enrich the currently-open BUY even if it happened before enhanced logging existed.
        s=r.get('symbol','')
        if not px and r.get('side')=='BUY' and pos.get(s,{}).get('qty',0)>0:
            last,_=latest_open_buy(trs,details,s)
            if last is r or (last and key(last)==key(r)):
                px=pos[s].get('entry',0); q=fnum(r.get('notional_chf'))/px if px else 0
        reason=r.get('reason','') or 'Registro histórico'
        trade_rows.append(f"<tr><td>{r.get('timestamp','')[:19].replace('T',' ')} UTC</td><td><b>{escape(s)}</b></td><td><span class='side {r.get('side','').lower()}'>{escape(r.get('side',''))}</span></td><td>CHF {fnum(r.get('notional_chf')):.2f}</td><td>{fmtpx(px) if px else 'n/d histórico'}</td><td>{f'{q:.8f}' if q else 'n/d'}</td><td>CHF {fnum(r.get('fee_chf')):.4f}</td><td>{escape(reason)}</td></tr>")
    if not trade_rows:trade_rows=["<tr><td colspan='8' class='muted'>Todavía no ha ejecutado operaciones.</td></tr>"]
    updated=sm.get('timestamp',''); status=sm.get('status','RUNNING'); cycles=sm.get('cycle_count',st.get('cycle_count',st.get('cycles',0))); tc=sm.get('trade_count',trade_count(a,st))
    accent=c['accent']; bg=c['bg']
    html=f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta http-equiv="refresh" content="60"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(c['name'])}</title><style>
*{{box-sizing:border-box}}:root{{color-scheme:dark}}body{{margin:0;background:radial-gradient(circle at top,{accent}18,{bg} 42%,#05070a);color:#f6f8fb;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;padding:22px}}.w{{max-width:1250px;margin:auto}}.top{{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-start}}h1{{margin:0;font-size:36px;letter-spacing:-.04em}}.sub,.muted,small{{color:#91a0b2}}.pill{{border:1px solid {accent}66;color:{accent};padding:9px 13px;border-radius:999px;background:{accent}12;font-weight:800}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:18px}}.card,.box{{background:#0e141dcc;border:1px solid #273344;border-radius:16px}}.card{{padding:15px}}.lab{{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#8291a4}}.val{{font-size:26px;font-weight:850;margin-top:5px}}.pos{{color:#65e6a5}}.neg{{color:#ff788e}}h2{{margin:28px 0 10px;font-size:21px}}.box{{overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px 10px;border-bottom:1px solid #243041;text-align:left;font-size:13px;white-space:nowrap}}th{{color:#8797aa;font-size:11px;text-transform:uppercase}}a{{color:{accent};text-decoration:none}}.side{{font-weight:900;padding:4px 7px;border-radius:8px}}.buy{{color:#67e7a6;background:#123326}}.sell{{color:#ff879a;background:#38141c}}.source{{margin-top:12px;padding:12px 14px;border:1px solid {accent}55;background:{accent}0d;border-radius:13px;font-size:13px;line-height:1.5}}.foot{{margin:18px 0;color:#748397;font-size:12px}}@media(max-width:700px){{body{{padding:12px}}h1{{font-size:28px}}.val{{font-size:23px}}}}</style></head><body><div class="w">
<div class="top"><div><h1>{escape(c['name'])}</h1><div class="sub">{escape(c['tag'])} · paper trading · telemetría ampliada</div></div><div class="pill">{escape(str(status))}</div></div>
<div class="grid"><div class="card"><div class="lab">Patrimonio</div><div class="val">CHF {eq:.2f}</div></div><div class="card"><div class="lab">Resultado neto</div><div class="val {'pos' if pnl>=0 else 'neg'}">CHF {pnl:+.2f}</div></div><div class="card"><div class="lab">Efectivo</div><div class="val">CHF {ca:.2f}</div></div><div class="card"><div class="lab">Invertido ahora</div><div class="val">CHF {invested:.2f}</div></div><div class="card"><div class="lab">P/L abierto</div><div class="val {'pos' if unreal>=0 else 'neg'}">CHF {unreal:+.2f}</div></div><div class="card"><div class="lab">P/L cerrado + costes</div><div class="val {'pos' if closed_est>=0 else 'neg'}">CHF {closed_est:+.2f}</div></div><div class="card"><div class="lab">Fees acumulados</div><div class="val">CHF {fees:.3f}</div></div><div class="card"><div class="lab">Ciclos / trades</div><div class="val">{cycles} / {tc}</div></div></div>
<div class="source"><b>Precio del agente:</b> captura de Coinbase usada en el último ciclo, <span id="stamp">{escape(updated[:19].replace('T',' '))} UTC</span> · <span id="age"></span>. No es un ticker segundo a segundo. <a target="_blank" rel="noopener" href="https://www.coinbase.com/advanced-trade/spot">Abrir mercado spot de Coinbase ↗</a></div>
<h2>Mercado que está viendo el agente</h2><div class="box"><table><tr><th>Activo</th><th>Precio CHF</th><th>Lectura del agente</th><th>Comprobar mercado</th></tr>{''.join(market)}</table></div>
<h2>Posiciones abiertas</h2><div class="box"><table><tr><th>Activo</th><th>Cantidad</th><th>Precio entrada</th><th>Precio actual</th><th>Valor</th><th>P/L abierto</th><th>Compró</th></tr>{''.join(position_rows)}</table></div>
<h2>Historial de operaciones</h2><div class="box"><table><tr><th>Hora</th><th>Activo</th><th>Operación</th><th>Importe</th><th>Precio ejecución</th><th>Cantidad</th><th>Fee</th><th>Motivo</th></tr>{''.join(trade_rows)}</table></div>
<div class="foot">Los precios de ejecución exactos se registran desde esta mejora del panel. Operaciones anteriores que no guardaban ese dato aparecen como “n/d histórico”. La estrategia del agente no fue modificada.</div></div>
<script>const t=new Date({json.dumps(updated)});function age(){{if(isNaN(t))return;const m=Math.max(0,Math.floor((Date.now()-t)/60000));document.getElementById('age').textContent=m<1?'actualizado hace menos de 1 min':`actualizado hace ${{m}} min`;}}age();setInterval(age,30000);</script></body></html>'''
    (B/c['page']).write_text(html,encoding='utf-8')

def post(a,c):
    before=loadj(B/f'.dashboard_before_{a}.json',{'state':{},'trade_count':0}); st=loadj(B/c['state'],{}); sm=loadj(B/c['summary'],{}); trs=rows(B/c['trades'])
    details=capture_new_details(a,c,before,st,trs); render(a,c,st,sm,trs,details)
    p=B/f'.dashboard_before_{a}.json'
    if p.exists():p.unlink()

if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1] not in ('pre','post') or sys.argv[2] not in AGENTS:raise SystemExit('usage: dashboard_enhancer.py pre|post 001|002|003')
    mode,a=sys.argv[1],sys.argv[2]; c=AGENTS[a]
    pre(a,c) if mode=='pre' else post(a,c)
