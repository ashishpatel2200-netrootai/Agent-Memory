const $ = id => document.getElementById(id);
let colors = ['#1d4ed8','#2563eb','#0284c7','#60a5fa','#93c5fd'];
const labels = ['System prompt','Conversation','Working memory','Retrieved context','Tool results'];
const fmt = n => new Intl.NumberFormat('en-US', {notation:n>=10000?'compact':'standard',maximumFractionDigits:1}).format(n);
const money = n => '$'+n.toFixed(4);
let data = {events:[],categories:[]}, selected = [];
let activeWorkspace = 1, workspaceList = [], refreshVersion = 0;
try { activeWorkspace = Number(localStorage.getItem('netroot-workspace')) || 1; } catch {}
let example;
function updateExample(){
example = `curl http://127.0.0.1:${location.port || '8000'}/api/events \\\n  -H 'Content-Type: application/json' \\\n  -d '{"workspace":${activeWorkspace},"session":"run-001","agent":"My agent",
    "model":"my-model","capacity":128000,
    "system":2400,"conversation":16000,
    "working":8000,"retrieved":4000,"tools":1200,
    "input_tokens":31600,"output_tokens":800,
    "input_rate":2.50,"output_rate":10.00}'`;
$('example').textContent = example;
}
updateExample();
function toast(message){$('toast').textContent=message;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',3500)}
function escapeHTML(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function refresh(){
  const version = ++refreshVersion;
  try {
    const response=await fetch('/api/events?workspace='+activeWorkspace);if(!response.ok)throw Error('Server error');const incoming=await response.json();if(version!==refreshVersion)return;data=incoming;
    const previous=$('agent').value;
    $('agent').replaceChildren(new Option('All agents',''),...[...new Set(data.events.map(e=>e.agent))].sort().map(name=>new Option(name,name)));
    $('agent').value=previous;render();$('status').textContent='Updated '+new Date().toLocaleTimeString()+' · refreshes every 5s';
  }catch(error){if(version===refreshVersion)$('status').textContent='Connection unavailable · retrying';}
}
function render(){
  const source=$('source').value, agent=$('agent').value;
  selected=data.events.filter(e=>(!agent||e.agent===agent)&&(source==='all'||Boolean(e.demo)===(source==='demo')));
  const latest=new Map();selected.forEach(e=>latest.set(JSON.stringify([e.demo,e.agent,e.session]),e));
  const sessions=[...latest.values()], total=sessions.reduce((n,e)=>n+e.used,0), capacity=sessions.reduce((n,e)=>n+e.capacity,0);
  $('sessionsCount').textContent=sessions.length;$('context').innerHTML=fmt(total)+' <em>tokens</em>';
  $('utilization').textContent=(capacity?total/capacity*100:0).toFixed(1)+'%';$('spend').textContent=money(selected.reduce((n,e)=>n+e.cost,0));
  $('ringTotal').textContent=fmt(total);$('eventCount').textContent=selected.length+' events';
  let offset=0;
  const totals=data.categories.map(cat=>sessions.reduce((n,e)=>n+e[cat],0));
  const stops=totals.map((n,i)=>{let start=offset;offset+=total?n/total*100:0;return `${colors[i]} ${start}% ${offset}%`});
  $('ring').style.background=total?`conic-gradient(${stops.join(',')})`:'var(--subtle)';
  $('breakdown').innerHTML=totals.map((n,i)=>`<div class="break-row"><span><b class="swatch" style="background:${colors[i]}"></b>${labels[i]}</span><b>${fmt(n)}</b></div>`).join('');
  const query=$('search').value.toLowerCase();
  $('rows').innerHTML=sessions.filter(e=>(e.agent+' '+e.session+' '+e.model).toLowerCase().includes(query)).map(e=>{
    const percent=e.used/e.capacity*100, health=percent>=90?'critical':percent>=70?'elevated':'healthy';
    const cost=selected.filter(v=>v.session===e.session&&v.agent===e.agent&&v.demo===e.demo).reduce((n,v)=>n+v.cost,0);
    return `<tr><td><strong>${escapeHTML(e.agent)}</strong><small>${escapeHTML(e.session)}${e.demo?' · DEMO':''}</small></td><td>${escapeHTML(e.model)}</td><td>${fmt(e.used)} / ${fmt(e.capacity)} <small>${percent.toFixed(1)}% used</small><div class="usage"><div style="width:${Math.min(percent,100)}%"></div></div></td><td>${money(cost)}</td><td><span class="health ${health}">${health}</span></td><td>${new Date(e.timestamp).toLocaleTimeString()}</td></tr>`;
  }).join('') || '<tr><td colspan="6" class="empty">No sessions found. Load demo data or send your first event using the API below.</td></tr>';
  chart(latest);
}
function chart(latest){
  if(!selected.length){$('timeline').innerHTML='<div class="empty">Your context story starts with the first event.</div>';$('legend').textContent='';return;}
  const groups=[...latest.keys()], min=Math.min(...selected.map(e=>Date.parse(e.timestamp))), max=Math.max(...selected.map(e=>Date.parse(e.timestamp))), peak=Math.max(1,...selected.map(e=>e.used));
  let svg='';for(let i=0;i<5;i++){const y=15+i*39;svg+=`<line x1="48" x2="590" y1="${y}" y2="${y}" stroke="#f0f0f0"/><text x="0" y="${y+4}" font-size="10" fill="#949494">${fmt(peak*(1-i/4))}</text>`;}
  groups.forEach((key,i)=>{const points=selected.filter(e=>JSON.stringify([e.demo,e.agent,e.session])===key).map(e=>`${48+(Date.parse(e.timestamp)-min)/Math.max(1,max-min)*540},${171-e.used/peak*156}`);svg+=`<polyline points="${points.join(' ')}" fill="none" stroke="${colors[i%colors.length]}" stroke-width="2.5" stroke-linejoin="round"/>`;if(points.length===1){const [x,y]=points[0].split(',');svg+=`<circle cx="${x}" cy="${y}" r="4" fill="${colors[i%colors.length]}"/>`;}});
  svg+=`<text x="48" y="202" font-size="10" fill="#949494">${new Date(min).toLocaleTimeString()}</text><text x="590" y="202" text-anchor="end" font-size="10" fill="#949494">${new Date(max).toLocaleTimeString()}</text>`;
  $('timeline').innerHTML=`<svg viewBox="0 0 610 210" role="img" aria-label="Context tokens over time for selected sessions">${svg}</svg>`;
  $('legend').innerHTML=groups.map((key,i)=>`<span><b class="swatch" style="background:${colors[i%colors.length]}"></b>${escapeHTML(latest.get(key).agent)} · ${escapeHTML(latest.get(key).session)}</span>`).join('');
}
$('source').onchange=render;$('agent').onchange=render;$('search').oninput=render;
$('demo').onclick=async()=>{ $('demo').disabled=true;try{const response=await fetch('/api/demo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace:activeWorkspace})});if(!response.ok)throw Error();await refresh();toast('Demo sessions loaded. Use the Data filter to view live events.');}catch{toast('Could not load demo data.');}finally{$('demo').disabled=false;}};
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText(example);toast('API example copied');}catch{toast('Select and copy the API example manually.')}};
$('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(selected,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='memory-events.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
loadWorkspaces().catch(()=>{$('status').textContent='Could not load workspaces. Reload to retry.';});setInterval(refresh,5000);

function applyTheme(theme) {
  const dark = theme === 'dark';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  $('theme-toggle').textContent = dark ? 'White background' : 'Black background';
  $('theme-toggle').setAttribute('aria-pressed', String(dark));
  $('theme-toggle').setAttribute('aria-label', dark ? 'Switch to white background' : 'Switch to black background');
  colors = dark
    ? ['#bfdbfe','#60a5fa','#38bdf8','#3b82f6','#2563eb']
    : ['#1d4ed8','#2563eb','#0284c7','#60a5fa','#93c5fd'];
  render();
}
$('theme-toggle').onclick = () => {
  const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem('netroot-theme', theme); } catch {}
  applyTheme(theme);
};
applyTheme(document.documentElement.dataset.theme);

async function loadWorkspaces(){
  const response = await fetch('/api/workspaces');
  if(!response.ok) throw Error('Could not load workspaces');
  workspaceList = (await response.json()).workspaces;
  if(!workspaceList.some(w=>w.id===activeWorkspace)) activeWorkspace=1;
  $('workspace-select').replaceChildren(...workspaceList.map(w=>new Option(w.name,w.id)));
  selectWorkspace(activeWorkspace);
}
function selectWorkspace(id){
  activeWorkspace=Number(id); ++refreshVersion;
  $('workspace-select').value=String(activeWorkspace);
  $('workspace-heading').textContent=workspaceList.find(w=>w.id===activeWorkspace)?.name || 'My workspace';
  try {localStorage.setItem('netroot-workspace',activeWorkspace);} catch {}
  data={events:[],categories:[]}; selected=[];
  $('agent').replaceChildren(new Option('All agents','')); $('search').value=''; $('source').value='all';
  render();updateExample();refresh();
}
$('workspace-select').onchange=event=>selectWorkspace(event.target.value);
$('new-workspace').onclick=()=>{$('workspace-form').reset();$('workspace-error').textContent='';$('workspace-dialog').showModal();$('workspace-name').focus();};
$('workspace-cancel').onclick=()=>$('workspace-dialog').close();
$('workspace-form').onsubmit=async event=>{
  event.preventDefault();$('workspace-save').disabled=true;$('workspace-error').textContent='';
  try {
    const response=await fetch('/api/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('workspace-name').value})});
    const result=await response.json();if(!response.ok) throw Error(result.error||'Could not create workspace');
    workspaceList.push(result);$('workspace-select').add(new Option(result.name,result.id));
    selectWorkspace(result.id);$('workspace-dialog').close();toast('Workspace created');
  }catch(error){$('workspace-error').textContent=error.message;}finally{$('workspace-save').disabled=false;}
};
