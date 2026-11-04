// Supabase Auth over plain REST (no SDK). Session lives in localStorage; every /api call gets the access token.
const AUTH = (() => {
  const K = 'zen.session'
  let cfg = null
  const get = () => { try { return JSON.parse(localStorage.getItem(K)) } catch { return null } }
  const put = s => { try { s ? localStorage.setItem(K, JSON.stringify(s)) : localStorage.removeItem(K) } catch {} }
  const config = async () => cfg || (cfg = await fetch('/api/config').then(r => r.json()))
  const keep = d => { const s = { access_token: d.access_token, refresh_token: d.refresh_token, expires_at: Date.now() / 1000 + d.expires_in, email: d.user.email }; put(s); return s }
  const call = async (path, body) => {
    const c = await config()
    const r = await fetch(c.url + '/auth/v1/' + path, { method: 'POST', headers: { apikey: c.key, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const d = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(d.msg || d.error_description || d.message || 'Request failed')
    return d
  }
  const token = async () => {
    const s = get()
    if (!s) return null
    if (s.expires_at - 30 > Date.now() / 1000) return s.access_token
    try { return keep(await call('token?grant_type=refresh_token', { refresh_token: s.refresh_token })).access_token } catch { put(null); return null }
  }
  return {
    config, get, token,
    login: async (email, password) => keep(await call('token?grant_type=password', { email, password })),
    signup: async (email, password) => { const d = await call('signup', { email, password }); return d.access_token ? keep(d) : null },
    logout: () => { put(null); location.href = '/' },
  }
})()

// Same-origin /api calls carry the token; a 401 sends the person back to the landing page.
const _fetch = window.fetch
window.fetch = async (url, opts = {}) => {
  if (typeof url !== 'string' || !url.startsWith('/api/') || url === '/api/config') return _fetch(url, opts)
  const c = await AUTH.config()
  if (c.auth) {
    const t = await AUTH.token()
    if (!t) { location.href = '/'; return new Promise(() => {}) }
    opts = { ...opts, headers: { ...opts.headers, Authorization: 'Bearer ' + t } }
  }
  const r = await _fetch(url, opts)
  if (r.status === 401 && c.auth) { AUTH.logout(); return new Promise(() => {}) }
  return r
}

// Account chip, bottom right. Pages put <div class=acct id=acct></div> where it belongs.
document.head.insertAdjacentHTML('beforeend', `<style>
.acct{position:fixed;right:16px;bottom:16px;z-index:5;display:flex;align-items:center;gap:12px;height:40px;padding:0 8px 0 8px;border:1px solid var(--line);border-radius:12px;background:var(--card);font-size:13px;color:var(--fg2)}
.acct .av{width:24px;height:24px;border-radius:12px;background:var(--accent);color:var(--on-accent,#fff);display:grid;place-items:center;font-size:12px;font-weight:500;text-transform:uppercase}
.acct .em{max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--fg)}
.acct button{border:0;background:none;color:var(--fg3);font:inherit;cursor:pointer;padding:0}.acct button:hover{color:var(--fg)}
</style>`)
AUTH.config().then(c => {
  const el = document.getElementById('acct')
  if (!el) return
  const email = c.auth ? (AUTH.get() || {}).email || '' : 'local mode'
  const mk = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls, textContent: text })
  const em = mk('span', 'em', email)
  em.title = email
  el.append(mk('span', 'av', email[0] || '?'), em)
  if (c.auth) { const b = mk('button', '', 'Sign out'); b.onclick = AUTH.logout; el.append(b) }
})
