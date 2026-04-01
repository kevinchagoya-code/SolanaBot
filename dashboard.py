"""
Solana Bot Web Dashboard
Run alongside scanner.py: python dashboard.py
Opens at http://localhost:8080
"""
import json, asyncio
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Solana Bot Dashboard")
DASHBOARD_FILE = Path(__file__).parent / "dashboard_data.json"


def get_data() -> dict:
    try:
        return json.loads(DASHBOARD_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "Waiting for scanner data..."}


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Solana Bot Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:'Consolas','Monaco','Courier New',monospace;font-size:14px}

/* ── HEADER ── */
.header{background:#111119;border-bottom:1px solid #1e1e2e;padding:10px 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.header h1{font-size:18px;color:#7c3aed;letter-spacing:1px}
.header-right{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{padding:3px 10px;border-radius:4px;font-weight:bold;font-size:11px;letter-spacing:1px}
.badge-sim{background:#1e3a5f;color:#60a5fa}
.badge-live{background:#3f1e1e;color:#f87171;animation:pulse 2s infinite}
.badge-hot{background:#3f1e1e;color:#f87171}
.badge-warm{background:#3f2e1a;color:#eab308}
.badge-slow{background:#1a2e3f;color:#60a5fa}
.badge-dead{background:#1e1e1e;color:#666}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
@keyframes newpos{0%{background:#1a2a1a}100%{background:transparent}}
@keyframes closepos{0%{opacity:1}100%{opacity:0;height:0;padding:0}}
.dot-on{width:8px;height:8px;border-radius:50%;background:#22c55e;display:inline-block}
.dot-off{width:8px;height:8px;border-radius:50%;background:#ef4444;display:inline-block}

/* ── GRID ── */
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:10px;padding:12px}
.c3{grid-column:span 3}.c4{grid-column:span 4}.c5{grid-column:span 5}
.c6{grid-column:span 6}.c7{grid-column:span 7}.c8{grid-column:span 8}
.c12{grid-column:span 12}
@media(max-width:900px){.grid{grid-template-columns:1fr}
  .c3,.c4,.c5,.c6,.c7,.c8,.c12{grid-column:span 1}}

.card{background:#111119;border:1px solid #1e1e2e;border-radius:6px;padding:14px;overflow:hidden}
.card h2{font-size:11px;color:#555;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px}

/* ── P&L ── */
.pnl-big{font-size:34px;font-weight:bold;line-height:1.1}
.green{color:#22c55e}.red{color:#ef4444}.dim{color:#555}.purple{color:#7c3aed}
.yellow{color:#eab308}.cyan{color:#22d3ee}.white{color:#e0e0e0}
.sub{font-size:12px;color:#555;margin-top:4px}

/* ── STATS ── */
.stats{display:flex;gap:16px;flex-wrap:wrap}
.stat{text-align:center;min-width:55px}
.stat b{display:block;font-size:20px;color:#fff}
.stat span{font-size:10px;color:#555;text-transform:uppercase;letter-spacing:.5px}

/* ── TABLE ── */
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;color:#444;text-transform:uppercase;font-size:10px;padding:5px 6px;border-bottom:1px solid #1e1e2e;letter-spacing:.5px}
td{padding:5px 6px;border-bottom:1px solid #0d0d14}
tr:hover{background:#14141e}
tr.new-pos{animation:newpos .8s ease-out}

/* ── HEAT BAR ── */
.hbar{width:50px;height:6px;background:#1a1a24;border-radius:3px;overflow:hidden;display:inline-block;vertical-align:middle}
.hfill{height:100%;border-radius:3px;transition:width .5s}
.h-rocket{background:#ef4444}.h-heat{background:#eab308}.h-warm{background:#6b7280}.h-cold{background:#374151}

/* ── TRADE FEED ── */
.trade{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #0d0d14;font-size:12px}
.trade:last-child{border:none}

/* ── CHART ── */
.chart-wrap{position:relative;height:180px}

/* ── LOSS BAR ── */
.loss-track{width:100%;height:14px;background:#1a1a24;border-radius:7px;overflow:hidden}
.loss-fill{height:100%;border-radius:7px;transition:width .5s;background:linear-gradient(90deg,#22c55e 0%,#eab308 50%,#ef4444 100%)}

/* ── STRATEGY CARDS ── */
.strat-row{display:flex;gap:8px;flex-wrap:wrap}
.strat-card{flex:1;min-width:100px;background:#0d0d14;border:1px solid #1e1e2e;border-radius:4px;padding:8px;text-align:center}
.strat-card b{display:block;font-size:16px}
.strat-card span{font-size:10px;color:#555;text-transform:uppercase}

/* ── ERRORS ── */
.err{font-size:11px;color:#f87171;padding:2px 0;border-bottom:1px solid #1a1a24;word-break:break-all}

/* ── TOAST ── */
.toast-container{position:fixed;bottom:20px;right:20px;z-index:999;display:flex;flex-direction:column;gap:6px}
.toast{padding:10px 16px;border-radius:6px;font-size:13px;font-family:inherit;color:#fff;opacity:0;
  transform:translateX(50px);transition:all .3s ease;max-width:380px;box-shadow:0 4px 12px rgba(0,0,0,.5)}
.toast.show{opacity:1;transform:translateX(0)}
.toast-win{background:#14532d;border-left:3px solid #22c55e}
.toast-loss{background:#450a0a;border-left:3px solid #ef4444}

/* ── EMPTY STATE ── */
.empty-state{text-align:center;padding:30px 10px;color:#444;font-size:13px}
.empty-state b{color:#666;font-size:14px}

/* ── MOBILE POSITION CARDS ── */
@media(max-width:900px){
  .pos-table{display:none!important}
  .pos-cards{display:flex!important}
}
@media(min-width:901px){
  .pos-cards{display:none!important}
}
.pos-cards{flex-direction:column;gap:8px}
.pos-card{background:#0d0d14;border:1px solid #1e1e2e;border-radius:6px;padding:10px 12px}
.pos-card-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.pos-card-head b{font-size:14px}.pos-card-head span{font-size:11px}
.pos-card-row{display:flex;justify-content:space-between;font-size:12px;color:#888;margin-top:3px}

/* ── SCROLLBAR ── */
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:#0a0a0f}::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
</style>
</head>
<body>

<div class="header">
  <h1>&#9889; SOLANA BOT</h1>
  <div class="header-right">
    <span id="ws-dot" class="dot-off" title="WebSocket"></span>
    <span id="uptime" class="dim">--:--:--</span>
    <span id="mode" class="badge badge-sim">SIM</span>
    <span id="market" class="badge badge-warm">WARM</span>
    <span id="session" class="dim">S#-</span>
    <span id="scanned" class="dim">0 scanned</span>
  </div>
</div>

<div class="grid">

  <!-- ROW 1: P&L, Stats, AI -->
  <div class="card c4">
    <h2>Profit &amp; Loss</h2>
    <div id="pnl" class="pnl-big green">$0.00</div>
    <div class="sub"><span id="pnl-sol">+0.0000 SOL</span> &middot; Bal: <span id="bal">5.000</span> SOL &middot; SOL $<span id="sol-px">0</span></div>
    <div class="sub" style="margin-top:6px">
      Rate: <span id="rate" class="cyan">$0.00/hr</span> &middot;
      Proj: <span id="proj" class="dim">$0/day</span>
    </div>
  </div>

  <div class="card c4">
    <h2>Today</h2>
    <div class="stats">
      <div class="stat"><b id="wr">0%</b><span>Win Rate</span></div>
      <div class="stat"><b id="wl">0/0</b><span>W / L</span></div>
      <div class="stat"><b id="tok">0</b><span>Tokens</span></div>
      <div class="stat"><b id="nopen">0</b><span>Open</span></div>
      <div class="stat"><b id="tpm">0</b><span>Tr/Hr</span></div>
    </div>
  </div>

  <div class="card c4">
    <h2>AI Engine</h2>
    <div style="display:flex;align-items:center;gap:8px">
      <span id="ai-dot" class="dot-on"></span>
      <span id="ai-name" class="white">Groq</span>
      <span class="dim">&middot;</span>
      <span id="ai-ms" class="cyan">--ms</span>
      <span class="dim">&middot;</span>
      <span id="ai-last" class="dim">none</span>
    </div>
    <div style="margin-top:8px">
      <div class="hbar" style="width:100%;height:8px">
        <div id="ai-bar" class="hfill h-heat" style="width:0%"></div>
      </div>
      <div class="sub" style="margin-top:2px">Calls: <span id="ai-calls">0</span> / 14,400</div>
    </div>
  </div>

  <!-- ROW 2: Balance chart -->
  <div class="card c12">
    <h2>Balance Over Time</h2>
    <div class="chart-wrap"><canvas id="chart"></canvas></div>
  </div>

  <!-- ROW 3: Positions + Trades -->
  <div class="card c8">
    <h2>Open Positions <span id="pos-n" class="purple">0</span></h2>
    <div class="pos-table" style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>Token</th><th>Strat</th><th>P&amp;L</th><th>Peak</th>
        <th>Heat</th><th>Dir</th><th>ATR</th><th>Trail</th><th>Held</th>
      </tr></thead>
      <tbody id="ptbody"></tbody>
    </table>
    </div>
    <div id="pos-empty" class="empty-state" style="display:none">
      <b>Scanning...</b><br><span id="empty-tok">0</span> tokens found | Waiting for entry signal
    </div>
    <!-- Mobile cards -->
    <div class="pos-cards" id="pos-cards-container"></div>
  </div>

  <div class="card c4">
    <h2>Recent Trades</h2>
    <div id="feed" style="max-height:320px;overflow-y:auto"></div>
  </div>

  <!-- ROW 4: Strategies + Loss budget -->
  <div class="card c8">
    <h2>Strategy Breakdown</h2>
    <div class="strat-row" id="strats"></div>
  </div>

  <div class="card c4">
    <h2>Daily Loss Budget</h2>
    <div class="loss-track"><div id="loss-fill" class="loss-fill" style="width:0%"></div></div>
    <div class="sub" style="margin-top:4px"><span id="loss-txt">0 / 1.2 SOL (0%)</span></div>
    <div style="margin-top:10px">
      <h2>Errors</h2>
      <div id="errors" style="max-height:100px;overflow-y:auto"></div>
    </div>
  </div>

</div>

<!-- Toast container -->
<div class="toast-container" id="toasts"></div>

<script>
// ── Chart ────────────────────────────────────────────────────────────
const ctx = document.getElementById('chart').getContext('2d');
const chart = new Chart(ctx, {
  type:'line',
  data:{labels:[],datasets:[
    {label:'Balance',data:[],borderColor:'#7c3aed',backgroundColor:'rgba(124,58,237,.08)',fill:true,tension:.3,pointRadius:0,borderWidth:2},
    {label:'Starting',data:[],borderColor:'#333',borderDash:[4,4],borderWidth:1,pointRadius:0,fill:false}
  ]},
  options:{
    responsive:true,maintainAspectRatio:false,animation:{duration:0},
    plugins:{legend:{display:false},tooltip:{mode:'index',intersect:false}},
    scales:{
      x:{grid:{color:'#1a1a24'},ticks:{color:'#444',maxTicksLimit:12,font:{size:10}}},
      y:{grid:{color:'#1a1a24'},ticks:{color:'#444',font:{size:10}}}
    }
  }
});

// ── Helpers ──────────────────────────────────────────────────────────
const $=id=>document.getElementById(id);
function cls(v){return v>=0?'green':'red'}
function fmt(v,d=4){return (v>=0?'+':'')+v.toFixed(d)}
function heldStr(s){
  if(s>=3600)return Math.floor(s/3600)+'h'+Math.floor((s%3600)/60)+'m';
  if(s>=60)return Math.floor(s/60)+'m'+Math.floor(s%60)+'s';
  return Math.floor(s)+'s';
}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
const SC={HFT:'#eab308',SCALP:'#e0e0e0',GRAD_SNIPE:'#22c55e',SWING:'#22d3ee',ESTAB:'#a78bfa',MOONBAG:'#f59e0b'};

function dirArrow(p){
  const d=p.price_direction||'FLAT',cu=p.consecutive_up||0,cd=p.consecutive_down||0;
  const acc=p.accelerating?'!':'';
  if(d==='UP') return '<td class="green">'+'&uarr;'.repeat(Math.min(cu||1,4))+acc+'</td>';
  if(d==='DOWN') return '<td class="red">'+'&darr;'.repeat(Math.min(cd||1,4))+acc+'</td>';
  return '<td class="dim">&rarr;</td>';
}
function atrCell(a){const c=a>=10?'red':a>=3?'yellow':'dim';return '<td class="'+c+'">'+a.toFixed(1)+'</td>';}
function trailCell(t){return '<td class="dim">'+t+'%</td>';}
function heatHtml(p){
  const h=p.heat||0,hc=h>=80?'h-rocket':h>=60?'h-heat':h>=40?'h-warm':'h-cold';
  const lbl=p.heat_label?p.heat_label.slice(0,3):'';
  return '<div class="hbar"><div class="hfill '+hc+'" style="width:'+Math.min(100,h)+'%"></div></div> '+h.toFixed(0)+' <span class="dim">'+lbl+'</span>';
}

// ── Toast notifications ─────────────────────────────────────────────
let toastCount=0;
function showToast(msg,isWin){
  const el=document.createElement('div');
  el.className='toast '+(isWin?'toast-win':'toast-loss');
  el.textContent=(isWin?'\u2713 ':'\u2717 ')+msg;
  const container=$('toasts');
  container.appendChild(el);
  // Limit to 3
  while(container.children.length>3) container.removeChild(container.firstChild);
  requestAnimationFrame(()=>el.classList.add('show'));
  setTimeout(()=>{el.classList.remove('show');setTimeout(()=>el.remove(),300)},4000);
}

// ── State tracking for new/closed detection ─────────────────────────
let prevPositionNames=new Set();
let prevTradeCount=0;

// ── WebSocket ────────────────────────────────────────────────────────
let reconnectTimer;
function connect(){
  const ws=new WebSocket('ws://'+location.host+'/ws');
  ws.onopen=()=>{$('ws-dot').className='dot-on';clearTimeout(reconnectTimer)};
  ws.onclose=()=>{$('ws-dot').className='dot-off';reconnectTimer=setTimeout(connect,3000)};
  ws.onerror=()=>ws.close();
  ws.onmessage=e=>{
    const d=JSON.parse(e.data);
    if(d.error){$('pnl').textContent=d.error;return}
    update(d);
  };
}

function update(d){
  // P&L
  const pu=d.pnl_usd||0,ps=d.pnl_sol||0;
  $('pnl').textContent='$'+fmt(pu,2);
  $('pnl').className='pnl-big '+cls(pu);
  $('pnl-sol').textContent=fmt(ps)+' SOL';
  $('bal').textContent=(d.balance||0).toFixed(3);
  $('sol-px').textContent=(d.sol_price||0).toFixed(2);

  // Rate
  const rSol=d.rate_sol_hr||0,rUsd=rSol*(d.sol_price||0);
  $('rate').textContent='$'+fmt(rUsd,2)+'/hr';
  $('proj').textContent='$'+(rUsd*24).toFixed(0)+'/day';

  // Header
  const m=d.mode||'SIM';
  $('mode').textContent=m;$('mode').className='badge badge-'+(m==='LIVE'?'live':'sim');
  const ms=d.market_state||'WARM';
  $('market').textContent=ms;$('market').className='badge badge-'+ms.toLowerCase();
  $('session').textContent='S#'+(d.session_number||'?');
  $('uptime').textContent=d.uptime||'--:--:--';
  $('scanned').textContent=(d.tokens_found||0).toLocaleString()+' scanned';

  // Stats
  const t=d.trades_today||{};
  $('wr').textContent=(t.win_rate||0)+'%';
  $('wr').className=((t.win_rate||0)>=25?'green':'yellow');
  $('wl').textContent=(t.wins||0)+'W/'+(t.losses||0)+'L';
  $('tok').textContent=(d.tokens_found||0).toLocaleString();
  $('nopen').textContent=(d.positions||[]).length;
  $('tpm').textContent=(d.trades_per_hour||0).toFixed(0);

  // AI
  const ai=d.ai_status||{};
  $('ai-name').textContent=ai.engine||'?';
  $('ai-ms').textContent=(ai.last_latency_ms||0).toFixed(0)+'ms';
  $('ai-calls').textContent=(ai.calls_today||0).toLocaleString();
  $('ai-last').textContent=ai.last_decision||'none';
  $('ai-bar').style.width=((ai.calls_today||0)/(ai.calls_limit||14400)*100)+'%';
  $('ai-dot').className=(ai.status==='OK'||ai.status==='INIT')?'dot-on':'dot-off';

  // ── Positions ─────────────────────────────────────────────────────
  const pos=d.positions||[];
  const curNames=new Set(pos.map(p=>p.name));
  $('pos-n').textContent=pos.length;

  // Detect new positions (glow) and closed positions (toast)
  const newNames=new Set([...curNames].filter(n=>!prevPositionNames.has(n)));
  const closedNames=[...prevPositionNames].filter(n=>!curNames.has(n));

  // Toast for closed positions
  const trades=d.recent_trades||[];
  const totalTrades=(d.trades_today||{}).total||0;
  if(totalTrades>prevTradeCount && prevTradeCount>0){
    // Find the most recent trade(s) that are new
    const newCount=totalTrades-prevTradeCount;
    trades.slice(0,Math.min(newCount,3)).forEach(tr=>{
      const win=tr.pnl>=0;
      const msg=esc(tr.name)+' '+fmt(tr.pnl)+' SOL '+esc(tr.exit_reason||'')+(tr.held?' ('+heldStr(tr.held)+')':'');
      showToast(msg,win);
    });
  }
  prevTradeCount=totalTrades;
  prevPositionNames=curNames;

  // Empty state
  if(pos.length===0){
    $('pos-empty').style.display='block';
    $('empty-tok').textContent=(d.tokens_found||0).toLocaleString();
    $('ptbody').innerHTML='';
    $('pos-cards-container').innerHTML='';
  }else{
    $('pos-empty').style.display='none';

    // Desktop table
    $('ptbody').innerHTML=pos.map(p=>{
      const pc=p.pnl_pct||0,pk=p.peak_pct||0,atr=p.atr||5,trail=p.trail_pct||60;
      const sc=SC[p.strategy]||'#666';
      const isNew=newNames.has(p.name)?'class="new-pos"':'';
      return '<tr '+isNew+'>'+
        '<td><b>'+esc(p.name||'?')+'</b></td>'+
        '<td style="color:'+sc+'">'+esc(p.strategy||'?')+'</td>'+
        '<td class="'+(pc>=0?'green':'red')+'">'+(pc>=0?'+':'')+pc.toFixed(1)+'%</td>'+
        '<td class="dim">'+(pk>=0?'+':'')+pk.toFixed(1)+'%</td>'+
        '<td>'+heatHtml(p)+'</td>'+
        dirArrow(p)+
        atrCell(atr)+
        trailCell(trail)+
        '<td class="dim">'+heldStr(p.held_seconds||0)+'</td></tr>';
    }).join('');

    // Mobile cards
    $('pos-cards-container').innerHTML=pos.map(p=>{
      const pc=p.pnl_pct||0,pk=p.peak_pct||0,atr=p.atr||5,trail=p.trail_pct||60;
      const sc=SC[p.strategy]||'#666';
      const dir=p.price_direction==='UP'?'<span class="green">&uarr;</span>':
                p.price_direction==='DOWN'?'<span class="red">&darr;</span>':'<span class="dim">&rarr;</span>';
      return '<div class="pos-card">'+
        '<div class="pos-card-head"><b>'+esc(p.name)+'</b> <span style="color:'+sc+'">'+p.strategy+'</span></div>'+
        '<div class="pos-card-row"><span class="'+(pc>=0?'green':'red')+'" style="font-size:18px;font-weight:bold">'+(pc>=0?'+':'')+pc.toFixed(1)+'%</span>'+
        '<span class="dim">peak '+(pk>=0?'+':'')+pk.toFixed(1)+'%</span></div>'+
        '<div class="pos-card-row"><span>'+heatHtml(p)+'</span> '+dir+' <span class="dim">'+p.price_source+'</span></div>'+
        '<div class="pos-card-row"><span class="dim">ATR:'+atr.toFixed(1)+' Trail:'+trail+'%</span> <span class="dim">'+heldStr(p.held_seconds||0)+'</span></div></div>';
    }).join('');
  }

  // ── Trades feed (with ATR in exit reasons) ────────────────────────
  const recentTrades=trades.slice().reverse().slice(0,20);
  $('feed').innerHTML=recentTrades.map(tr=>{
    const c=tr.pnl>=0?'green':'red';
    const reason=esc(tr.exit_reason||'');
    return '<div class="trade"><span>'+esc(tr.name)+' <span class="dim">'+esc(tr.strategy)+'</span></span>'+
           '<span class="'+c+'">'+fmt(tr.pnl)+' <span class="dim">'+reason+'</span></span></div>';
  }).join('');

  // ── Strategy breakdown (P&L per strategy) ─────────────────────────
  const st=d.strategies||{};
  $('strats').innerHTML=Object.entries(st).map(([k,v])=>{
    const c=SC[k]||'#666';
    const pnl=v.pnl||0;
    const pnlUsd=pnl*(d.sol_price||0);
    return '<div class="strat-card">'+
      '<b style="color:'+c+'">'+(pnl>=0?'+':'')+pnl.toFixed(4)+'</b>'+
      '<div class="dim" style="font-size:10px">$'+(pnlUsd>=0?'+':'')+pnlUsd.toFixed(2)+'</div>'+
      '<span>'+k+'</span><br>'+
      '<span class="dim">'+(v.trades||0)+' trades &middot; '+(v.wr||0)+'% &middot; '+(v.open||0)+' open</span></div>';
  }).join('');

  // Loss budget
  const lu=d.daily_loss_used||0,ll=d.daily_loss_limit||1.2;
  const lp=Math.min(100,lu/ll*100);
  $('loss-fill').style.width=lp+'%';
  $('loss-txt').textContent=lu.toFixed(3)+' / '+ll+' SOL ('+lp.toFixed(0)+'%)';

  // Errors
  const errs=d.errors_last_hour||[];
  $('errors').innerHTML=errs.length?errs.map(e=>'<div class="err">'+esc(e)+'</div>').join(''):'<div class="dim" style="font-size:11px">No errors</div>';

  // Chart
  const hist=d.balance_history||[];
  if(hist.length>0){
    chart.data.labels=hist.map(h=>h.time);
    chart.data.datasets[0].data=hist.map(h=>h.balance);
    chart.data.datasets[1].data=hist.map(()=>d.starting_balance||5.0);
    chart.update('none');
  }
}

connect();
</script>
</body>
</html>"""


@app.get("/")
async def home():
    return HTMLResponse(HTML)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(get_data())
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


if __name__ == "__main__":
    print("Dashboard starting at http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
