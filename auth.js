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
    logout: () => { put(null); if (location.pathname !== '/') location.href = '/' },
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
  if (r.status === 401 && c.auth) { AUTH.logout(); if (location.pathname !== '/') return new Promise(() => {}) }
  return r
}

// Account menu, top right: a profile circle that opens email, page links and Sign out. Pages put <div class=acct id=acct></div> in their top bar.
document.head.insertAdjacentHTML('beforeend', `<style>
.acct{position:relative;flex:none}
.acct .av{width:32px;height:32px;border-radius:16px;border:0;background:var(--accent);color:var(--on-accent,#fff);display:grid;place-items:center;font:600 13px/1 Inter,system-ui,sans-serif;text-transform:uppercase;cursor:pointer;padding:0;transition:box-shadow 150ms}
.acct .av:hover,.acct .av[aria-expanded=true]{box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 25%,transparent)}
.acct .menu{position:absolute;right:0;top:40px;z-index:30;min-width:232px;padding:8px;border:1px solid var(--line-strong,var(--line));border-radius:12px;background:var(--card);box-shadow:0 1px 2px rgba(30,23,27,.05),0 8px 24px rgba(30,23,27,.14)}
.acct .menu[hidden]{display:none}
.acct .who{padding:8px 12px 12px;border-bottom:1px solid var(--line);margin-bottom:8px}
.acct .who small{display:block;color:var(--fg3);font-size:12px;line-height:16px}.acct .who b{display:block;font-weight:500;font-size:14px;line-height:20px;color:var(--fg);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:208px}
.acct .menu a,.acct .menu button{display:block;width:100%;height:36px;line-height:36px;padding:0 12px;border:0;border-radius:8px;background:none;color:var(--fg2);font:400 14px/36px Inter,system-ui,sans-serif;text-align:left;cursor:pointer;text-decoration:none}
.acct .menu a:hover,.acct .menu button:hover{background:var(--raised);color:var(--fg)}
.acct .menu hr{border:0;border-top:1px solid var(--line);margin:8px 0}
</style>`)
AUTH.config().then(c => {
  const el = document.getElementById('acct')
  if (!el) return
  const email = c.auth ? (AUTH.get() || {}).email || '' : 'local mode'
  const mk = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls, textContent: text })
  const av = mk('button', 'av', email[0] || '?')
  av.setAttribute('aria-haspopup', 'menu'); av.setAttribute('aria-expanded', 'false'); av.setAttribute('aria-label', 'Account menu'); av.title = email
  const menu = mk('div', 'menu'); menu.hidden = true; menu.setAttribute('role', 'menu')
  const who = mk('div', 'who'); who.append(mk('small', '', 'Signed in as'), mk('b', '', email)); menu.append(who)
  for (const [t, h] of [['Chat', '/app'], ['Dashboard', '/dashboard'], ['Policies', '/policies']].filter(x => x[1] !== location.pathname)) { const a = mk('a', '', t); a.href = h; a.setAttribute('role', 'menuitem'); menu.append(a) }
  if (c.auth) { menu.append(document.createElement('hr')); const b = mk('button', '', 'Sign out'); b.setAttribute('role', 'menuitem'); b.onclick = AUTH.logout; menu.append(b) }
  const toggle = open => { menu.hidden = !open; av.setAttribute('aria-expanded', String(open)) }
  av.onclick = e => { e.stopPropagation(); toggle(menu.hidden) }
  document.addEventListener('click', e => { if (!el.contains(e.target)) toggle(false) })
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { toggle(false); av.focus() } })
  el.append(av, menu)
})
