'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => Number(value || 0).toLocaleString('en-IN', {maximumFractionDigits: 0});
const money = value => '₹' + number(value);
const compact = value => Math.abs(value)>=1e7 ? '₹'+(value/1e7).toFixed(2)+'Cr' : Math.abs(value)>=1e5 ? '₹'+(value/1e5).toFixed(1)+'L' : money(value);
const colors = ['#39d4b1','#82a5ff','#e9ba73','#af8cde','#ed8e9a','#70c8d8'];
const state = {page:'overview', datasets:[], active:0, analytics:null, chats:new Map(), chatVersion:0, pending:null, sequence:0, user:null};

async function api(action, extra={}) {
  const dataset=state.datasets[state.active];
  const filters={start:$('start').value,end:$('end').value,region:$('region').value?[$('region').value]:[],category:$('category').value?[$('category').value]:[],store_id:$('store').value?[$('store').value]:[]};
  const body={action, ...extra};
  if (!['demo','upload','health','login','logout','session'].includes(action)) Object.assign(body,{rows:dataset?.demo?null:dataset?.rows, dataset_name:dataset?.name, filters});
  const payload=JSON.stringify(body);
  if(new TextEncoder().encode(payload).length>4000000) throw new Error('This dataset exceeds the web request limit. Use a smaller dataset.');
  const response=await fetch('/api/index',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:payload});
  if(response.status===401){window.location.replace('/login.html');throw new Error('Your session has expired. Please sign in again.');}
  let result;
  try { result=await response.json(); } catch { throw new Error('The server did not return a valid response. Please retry in a moment.'); }
  if(!response.ok) throw new Error(result.error || `Server error ${response.status}`);
  return result;
}

function notify(message,success=false){$('notice').textContent=message;$('notice').className=success?'success':'';$('notice').hidden=false;}
function busy(yes){$('loading').hidden=!yes;}

const dbPromise = new Promise((resolve,reject)=>{
  const request=indexedDB.open('retailmind-web',1);
  request.onupgradeneeded=()=>request.result.createObjectStore('datasets',{keyPath:'id'});
  request.onsuccess=()=>resolve(request.result);
  request.onerror=()=>reject(new Error('Browser storage is unavailable. Demo data still works.'));
});
async function savedDatasets(){const db=await dbPromise;return new Promise((resolve,reject)=>{const r=db.transaction('datasets').objectStore('datasets').getAll();r.onsuccess=()=>resolve(r.result.filter(d=>d.owner===state.user.id));r.onerror=()=>reject(r.error);});}
async function saveDataset(dataset){dataset.owner=state.user.id;const db=await dbPromise;return new Promise((resolve,reject)=>{const transaction=db.transaction('datasets','readwrite');transaction.objectStore('datasets').put(dataset);transaction.oncomplete=resolve;transaction.onerror=()=>reject(new Error('Could not save to browser storage. Free space and retry.'));});}

function setDataset(){
  const dataset=state.datasets[state.active];
  $('dataset').innerHTML=state.datasets.map((d,i)=>`<option value="${i}">${esc(d.name)}</option>`).join('');
  $('dataset').value=state.active;
  for(const [id,key,label] of [['region','region','regions'],['category','category','categories'],['store','store_id','stores']]){
    $(id).innerHTML=`<option value="">All ${label}</option>`+[...new Set(dataset.rows.map(r=>r[key]))].sort().map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
  }
  const dates=dataset.rows.map(r=>r.date).sort();
  $('start').value=dates[0];$('end').value=dates.at(-1);
  for(const id of ['start','end']){$(id).min=dates[0];$(id).max=dates.at(-1);}
  state.chatVersion++;
}

function table(rows,limit=100){
  if(!rows?.length)return '<div class="empty">No matching records.</div>';
  const keys=Object.keys(rows[0]);
  return `<div class="table-wrap"><table><thead><tr>${keys.map(k=>`<th>${esc(k.replaceAll('_',' ').toUpperCase())}</th>`).join('')}</tr></thead><tbody>${rows.slice(0,limit).map(row=>`<tr>${keys.map(k=>`<td>${esc(typeof row[k]==='number'?Number(row[k].toFixed(2)).toLocaleString('en-IN'):row[k]??'—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${rows.length>limit?`<p class="caption">Showing ${limit} of ${number(rows.length)} rows.</p>`:''}`;
}
function metric(label,value,note,icon='◈'){return `<div class="metric"><span class="icon">${icon}</span><label>${esc(label)}</label><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`;}
function card(title,subtitle,content){return `<article class="card"><h2>${esc(title)}</h2><div class="caption">${esc(subtitle)}</div>${content}</article>`;}
function bars(rows,key,value,unit=money,limit=8){
  const max=Math.max(...rows.map(r=>Math.abs(r[value])),1);
  return `<div class="bars">${rows.slice(0,limit).map((r,i)=>`<div class="bar-row"><span class="bar-name" title="${esc(r[key])}">${esc(r[key])}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.max(0,Math.abs(r[value])/max*100)}%;background:${colors[i%colors.length]}"></div></div><span class="bar-value">${esc(unit(r[value]))}</span></div>`).join('')}</div>`;
}
function lineChart(rows){
  if(!rows.length)return '<div class="empty">No time-series data.</div>';
  const w=650,h=235,left=66,right=15,top=15,bottom=34,max=Math.max(...rows.map(r=>r.total_sales),1);
  const x=i=>left+(w-left-right)*i/Math.max(rows.length-1,1),y=v=>h-bottom-(h-top-bottom)*v/max;
  const points=rows.map((r,i)=>`${x(i)},${y(r.total_sales)}`).join(' ');
  let grid='';for(let i=0;i<4;i++){const v=max*i/3;grid+=`<line x1="${left}" y1="${y(v)}" x2="${w-right}" y2="${y(v)}" stroke="#26354b" stroke-dasharray="3 5"/><text x="${left-10}" y="${y(v)+4}" text-anchor="end" fill="#7186a2" font-size="10">${esc(compact(v))}</text>`;}
  const marks=[...new Set([0,Math.floor(rows.length/3),Math.floor(rows.length*2/3),rows.length-1])];
  return `<div class="chart"><svg role="img" aria-label="Revenue time series" viewBox="0 0 ${w} ${h}"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#37cbae" stop-opacity=".22"/><stop offset="1" stop-color="#37cbae" stop-opacity="0"/></linearGradient></defs>${grid}<polygon points="${left},${h-bottom} ${points} ${x(rows.length-1)},${h-bottom}" fill="url(#area)"/><polyline fill="none" stroke="#42d6b5" stroke-width="2.5" stroke-linejoin="round" points="${points}"/>${rows.map((r,i)=>`<circle cx="${x(i)}" cy="${y(r.total_sales)}" r="4" fill="#3bd7b5" opacity=".6"><title>${esc(r.date.slice(0,10))}: ${money(r.total_sales)}</title></circle>`).join('')}${marks.map(i=>`<text x="${x(i)}" y="${h-8}" text-anchor="middle" fill="#7186a2" font-size="10">${esc(new Date(rows[i].date).toLocaleDateString('en-IN',{month:'short',day:'numeric'}))}</text>`).join('')}</svg></div>`;
}
function donut(rows){
  const total=rows.reduce((s,r)=>s+r.total_sales,0);let offset=0;
  const circles=rows.map((r,i)=>{const length=total?r.total_sales/total*100:0;const out=`<circle cx="130" cy="110" r="75" fill="none" stroke="${colors[i%colors.length]}" stroke-width="22" pathLength="100" stroke-dasharray="${length} ${100-length}" stroke-dashoffset="${-offset}" transform="rotate(-90 130 110)"><title>${esc(r.category)}: ${money(r.total_sales)}</title></circle>`;offset+=length;return out;}).join('');
  return `<div class="chart"><svg viewBox="0 0 260 225" role="img" aria-label="Category revenue share">${circles}<text x="130" y="104" text-anchor="middle" fill="#8c9bb3" font-size="10">TOTAL REVENUE</text><text x="130" y="129" text-anchor="middle" fill="#e9f0fa" font-size="22" font-weight="700">${esc(compact(total))}</text></svg></div><div class="legend">${rows.map((r,i)=>`<span><i style="background:${colors[i%colors.length]}"></i>${esc(r.category)}</span>`).join('')}</div>`;
}

function overview(){
  const a=state.analytics,m=a.metrics;
  $('content').innerHTML=`<div class="metrics">${metric('Total revenue',compact(m.Revenue),'Across the selected period','↗')}${metric('Net profit',compact(m.Profit),m['Margin %'].toFixed(1)+'% profit margin','◫')}${metric('Total orders',number(m.Orders),number(m['Units sold'])+' units sold','▤')}${metric('Average order value',money(m['Average order']),'Revenue per distinct transaction','◇')}</div>
  <div class="grid"><article class="card"><div class="card-head"><div><h2>Revenue overview</h2><div class="caption">The rhythm of your retail business</div></div><select id="interval" aria-label="Chart interval"><option value="monthly">Monthly</option><option value="weekly">Weekly</option><option value="daily">Daily</option></select></div><div id="time-chart">${lineChart(a.monthly)}</div></article>${card('Category mix','Where your revenue comes from',donut(a.categories))}</div>
  <div class="grid">${card('Store leaderboard','Revenue across all selected stores',bars(a.stores,'store_id','total_sales',compact))}${card('Performance pulse','Signals worth a closer look',`<div class="pulse"><strong>${m['Margin %'].toFixed(1)}%</strong><span>Profit margin<br>on ${number(a.row_count)} transaction records</span></div><p class="caption">${esc(a.categories[0]?.category)} leads revenue in this selection. Explore product demand and profitability before planning your next move.</p><button class="text-link" id="explore-ask">Ask a question about your data ↗</button>`)}</div>`;
  $('interval').onchange=e=>$('time-chart').innerHTML=lineChart(a[e.target.value]);
  $('explore-ask').onclick=()=>navigate('ask');
}
function products(){
  const a=state.analytics;
  $('content').innerHTML=`<div class="grid equal">${card('Product performance','Best and least selling products by revenue',bars(a.products,'product_name','total_sales',compact,10))}${card('Store comparison','Revenue ranking for selected stores',bars(a.stores,'store_id','total_sales',compact))}</div><div class="grid equal">${card('Category profitability','Calculated net profit',bars(a.category_profit,'category','profit',compact))}${card('Regional profit','Compare your regional footprint',bars(a.regions,'region','profit',compact))}</div><div class="hint warning">Inventory suggestions are demand-based. Stock-on-hand and supplier lead times are unavailable, so stockouts and reorder quantities cannot be calculated.</div><div class="grid equal">${card('High-demand products','Units sold in the current selection',bars(a.demand,'product_name','quantity',number,10))}${card('Product profitability','Profit by product',bars(a.product_profit,'product_name','profit',compact,10))}</div>${card('Product movement','Trailing 30 days vs prior 30 days, anchored to the latest selected transaction. Partial windows can distort comparisons.',table(a.changes))}`;
}
async function customerPage(sequence){
  const a=await api('customers');if(sequence!==state.sequence)return;
  $('content').innerHTML=`<div class="metrics">${metric('Customers',number(a.count),'Distinct customer IDs')}${metric('Repeat customers',number(a.repeat),'More than one transaction')}${metric('Repeat rate',a.repeat_rate.toFixed(1)+'%','Within the selected scope')}${metric('Customer segments',number(new Set(a.rows.map(r=>r.segment)).size),'K-Means clusters')}</div><div class="hint">K-Means uses standardized frequency, spending and recency. Segment IDs are cluster labels, not value rankings. Recency is measured from the latest selected transaction.</div>${card('Customer segments','Spending and purchase frequency',scatter(a.rows))}${card('Customer detail','Purchase frequency, spend, recency and segment',table(a.rows))}`;
}
function scatter(rows){
  const maxX=Math.max(...rows.map(r=>r.orders),1),maxY=Math.max(...rows.map(r=>r.spend),1);
  return `<div class="chart"><svg viewBox="0 0 900 290" role="img" aria-label="Customer spending by purchase frequency"><line x1="60" y1="250" x2="870" y2="250" stroke="#354660"/><line x1="60" y1="15" x2="60" y2="250" stroke="#354660"/>${rows.slice(0,5000).map(r=>`<circle cx="${60+r.orders/maxX*790}" cy="${245-r.spend/maxY*220}" r="4" opacity=".65" fill="${colors[Number(r.segment)%colors.length]}"><title>${esc(r.customer_id)} · ${r.orders} orders · ${money(r.spend)} · Segment ${esc(r.segment)}</title></circle>`).join('')}<text x="450" y="280" text-anchor="middle" fill="#8c9bb3" font-size="12">Purchase frequency · up to ${maxX} orders</text><text x="68" y="14" fill="#8c9bb3" font-size="10">Spend · up to ${esc(compact(maxY))}</text></svg></div>`;
}

function chatKey(){return JSON.stringify([state.active,$('start').value,$('end').value,$('region').value,$('category').value,$('store').value]);}
function askPage(){
  const examples=state.analytics.examples;
  $('content').innerHTML=`<div class="hint">✧ Grounded local intelligence. Answers use all selected records; retrieved examples provide context. Numerical answers are calculated, never estimated by a language model.</div><div class="question-grid">${examples.slice(0,6).map(q=>`<button class="example">${esc(q)} ↗</button>`).join('')}</div><form id="ask-form" class="ask-form"><input id="question" autocomplete="off" maxlength="1000" required placeholder="Ask about sales, profit, products, or stores…" aria-label="Your question"><button class="primary" type="submit">Ask RetailMind ↗</button></form><div class="row"><label>More questions<select id="more-questions"><option value="">Choose a question…</option>${examples.map(q=>`<option>${esc(q)}</option>`).join('')}</select></label><button id="clear-chat" class="secondary">Clear history</button></div><div id="chat-history"></div>`;
  renderChats();
  document.querySelectorAll('.example').forEach(b=>b.onclick=()=>{$('question').value=b.textContent.replace(/ ↗$/,'');$('ask-form').requestSubmit();});
  $('more-questions').onchange=e=>{if(e.target.value){$('question').value=e.target.value;$('question').focus();}};
  $('clear-chat').onclick=()=>{state.chats.set(chatKey(),[]);renderChats();};
  $('ask-form').onsubmit=async e=>{
    e.preventDefault();const question=$('question').value.trim();if(!question)return;
    const key=chatKey();const version=state.sequence;const button=e.target.querySelector('button');button.disabled=true;busy(true);$('notice').hidden=true;
    try{const result=await api('ask',{question});const history=state.chats.get(key)||[];history.push({question,result});state.chats.set(key,history);if(state.page==='ask'&&version===state.sequence){$('question').value='';renderChats();}}
    catch(error){notify(error.message);}finally{button.disabled=false;busy(false);}
  };
}
function renderChats(){
  $('chat-history').innerHTML=(state.chats.get(chatKey())||[]).slice().reverse().map(({question,result:r})=>`<article class="card answer"><h3>✧ ${esc(question)}</h3><p>${esc(r.answer)}</p><div class="caption">${esc(r.scope)}</div><p class="caption">${esc(r.explanation)}</p><div class="action">${esc(r.action)}</div>${table(r.data)}<details><summary>Inspect evidence & calculation</summary><div class="caption">${esc(r.retrieval_mode)}. Retrieved examples are contextual; the table above covers the full calculation scope.</div>${r.sources.map(s=>`<div class="source">${esc(s.text)}<br><small>${esc(Object.entries(s.metadata).map(([k,v])=>k+': '+v).join(' · '))}</small></div>`).join('')}${r.sql?`<pre>${esc(r.sql)}\n${esc(JSON.stringify(r.params))}</pre>`:''}</details></article>`).join('');
}

function dataPage(){
  $('content').innerHTML=`<div class="hint">Datasets are saved in this browser using IndexedDB. Each analysis sends selected data to the Python backend over HTTPS. Uploads are not placed in a shared server database.</div><article class="card"><h2>Bring your retail data</h2><p class="caption">CSV or Excel (.xlsx) · up to 10,000 rows · files up to 2.5 MB</p><div class="upload-zone"><div class="upload-icon">⇧</div><h3>A fresh perspective starts with your data</h3><p>Choose a dataset to validate, clean, and preview.</p><input id="upload" type="file" accept=".csv,.xlsx" aria-label="Choose CSV or Excel dataset"></div><div id="sheet-picker"></div><div class="row"><button id="template" class="secondary">↓ Download CSV template</button></div><details><summary>Required schema and cleaning rules</summary><p>transaction_id, date, store_id, product_id, category, product_name, quantity, unit_price, total_sales, discount, customer_id, region, payment_method, profit</p><p>Discount is a fraction (0.10 = 10%). Exact duplicates are removed. Invalid financial/date rows are rejected; missing descriptive fields become Unknown. No financial values are imputed. Negative profit is accepted.</p></details></article><div id="upload-result"></div><div style="height:20px"></div>${card('Dataset library','Saved datasets are private to this browser',table(state.datasets.map(d=>({name:d.name,rows:d.rows.length,storage:d.demo?'Included demo':'This browser'}))))}`;
  $('template').onclick=()=>downloadCSV(state.datasets[0].rows.slice(0,20),'retailmind_template.csv');
  $('upload').onchange=async e=>{
    const file=e.target.files[0];if(!file)return;
    if(file.size>2500000)return notify('Choose a file smaller than 2.5 MB.');
    busy(true);$('notice').hidden=true;
    try{
      const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
      const payload={name:file.name,content:btoa(binary)};
      state.pending=null;$('upload-result').innerHTML='';$('sheet-picker').innerHTML='';
      if(file.name.toLowerCase().endsWith('.xlsx')){
        const result=await api('upload',{...payload,list_sheets:true});
        $('sheet-picker').innerHTML=`<div class="row"><label>Worksheet<select id="worksheet">${result.sheets.map(s=>`<option>${esc(s)}</option>`).join('')}</select></label><button id="load-sheet" class="secondary">Validate worksheet</button></div>`;
        $('load-sheet').onclick=()=>validateUpload({...payload,sheet:$('worksheet').value},file.name);
      }else await validateUpload(payload,file.name);
    }catch(error){notify(error.message);}finally{busy(false);}
  };
}
async function validateUpload(payload,name){
  busy(true);$('notice').hidden=true;
  try{
    const result=await api('upload',payload);state.pending={name,result};
    $('upload-result').innerHTML=`<div style="height:20px"></div><article class="card"><h2>Data quality report</h2><div class="metrics" style="margin-top:20px">${metric('Accepted',number(result.report.accepted_rows),'Ready for analysis')}${metric('Duplicates removed',number(result.report.duplicates_removed),'Exact duplicate records')}${metric('Rejected',number(result.report.rejected_rows),'Invalid required values')}${metric('Missing cells',number(result.report.missing_cells),'Before cleaning')}</div>${table(result.preview)}<div class="row" style="margin-top:20px"><label>Dataset name<input id="dataset-name" maxlength="100" value="${esc(name)}"></label><button id="save-upload" class="primary">Save & analyze</button>${result.rejected.length?'<button id="rejected" class="secondary">↓ Rejected records</button>':''}</div></article>`;
    if(result.rejected.length)$('rejected').onclick=()=>downloadCSV(result.rejected,'rejected.csv');
    $('save-upload').onclick=async()=>{
      const button=$('save-upload');button.disabled=true;
      try{
        const dataset={id:crypto.randomUUID(),name:$('dataset-name').value.trim()||name,rows:result.rows};
        await saveDataset(dataset);state.datasets.push(dataset);state.active=state.datasets.length-1;setDataset();await refresh();notify('Dataset saved in this browser. Select Overview to explore it.',true);
      }catch(error){notify(error.message);}finally{button.disabled=false;}
    };
  }catch(error){notify(error.message);}finally{busy(false);}
}

function downloadCSV(rows,filename){
  if(!rows.length)return notify('No rows to export.');const keys=Object.keys(rows[0]);
  const quote=value=>{let text=String(value??'');if(typeof value==='string'&&/^[=+@\-\t\r]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"';};
  const csv=[keys.map(quote).join(','),...rows.map(r=>keys.map(k=>quote(r[k])).join(','))].join('\r\n');
  const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function selectedRows(){return state.datasets[state.active].rows.filter(r=>(!$('start').value||r.date>=$('start').value)&&(!$('end').value||r.date<=$('end').value)&&(!$('region').value||r.region===$('region').value)&&(!$('category').value||r.category===$('category').value)&&(!$('store').value||r.store_id===$('store').value));}
const pageTitles={overview:['Overview','A clearer view of your business.'],ask:['Ask RetailMind','Your data. A better conversation.'],products:['Products & stores','Find your next growth opportunity.'],customers:['Customers','Understand who comes back.'],data:['Data studio','Better decisions start with clean data.']};
async function navigate(page){state.page=page;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===page));$('breadcrumb').textContent=pageTitles[page][0];$('title').textContent=pageTitles[page][1];await render();}
async function render(){
  const sequence=++state.sequence;busy(true);
  try{
    if(state.page==='data')dataPage();
    else if(!state.analytics)$('content').innerHTML='<div class="empty">Adjust the filters to find matching records.</div>';
    else if(state.page==='overview')overview();
    else if(state.page==='products')products();
    else if(state.page==='ask')askPage();
    else await customerPage(sequence);
  }catch(error){if(sequence===state.sequence)notify(error.message);}finally{if(sequence===state.sequence)busy(false);}
}
let refreshVersion=0;
async function refresh(){
  const version=++refreshVersion;state.sequence++;busy(true);$('notice').hidden=true;
  try{
    const result=await api('analytics');if(version!==refreshVersion)return;
    state.analytics=result;$('subtitle').textContent=`${state.datasets[state.active].name} · ${number(result.row_count)} selected records · INR`;
    await render();
  }catch(error){if(version===refreshVersion){state.analytics=null;$('content').innerHTML='<div class="empty">No analytics available. Check your filters or reload to retry.</div>';notify(error.message);if(state.page==='data')dataPage();}}
  finally{if(version===refreshVersion)busy(false);}
}
async function init(){
  busy(true);
  try{
    const session=await api('session');state.user=session.user;
    $('signed-in-user').textContent=state.user.username;
    document.body.classList.remove('auth-pending');
    $('logout').onclick=async()=>{
      $('logout').disabled=true;
      try{await api('logout');state.chats.clear();state.datasets=[];state.analytics=null;window.location.replace('/login.html');}
      catch(error){notify('Could not log out. '+error.message);$('logout').disabled=false;}
    };
    const demo=await api('demo');state.datasets=[{id:'demo',demo:true,name:demo.name,rows:demo.rows}];
    try{state.datasets.push(...await savedDatasets());}catch(error){notify(error.message);}
    setDataset();
    document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>navigate(b.dataset.page));
    $('dataset').onchange=e=>{state.active=Number(e.target.value);setDataset();refresh();};
    for(const id of ['start','end','region','category','store'])$(id).onchange=refresh;
    $('reset').onclick=()=>{setDataset();refresh();};
    $('export').onclick=()=>downloadCSV(selectedRows(),'retailmind_export.csv');
    await refresh();
  }catch(error){notify('Could not connect to RetailMind. '+error.message+' Reload to retry.');busy(false);}
}
init();
// Restored browser history must revalidate the session before displaying data.
window.addEventListener('pageshow',event=>{if(event.persisted)window.location.reload();});
