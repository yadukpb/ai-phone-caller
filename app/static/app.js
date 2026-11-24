const $ = (s) => document.querySelector(s);
const apiKey = () => localStorage.getItem('callroom-api-key') || '';
const headers = () => apiKey() ? {'X-API-Key': apiKey()} : {};
let calls = [];

async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type': 'application/json', ...headers(), ...(options.headers || {})}});
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `Request failed (${response.status})`);
  return response.json();
}
function toast(message, error = false) { const el = $('#toast'); el.textContent = message; el.style.background = error ? '#a54e47' : '#173f32'; el.classList.add('show'); setTimeout(() => el.classList.remove('show'), 3000); }
function badge(status) { return `<span class="badge ${status}">${String(status || '').replaceAll('_', ' ')}</span>`; }
function date(value) { return value ? new Date(value).toLocaleString([], {month:'short', day:'numeric', hour:'numeric', minute:'2-digit'}) : '—'; }
function callRow(call, full = false) { return `<tr><td>${call.phone_number || '—'}</td><td>${call.agent_id || '—'}</td>${full ? `<td>${call.tts_model || '—'}</td>` : ''}<td>${badge(call.status)}</td>${full ? `<td class="mono">${(call.call_id || '').slice(0,8)}…</td>` : `<td>${date(call.created_at || call.started_at)}</td><td>→</td>`}</tr>`; }
function renderCalls() { $('#recent-calls').innerHTML = calls.length ? calls.slice(0,5).map(c => callRow(c)).join('') : '<tr><td colspan="5" class="empty">No calls yet. Start your first conversation.</td></tr>'; $('#all-calls').innerHTML = calls.length ? calls.map(c => callRow(c, true)).join('') : '<tr><td colspan="5" class="empty">No calls yet.</td></tr>'; $('#nav-call-count').textContent = calls.length; $('#metric-total').textContent = calls.length; $('#metric-active').textContent = calls.filter(c => ['queued','starting','in_progress'].includes(c.status)).length; $('#metric-completed').textContent = calls.filter(c => c.status === 'completed').length; }
async function loadCalls() { try { calls = await api('/v1/calls?limit=200'); renderCalls(); } catch (e) { toast(e.message, true); } }
async function loadHealth() { try { const health = await api('/health'); $('#mode-label').textContent = health.dry_run ? 'Dry run mode' : 'Live calling enabled'; $('#provider-label').textContent = health.dry_run ? 'No carrier calls placed' : 'Provider: connected'; } catch(e) { $('#provider-label').textContent = 'API unavailable'; } }
async function loadCampaigns() { try { const items = await api('/v1/campaigns'); $('#campaign-list').innerHTML = items.length ? items.map(c => `<div class="metric"><div class="eyebrow">${c.status || 'DRAFT'}</div><h3>${c.name}</h3><p class="muted">${c.agent_id} · ${c.calls_per_minute} calls/min</p></div>`).join('') : '<div class="empty-card">No campaigns yet. Campaign creation can be added from the API.</div>'; } catch(e) { toast(e.message, true); } }
function showView(view) { document.querySelectorAll('.view').forEach(v => v.classList.add('hidden')); $(`#${view}-view`).classList.remove('hidden'); document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view)); $('#page-title').textContent = view === 'overview' ? 'Good morning, operator' : view[0].toUpperCase() + view.slice(1); if(view === 'campaigns') loadCampaigns(); }
document.querySelectorAll('.nav-item').forEach(n => n.addEventListener('click', () => showView(n.dataset.view))); document.querySelectorAll('[data-view-link]').forEach(n => n.addEventListener('click', () => showView(n.dataset.viewLink))); $('#refresh-calls').addEventListener('click', loadCalls); $('#refresh-campaigns').addEventListener('click', loadCampaigns); $('#new-call-button').addEventListener('click', () => $('#call-dialog').showModal());
$('#call-form').addEventListener('submit', async (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.target)); try { await api('/v1/calls', {method:'POST', body:JSON.stringify(data)}); event.target.reset(); $('#call-dialog').close(); toast('Call queued successfully'); await loadCalls(); } catch(e) { toast(e.message, true); } });
$('#api-key-button').addEventListener('click', () => { $('#api-key-input').value = apiKey(); $('#key-dialog').showModal(); }); $('#key-form').addEventListener('submit', (e) => { e.preventDefault(); localStorage.setItem('callroom-api-key', $('#api-key-input').value); $('#key-dialog').close(); toast('API key saved in this browser'); loadCalls(); });
loadHealth(); loadCalls();
