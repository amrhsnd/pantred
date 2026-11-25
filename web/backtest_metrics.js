/* Shared calculations for the settings comparison; usable in the browser and Node. */
(function (root) {
  'use strict';
  const definitions = [
    {key:'net', label:'Net P&L', unit:'money', direction:'desc', description:'Gross P&L minus trading fees plus modeled funding; includes incurred costs on open positions.'},
    {key:'average_net', label:'Average net per closed trade', unit:'money', direction:'desc', description:'Total net P&L of closed trades divided by closed trades.'},
    {key:'win_rate', label:'Net win rate', unit:'percent', direction:'desc', description:'Profitable closed trades divided by all closed trades, including flat trades.'},
    {key:'profit_factor', label:'Profit factor', unit:'ratio', direction:'desc', description:'Positive closed-trade net P&L divided by the absolute sum of negative closed-trade net P&L.'},
    {key:'gross', label:'Gross P&L', unit:'money', direction:'desc', description:'Closed-trade P&L before trading fees and funding.'},
    {key:'fees', label:'Trading fees', unit:'money', direction:'asc', description:'All incurred trading fees. Lower costs can also reflect fewer filled trades.'},
    {key:'funding', label:'Funding cash flow', unit:'money', direction:'desc', description:'Modeled historical funding receipts minus payments. Available for Binance futures only.'},
    {key:'orders', label:'Orders', unit:'count', direction:'desc', description:'All valid generated orders; a larger count is activity, not profitability.'},
    {key:'filled', label:'Filled orders', unit:'count', direction:'desc', description:'Orders that filled, including positions still open.'},
    {key:'closed', label:'Closed trades', unit:'count', direction:'desc', description:'Filled trades that exited before the data ended.'},
    {key:'wins', label:'Wins', unit:'count', direction:'desc', description:'Closed trades with positive net P&L after fees and modeled funding.'},
    {key:'losses', label:'Losses', unit:'count', direction:'asc', description:'Closed trades with negative net P&L.'},
    {key:'flat', label:'Flat trades', unit:'count', direction:'desc', description:'Closed trades with zero net P&L.'},
    {key:'expired', label:'Expired orders', unit:'count', direction:'asc', description:'Orders that reached their entry expiration without filling.'},
    {key:'pending', label:'Pending orders', unit:'count', direction:'asc', description:'Unfilled orders whose entry expiration extends beyond the data end.'},
    {key:'open', label:'Open positions', unit:'count', direction:'asc', description:'Filled positions without an exit before the data ended; unrealized P&L is excluded.'},
    {key:'invalid', label:'Invalid setups', unit:'count', direction:'asc', description:'Candidate signals skipped because their entry, stop and target levels were invalid.'},
    {key:'ambiguous', label:'Intrabar ambiguity', unit:'count', direction:'asc', description:'Orders affected by unknown within-minute fill/exit ordering; candle replays only.'},
    {key:'funding_ambiguous', label:'Funding timing ambiguity', unit:'count', direction:'asc', description:'Orders with funding settlements in a possible entry/exit minute; Binance futures only.'},
  ];
  function summarize(run, market) {
    const orders=run.orders, count=status=>orders.filter(o=>o.status===status).length;
    const closedOrders=orders.filter(o=>o.pnl!=null);
    const closed=closedOrders.length;
    const gains=closedOrders.reduce((sum,o)=>sum+Math.max(0,o.pnl),0);
    const losses=closedOrders.reduce((sum,o)=>sum+Math.max(0,-o.pnl),0);
    const gross=orders.reduce((sum,o)=>sum+(o.gross??0),0);
    const fees=orders.reduce((sum,o)=>sum+o.fees,0);
    const funding=market==='binance-futures'?orders.reduce((sum,o)=>sum+(o.funding??0),0):null;
    return {
      threshold:run.threshold, atr_period:run.atr_period, orders:orders.length,
      filled:orders.filter(o=>o.fill!=null).length, closed,
      wins:count('Win'), losses:count('Loss'), flat:count('Flat'),
      expired:count('Expired'), pending:count('Pending'), open:count('Open'), invalid:run.invalid,
      gross, fees, funding, net:gross-fees+(funding??0),
      average_net:closed?closedOrders.reduce((sum,o)=>sum+o.pnl,0)/closed:null,
      win_rate:closed?100*count('Win')/closed:null,
      profit_factor:losses?gains/losses:gains?Infinity:null,
      ambiguous:market.startsWith('binance')?orders.filter(o=>o.ambiguous).length:null,
      funding_ambiguous:market==='binance-futures'?orders.filter(o=>o.funding_ambiguous).length:null,
    };
  }
  function rank(rows, key) {
    const setting=row=>row.atr_period??row.threshold;
    const definition=definitions.find(d=>d.key===key);
    if(!definition)throw new Error('Unknown comparison metric: '+key);
    const eligible=rows.filter(r=>r.closed>0&&r[key]!=null);
    eligible.sort((a,b)=>a[key]===b[key]?setting(a)-setting(b):
      (a[key]<b[key]?-1:1)*(definition.direction==='asc'?1:-1));
    const ranks=new Map();
    let previous,position=0;
    eligible.forEach((row,index)=>{
      if(index===0||row[key]!==previous)position=index+1;
      previous=row[key];ranks.set(setting(row),position);
    });
    const lastRank=Math.max(1,...ranks.values());
    return rows.map(row=>{
      const position=ranks.get(setting(row))??null;
      return {...row,rank:position,strength:position==null?null:lastRank===1?.5:1-(position-1)/(lastRank-1)};
    });
  }
  const api={definitions,summarize,rank};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.PantredMetrics=api;
})(globalThis);
