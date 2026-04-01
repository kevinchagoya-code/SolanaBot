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
.header{background:#111119;border-bottom:1px solid #1e1e2e;padding:10px 20px;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:18px;color:#7c3aed;letter-spacing:1px}
.header-right{display:flex;align-items:center;gap:12px}
.badge{padding:3px 10px;border-radius:4px;font-weight:bold;font-size:11px;letter-spacing:1px}
.badge-sim{background:#1e3a5f;color:#60a5fa}
.badge-live{background:#3f1e1e;color:#f87171;animation:pulse 2s infinite}
.badge-hot{background:#3f1e1e;color:#f87171}
.badge-warm{background:#3f2e1a;color:#eab308}
.badge-slow{background:#1a2e3f;color:#60a5fa}
.badge-dead{background:#1e1e1e;color:#666}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
.connected{width:8px;height:8px;border-radius:50%;background:#22c55e;display:inline-block}
.disconnected{width:8px;height:8px;border-radius:50%;background:#ef4444;display:inline-block}

/* ── GRID ── */
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:10px;padding:12px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.c1{grid-column:span 1}.c2{grid-column:span 2}.c3{grid-column:span 3}
.c4{grid-column:span 4}.c5{grid-column:span 5}.c6{grid-column:span 6}
.c7{grid-column:span 7}.c8{grid-column:span 8}.c9{grid-column:span 9}
.c12{grid-column:span 12}
@media(max-width:900px){.c1,.c2,.c3,.c4,.c5,.c6,.c7,.c8,.c9,.c12{grid-column:span 1}}

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

/* ── SCROLLBAR ── */
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:#0a0a0f}::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
</style>
</head>
<body>

<div class="header">
  <h1>&#9889; SOLANA BOT</h1>
  <div class="header-right">
    <span id="ws-dot" class="disconnected" title="WebSocket"></span>
    <span id="uptime" class="dim">--:--:--</span>
    <span id="mode" class="badge badge-sim">SIM</span>
    <span id="market" class="badge badge-warm">WARM</span>
    <span id="session" class="dim">S#-</span>
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
      <span id="ai-dot" class="connected"></span>
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
    <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>Token</th><th>Strat</th><th>Score</th><th>P&amp;L</th>
        <th>Heat</th><th>Dir</th><th>ATR</th><th>Held</th>
      </tr></thead>
      <tbody id="ptbody"></tbody>
    </table>
    </div>
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
const stratColors={HFT:'#eab308',SCALP:'#e0e0e0',GRAD_SNIPE:'#22c55e',SWING:'#22d3ee',ESTAB:'#a78bfa',MOONBAG:'#f59e0b'};

function atrCell(p){
  const a=p.atr||0;
  const c=a>=10?'red':a>=3?'yellow':'dim';
  return '<td class="'+c+'">'+a.toFixed(1)+'%';
}

function dirArrow(p){
  const d=p.price_direction||'FLAT';
  const cu=p.consecutive_up||0, cd=p.consecutive_down||0;
  const acc=p.accelerating?'!':'';
  if(d==='UP'){
    const arrows='↑'.repeat(Math.min(cu||1,4));
    return '<td class="green">'+arrows+acc+'</td>';
  }else if(d==='DOWN'){
    const arrows='↓'.repeat(Math.min(cd||1,4));
    return '<td class="red">'+arrows+acc+'</td>';
  }
  return '<td class="dim">→</td>';
}

// ── WebSocket ────────────────────────────────────────────────────────
let reconnectTimer;
function connect(){
  const ws=new WebSocket('ws://'+location.host+'/ws');
  ws.onopen=()=>{$('ws-dot').className='connected';clearTimeout(reconnectTimer)};
  ws.onclose=()=>{$('ws-dot').className='disconnected';reconnectTimer=setTimeout(connect,3000)};
  ws.onerror=()=>ws.close();
  ws.onmessage=e=>{
    const d=JSON.parse(e.data);
    if(d.error){$('pnl').textContent=d.error;return}
    update(d);
  };
}

function update(d){
  // P&L
  const pu=d.pnl_usd||0, ps=d.pnl_sol||0;
  $('pnl').textContent='$'+fmt(pu,2);
  $('pnl').className='pnl-big '+cls(pu);
  $('pnl-sol').textContent=fmt(ps)+' SOL';
  $('bal').textContent=(d.balance||0).toFixed(3);
  $('sol-px').textContent=(d.sol_price||0).toFixed(2);

  // Rate
  const rSol=d.rate_sol_hr||0, rUsd=rSol*(d.sol_price||0);
  $('rate').textContent='$'+fmt(rUsd,2)+'/hr';
  $('proj').textContent='$'+(rUsd*24).toFixed(0)+'/day';

  // Header
  const m=d.mode||'SIM';
  $('mode').textContent=m;$('mode').className='badge badge-'+(m==='LIVE'?'live':'sim');
  const ms=d.market_state||'WARM';
  $('market').textContent=ms;$('market').className='badge badge-'+ms.toLowerCase();
  $('session').textContent='S#'+(d.session_number||'?');
  $('uptime').textContent=d.uptime||'--:--:--';

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
  const aiOk=ai.status==='OK'||ai.status==='INIT';
  $('ai-dot').className=aiOk?'connected':'disconnected';

  // Positions
  const pos=d.positions||[];
  $('pos-n').textContent=pos.length;
  $('ptbody').innerHTML=pos.map(p=>{
    const pc=p.pnl_pct||0, hc=p.heat>=80?'h-rocket':p.heat>=60?'h-heat':p.heat>=40?'h-warm':'h-cold';
    const hw=Math.min(100,p.heat||0)+'%';
    const sc=stratColors[p.strategy]||'#666';
    return '<tr>'+
      '<td><b>'+esc(p.name||'?')+'</b></td>'+
      '<td style="color:'+sc+'">'+esc(p.strategy||'?')+'</td>'+
      '<td>'+(p.score||0)+'</td>'+
      '<td class="'+(pc>=0?'green':'red')+'">'+(pc>=0?'+':'')+pc.toFixed(1)+'%</td>'+
      '<td><div class="hbar"><div class="hfill '+hc+'" style="width:'+hw+'"></div></div> '+(p.heat||0).toFixed(0)+'</td>'+
      dirArrow(p)+'</td>'+
      atrCell(p)+'</td>'+
      '<td class="dim">'+heldStr(p.held_seconds||0)+'</td></tr>';
  }).join('');

  // Trades feed
  const trades=(d.recent_trades||[]).slice().reverse().slice(0,20);
  $('feed').innerHTML=trades.map(t=>{
    const c=t.pnl>=0?'green':'red';
    return '<div class="trade"><span>'+esc(t.name)+' <span class="dim">'+esc(t.strategy)+'</span></span>'+
           '<span class="'+c+'">'+fmt(t.pnl)+' <span class="dim">'+esc(t.exit_reason||'')+'</span></span></div>';
  }).join('');

  // Strategy breakdown
  const st=d.strategies||{};
  $('strats').innerHTML=Object.entries(st).map(([k,v])=>{
    const c=stratColors[k]||'#666';
    return '<div class="strat-card"><b style="color:'+c+'">'+(v.pnl||0).toFixed(3)+'</b>'+
           '<span>'+k+'</span><br><span class="dim">'+(v.trades||0)+' trades &middot; '+(v.wr||0)+'% WR &middot; '+(v.open||0)+' open</span></div>';
  }).join('');

  // Loss budget
  const lu=d.daily_loss_used||0, ll=d.daily_loss_limit||1.2;
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

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

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
