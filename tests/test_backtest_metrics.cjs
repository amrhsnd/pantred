const test=require('node:test');
const assert=require('node:assert/strict');
const {summarize,rank}=require('../web/backtest_metrics.js');

test('summary reconciles closed net, open costs, funding and denominators',()=>{
  const run={degree:68,history:30,invalid:3,orders:[
    {fill:1,status:'Win',gross:12,fees:2,funding:1,pnl:11},
    {fill:2,status:'Loss',gross:-5,fees:1,funding:-.5,pnl:-6.5,ambiguous:true},
    {fill:3,status:'Flat',gross:1,fees:1,funding:0,pnl:0},
    {fill:4,status:'Open',gross:null,fees:.2,funding:-.1,pnl:null,funding_ambiguous:true},
    {fill:null,status:'Expired',gross:null,fees:0,funding:0,pnl:null},
  ]};
  const row=summarize(run,'binance-futures');
  assert.equal(row.orders,5);assert.equal(row.filled,4);assert.equal(row.closed,3);
  assert.equal(row.average_net,1.5);assert.equal(row.win_rate,100/3);
  assert.equal(row.profit_factor,11/6.5);assert.ok(Math.abs(row.net-4.2)<1e-12);
  assert.equal(row.ambiguous,1);assert.equal(row.funding_ambiguous,1);
  assert.equal(row.expired,1);assert.equal(row.invalid,3);
});

test('unmodeled funding is missing rather than an observed zero',()=>{
  const run={degree:68,history:30,invalid:0,orders:[]};
  assert.equal(summarize(run,'binance').funding,null);
  assert.equal(summarize(run,'hyperliquid').funding,null);
  assert.equal(summarize(run,'hyperliquid').ambiguous,null);
  assert.equal(summarize(run,'binance-futures').funding,0);
});

test('no-trade zero cannot outrank a losing strategy',()=>{
  const rows=[{degree:68,history:30,closed:0,net:0},{degree:250,history:10,closed:4,net:-5}];
  const result=rank(rows,'net');
  assert.equal(result[0].rank,null);assert.equal(result[0].net,0);
  assert.equal(result[1].rank,1);
});

test('costs rank ascending, profits descending, with stable ties',()=>{
  const rows=[{degree:68,history:30,closed:5,fees:10,net:-10},
              {degree:100,history:30,closed:5,fees:4,net:-4},
              {degree:168,history:30,closed:5,fees:4,net:-4}];
  assert.deepEqual(rank(rows,'fees').map(r=>r.rank),[3,1,1]);
  assert.deepEqual(rank(rows,'net').map(r=>r.rank),[3,1,1]);
  assert.equal(rank(rows,'net')[0].strength,0);
  assert.equal(rank(rows,'net')[1].strength,1);
});

test('profit factor distinguishes infinity, undefined and zero',()=>{
  const row=pnl=>summarize({degree:68,history:30,invalid:0,orders:[
    {fill:1,status:pnl>0?'Win':pnl<0?'Loss':'Flat',gross:pnl,fees:0,pnl}
  ]},'binance');
  assert.equal(row(2).profit_factor,Infinity);
  assert.equal(row(0).profit_factor,null);
  assert.equal(row(-2).profit_factor,0);
  const result=rank([{...row(2),degree:68},{...row(-2),degree:100}],'profit_factor');
  assert.deepEqual(result.map(r=>r.rank),[1,2]);
});

test('missing values and all-flat metrics do not create false leaders',()=>{
  const rows=[{degree:68,history:30,closed:3,funding:null},
              {degree:100,history:30,closed:3,funding:null}];
  assert.ok(rank(rows,'funding').every(r=>r.rank===null));
  const tied=rank(rows.map(r=>({...r,funding:0})),'funding');
  assert.ok(tied.every(r=>r.rank===1&&r.strength===.5));
});
