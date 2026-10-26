"use strict";
(()=>{
 const key='ab-dashboard-interface-language';
 let saved='nl';try{saved=localStorage.getItem(key)||'nl';}catch{}
 const language=saved==='en'?'en':'nl',locale=language==='en'?'en-GB':'nl-BE';
 let dictionary=/*__AB_CATALOG__*/{},pattern=null;
 const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 function translate(value){
  if(language!=='en'||typeof value!=='string'||!pattern)return value;
  return value.replace(pattern,match=>dictionary[match]??match);
 }
 function html(strings,...values){
  // Translate only authored UI text. Interpolated source values are never passed
  // through the dictionary, even when they happen to equal an interface label.
  return strings.map((part,i)=>translate(part)+(i<values.length?values[i]:'')).join('');
 }
 function url(path){
  if(language!=='en'||!path.startsWith('/api/'))return path;
  const target=new URL(path,location.href);target.searchParams.set('ui_lang',language);
  return target.pathname+target.search+target.hash;
 }
 function staticPage(){
  document.documentElement.lang=language;
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  for(let node=walker.nextNode();node;node=walker.nextNode()){
   if(!['SCRIPT','STYLE'].includes(node.parentElement?.tagName))node.nodeValue=translate(node.nodeValue);
  }
  for(const node of document.querySelectorAll('[aria-label],[placeholder],[title]')){
   for(const attribute of ['aria-label','placeholder','title'])if(node.hasAttribute(attribute))node.setAttribute(attribute,translate(node.getAttribute(attribute)));
  }
  const button=document.getElementById('language-toggle');
  button.textContent=language==='en'?'Nederlands':'English';
  button.lang=language==='en'?'nl':'en';
  button.setAttribute('aria-label',language==='en'?'Switch interface to Dutch':'Switch interface to English');
  button.title=language==='en'?'Source texts and quotations keep their original language.':'Bronteksten en citaten behouden hun oorspronkelijke taal.';
  button.addEventListener('click',()=>{
   try{sessionStorage.setItem('ab-dashboard-language-chart',JSON.stringify({chart:document.getElementById('chart-picker')?.value,top:document.getElementById('chart-top')?.value}));}catch{}
   try{localStorage.setItem(key,language==='en'?'nl':'en');}catch{}
   // Keep the current route, source-language filter and all other filters.
   location.reload();
  });
 }
 if(language==='en'){
  const keys=Object.keys(dictionary).sort((a,b)=>b.length-a.length);
  pattern=new RegExp(keys.map(k=>(/^[\p{L}\p{N}_]/u.test(k)?'(?<![\\p{L}\\p{N}_])':'')+escape(k)+(/[\p{L}\p{N}_]$/u.test(k)?'(?![\\p{L}\\p{N}_])':'')).join('|'),'gu');
 }
 const ready=Promise.resolve().then(staticPage);
 let chartState=null;try{chartState=JSON.parse(sessionStorage.getItem('ab-dashboard-language-chart'));sessionStorage.removeItem('ab-dashboard-language-chart');}catch{}
 window.ABI18N={language,locale,t:translate,html,url,ready,chartState};
})();
