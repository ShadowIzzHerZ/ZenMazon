// Colour theme: light, dark, or the system setting until the person picks one. Runs in <head> so the page never flashes.
(() => {
  const K = 'zen.theme', root = document.documentElement, mq = matchMedia('(prefers-color-scheme:dark)')
  const stored = () => { try { return localStorage.getItem(K) } catch { return null } }
  const apply = () => root.setAttribute('data-theme', stored() || (mq.matches ? 'dark' : 'light'))
  apply()
  mq.addEventListener('change', () => { if (!stored()) apply() })
  document.addEventListener('click', e => {
    if (!e.target.closest('[data-theme-toggle]')) return
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'
    try { localStorage.setItem(K, next) } catch {}
    apply()
  })
})()
