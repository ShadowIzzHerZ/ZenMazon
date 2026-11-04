// Batch run: 1,000 planned Indian corporate scenarios go through the policy engine two per second. Each one goes through,
// is revoked, or stops the run and asks a human. Mounts into <div id=batch> on the dashboard.
(() => {
  const mount = document.getElementById('batch')
  if (!mount) return
  document.head.insertAdjacentHTML('beforeend', `<style>
.br{margin-bottom:48px}.br h2{font-size:20px;line-height:28px;font-weight:600;margin:0 0 4px}.br .cap{max-width:680px;font-size:14px;color:var(--fg2);margin:0 0 20px}
.brc{display:flex;align-items:center;gap:16px;flex-wrap:wrap}.brc .btn{height:40px;padding:0 24px;font-weight:500}.brc .note{color:var(--fg3);font-size:13px}
.brsplit{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--raised);margin:20px 0 12px}.brsplit i{display:block;height:100%;transition:width .3s}
.brsplit .ok{background:var(--ok)}.brsplit .warn{background:var(--warn)}.brsplit .bad{background:var(--bad)}
.brleg{display:flex;gap:32px;flex-wrap:wrap}.brleg .n{font-size:28px;line-height:36px;font-weight:600;font-variant-numeric:tabular-nums}.brleg .k{display:flex;align-items:center;gap:8px;color:var(--fg2);font-size:13px}.brleg .k i{width:8px;height:8px;border-radius:2px}
.brhuman{margin:20px 0 0;padding:16px;border:1.5px solid var(--warn);border-radius:12px;background:var(--card);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.brhuman .t{flex:1;min-width:240px}.brhuman .h{font-size:12px;font-weight:500;color:var(--warn)}.brhuman .x{margin-top:4px}.brhuman .w{font-size:13px;color:var(--fg2);margin-top:4px}
.brhuman .a{display:flex;gap:8px}.brhuman .btn{height:36px;padding:0 16px}
.brlive{margin-top:20px;border-top:1px solid var(--line)}
.brtr{display:grid;grid-template-columns:72px minmax(0,1fr) 112px 160px minmax(0,1.1fr);gap:16px;align-items:center;min-height:48px;padding:8px 0;border-bottom:1px solid var(--line)}
.brtr.h{min-height:40px;font-size:11px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--fg2)}
.brtr .id{color:var(--fg3);font-size:12px}.brtr .amt{text-align:right;font-variant-numeric:tabular-nums}.brtr .why{font-size:13px;color:var(--fg2)}.brtr .why kbd{margin-right:8px}
.brtr.new{animation:brin .25s var(--ease) both}@keyframes brin{from{opacity:0;transform:translateY(-6px)}}
.brtabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-top:32px;flex-wrap:wrap}
.brtabs button{height:40px;padding:0 16px;border:0;border-bottom:2px solid transparent;background:none;color:var(--fg2);font:500 14px/1 Inter,system-ui,sans-serif;cursor:pointer;margin-bottom:-1px}
.brtabs button[aria-selected=true]{color:var(--fg);border-color:var(--accent)}.brtabs b{font-weight:400;color:var(--fg3);margin-left:6px}
.brscore{margin-top:20px;color:var(--fg2);font-size:14px}.brscore b{color:var(--fg);font-weight:600}
.brtoasts{position:fixed;left:16px;bottom:16px;display:flex;flex-direction:column-reverse;gap:8px;z-index:20;width:min(340px,calc(100vw - 32px));pointer-events:none}
.brtoast{display:grid;gap:4px;padding:12px 16px;border:1px solid var(--warn-bd);border-left:3px solid var(--warn);border-radius:12px;background:var(--card);box-shadow:0 4px 12px rgba(30,23,27,.12);animation:brt .3s var(--ease) both;transition:opacity .3s,transform .3s}
.brtoast.out{opacity:0;transform:translateX(-12px)}.brtoast .m{font-size:12px;font-weight:500;color:var(--warn)}.brtoast .t{font-size:13px;line-height:18px}
@keyframes brt{from{opacity:0;transform:translateX(-24px)}}
@media(max-width:900px){.brtr{grid-template-columns:1fr auto;gap:4px 16px}.brtr.h{display:none}.brtr .id,.brtr .why{grid-column:1/-1}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
</style>`)
  mount.innerHTML = `<section class=br><h2>Batch run</h2>
<p class=cap>1,000 planned Indian corporate scenarios: expense claims, payments and travel bookings, some with planted problems. Run feeds them to the policy engine two a second. Each one goes through, gets revoked, or stops the run and asks for a human. No AI model is called.</p>
<div class=brc><button class="btn primary" id=brRun>Run</button><button class=btn id=brStop hidden>Stop</button>
<label class=sw><input type=checkbox id=brPause checked>Pause for human approval</label><span class=note id=brNote></span></div>
<div id=brSum></div><div id=brHuman></div><div class=brlive id=brLive></div><div id=brRes></div></section><div class=brtoasts id=brToasts aria-hidden=true></div>`
  const $ = id => document.getElementById(id), esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
  const IC = { allow: '<svg viewBox="0 0 24 24"><path d="M5 12l5 5 9-10"/></svg>', approve: '<svg viewBox="0 0 24 24"><path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5v.01"/></svg>', deny: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/></svg>' }
  const LAB = { allow: 'Went through', approve: 'Needs approval', deny: 'Revoked', yes: 'Human approved', no: 'Human rejected' }
  const rs = n => n == null ? '' : 'Rs ' + Number(n).toLocaleString('en-IN')
  let D, k, c, timer, waiting, tab, shown
  const TABS = [['deny', 'Revoked'], ['approve', 'Asked a human'], ['allow', 'Went through'], ['miss', 'Missed']]
  const seen = () => D.rows.slice(0, k)
  const inTab = (r, t) => t === 'miss' ? (r.expected === 'deny' && r.verdict !== 'deny') : r.verdict === t

  function summary() {
    const n = D.n, w = c.through, v = c.revoked, h = c.human - c.decided
    $('brSum').innerHTML = `<div class=brsplit><i class=ok style="width:${w / n * 100}%"></i><i class=warn style="width:${h / n * 100}%"></i><i class=bad style="width:${v / n * 100}%"></i></div>
<div class=brleg><div><div class=k><i style="background:var(--ok)"></i>Went through</div><div class=n>${w}</div></div><div><div class=k><i style="background:var(--bad)"></i>Revoked</div><div class=n>${v}</div></div>
<div><div class=k><i style="background:var(--warn)"></i>Asked a human</div><div class=n>${c.human}</div></div><div><div class=k>Scenario</div><div class=n>${k}<span style="color:var(--fg3);font-size:16px"> / ${n}</span></div></div></div>`
  }
  const rowHTML = r => `<span class="id mono">${r.id}</span><span>${esc(r.text)}</span><span class="amt mono">${rs(r.amount)}</span><span class="verdict ${r.verdict}">${IC[r.verdict]}${LAB[r.verdict]}</span><span class=why>${r.rule ? `<kbd>${r.rule}</kbd>${esc(r.reason)}` : 'No rule applies'}</span>`
  function toast(r) {
    const box = $('brToasts'); while (box.children.length >= 3) box.firstChild.remove()
    const d = document.createElement('div'); d.className = 'brtoast'; d.innerHTML = `<span class=m>Needs approval</span><span class=t>${esc(r.text)}</span>`; box.appendChild(d)
    setTimeout(() => { d.classList.add('out'); setTimeout(() => d.remove(), 300) }, 3500)
  }
  function settle(r, ok) {  // a human decided: update counters, the feed row and the audit log
    c.decided++; ok ? c.through++ : c.revoked++
    const el = r.el; if (el) { const p = el.querySelector('.verdict'); p.className = 'verdict ' + (ok ? 'allow' : 'deny'); p.innerHTML = IC[ok ? 'allow' : 'deny'] + LAB[ok ? 'yes' : 'no'] }
    fetch('/api/batch/decide', { method: 'POST', body: JSON.stringify({ id: r.id, text: r.text, tool: r.tool, rule: r.rule, reason: r.reason, approve: ok }) }).catch(() => {})
  }
  function ask(r) {
    waiting = r
    $('brHuman').innerHTML = `<div class=brhuman role=alert><div class=t><div class=h>Human intervention needed</div><div class=x>${esc(r.text)}</div><div class=w><kbd>${r.rule}</kbd>${esc(r.reason)}</div></div><div class=a><button class="btn primary" id=brYes>Approve</button><button class=btn id=brNo>Reject</button></div></div>`
    const done = ok => { settle(r, ok); waiting = null; $('brHuman').innerHTML = ''; summary() }
    $('brYes').onclick = () => done(true); $('brNo').onclick = () => done(false); $('brYes').focus()
  }
  function tick() {
    if (waiting) return
    if (k >= D.n) return finish()
    const r = D.rows[k++]
    if (r.verdict === 'allow') c.through++; else if (r.verdict === 'deny') c.revoked++; else { c.human++; toast(r) }
    const row = document.createElement('div'); row.className = 'brtr new'; row.innerHTML = rowHTML(r); r.el = row
    $('brLive').prepend(row); while ($('brLive').children.length > 10) $('brLive').lastChild.remove()
    if (r.verdict === 'approve' && $('brPause').checked) ask(r)
    summary()
  }
  function table() {
    const rows = seen().filter(r => inTab(r, tab))
    $('brTabs').innerHTML = TABS.map(([t, l]) => `<button role=tab aria-selected=${t === tab} data-t=${t}>${l}<b>${seen().filter(r => inTab(r, t)).length}</b></button>`).join('')
    $('brTbl').innerHTML = rows.length ? `<div class="brtr h"><span>ID</span><span>Scenario</span><span style="text-align:right">Amount</span><span>Outcome</span><span>Rule</span></div>` + rows.slice(0, shown).map(r => `<div class=brtr>${rowHTML(r)}</div>`).join('') + (rows.length > shown ? `<button class=btn id=brMore style="margin-top:16px">Show ${Math.min(100, rows.length - shown)} more</button>` : '') : '<div style="color:var(--fg3);padding:24px 0">Nothing here</div>'
    if ($('brMore')) $('brMore').onclick = () => { shown += 100; table() }
  }
  function finish(stopped) {
    clearInterval(timer); waiting = null; $('brHuman').innerHTML = ''
    $('brStop').hidden = true; $('brRun').disabled = false; $('brRun').textContent = 'Run again'
    const bad = seen().filter(r => r.expected === 'deny'), caught = bad.filter(r => r.verdict === 'deny').length
    $('brNote').textContent = (stopped ? 'Stopped' : 'Finished') + ' at ' + k + ' of ' + D.n + '. Seed ' + D.seed
    $('brRes').innerHTML = `<div class=brscore>Of the <b>${bad.length}</b> planted violations seen, the rules caught <b>${caught}</b> and missed <b>${bad.length - caught}</b>.</div><div class=brtabs id=brTabs role=tablist></div><div id=brTbl></div>`
    tab = 'deny'; shown = 60; table()
    $('brRes').onclick = e => { const b = e.target.closest('[data-t]'); if (b) { tab = b.dataset.t; shown = 60; table() } }
  }
  $('brRun').onclick = async () => {
    $('brRun').disabled = true; $('brRun').textContent = 'Starting'; $('brRes').innerHTML = ''; $('brLive').innerHTML = ''; $('brHuman').innerHTML = ''
    D = await fetch('/api/batch', { method: 'POST', body: JSON.stringify({ n: 1000 }) }).then(r => r.json()).catch(e => ({ error: String(e) }))
    if (D.error) { $('brNote').textContent = D.error; $('brRun').disabled = false; $('brRun').textContent = 'Run'; return }
    k = 0; waiting = null; c = { through: 0, revoked: 0, human: 0, decided: 0 }
    $('brRun').textContent = 'Running'; $('brStop').hidden = false; $('brNote').textContent = ''
    summary(); timer = setInterval(tick, 500)  // two scenarios a second
  }
  $('brStop').onclick = () => finish(true)
})()
