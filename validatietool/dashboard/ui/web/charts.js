"use strict";
(()=>{
let selected='flow',top=0,filters={},catalog=[],data=null,request=null,serial=0,proofSerial=0,flowSerial=0;
const topSelections=new Map();
if(window.ABI18N?.chartState?.chart){selected=window.ABI18N.chartState.chart;topSelections.set(selected,Number(window.ABI18N.chartState.top));}
const root=()=>document.getElementById('charts-root');
const query=extra=>new URLSearchParams({...filters,top,...extra}).toString();
const unit=d=>d.unit==='duties'?trUI('bepalingen'):'acts';
function cancel(){serial++;proofSerial++;flowSerial++;request?.abort();}
function limitControl(){
 const choice=catalog.find(c=>c.id===selected)||{};
 top=topSelections.get(selected)??choice.default_top??10;
 const control=document.getElementById('chart-top');
 control.innerHTML=[...(choice.allow_all?[0]:[]),5,10,20,30,50].map(n=>htmlUI`<option value="${n}"${n===top?' selected':''}>${n===0?trUI('Alle categorieën'):'Top '+n}</option>`).join('');
 control.value=String(top);
 document.getElementById('chart-limit-control').hidden=choice.limit_control===false;
}
function mount(f,charts){
 cancel();filters={...f};catalog=charts??[];
 if(!catalog.some(c=>c.id===selected))selected=catalog[0]?.id??'flow';
 const groups=[...new Set(catalog.map(c=>c.group))];
 root().innerHTML=htmlUI`<div class="analysis-intro"><div><p class="eyebrow">VAN UITKOMST NAAR INFORMATIESTROOM</p><h2>Grafieken en informatiestromen</h2><p>Klik op een balk of band om de actlijst te filteren. Open broncitaten via de tabel met exacte waarden.</p></div></div><div class="chart-controls"><label>Grafiek<select id="chart-picker">${groups.map(g=>htmlUI`<optgroup label="${esc(g)}">${catalog.filter(c=>c.group===g).map(c=>htmlUI`<option value="${c.id}"${c.id===selected?' selected':''}>${esc(c.title)}</option>`).join('')}</optgroup>`).join('')}</select></label><label id="chart-limit-control">Weergave<select id="chart-top"></select></label></div><div id="chart-output" aria-live="polite"></div><div id="chart-evidence"></div><section class="flow-workbench"><h3>Hoe kan een IO verderlopen?</h3><p>Onderzoek binnen één act wie informatie ontvangt en zelf weer een informatieplicht heeft. Aansluitende namen zijn mogelijke schakels, geen bewijs dat hetzelfde dossier of dezelfde gegevens worden doorgegeven.</p><form id="flow-search-form"><label for="flow-search">Zoek een act op NUMAC of titel</label><div><input id="flow-search" type="search" maxlength="500" placeholder="Bijvoorbeeld een NUMAC of een deel van de titel"><button type="submit">Zoeken</button></div></form><div id="flow-search-results"></div><div id="flow-act-output"></div></section>`;
 limitControl();
 document.getElementById('chart-picker').addEventListener('change',event=>{selected=event.target.value;limitControl();load();});
 document.getElementById('chart-top').addEventListener('change',event=>{top=Number(event.target.value);topSelections.set(selected,top);load();});
 document.getElementById('flow-search-form').addEventListener('submit',searchActs);
 root().addEventListener('click',click);
 root().addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target.closest('[data-point]')){event.preventDefault();window.ABList.drill(selected,event.target.closest('[data-point]').dataset.point);}});
 load();
}
async function load(){
 request?.abort();request=new AbortController();const token=++serial;proofSerial++;flowSerial++;data=null;
 document.getElementById('chart-output').innerHTML=trUI('<p class="chart-loading" role="status">Grafiek laden…</p>');
 document.getElementById('chart-evidence').innerHTML='';document.getElementById('flow-act-output').innerHTML='';
 try{
  const result=await window.ABList.api(htmlUI`/api/chart/${selected}?${query()}`,request.signal);
  if(token!==serial||!root())return;data=result;
  const base=htmlUI`/api/chart/${selected}/export.`,count=result.rows.length;
  const rows=result.rows.map(r=>htmlUI`<tr><td>${r.drillable?htmlUI`<button type="button" data-point="${r.point_id}">${esc(r.label)}</button>`:esc(r.label)}</td><td class="number">${number(r.value)}</td><td class="number">${number(r.register_acts)}</td>${selected==='ab_year'?htmlUI`<td class="number">${r.y!=='classifier'?'—':r.share==null?trUI('Niet beschikbaar'):esc(new Intl.NumberFormat(UI.locale,{style:'percent',maximumFractionDigits:2}).format(r.share))}</td>`:''}<td>${r.drillable?htmlUI`<button type="button" data-inspect="${r.point_id}">${selected==='domain'||selected==='org'?trUI('Bronbewijs'):result.unit==='acts'?trUI('Gekoppelde acts'):trUI('Broncitaten')}</button>`:''}</td></tr>`).join('');
  document.getElementById('chart-output').innerHTML=htmlUI`<div class="chart-heading"><h3>${esc(result.title)}</h3><div class="chart-exports"><a href="${UI.url(`${base}png?${query()}`)}">PNG ↓</a><a href="${UI.url(`${base}csv?${query()}`)}">CSV (getoond) ↓</a>${result.display?.limited?htmlUI`<a href="${UI.url(`${base}csv?${query({top:0})}`)}">Volledige CSV</a>`:''}</div></div><p class="chart-completeness" role="status">${esc(result.display?.description||'')}</p>${result.coverage?htmlUI`<p class="chart-coverage">${esc(result.coverage.description)}</p>`:''}<div class="chart-surface">${result.svg}</div><div class="chart-notes">${result.notes.filter(n=>n!==result.coverage?.description&&n!==result.display?.description).map(n=>htmlUI`<p>${esc(n)}</p>`).join('')}</div>${result.flow_examples.length?htmlUI`<div class="flow-examples"><strong>Onderzoek aansluitende gemeentebenamingen</strong><p>Voorbeelden binnen de huidige selectie. De knop opent alle bepalingen van die act/run.</p>${result.flow_examples.map(a=>htmlUI`<button type="button" data-flow-act="${a.act_id}" data-run="${a.run_id}">${esc(a.numac)}</button>`).join(' ')}</div>`:''}<details class="chart-data"><summary>Exacte waarden, broncitaten en actlijst (${number(count)} getoonde punten${result.display?.points_total>count?trUI(' van ')+number(result.display.points_total):''})</summary><div class="chart-table"><table><thead><tr><th>Categorie</th><th>${unit(result)}</th><th>Gekoppelde registeracts</th>${selected==='ab_year'?trUI('<th>Aandeel corpus</th>'):''}<th>Bronnen</th></tr></thead><tbody>${rows||trUI('<tr><td>Geen gegevens.</td></tr>')}</tbody></table></div></details>`;
 }catch(error){if(error.name!=='AbortError'&&token===serial&&root())document.getElementById('chart-output').innerHTML=htmlUI`<p class="error" role="alert">${esc(error.message)}</p>`;}
}
async function inspect(point){
 const row=data?.rows.find(r=>r.point_id===point);if(!row)return;
 const token=++proofSerial,chart=data.chart_id;
 const target=document.getElementById('chart-evidence');
 target.innerHTML=htmlUI`<div class="evidence-selection"><h3>${esc(row.label)}</h3><p>${number(row.value)} ${unit(data)} · ${number(row.register_acts)} gekoppelde registeracts.</p><button type="button" data-drill="${point}">Toon deze acts in de actlijst →</button></div><p role="status">Bronnen laden…</p>`;
 target.scrollIntoView?.({behavior:'smooth',block:'nearest'});
 try{
  const result=await window.ABList.api(htmlUI`/api/chart/${chart}/evidence?${query({point})}`);
  if(token!==proofSerial||!root())return;
  const proof=c=>htmlUI`<article class="flow-proof"><div class="proof-heading"><strong>Bepaling ${c.duty_id}</strong><span>${esc(c.provision??trUI('Artikel niet opgeslagen'))} · ${esc(c.io_id??trUI('IO-type niet opgeslagen'))} · beoordeling ${c.obligation_id}</span></div><dl><dt>Drager</dt><dd>${esc(c.duty_bearer??trUI('Niet opgeslagen'))}</dd><dt>Ontvanger</dt><dd>${esc(c.recipient??trUI('Niet opgeslagen'))}</dd></dl><blockquote>${esc(c.quote??'Geen citaat opgeslagen')}</blockquote><a href="#act/${c.act_id}/run/${c.run_id}">Open de volledige motivering →</a></article>`;
  target.innerHTML=htmlUI`<div class="evidence-selection"><h3>${esc(row.label)}</h3><p>${number(row.value)} ${unit(data)} in deze categorie. ${number(result.acts.summary.acts)} registeracts zijn doorklikbaar.</p><button type="button" data-drill="${point}">Toon deze acts in de actlijst →</button></div>${(result.policy_proofs||[]).slice(0,5).map(p=>htmlUI`<article class="flow-proof"><h4>${esc(p.label??p.beleidsdomein)}: ${esc(p.numac)}</h4><p>${p.method==='expliciete_voordragende_portefeuille'?trUI('Expliciete portefeuille van de voordragende minister'):trUI('Expliciete diensthoofding')}</p>${p.evidence.map(e=>htmlUI`<blockquote>${esc(e.text)}</blockquote>`).join('')}<a href="#act/${p.act_id}">Open de act en bronverantwoording</a></article>`).join('')}${result.proofs.slice(0,5).map(proof).join('')}${result.proofs.length>5?htmlUI`<details class="more-proofs"><summary>Meer bronbeoordelingen (${result.proofs.length-5})</summary>${result.proofs.slice(5).map(proof).join('')}</details>`:''}<p class="chart-caption">Maximaal ${selected==='domain'?5:result.proof_limit} bronvoorbeelden; de actlijst bevat alle passende registeracts. Lezersbeoordelingen zijn geen extra registerbepalingen.</p>${result.acts.items.length?htmlUI`<div class="flow-act-choices"><strong>Informatiestappen per act</strong>${result.acts.items.slice(0,8).map(a=>htmlUI`<button type="button" data-flow-act="${a.act_id}" data-run="${a.run_id}">${esc(a.numac)}</button>`).join('')}</div>`:''}`;
 }catch(error){if(token===proofSerial&&root())target.innerHTML=htmlUI`<p class="error">${esc(error.message)}</p>`;}
}
function stepCard(edge,index){
 const sources=edge.sources??[];
 return htmlUI`<article class="chain-step"><h5>Stap ${index} · ${esc(edge.provision??trUI('Artikel niet opgeslagen'))}</h5><p><strong>${esc(edge.bearer??trUI('Drager onbekend'))}</strong><span class="step-arrow">→</span><strong>${esc(edge.recipient??trUI('Ontvanger niet opgeslagen'))}</strong></p><blockquote>${esc(edge.quote??trUI('Citaat ontbreekt'))}</blockquote><p class="chain-status">Register: ${edge.duty_counts_as_ab?trUI('telt als AB'):trUI('niet als AB geteld')} · ${esc(edge.io_id??trUI('IO-type ontbreekt'))}</p><details><summary>Lezersmotiveringen en gevraagde gegevens (${sources.length})</summary>${sources.map(c=>htmlUI`<div class="chain-source"><strong>Beoordeling ${c.obligation_id}: ${c.counts_as_ab===true?trUI('telt mee als AB'):c.counts_as_ab===false?trUI('telt niet mee als AB'):trUI('meetellen onbekend')}</strong>${c.quote&&c.quote!==edge.quote?htmlUI`<blockquote>${esc(c.quote)}</blockquote>`:''}<p>${esc(c.io_reason??trUI('IO-motivering ontbreekt'))}</p><p>${esc(c.ab_reason??trUI('AB-motivering ontbreekt'))}</p><p><b>Meetelreden:</b> ${esc(c.rule_reason??trUI('Niet opgeslagen'))}</p><p><b>Gegevens:</b> ${esc((c.data_items??[]).join('; ')||trUI('Niet opgeslagen'))}</p></div>`).join('')}</details></article>`;
}
async function flowAct(id,run){
 const token=++flowSerial,target=document.getElementById('flow-act-output');target.innerHTML=trUI('<p role="status">Informatiestappen laden…</p>');target.scrollIntoView?.({behavior:'smooth',block:'start'});
 try{
  const result=await window.ABList.api(htmlUI`/api/flow/act/${id}${run?'?run_id='+run:''}`);
  if(token!==flowSerial||!root())return;
  // Presentatievolgorde, geen bewijswaardering: eerst veldoverlap, dan gelijk IO-type.
  const pairs=[...result.candidates].sort((a,b)=>(Number(!a.shared_data_items.length)-Number(!b.shared_data_items.length))||(Number(a.first.io_id!==a.second.io_id)-Number(b.first.io_id!==b.second.io_id)));
  const candidates=pairs.slice(0,8).map((p,index)=>htmlUI`<details class="chain-candidate"${index===0?' open':''}><summary><span>Mogelijke aansluiting ${index+1}</span><small>${esc(p.first.bearer??trUI('Onbekend'))} → ${esc(p.first.recipient??trUI('Onbekend'))} → ${esc(p.second.recipient??trUI('Onbekend'))}</small></summary><div class="chain-route" aria-label="Aansluitende actornamen"><span>${esc(p.first.bearer??trUI('Onbekend'))}</span><b>→</b><span>${esc(p.first.recipient??trUI('Onbekend'))}</span><b>→</b><span>${esc(p.second.recipient??trUI('Onbekend'))}</span></div><p class="chain-caveat">De middelste actornaam komt overeen. ${p.shared_data_items.length?'Ook de volgende data-omschrijvingen komen letterlijk overeen: '+esc(p.shared_data_items.join('; '))+'.':trUI('De data-omschrijvingen komen niet letterlijk overeen.')} Dit bewijst niet dat dezelfde informatie wordt doorgegeven.</p><div class="chain-steps">${stepCard(p.first,1)}${stepCard(p.second,2)}</div></details>`).join('');
  target.innerHTML=htmlUI`<header class="flow-act-heading"><p class="eyebrow">INFORMATIESTAPPEN BINNEN EEN ACT</p><h3>${esc(result.act.numac)} · Run ${result.run_id}</h3><p>${esc(result.act.title)}</p><a href="#act/${id}/run/${result.run_id}">Open het volledige actdetail →</a></header><p class="chain-method">${esc(result.method)} Hier worden alle bepalingen van deze act/run getoond, ook buiten de filters van het overzicht. Rangschikking: eerst letterlijke veldoverlap, daarna gelijk IO-type.</p>${candidates||trUI('<p class="chain-caveat">Geen aansluitende actornamen tussen verschillende bepalingen gevonden. Dat is geen bewijs dat er geen informatieketen bestaat.</p>')}${pairs.length>8?htmlUI`<p class="chart-caption">8 van ${number(pairs.length)} mogelijke aansluitingen getoond. Alle afzonderlijke bepalingen staan in het actdetail.</p>`:''}<details class="direct-steps"><summary>Alle rechtstreeks opgeslagen relaties (${result.edges.length})</summary>${result.edges.map((e,i)=>htmlUI`<div class="direct-edge"><strong>${esc(e.bearer??trUI('Onbekend'))} → ${esc(e.recipient??trUI('Niet opgeslagen'))}</strong><small>Bepaling ${e.duty_id} · ${esc(e.io_id??trUI('IO-type ontbreekt'))} · register ${e.duty_counts_as_ab?'AB':trUI('geen AB')}</small><blockquote>${esc(e.quote??trUI('Citaat ontbreekt'))}</blockquote></div>`).join('')}</details>`;
 }catch(error){if(token===flowSerial&&root())target.innerHTML=htmlUI`<p class="error">${esc(error.message)}</p>`;}
}
async function searchActs(event){
 event.preventDefault();const value=document.getElementById('flow-search').value.trim(),target=document.getElementById('flow-search-results');if(!value)return;
 const token=++flowSerial;target.textContent=trUI('Acts zoeken…');
 try{
  const result=await window.ABList.api('/api/acts?'+new URLSearchParams({q:value,q_in:'all',size:10,...(filters.run_id?{run_id:filters.run_id}:{})}));
  if(token!==flowSerial||!root())return;
  target.innerHTML=htmlUI`<p class="chart-caption">Actzoeker: los van de overige overzichtsfilters; de gekozen run blijft behouden.</p>${result.items.map(a=>htmlUI`<button type="button" class="flow-search-hit" data-flow-act="${a.act_id}" data-run="${a.run_id}"><strong>${esc(a.numac)}</strong> ${esc(a.title??trUI('Titel ontbreekt'))}</button>`).join('')||trUI('<p>Geen passende gelezen act.</p>')}`;
 }catch(error){if(token===flowSerial&&root())target.textContent=error.message;}
}
function click(event){
 const point=event.target.closest('[data-point]');if(point){event.preventDefault();window.ABList.drill(selected,point.dataset.point);return;}
 const inspectButton=event.target.closest('[data-inspect]');if(inspectButton){event.preventDefault();inspect(inspectButton.dataset.inspect);return;}
 const drill=event.target.closest('[data-drill]');if(drill){event.preventDefault();window.ABList.drill(selected,drill.dataset.drill);return;}
 const act=event.target.closest('[data-flow-act]');if(act){event.preventDefault();flowAct(act.dataset.flowAct,act.dataset.run);}
}
window.ABCharts={mount,cancel,inspect,flowAct};
})();
