// Batch run: 2,000 planned Indian corporate scenarios go through the policy engine two per second. Each one goes through,
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
.brhuman{margin:12px 0 4px;padding:16px;border:1.5px solid var(--warn);border-radius:12px;background:var(--card);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.brhuman .t{flex:1;min-width:240px}.brhuman .h{font-size:12px;font-weight:500;color:var(--warn)}.brhuman .x{margin-top:4px}.brhuman .w{font-size:13px;color:var(--fg2);margin-top:4px}
.brhuman .a{display:flex;gap:8px}.brhuman .aiout{flex-basis:100%;font-size:13px;line-height:18px;color:var(--fg2)}.brhuman .aiout:empty{display:none}.brhuman .aiout b{color:var(--fg);font-weight:500}.brhuman .btn{height:36px;padding:0 16px}
.brlive{margin-top:20px;border-top:1px solid var(--line)}
/* fixed-size areas while a run is going, so nothing above the graph changes height and the page never shifts */
.br.has .brlive{height:540px;overflow:hidden}.br.has #brSum{min-height:104px}.br *,.br{overflow-anchor:none}
.brtr{display:grid;grid-template-columns:72px minmax(0,1fr) 112px 160px minmax(0,1.1fr);gap:16px;align-items:center;min-height:48px;padding:8px 0;border-bottom:1px solid var(--line)}
.brtr .mono{font-family:inherit;font-variant-numeric:tabular-nums}
.brtr.act{grid-template-columns:72px minmax(0,1fr) 112px 160px minmax(0,1fr) 236px}
.racts{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.racts .btn{height:32px;padding:0 12px;font-size:13px}
.rai{grid-column:1/-1;font-size:13px;line-height:18px;color:var(--fg2);padding-bottom:4px}.rai:empty{display:none}.rai b{color:var(--fg);font-weight:500}
.brtr.h{min-height:40px;font-size:11px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--fg2)}
.brtr .id{color:var(--fg3);font-size:12px}.brtr .amt{text-align:right;font-variant-numeric:tabular-nums}.brtr .why{font-size:13px;color:var(--fg2)}.brtr .why kbd{margin-right:8px}
.brw{display:grid;grid-template-rows:0fr;opacity:0;transition:grid-template-rows .45s var(--ease),opacity .45s var(--ease)}
.brw.open{grid-template-rows:1fr;opacity:1}.brw.close{grid-template-rows:0fr;opacity:0}.brw>.in{overflow:hidden;min-height:0}
@media(prefers-reduced-motion:reduce){.brw{transition:none}}
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
  mount.innerHTML = `<section class=br id=brSec>
<div class=brc><button class="btn primary" id=brRun>Run</button><button class=btn id=brStop hidden>Stop</button>
<label class=sw><input type=checkbox id=brPause checked>Pause for human approval</label><span class=note id=brNote></span></div>
<div id=brSum></div><div class=brlive id=brLive><div id=brHuman></div><div id=brRows></div></div><div id=brRes></div></section><div class=brtoasts id=brToasts aria-hidden=true></div>`
  const $ = id => document.getElementById(id), esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
  const IC = { allow: '<svg viewBox="0 0 24 24"><path d="M5 12l5 5 9-10"/></svg>', approve: '<svg viewBox="0 0 24 24"><path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5v.01"/></svg>', deny: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/></svg>' }
  const LAB = { allow: 'Went through', approve: 'Needs approval', deny: 'Revoked', yes: 'Human approved', no: 'Human rejected', yesAI: 'Accepted using AI', noAI: 'Rejected using AI' }
  const rs = n => n == null ? '' : 'Rs ' + Number(n).toLocaleString('en-IN')
  let D, k, c, timer, waiting, tab, shown
  const TABS = [['deny', 'Revoked'], ['approve', 'Asked a human'], ['allow', 'Went through'], ['miss', 'Missed']]
  const seen = () => D.rows.slice(0, k)
  const inTab = (r, t) => t === 'miss' ? (r.expected === 'deny' && r.verdict !== 'deny') : r.verdict === t

  function summary() {
    document.dispatchEvent(new CustomEvent('zen:batch', { detail: { k, n: D.n, c: { ...c } } }))  // the dashboard chart follows the run
    const n = D.n, w = c.through, v = c.revoked, h = c.human - c.decided
    $('brSum').innerHTML = `<div class=brsplit><i class=ok style="width:${w / n * 100}%"></i><i class=warn style="width:${h / n * 100}%"></i><i class=bad style="width:${v / n * 100}%"></i></div>
<div class=brleg><div><div class=k><i style="background:var(--ok)"></i>Went through</div><div class=n>${w}</div></div><div><div class=k><i style="background:var(--bad)"></i>Revoked</div><div class=n>${v}</div></div>
<div><div class=k><i style="background:var(--warn)"></i>Asked a human</div><div class=n>${c.human}</div></div><div><div class=k>Scenario</div><div class=n>${k}<span style="color:var(--fg3);font-size:16px"> / ${n}</span></div></div></div>`
  }
  const rowHTML = r => { const d = r.decision, cls = d ? (d.startsWith('yes') ? 'allow' : 'deny') : r.verdict; return `<span class="id mono">${r.id}</span><span>${esc(r.text)}</span><span class="amt mono">${rs(r.amount)}</span><span class="verdict ${cls}">${IC[cls]}${d ? LAB[d] : LAB[r.verdict]}</span><span class=why>${r.rule ? `<kbd>${r.rule}</kbd>${esc(r.reason)}` : 'No rule applies'}</span>` }
  function toast(r) {
    const box = $('brToasts'); while (box.children.length >= 3) box.firstChild.remove()
    const d = document.createElement('div'); d.className = 'brtoast'; d.innerHTML = `<span class=m>Needs approval</span><span class=t>${esc(r.text)}</span>`; box.appendChild(d)
    setTimeout(() => { d.classList.add('out'); setTimeout(() => d.remove(), 300) }, 3500)
  }
  function settle(r, ok, by) {  // a human decided: update counters, the feed row and the audit log
    c.decided++; ok ? c.through++ : c.revoked++
    r.decision = (ok ? 'yes' : 'no') + (by === 'ai' ? 'AI' : '')
    const el = r.el; if (el) { const p = el.querySelector('.verdict'); p.className = 'verdict ' + (ok ? 'allow' : 'deny'); p.innerHTML = IC[ok ? 'allow' : 'deny'] + LAB[(ok ? 'yes' : 'no') + (by === 'ai' ? 'AI' : '')] }
    fetch('/api/batch/decide', { method: 'POST', body: JSON.stringify({ id: r.id, text: r.text, tool: r.tool, rule: r.rule, reason: r.reason, amount: r.amount, approve: ok, by }) }).then(() => document.dispatchEvent(new Event('zen:decided'))).catch(() => {})
  }
  function ask(r) {
    waiting = r
    $('brHuman').innerHTML = `<div class=brhuman role=alert><div class=t><div class=h>Human intervention needed</div><div class=x>${esc(r.text)}</div><div class=w><kbd>${r.rule}</kbd>${esc(r.reason)}</div></div><div class=a><button class="btn primary" id=brYes>Approve</button><button class=btn id=brNo>Reject</button><button class=btn id=brAsk>Ask AI</button></div><div class=aiout id=brAI></div></div>`
    const done = (ok, by) => { settle(r, ok, by); waiting = null; $('brHuman').innerHTML = ''; summary() }
    $('brAsk').onclick = async () => { const o = $('brAI'); o.innerHTML = '<b>Ask AI</b> Thinking'; const a = await fetch('/api/advise', { method: 'POST', body: JSON.stringify({ tool: r.tool, text: r.text, rule: r.rule, reason: r.reason, args: { amount: r.amount } }) }).then(x => x.json()).catch(e => ({ error: String(e) })); o.innerHTML = '<b>Ask AI</b> ' + esc(a.advice || a.error || 'No answer')
      if (a.decision === 'approve' || a.decision === 'reject') { $('brYes').disabled = $('brNo').disabled = $('brAsk').disabled = true; await new Promise(x => setTimeout(x, 1200)); done(a.decision === 'approve', 'ai') }
      else if (a.advice) o.innerHTML += ' <b>The AI is not sure, so the decision is yours.</b>' }
    $('brYes').onclick = () => done(true); $('brNo').onclick = () => done(false); $('brYes').focus({ preventScroll: true })
  }
  function tick() {
    if (waiting) return
    if (k >= D.n) return finish()
    const r = D.rows[k++]
    if (r.expected === 'deny') { c.by[r.kind].b++; if (r.verdict !== 'deny') c.by[r.kind].g++ }  // b: would have run without the policy layer, g: ran anyway
    if (r.verdict === 'allow') c.through++; else if (r.verdict === 'deny') c.revoked++; else { c.human++; toast(r) }
    const row = document.createElement('div'); row.className = 'brtr'; row.innerHTML = rowHTML(r); r.el = row
    const wrap = document.createElement('div'); wrap.className = 'brw'; wrap.innerHTML = '<div class=in></div>'; wrap.firstChild.append(row)
    $('brRows').prepend(wrap)  // the new row opens from zero height, so the rows below slide down instead of jumping
    requestAnimationFrame(() => requestAnimationFrame(() => wrap.classList.add('open')))
    const live = [...$('brRows').children].filter(x => !x.classList.contains('close'))
    for (const old of live.slice(10)) { old.classList.add('close'); setTimeout(() => old.remove(), 500) }
    if (r.verdict === 'approve' && $('brPause').checked) ask(r)
    summary()
  }
  function table() {
    const rows = seen().filter(r => inTab(r, tab))
    $('brTabs').innerHTML = TABS.map(([t, l]) => `<button role=tab aria-selected=${t === tab} data-t=${t}>${l}<b>${seen().filter(r => inTab(r, t)).length}</b></button>`).join('')
    const act = tab === 'approve'  // scenarios that asked for a human can be decided here too
    const acts = r => r.decision ? '' : `<span class=racts><button class="btn primary" data-a=yes data-id=${r.id}>Approve</button><button class=btn data-a=no data-id=${r.id}>Reject</button><button class=btn data-a=ai data-id=${r.id}>Ask AI</button></span>`
    $('brTbl').innerHTML = rows.length ? `<div class="brtr h${act ? ' act' : ''}"><span>ID</span><span>Scenario</span><span style="text-align:right">Amount</span><span>Outcome</span><span>Rule</span>${act ? '<span></span>' : ''}</div>` + rows.slice(0, shown).map(r => `<div class="brtr${act ? ' act' : ''}">${rowHTML(r)}${act ? acts(r) + `<span class=rai id=rai${r.id}></span>` : ''}</div>`).join('') + (rows.length > shown ? `<button class=btn id=brMore style="margin-top:16px">Show ${Math.min(100, rows.length - shown)} more</button>` : '') : '<div style="color:var(--fg3);padding:24px 0">Nothing here</div>'
    if ($('brMore')) $('brMore').onclick = () => { shown += 100; table() }
  }
  function finish(stopped) {
    clearInterval(timer); waiting = null; $('brHuman').innerHTML = ''; $('brSec').classList.remove('run'); $('brRes').style.minHeight = ''
    $('brStop').hidden = true; $('brRun').disabled = false; $('brRun').textContent = 'Run again'
    const bad = seen().filter(r => r.expected === 'deny'), caught = bad.filter(r => r.verdict === 'deny').length
    $('brNote').textContent = (stopped ? 'Stopped' : 'Finished') + ' at ' + k + ' of ' + D.n + '. Seed ' + D.seed
    $('brRes').innerHTML = `<div class=brscore>Of the <b>${bad.length}</b> planted violations seen, the rules caught <b>${caught}</b> and missed <b>${bad.length - caught}</b>.</div><div class=brtabs id=brTabs role=tablist></div><div id=brTbl></div>`
    tab = 'deny'; shown = 60; table()
    $('brRes').onclick = async e => {
      const b = e.target.closest('[data-t]'); if (b) { tab = b.dataset.t; shown = 60; table(); return }
      const a = e.target.closest('[data-a]'); if (!a) return
      const r = D.rows.find(x => x.id === a.dataset.id), out = $('rai' + r.id), decide = (ok, by) => { settle(r, ok, by); summary(); table() }
      if (a.dataset.a !== 'ai') return decide(a.dataset.a === 'yes', 'human')
      out.innerHTML = '<b>Ask AI</b> Thinking'
      const x = await fetch('/api/advise', { method: 'POST', body: JSON.stringify({ tool: r.tool, text: r.text, rule: r.rule, reason: r.reason, args: { amount: r.amount } }) }).then(y => y.json()).catch(err => ({ error: String(err) }))
      out.innerHTML = '<b>Ask AI</b> ' + esc(x.advice || x.error || 'No answer')
      if (x.decision === 'approve' || x.decision === 'reject') { await new Promise(y => setTimeout(y, 1200)); decide(x.decision === 'approve', 'ai') }
      else if (x.advice) out.innerHTML += ' <b>The AI is not sure, so the decision is yours.</b>'
    }
  }
  $('brRun').onclick = async () => {
    $('brRun').disabled = true; $('brRun').textContent = 'Starting'
    $('brSec').classList.add('has', 'run')
    $('brRes').style.minHeight = $('brRes').offsetHeight + 'px'  // keep the old results' height until the run ends so the page below does not jump
    $('brRes').innerHTML = ''; $('brRows').innerHTML = ''; $('brHuman').innerHTML = ''
    D = await fetch('/api/batch', { method: 'POST', body: JSON.stringify({ n: 2000 }) }).then(r => r.json()).catch(e => ({ error: String(e) }))
    if (D.error) { $('brNote').textContent = D.error; $('brRun').disabled = false; $('brRun').textContent = 'Run'; return }
    k = 0; waiting = null; c = { through: 0, revoked: 0, human: 0, decided: 0, by: { claim: { b: 0, g: 0 }, payment: { b: 0, g: 0 }, booking: { b: 0, g: 0 } } }
    $('brRun').textContent = 'Running'; $('brStop').hidden = false; $('brNote').textContent = ''
    summary(); timer = setInterval(tick, 500)  // two scenarios a second
  }
  $('brStop').onclick = () => finish(true)
})()
