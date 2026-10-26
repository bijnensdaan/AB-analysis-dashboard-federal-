"use strict";
const UI=window.ABI18N??{language:'nl',locale:'nl-BE',t:value=>value,html:(parts,...values)=>parts.map((s,i)=>s+(i<values.length?values[i]:'')).join(''),url:value=>value,ready:Promise.resolve()};
const trUI=UI.t,htmlUI=UI.html;
// Later script files provide the overview, charts and detail controllers.
// A fast API response must not initialise the page before those files arrive.
const controllersReady=document.readyState==='loading'
 ?new Promise(resolve=>document.addEventListener('DOMContentLoaded',resolve,{once:true}))
 :Promise.resolve();

const $=id=>document.getElementById(id);
const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const number=value=>new Intl.NumberFormat(UI.locale).format(value);
const labels={year_from:trUI("Jaar vanaf"),year_to:trUI("Jaar tot"),run_id:"Run",level:trUI("Bestuursniveau"),entity:trUI("Entiteit"),act_form:trUI("Instrument"),lang:trUI("Taal"),io_id:"IO-type",duty_bearer_kind:trUI("Drager"),recipient_kind:trUI("Ontvanger"),scope:"Scope",frequency:trUI("Frequentie"),cost_category:trUI("Kostencategorie"),source_kind:trUI("Bron"),is_new_here:trUI("Nieuw in act"),duty_status:trUI("Status bepaling"),truncated:trUI("Afkapsignaal"),disposition:trUI("Tekstselectie"),verdict:trUI("Actverdict"),q:trUI("Zoekterm")};
const values={business:trUI("Onderneming"),citizen:trUI("Burger"),both:trUI("Onderneming en burger"),yes:trUI("Ja"),no:trUI("Nee"),unknown:trUI("Onbekend"),national_act:trUI("Nationale act"),eu_directive:trUI("EU-richtlijn"),eu_regulation:trUI("EU-verordening"),eu_decision:trUI("EU-beslissing"),treaty:trUI("Verdrag"),none:trUI("Geen bron"),other:trUI("Overige bron"),accepted:"Accepted",needs_review:"Needs review",public_body:trUI("Overheidsinstantie"),private_business:trUI("Onderneming"),private_person:trUI("Burger"),semi_public:trUI("Semipublieke drager"),unclear:trUI("Onduidelijk"),government:trUI("Overheid"),third_party:trUI("Derde"),nl:trUI("Nederlands"),fr:trUI("Frans"),de:trUI("Duits"),NL:trUI("Nederlands"),FR:trUI("Frans"),DE:trUI("Duits"),federal:trUI("Federaal"),regional:trUI("Regionaal"),region:trUI("Gewest"),community:trUI("Gemeenschap"),commission:trUI("Gemeenschapscommissie"),Unknown:trUI("Onbekend")};
const columns=[["numac","NUMAC"],["title",trUI("Titel")],["pub_date",trUI("Publicatie")],["act_form",trUI("Instrument")],["level",trUI("Niveau")],["orgaan",trUI("Orgaan")],["ab",trUI("Verdict")],["ab_duties",trUI("AB-bepalingen")],["scope","Scope"],["needs_review","Needs review"],["truncated",trUI("Afkapsignaal")],["run_id","Run"],["lang",trUI("Taal")]];
Object.assign(values,{private_individual:trUI('Burger'),public_authority:trUI('Overheidsinstantie'),mixed:trUI('Gemengde ontvangers'),per_application:trUI('Per aanvraag'),one_off:trUI('Eenmalig'),periodic:trUI('Periodiek'),annual:trUI('Jaarlijks'),monthly:trUI('Maandelijks'),quarterly:trUI('Per kwartaal'),weekly:trUI('Wekelijks'),daily:trUI('Dagelijks'),one_time:trUI('Eenmalig'),event_triggered:trUI('Bij een gebeurtenis'),on_request:trUI('Op verzoek'),continuous:trUI('Doorlopend')});
let state=Object.fromEntries(new URLSearchParams(location.search)),meta=null,data=null,controller=null,sequence=0,debounce=null;
let activeView=location.hash==='#overview'?'overview':'acts';
function syncView(){
 if(location.hash==='#overview')activeView='overview';else if(location.hash==='#acts')activeView='acts';
 $('overview-view').hidden=activeView!=='overview';$('actlist-view').hidden=activeView==='overview';
 $('view-title').textContent=activeView==='overview'?trUI('Overzicht'):trUI('Actlijst');
 $('view-description').textContent=activeView==='overview'?trUI('Van corpus en selectie naar opgeslagen uitkomsten en verplichtingen.'):trUI('Zoek publicaties en bekijk hun vastgelegde uitkomst.');
 for(const name of ['overview','acts']){$('nav-'+name).className=activeView===name?'active':'';$('nav-'+name).setAttribute('aria-current',activeView===name?'page':'false');}
 document.title=(activeView==='overview'?trUI('Overzicht'):trUI('Actlijst'))+' · AB-dashboard';
}
const view=value=>trUI(values[value]??value??"Onbekend");
function option(value,label,selected){return htmlUI`<option value="${esc(value)}"${String(selected??"")===String(value)?" selected":""}>${esc(label)}</option>`;}
function selectField(key,choices){const current=state[key]??"";let choices2=[...choices];if(current&&!choices2.some(([v])=>String(v)===String(current)))choices2.push([current,current]);return htmlUI`<div class="field"><label for="filter-${key}">${labels[key]}</label><select id="filter-${key}" data-filter="${key}">${option("",trUI("Alles"),current)}${choices2.map(([v,label])=>option(v,label,current)).join("")}</select></div>`;}
function rawOptions(key){return (meta.options[key]??[]).map(v=>[v,key==='orgaan'?(v==='Onbekend'?trUI(v):v):view(v)]);}
function buildFilters(){
 labels.orgaan=trUI('Overheidsorgaan');labels.beleidsdomein=trUI('Beleidsrubriek');
 labels.chart_id=trUI('Grafiekselectie');
 const mapping=meta.authority_mapping;
 if(mapping){const c=mapping.coverage,percent=n=>new Intl.NumberFormat(UI.locale,{maximumFractionDigits:1}).format(n);$('authority-coverage').hidden=false;$('authority-coverage').textContent=htmlUI`Orgaan herkend: ${number(c.orgaan_known)} / ${number(c.acts)} (${percent(c.orgaan_percent)}%) · Beleidsrubriek: ${number(c.domain_known)} / ${number(c.acts)} (${percent(c.domain_percent)}%). Dekking van de volledige registersnapshot.`;}
 const runChoices=meta.runs.map(r=>[r.run_id,htmlUI`Run ${r.run_id} · ${new Date(r.started_at).toLocaleDateString(UI.locale)}`]);
 const publicFields=htmlUI`<details class="group" open><summary>Publicatie</summary><div class="years"><div class="field"><label for="filter-year_from">Jaar vanaf</label><input id="filter-year_from" data-filter="year_from" type="number" min="1" max="9998" placeholder="Vanaf" value="${esc(state.year_from??"")}"></div><div class="field"><label for="filter-year_to">Jaar tot</label><input id="filter-year_to" data-filter="year_to" type="number" min="1" max="9998" placeholder="Tot" value="${esc(state.year_to??"")}"></div></div>${["level","entity","orgaan","beleidsdomein","act_form","lang"].map(k=>selectField(k,rawOptions(k))).join("")}${selectField("run_id",runChoices)}<p class="hint">Zonder runfilter: laatste run per act.</p></details>`;
 const ioChoices=meta.options.io_types.map(t=>[t.io_id,htmlUI`${t.io_id} · ${t.name_short}`]);
 const costs=meta.options.cost_categories.map(t=>[t.code,htmlUI`${t.code} · ${t.name}`]);
 const claimFields=htmlUI`<details class="group"><summary>Lezersclaims</summary>${selectField("io_id",ioChoices)}${["duty_bearer_kind","recipient_kind","scope","frequency"].map(k=>selectField(k,rawOptions(k))).join("")}${selectField("cost_category",costs)}${selectField("source_kind",rawOptions("source_kind"))}${selectField("is_new_here",[["yes",trUI("Ja")],["no",trUI("Nee")],["unknown",trUI("Onbekend")]])}</details>`;
 const quality=htmlUI`<details class="group"><summary>Status en tekstkwaliteit</summary>${selectField("duty_status",[["accepted","Accepted"],["needs_review","Needs review"]])}${selectField("truncated",[["yes",trUI("Mogelijk afgekapt")],["no",trUI("Geen afkapsignaal")],["unknown",trUI("Onbekend")]])}${selectField("disposition",rawOptions("disposition"))}</details>`;
 $("filter-fields").innerHTML=publicFields+claimFields+quality;
 document.querySelectorAll("[data-filter]").forEach(el=>el.addEventListener("change",()=>apply({[el.dataset.filter]:el.value,page:1})));
}
function updateControls(){
 $("q").value=state.q??"";$("q_in").value=state.q_in??"all";$("size").value=state.size??"25";
 document.querySelectorAll("[data-filter]").forEach(el=>{el.value=state[el.dataset.filter]??"";});
 document.querySelectorAll("[data-verdict]").forEach(el=>el.setAttribute("aria-pressed",String(el.dataset.verdict===(state.verdict??""))));
 const active=Object.entries(state).filter(([key,value])=>labels[key]&&value!==""&&value!=null);
 $("filter-count").textContent=String(active.length);
 $("active-filters").innerHTML=active.map(([key,value])=>{const display=key==='chart_id'?(data?.chart_selection?.label??trUI('Geselecteerde grafiekpunten')):['q','orgaan'].includes(key)?value:view(value);return htmlUI`<button type="button" class="chip" data-clear="${key}" title="${esc(labels[key]+': '+display)}">${labels[key]}: ${esc(String(display).length>90?String(display).slice(0,90)+'…':display)}<span aria-hidden="true">×</span></button>`;}).join("");
}
async function api(path,signal){const response=await fetch(UI.url(path),{signal});let result;try{result=await response.json();}catch{throw Error(trUI("Het dashboard gaf geen leesbaar antwoord."));}if(!response.ok)throw Error(result.fout??trUI("De selectie kon niet worden geladen."));return result;}
function apply(changes,push=true){clearTimeout(debounce);state={...state,...changes};for(const [key,value] of Object.entries(state))if(value===""||value==null||(key==="page"&&String(value)==="1"))delete state[key];if(push){const query=new URLSearchParams(state).toString();history.pushState(null,"",location.pathname+(query?"?"+query:"")+(activeView==='overview'?'#overview':''));}updateControls();load();}
function yesNo(value){return value===null?trUI("Onbekend"):value?trUI("Ja"):trUI("Nee");}
function verdict(value){const cls=value===null?"unknown":value?"yes":"no";return htmlUI`<span class="pill ${cls}">${value===null?trUI("Onbekend"):value?"AB":trUI("Geen AB")}</span>`;}
function safeUrl(value){try{const url=new URL(value);return ["https:","http:"].includes(url.protocol)?url.href:null;}catch{return null;}}
function row(item){
 const href=htmlUI`#act/${item.act_id}/run/${item.run_id}`;const numac=htmlUI`<a href="${href}" title="Open het actdetail">${esc(item.numac)} →</a>`;
 const quote=item.matched_quote?htmlUI`<span class="quote-hit" title="${esc(item.matched_quote)}">Citaat: ${esc(item.matched_quote)}</span>`:"";
 const failed=item.successes===0?trUI('<span class="row-warning">Alleen mislukte lezingen</span>'):"";
 const dutiesTitle=htmlUI`${number(item.ab_duties)} AB-bepalingen binnen de filters; ${number(item.ab_duties_total)} in deze act en run.`;
 const extra=item.ab_duties!==item.ab_duties_total?htmlUI`<span class="subcount">van ${number(item.ab_duties_total)}</span>`:"";
 return htmlUI`<tr><td>${numac}</td><td class="title-cell"><a href="${href}" class="title-text" title="${esc(item.title)}">${esc(item.title??trUI("Titel ontbreekt"))}</a>${quote}${failed}</td><td class="nowrap">${esc(item.pub_date?new Date(item.pub_date+"T12:00:00").toLocaleDateString(UI.locale):trUI("Onbekend"))}</td><td>${esc(view(item.act_form))}</td><td>${esc(view(item.level))}</td><td title="${esc(item.beleidsdomein??trUI('Onbekend'))}">${esc(item.orgaan??trUI('Onbekend'))}</td><td>${verdict(item.ab)}</td><td class="number" title="${dutiesTitle}">${number(item.ab_duties)}${extra}</td><td>${esc(view(item.ab_scope))}</td><td title="${number(item.needs_review_duties)} filterpassende bepalingen met needs_review; cel toont de opgeslagen actvlag.">${yesNo(item.needs_review)}</td><td title="Opgeslagen afkapsignaal of ruwe tekst van precies 32.767 tekens">${item.truncated?trUI('<span class="pill unknown">Ja</span>'):yesNo(item.truncated)}</td><td>${item.run_id}</td><td>${esc(view(item.lang))}</td></tr>`;
}
function render(){
 const summary=data.summary;
 $("summary").innerHTML=htmlUI`<strong>${number(summary.acts)}</strong> acts <span class="muted">·</span> <strong>${number(summary.duties)}</strong> bepalingen <span class="muted">·</span> ${number(summary.ab_duties)} AB-bepalingen<span class="secondary">${number(summary.read_success)} met geslaagde lezing${summary.read_failed?htmlUI` · ${number(summary.read_failed)} alleen mislukt`:""}</span>`;
 $("thead").innerHTML=htmlUI`<tr>${columns.map(([key,label])=>{const active=key===(state.sort??"pub_date");const direction=state.direction??"desc";return htmlUI`<th scope="col" aria-sort="${active?(direction==="asc"?"ascending":"descending"):"none"}"><button type="button" data-sort="${key}" aria-label="Sorteer op ${label}">${label}<span class="sort-arrow" aria-hidden="true">${active?(direction==="asc"?"↑":"↓"):"↕"}</span></button></th>`;}).join("")}</tr>`;
 $("tbody").innerHTML=data.items.length?data.items.map(row).join(""):trUI('<tr><td colspan="13" class="empty">Geen acts voor deze selectie. Pas je zoekterm aan of wis filters.</td></tr>');
 $("page").value=data.page;$("page").max=data.pages;$("pages").textContent=htmlUI`van ${number(data.pages)}`;
 $("prev").disabled=data.page<=1;$("next").disabled=data.page>=data.pages;
 const from=summary.acts?(data.page-1)*data.size+1:0,to=Math.min(data.page*data.size,summary.acts);
 $("range").textContent=htmlUI`${number(from)}–${number(to)} van ${number(summary.acts)} acts`;
 if(state.page&&Number(state.page)!==data.page){state.page=data.page;history.replaceState(null,"",location.pathname+"?"+new URLSearchParams(state)+(activeView==='overview'?'#overview':''));}
 updateControls();
}
async function load(){
 if(controller)controller.abort();controller=new AbortController();const token=++sequence;
 $("tablebox").setAttribute("aria-busy","true");$("error").hidden=true;
 const overview=activeView==='overview';window.ABCharts?.cancel();if(overview)window.ABOverview?.loading();
 try{const [result,kpis]=await Promise.all([api("/api/acts?"+new URLSearchParams(state),controller.signal),overview?api('/api/overview?'+new URLSearchParams(state),controller.signal):Promise.resolve(null)]);if(token!==sequence)return;data=result;render();if(kpis){window.ABOverview?.render(kpis);window.ABCharts?.mount(state,meta.charts);}}
 catch(error){if(error.name==="AbortError"||token!==sequence)return;$("error").textContent=error.message;$("error").hidden=false;$("summary").textContent=trUI("Selectie niet geladen");$("tbody").innerHTML="";$("prev").disabled=true;$("next").disabled=true;$("range").textContent="";if(overview)window.ABOverview?.error(trUI('De kerncijfers konden niet worden geladen.'));}
 finally{if(token===sequence)$("tablebox").setAttribute("aria-busy","false");}
}
$("search-form").addEventListener("submit",event=>{event.preventDefault();apply({q:$("q").value,q_in:$("q_in").value,page:1});});
$("q").addEventListener("input",()=>{clearTimeout(debounce);debounce=setTimeout(()=>apply({q:$("q").value,q_in:$("q_in").value,page:1}),350);});
$("q_in").addEventListener("change",()=>apply({q_in:$("q_in").value,q:$("q").value,page:1}));
$("size").addEventListener("change",()=>apply({size:$("size").value,page:1}));
$("reset").addEventListener("click",()=>{state={};apply({});});
$("verdict-buttons").addEventListener("click",event=>{const button=event.target.closest("[data-verdict]");if(button)apply({verdict:button.dataset.verdict,page:1});});
$("active-filters").addEventListener("click",event=>{const button=event.target.closest("[data-clear]");if(button)apply(button.dataset.clear==='chart_id'?{chart_id:'',point_id:'',page:1}:{[button.dataset.clear]:"",page:1});});
$("thead").addEventListener("click",event=>{const button=event.target.closest("[data-sort]");if(!button)return;const key=button.dataset.sort;const current=state.sort??"pub_date",direction=state.direction??"desc";apply({sort:key,direction:key===current?(direction==="asc"?"desc":"asc"):(key==="pub_date"?"desc":"asc"),page:1});});
$("prev").addEventListener("click",()=>{if(data)apply({page:data.page-1});});$("next").addEventListener("click",()=>{if(data)apply({page:data.page+1});});
$("page-form").addEventListener("submit",event=>{event.preventDefault();apply({page:$("page").value});});
window.ABList={api,drill:(chart,point)=>{const charts=(state.chart_id??'').split(',').filter(Boolean),points=(state.point_id??'').split(',').filter(Boolean);if(!charts.some((c,i)=>c===chart&&points[i]===point)){if(charts.length>=6){$('error').textContent=trUI('Wis eerst de bestaande grafiekselectie voordat je verder verfijnt.');$('error').hidden=false;return;}charts.push(chart);points.push(point);}activeView='acts';apply({chart_id:charts.join(','),point_id:points.join(','),page:1});syncView();window.scrollTo?.({top:0});},returnUrl:()=>location.pathname+location.search+(activeView==='overview'?'#overview':'#acts'),returnLabel:()=>activeView==='overview'?trUI('Terug naar het overzicht'):trUI('Terug naar de actlijst'),showRoute:async()=>{syncView();updateControls();await load();},restore:async()=>{$("list-intro").hidden=false;$("list-layout").hidden=false;$("act-detail").hidden=true;syncView();updateControls();await load();},hide:()=>{window.ABCharts?.cancel();$("list-intro").hidden=true;$("list-layout").hidden=true;$("act-detail").hidden=false;}};
window.addEventListener("popstate",()=>{state=Object.fromEntries(new URLSearchParams(location.search));if(window.ABDetail)window.ABDetail.route();else{updateControls();load();}});
(async()=>{try{await UI.ready;await controllersReady;meta=await api("/api/meta");const date=new Date(meta.source.snapshot_utc);$("snapshot").textContent=htmlUI`Registersnapshot ${date.toLocaleString(UI.locale,{timeZone:"Europe/Brussels",dateStyle:"long",timeStyle:"medium"})} (Europe/Brussels) · Alleen-lezen · ${number(meta.control.acts)} registeracts`;buildFilters();syncView();updateControls();if(window.ABDetail&&location.hash?.startsWith("#act/"))await window.ABDetail.route();else await load();}catch(error){$("snapshot").textContent=trUI("Gegevensversie niet beschikbaar");$("error").textContent=error.message;$("error").hidden=false;}})();
