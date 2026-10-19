const $ = id => document.getElementById(id);
const number = value => value === null || value === undefined || !Number.isFinite(Number(value)) ? '--' : Number(value).toLocaleString('en-US', {maximumFractionDigits: 5});
const compact = value => value === null || value === undefined ? '--' : Number(value).toLocaleString('en-US', {notation:'compact',maximumFractionDigits:2});
const utc = value => new Date(value).toISOString().slice(11, 19);
let current = null, busy = false, actionBusy = false;
const error = message => { $('error').textContent = message || ''; $('error').hidden = !message; };

function table(id, rows, columns) {
  const target = $(id); target.replaceChildren();
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const column of columns) {
      const td = document.createElement('td'); td.textContent = column(row); tr.appendChild(td);
    }
    target.appendChild(tr);
  }
}

function draw(data) {
  const ha = document.querySelector('input[name="style"]:checked').value === 'ha';
  let previousOpen, previousClose;
  const candles = data.candles.map((row, i) => {
    const c = Object.fromEntries(['open','high','low','close','volume'].map(k => [k, Number(row[k])]));
    if (ha) {
      const close = (c.open + c.high + c.low + c.close) / 4;
      const open = i ? (previousOpen + previousClose) / 2 : (c.open + c.close) / 2;
      c.high = Math.max(c.high, open, close); c.low = Math.min(c.low, open, close);
      c.open = open; c.close = close; previousOpen = open; previousClose = close;
    }
    return {...c, time: new Date(row.open_ms).toISOString()};
  });
  const x = candles.map(c => c.time);
  const traces = [{type:'candlestick', x, open:candles.map(c=>c.open), high:candles.map(c=>c.high), low:candles.map(c=>c.low), close:candles.map(c=>c.close), name:ha?'Heikin Ashi':'OHLC', increasing:{line:{color:'#008a75'}}, decreasing:{line:{color:'#ce4a5b'}}},
    {type:'bar', x, y:candles.map(c=>c.volume), yaxis:'y2', name:'Volume', marker:{color:candles.map(c=>c.close>=c.open?'#b0dcd4':'#edc1c8')}}];
  Plotly.react('chart', traces, {margin:{l:60,r:20,t:15,b:55}, paper_bgcolor:'#fff',plot_bgcolor:'#fff',font:{family:'system-ui',size:11,color:'#6b7880'},showlegend:false,
    xaxis:{type:'date',rangeslider:{visible:false},showgrid:false,title:{text:'UTC',standoff:15},anchor:'y2',nticks:5,tickformat:'%H:%M',hoverformat:'%d %b %Y %H:%M UTC'},
    yaxis:{domain:[.24,1],gridcolor:'#edf1f3',fixedrange:false},yaxis2:{domain:[0,.16],gridcolor:'#edf1f3',title:{text:'Vol.'}},
    uirevision:`${data.symbol}-${data.interval}-${$('window').value}-${ha}`, dragmode:'pan'},
    {responsive:true,displayModeBar:false,scrollZoom:true});
  $('empty').hidden = !!candles.length;
  $('empty').textContent = data.process.running ? 'Loading market history...' : 'No recorded data yet.';
  $('chart-title').textContent = `${data.symbol} / ${data.interval}${ha?' / Heikin Ashi':''}`;
  const last = data.candles.at(-1);
  $('candle-status').textContent = last ? `${candles.length} candles / ${last.close_ms >= data.now_ms ? 'Last candle forming' : 'Stored history'}` : 'No recorded candles';
}

function render(data) {
  current = data;
  const running = data.process.running;
  $('record').disabled = running || actionBusy; $('stop').disabled = !running || actionBusy;
  $('recorder-state').textContent = running ? 'Recorder running' : data.process.exit_code ? 'Recorder error' : 'Recorder stopped';
  if(data.process.exit_code && !running) error('The recorder exited with an error. See Collector activity and data/hyperliquid/recorder.log.');
  const ctx = data.context?.data.ctx || {};
  $('mark').textContent = number(ctx.markPx); $('oracle').textContent = number(ctx.oraclePx);
  $('funding').textContent = ctx.funding === undefined ? '--' : `${number(Number(ctx.funding)*100)}%`;
  $('oi').textContent = compact(ctx.openInterest); $('oi').title = number(ctx.openInterest); $('oi-unit').textContent = data.symbol;
  $('volume').textContent = ctx.dayNtlVlm === undefined ? '--' : `$${compact(ctx.dayNtlVlm)}`;
  $('volume').title = number(ctx.dayNtlVlm);
  const age = data.context ? Math.max(0,Math.round((data.now_ms-data.context.received_ms)/1000)) : null;
  $('freshness').textContent = age === null ? 'Waiting for market observations' : `Context: ${age}s ago${age>30?' / stale':''}`;
  const levels = data.book?.data.levels || [[],[]];
  $('spread').textContent = levels[0][0] && levels[1][0] ? number(Number(levels[1][0].px)-Number(levels[0][0].px)) : '--';
  $('book-age').textContent = data.book ? `${Math.max(0,Math.round((data.now_ms-data.book.received_ms)/1000))}s ago` : 'No observations';
  table('bids',levels[0].slice(0,8),[r=>number(r.px),r=>number(r.sz)]);
  table('asks',levels[1].slice(0,8),[r=>number(r.px),r=>number(r.sz)]);
  table('trades',data.trades,[r=>utc(r.event_ms),r=>r.side==='B'?'Buy':'Sell',r=>number(r.price),r=>number(r.size)]);
  $('events').replaceChildren();
  for(const event of data.events) {
    const li=document.createElement('li'), time=document.createElement('time'), kind=document.createElement('span'), detail=document.createElement('span');
    time.textContent=utc(event.time_ms); kind.textContent=event.kind; detail.textContent=event.details;
    li.append(time,kind,detail); $('events').appendChild(li);
  }
  draw(data);
}

async function refresh() {
  if(busy) return;
  busy=true;
  const symbol=$('symbol').value, interval=$('interval').value, limit=$('window').value;
  try {
    const response=await fetch(`/api/monitor?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=${limit}`);
    if(!response.ok) throw new Error('Could not read recorded data.');
    const data=await response.json();
    if(symbol===$('symbol').value && interval===$('interval').value && limit===$('window').value) render(data);
  } catch(e) { error(e.message); } finally {busy=false;}
}
async function control(action) {
  actionBusy=true; $('record').disabled=true; $('stop').disabled=true; error('');
  try {
    const response=await fetch('/api/recorder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})});
    const data=await response.json(); if(!response.ok) throw new Error(data.error || 'Recorder request failed.');
  } catch(e) {error(e.message);} finally {actionBusy=false; await refresh();}
}
$('record').onclick=()=>control('start'); $('stop').onclick=()=>control('stop');
for(const id of ['symbol','interval','window']) $(id).onchange=refresh;
document.querySelectorAll('input[name="style"]').forEach(input=>input.onchange=()=>current&&draw(current));
refresh(); setInterval(refresh, 2000);
window.addEventListener('resize',()=>Plotly.Plots.resize('chart'));
