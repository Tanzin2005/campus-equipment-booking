'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {user:null, csrf:'', view:'equipment', category:'', equipment:[], bookings:[], bookingView:'upcoming', adminView:'equipment', offset:0, total:0, limit:10, selected:null, editing:null, cancelling:null, pendingItem:null, authMode:'login', sequence:0, scheduleSequence:0};
const categories = ['Electronics','Computing','Presentation','Fabrication'];
const initials = name => name.trim().split(/\s+/).slice(0,2).map(s=>s[0]).join('').toUpperCase();
const dateLabel = value => new Date(value).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'});
const timeLabel = value => new Date(value).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});
const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const localValue = date => new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate()+1); tomorrow.setHours(10,0,0,0);
$('#filter-start').value = localValue(tomorrow);
$('#filter-end').value = localValue(new Date(tomorrow.getTime()+3600000));
$('#timezone-label').textContent = `Times shown in ${zone}`;
$('#booking-timezone').textContent = `Your timezone: ${zone} · Maximum 24 hours`;
let toastTimer;
function toast(message){ $('#toast').textContent=message; $('#toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').hidden=true,5000); }
function empty(title, text, action=''){ return `<div class="empty-state"><h2>${escapeHTML(title)}</h2><p>${escapeHTML(text)}</p>${action}</div>`; }
function busy(form,value){form.querySelectorAll('button[type="submit"]').forEach(button=>button.disabled=value);}
async function api(path,options={}){
  const headers = {...options.headers};
  if(options.body) headers['Content-Type']='application/json';
  if(options.method && !['GET','HEAD'].includes(options.method) && state.csrf) headers['X-CSRF-Token']=state.csrf;
  let response;
  try { response=await fetch(path,{...options,headers,credentials:'same-origin'}); }
  catch { throw new Error('Could not reach the server. Check your connection and try again.'); }
  if(response.status===204) return null;
  const data=await response.json().catch(()=>({}));
  if(!response.ok){
    if(response.status===401 && !path.startsWith('/auth/')){state.user=null;state.csrf='';renderAccount();}
    const message=Array.isArray(data.detail)?data.detail.map(e=>e.msg).join('. '):data.detail;
    const error=new Error(message||`Request failed (${response.status}). Please try again.`); error.status=response.status; throw error;
  }
  return data;
}
function renderAccount(){
  $('#admin-nav').hidden=state.user?.role!=='admin';
  $('#account-controls').innerHTML=state.user?`<span class="avatar">${escapeHTML(initials(state.user.name))}</span><span class="account-name">${escapeHTML(state.user.name)}</span><button class="text-button" id="sign-out">Sign out</button>`:'<button class="button primary small" id="sign-in">Sign in</button>';
}
function categoryMark(category){return `<span class="category-mark mark-${escapeHTML(category.toLowerCase())}" aria-hidden="true">${({Electronics:'EL',Computing:'CO',Presentation:'PR',Fabrication:'FA'})[category]||'EQ'}</span>`;}
function availability(){
  const start = new Date($('#filter-start').value), end = new Date($('#filter-end').value);
  if(!Number.isFinite(+start)||!Number.isFinite(+end)) throw new Error('Choose a start and end time.');
  if(+start<=Date.now()) throw new Error('Choose a start time in the future.');
  if(+end<=+start) throw new Error('End time must be after start time.');
  if(+end-+start>86400000) throw new Error('Choose a reservation of up to 24 hours.');
  return {start_at:start.toISOString(),end_at:end.toISOString()};
}
async function navigate(){
  state.view=['equipment','bookings','admin'].includes(location.hash.slice(1))?location.hash.slice(1):'equipment';
  state.offset=0;
  await renderView();
}
function setHeading(title,description,eyebrow='CAMPUS RESOURCES'){
  $('#page-title').textContent=title; $('#breadcrumb').textContent=title; $('#page-description').textContent=description; $('#eyebrow').textContent=eyebrow;
}
async function renderView(){
  const sequence=++state.sequence;
  $$('.nav-link').forEach(link=>{const active=link.dataset.view===state.view;link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
  $('#catalog-filters').hidden=state.view!=='equipment'; $('#heading-action').innerHTML=''; $('#pagination').hidden=true; $('#view-controls').innerHTML='';
  $('#content').setAttribute('aria-busy','true');
  $('#content').innerHTML=empty('Loading…','');
  try{
    if(state.view==='equipment'){
      setHeading('Equipment library','Find the tools you need. Reserve a time that works.');
      const params=new URLSearchParams({...availability(),q:$('#search').value,category:state.category,available_only:$('#available-only').checked,limit:13,offset:state.offset});
      const items=await api(`/equipment?${params}`); if(sequence!==state.sequence)return;
      state.equipment=items.slice(0,12);
      const visible=state.equipment;
      $('#view-controls').innerHTML=`<div class="tabs" aria-label="Equipment categories">${['',...categories].map(category=>`<button class="tab ${state.category===category?'active':''}" data-category="${category}" aria-pressed="${state.category===category}">${category||'All equipment'}</button>`).join('')}</div><span class="result-count">${visible.length} ${visible.length===1?'item':'items'}</span>`;
      $('#heading-action').innerHTML=`<span class="heading-count">${visible.filter(item=>item.available).length} available on this page</span>`;
      $('#content').innerHTML=visible.length?`<div class="equipment-grid">${visible.map(item=>`<article class="equipment-card"><div class="card-top">${categoryMark(item.category)}<span class="badge ${item.available?'':'busy'}">${item.available?'Available':'Reserved'}</span></div><div class="card-body"><p class="card-category">${escapeHTML(item.category)}</p><h2>${escapeHTML(item.name)}</h2><span class="location">${escapeHTML(item.location)}</span><p class="card-description">${escapeHTML(item.description||'Available for campus lab and project work.')}</p></div><div class="card-bottom"><span class="equipment-id">ITEM ${String(item.id).padStart(3,'0')}</span><button class="button ${item.available?'primary':'secondary'}" data-book="${item.id}">${item.available?'Reserve equipment':'Find another time'}</button></div></article>`).join('')}</div>`:empty('No equipment matches','Try a different search, category, or reservation time.','<button class="button secondary" id="reset-filters">Reset filters</button>');
    if(state.offset>0||items.length>12){$('#pagination').hidden=false;$('#pagination').innerHTML=`<button class="button secondary small" id="previous-page" ${state.offset===0?'disabled':''}>Previous</button><span>Page ${Math.floor(state.offset/12)+1}</span><button class="button secondary small" id="next-page" ${items.length<=12?'disabled':''}>Next</button>`;}
    }else if(state.view==='bookings'){
      setHeading('My reservations','Your equipment, your schedule. Everything in one place.','YOUR WORKSPACE');
      if(!state.user){$('#content').innerHTML=empty('Your reservations live here','Sign in to see your bookings and reserve equipment.','<button class="button primary" data-login>Sign in</button>');return;}
      await renderBookings(false,sequence);
    }else{
      setHeading('Administration','Keep equipment and campus reservations running smoothly.','CAMPUS OPERATIONS');
      if(state.user?.role!=='admin'){$('#content').innerHTML=empty('Administrator access required','Sign in with an administrator account to manage equipment.','<button class="button primary" data-login>Sign in</button>');return;}
      if(state.adminView==='equipment'){
        $('#heading-action').innerHTML='<button class="button primary" id="add-equipment">+ Add equipment</button>';
        $('#view-controls').innerHTML=adminTabs();
        const items=await api('/admin/equipment');if(sequence!==state.sequence)return; state.equipment=items;
        $('#content').innerHTML=`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Equipment</th><th>Category</th><th>Status</th><th><span class="optional">Actions</span></th></tr></thead><tbody>${items.map(item=>`<tr><td>${escapeHTML(item.name)}<small>${escapeHTML(item.location)}</small></td><td>${escapeHTML(item.category)}</td><td><span class="badge ${item.active?'':'offline'}">${item.active?'Accepting bookings':'Offline'}</span></td><td><button class="button secondary small" data-edit="${item.id}">Edit</button></td></tr>`).join('')}</tbody></table></div><p class="admin-note">Taking equipment offline preserves its history. Cancel its upcoming reservations first.</p>`;
      }else{await renderBookings(true,sequence);}
    }
  }catch(error){if(sequence===state.sequence){$('#content').innerHTML=empty('Could not load this view',error.message,'<button class="button secondary" id="retry">Try again</button>');}}
  finally{if(sequence===state.sequence)$('#content').setAttribute('aria-busy','false');}
}
function adminTabs(){return `<div class="tabs"><button class="tab ${state.adminView==='equipment'?'active':''}" data-admin-view="equipment">Equipment</button><button class="tab ${state.adminView==='reservations'?'active':''}" data-admin-view="reservations">All reservations</button></div>`;}
async function renderBookings(admin,sequence){
  const params=new URLSearchParams({view:state.bookingView,limit:state.limit,offset:state.offset,all_users:admin});
  const page=await api(`/bookings?${params}`);if(sequence!==state.sequence)return;
  state.bookings=page.items;state.total=page.total;
  const tabs=`<div class="tabs" aria-label="Reservation status">${['upcoming','past','cancelled'].map(view=>`<button class="tab ${state.bookingView===view?'active':''}" data-booking-view="${view}" aria-pressed="${state.bookingView===view}">${view[0].toUpperCase()+view.slice(1)}</button>`).join('')}</div>`;
  $('#view-controls').innerHTML=admin?`${adminTabs()}${tabs}`:`${tabs}<span class="result-count">${page.total} ${page.total===1?'reservation':'reservations'}</span>`;
  $('#content').innerHTML=page.items.length?`<div class="reservation-list">${page.items.map(booking=>{
    const started=+new Date(booking.start_at)<=Date.now(),ended=+new Date(booking.end_at)<=Date.now();
    const label=booking.status==='cancelled'?'Cancelled':ended?'Completed':started?'In progress':'Confirmed';
    const cancellable=booking.status==='confirmed'&&(!started||admin);
    return `<article class="reservation">${categoryMark('Electronics')}<div><h2>${escapeHTML(booking.equipment_name)}</h2><span class="location">${escapeHTML(booking.location)}</span>${admin?`<p>${escapeHTML(booking.student_name)}${booking.user_id===null?' · Legacy reservation':''}</p>`:''}<p>${booking.purpose?escapeHTML(booking.purpose):`Reservation #${booking.id}`}</p></div><div class="reservation-time"><strong>${dateLabel(booking.start_at)}</strong><p>${timeLabel(booking.start_at)} – ${dateLabel(booking.start_at)!==dateLabel(booking.end_at)?dateLabel(booking.end_at)+' · ':''}${timeLabel(booking.end_at)}</p></div><div class="reservation-actions"><span class="badge ${booking.status==='cancelled'||ended?'cancelled':''}">${label}</span>${cancellable?`<button class="button secondary small" data-cancel="${booking.id}">Cancel reservation</button>`:''}</div></article>`;
  }).join('')}</div>`:empty(`No ${state.bookingView} reservations`,state.bookingView==='upcoming'?'Find something for your next project in the equipment library.':'Reservations will appear here when their status changes.',state.bookingView==='upcoming'?'<a class="button primary" href="#equipment">Browse equipment</a>':'');
  if(page.total>state.limit){$('#pagination').hidden=false;$('#pagination').innerHTML=`<button class="button secondary small" id="previous-page" ${state.offset===0?'disabled':''}>Previous</button><span>${state.offset+1}–${Math.min(state.offset+state.limit,page.total)} of ${page.total}</span><button class="button secondary small" id="next-page" ${state.offset+state.limit>=page.total?'disabled':''}>Next</button>`;}
}
function showAuth(mode='login'){
  state.authMode=mode;
  const register=mode==='register';
  $('#auth-title').textContent=register?'Make it your workspace':'Welcome back';
  $('#auth-description').textContent=register?'Create an account to reserve equipment for your next project.':'Sign in to reserve equipment and manage your bookings.';
  $('#name-field').hidden=!register; $('#auth-form').elements.name.required=register;
  $('#auth-form').elements.password.minLength=register?12:1;
  $('#auth-form').elements.password.autocomplete=register?'new-password':'current-password';
  $('#password-help').hidden=!register; $('#auth-submit').textContent=register?'Create account':'Sign in'; $('#auth-error').textContent='';
  $$('[data-auth-mode]').forEach(button=>button.classList.toggle('selected',button.dataset.authMode===mode));
  if(!$('#auth-dialog').open)$('#auth-dialog').showModal();
}
function showBooking(identifier){
  const item=state.equipment.find(item=>item.id===identifier);if(!item)return;
  if(!state.user){state.pendingItem=item;showAuth();return;}
  state.selected=item;const form=$('#booking-form');form.reset();
  form.elements.start_at.value=$('#filter-start').value;form.elements.end_at.value=$('#filter-end').value;
  $('#booking-title').textContent=item.name;$('#booking-location').textContent=item.location;$('#booking-error').textContent='';
  $('#booking-dialog').showModal();loadSchedule();
}
async function loadSchedule(){
  const sequence=++state.scheduleSequence;const form=$('#booking-form');
  const start=new Date(form.elements.start_at.value);if(!state.selected||!Number.isFinite(+start))return;
  const from=new Date(start);from.setHours(0,0,0,0);const to=new Date(from);to.setDate(to.getDate()+2);
  $('#schedule').textContent='Loading reserved times…';
  try{const rows=await api(`/equipment/${state.selected.id}/schedule?${new URLSearchParams({start_at:from.toISOString(),end_at:to.toISOString()})}`);if(sequence!==state.scheduleSequence)return;
    $('#schedule').innerHTML=rows.length?`<ul>${rows.map(row=>`<li>${dateLabel(row.start_at)} · ${timeLabel(row.start_at)} – ${dateLabel(row.start_at)!==dateLabel(row.end_at)?dateLabel(row.end_at)+' · ':''}${timeLabel(row.end_at)}</li>`).join('')}</ul>`:'No reservations on this day or the next. Availability is checked again when you confirm.';
  }catch(error){if(sequence===state.scheduleSequence)$('#schedule').textContent=error.message;}
}
function editEquipment(identifier=null){
  state.editing=identifier;const form=$('#equipment-form');form.reset();$('#equipment-error').textContent='';
  $('#equipment-title').textContent=identifier?'Edit equipment':'Add equipment';
  if(identifier){const item=state.equipment.find(item=>item.id===identifier);for(const key of ['name','location','category','description'])form.elements[key].value=item[key];form.elements.active.checked=item.active;}
  $('#equipment-dialog').showModal();
}
document.addEventListener('click',async event=>{
  const target=event.target.closest('button,a');if(!target)return;
  if(target.dataset.close){$('#'+target.dataset.close).close();return;}
  if(target.id==='sign-in'||target.hasAttribute('data-login')){showAuth();return;}
  if(target.dataset.authMode){showAuth(target.dataset.authMode);return;}
  if(target.id==='sign-out'){
    target.disabled=true;
    try{await api('/auth/logout',{method:'POST'});state.user=null;state.csrf='';state.pendingItem=null;renderAccount();toast('You have signed out.');await renderView();}catch(error){toast(error.message);target.disabled=false;}
    return;
  }
  if(target.hasAttribute('data-category')){state.category=target.dataset.category;state.offset=0;renderView();return;}
  if(target.dataset.bookingView){state.bookingView=target.dataset.bookingView;state.offset=0;renderView();return;}
  if(target.dataset.adminView){state.adminView=target.dataset.adminView;state.offset=0;renderView();return;}
  if(target.dataset.book){showBooking(Number(target.dataset.book));return;}
  if(target.dataset.edit){editEquipment(Number(target.dataset.edit));return;}
  if(target.id==='add-equipment'){editEquipment();return;}
  if(target.dataset.cancel){state.cancelling=state.bookings.find(item=>item.id===Number(target.dataset.cancel));$('#cancel-description').textContent=`${state.cancelling.equipment_name} · ${dateLabel(state.cancelling.start_at)}, ${timeLabel(state.cancelling.start_at)}`;$('#cancel-error').textContent='';$('#cancel-dialog').showModal();return;}
  if(target.id==='confirm-cancel'){
    target.disabled=true;
    try{await api(`/bookings/${state.cancelling.id}/cancel`,{method:'POST'});$('#cancel-dialog').close();toast('Reservation cancelled. The slot is available again.');state.offset=0;await renderView();}catch(error){$('#cancel-error').textContent=error.message;}finally{target.disabled=false;}
    return;
  }
  if(target.id==='reset-filters'){$('#search').value='';state.category='';state.offset=0;$('#available-only').checked=false;renderView();return;}
  if(target.id==='retry'){renderView();return;}
  if(target.id==='previous-page'){state.offset=Math.max(0,state.offset-(state.view==='equipment'?12:state.limit));renderView();return;}
  if(target.id==='next-page'){state.offset+=(state.view==='equipment'?12:state.limit);renderView();return;}
});
$('#search-form').addEventListener('submit',event=>{event.preventDefault();state.offset=0;renderView();});
$('#available-only').addEventListener('change',()=>{state.offset=0;renderView();});
$('#booking-form').elements.start_at.addEventListener('change',loadSchedule);
$('#auth-dialog').addEventListener('close',()=>{if(!state.user)state.pendingItem=null;$('#auth-form').elements.password.value='';});
$('#auth-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;busy(form,true);$('#auth-error').textContent='';
  const payload={email:form.elements.email.value.trim(),password:form.elements.password.value};if(state.authMode==='register')payload.name=form.elements.name.value.trim();
  try{const result=await api(`/auth/${state.authMode}`,{method:'POST',body:JSON.stringify(payload)});state.user=result.user;state.csrf=result.csrf_token;const pending=state.pendingItem;state.pendingItem=null;$('#auth-dialog').close();renderAccount();toast(state.authMode==='register'?'Your account is ready.':'Welcome back.');await renderView();if(pending&&state.view==='equipment')showBooking(pending.id);}
  catch(error){$('#auth-error').textContent=error.message;}finally{busy(form,false);}
});
$('#booking-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;busy(form,true);$('#booking-error').textContent='';
  try{const start=new Date(form.elements.start_at.value),end=new Date(form.elements.end_at.value);if(!Number.isFinite(+start)||!Number.isFinite(+end))throw new Error('Choose valid reservation times.');
    await api('/bookings',{method:'POST',body:JSON.stringify({equipment_id:state.selected.id,start_at:start.toISOString(),end_at:end.toISOString(),purpose:form.elements.purpose.value.trim()})});
    $('#booking-dialog').close();toast('Reservation confirmed. Find it in My reservations.');state.bookingView='upcoming';location.hash='bookings';
  }catch(error){$('#booking-error').textContent=error.message;loadSchedule();}finally{busy(form,false);}
});
$('#equipment-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;busy(form,true);$('#equipment-error').textContent='';
  const payload={};for(const key of ['name','location','category','description'])payload[key]=form.elements[key].value.trim();payload.active=form.elements.active.checked;
  try{await api(state.editing?`/admin/equipment/${state.editing}`:'/admin/equipment',{method:state.editing?'PUT':'POST',body:JSON.stringify(payload)});$('#equipment-dialog').close();toast('Equipment saved.');await renderView();}
  catch(error){$('#equipment-error').textContent=error.message;}finally{busy(form,false);}
});
window.addEventListener('hashchange',navigate);
async function boot(){
  try{const result=await api('/auth/me');state.user=result.user;state.csrf=result.csrf_token;}
  catch(error){if(error.status!==401)toast(error.message);}
  renderAccount();await navigate();
}
boot();
