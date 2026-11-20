import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import * as api from './api.js'

/* ---------- helpers ---------- */

const HUES = ['#158b83', '#4c7fe8', '#8067c7', '#d89042', '#b0532f', '#2f8f5b']
const kbHue = (kbs, id) => HUES[Math.max(0, kbs.findIndex((k) => k.id === id)) % HUES.length]

const STATUS = {
  pending: { cls: 'gray', label: '排队中' },
  processing: { cls: 'amber', label: '处理中' },
  ready: { cls: '', label: '已就绪' },
  failed: { cls: 'red', label: '失败' },
}

const fmtSize = (n) => {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

const fmtTime = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (x) => String(x).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const extGlyph = (name) => {
  const ext = (name.split('.').pop() || '').toLowerCase()
  return { pdf: '▤', doc: '¶', docx: '¶', xls: '▦', xlsx: '▦', csv: '▦', ppt: '◧', pptx: '◧', md: '✎', txt: '✎', html: '❮' }[ext] || '▤'
}

const escapeReg = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function Highlight({ text, terms }) {
  const uniq = [...new Set((terms || []).filter(Boolean))].sort((a, b) => b.length - a.length)
  if (!uniq.length) return text
  const re = new RegExp(`(${uniq.map(escapeReg).join('|')})`, 'gi')
  const parts = String(text).split(re)
  return parts.map((p, i) => (i % 2 === 1 ? <mark key={i}>{p}</mark> : <React.Fragment key={i}>{p}</React.Fragment>))
}

/* ---------- toast ---------- */

const ToastCtx = createContext(() => {})
const useToast = () => useContext(ToastCtx)

function ToastHost({ toasts, dismiss }) {
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind || ''}`}>
          <span>{t.msg}</span>
          {t.action && (
            <button type="button" onClick={() => { t.action.onClick(); dismiss(t.id) }}>{t.action.label}</button>
          )}
          <button type="button" aria-label="关闭提示" onClick={() => dismiss(t.id)}>✕</button>
        </div>
      ))}
    </div>
  )
}

/* ---------- overlays ---------- */

function Drawer({ open, onClose, title, sub, children, foot }) {
  const ref = useRef(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.inert = !open
    el.setAttribute('aria-hidden', String(!open))
  }, [open])
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') closeRef.current() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])
  return (
    <>
      <div className={`scrim ${open ? 'open' : ''}`} onClick={onClose} />
      <div ref={ref} className={`drawer ${open ? 'open' : ''}`} role="dialog" aria-label={title || '详情'}>
        <div className="drawer-head">
          <div>
            <h3>{title}</h3>
            {sub && <small>{sub}</small>}
          </div>
          <button type="button" className="x-btn" aria-label="关闭" onClick={onClose}>✕</button>
        </div>
        <div className="drawer-body">{children}</div>
        {foot && <div className="drawer-foot">{foot}</div>}
      </div>
    </>
  )
}

function Modal({ open, onClose, title, children, foot }) {
  const ref = useRef(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.inert = !open
    el.setAttribute('aria-hidden', String(!open))
    if (open) {
      const f = el.querySelector('input, select, textarea')
      if (f) setTimeout(() => f.focus(), 60)
    }
  }, [open])
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') closeRef.current() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])
  return (
    <>
      <div className={`scrim ${open ? 'open' : ''}`} style={{ zIndex: 92 }} onClick={onClose} />
      <div ref={ref} className={`modal ${open ? 'open' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button type="button" className="x-btn" aria-label="关闭" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">{children}</div>
        {foot && <div className="modal-foot">{foot}</div>}
      </div>
    </>
  )
}

/* ---------- small pieces ---------- */

const StatusPill = ({ status }) => {
  const s = STATUS[status] || { cls: 'gray', label: status || '未知' }
  return <span className={`status ${s.cls}`}><i className="dot" />{s.label}</span>
}

const Loading = ({ label = '加载中…' }) => (
  <div className="loading"><span className="spinner" />{label}</div>
)

const Empty = ({ glyph = '▤', children, action }) => (
  <div className="empty">
    <span className="glyph">{glyph}</span>
    <p>{children}</p>
    {action}
  </div>
)

const ErrorBanner = ({ msg, onRetry }) => (
  <div className="error-banner" role="alert">
    <span className="glyph">⚠</span>
    <span style={{ flex: 1 }}>{msg}</span>
    {onRetry && <button type="button" className="button sm" onClick={onRetry}>重试</button>}
  </div>
)

function Switch({ on, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={`switch ${on ? 'on' : ''}`}
      onClick={() => onChange(!on)}
    />
  )
}

function Segmented({ value, options, onChange }) {
  return (
    <div className="seg" role="tablist">
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" aria-selected={value === o.value}
          className={value === o.value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

function Stepper({ value, min, max, onChange }) {
  return (
    <div className="stepper">
      <button type="button" aria-label="减少" disabled={value <= min} onClick={() => onChange(Math.max(min, value - 1))}>−</button>
      <span className="val">{value}</span>
      <button type="button" aria-label="增加" disabled={value >= max} onClick={() => onChange(Math.min(max, value + 1))}>＋</button>
    </div>
  )
}

function Pager({ page, pages, total, onPage }) {
  if (pages <= 1) return <div className="pager"><span>共 {total} 条</span></div>
  const nums = []
  for (let i = 1; i <= pages; i += 1) {
    if (i === 1 || i === pages || Math.abs(i - page) <= 1) nums.push(i)
    else if (nums[nums.length - 1] !== '…') nums.push('…')
  }
  return (
    <div className="pager">
      <span>共 {total} 条 · 第 {page}/{pages} 页</span>
      <div className="pages">
        <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹</button>
        {nums.map((n, i) => n === '…'
          ? <span key={`e${i}`} style={{ padding: '4px 2px' }}>…</span>
          : <button key={n} type="button" className={n === page ? 'on' : ''} onClick={() => onPage(n)}>{n}</button>)}
        <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>›</button>
      </div>
    </div>
  )
}

/* ---------- document drawer ---------- */

function DocDrawer({ doc, kbs, onClose, onReingest, onDelete, onDocUpdate }) {
  const toast = useToast()
  const [jobs, setJobs] = useState(null)
  const [jobsError, setJobsError] = useState(null)
  const [live, setLive] = useState(doc)
  const docId = doc?.id

  useEffect(() => { setLive(doc) }, [doc])

  useEffect(() => {
    if (!docId) return undefined
    let alive = true
    setJobs(null)
    setJobsError(null)
    api.documentJobs(docId)
      .then((list) => { if (alive) setJobs(list) })
      .catch((e) => { if (alive) setJobsError(api.errMsg(e)) })
    return () => { alive = false }
  }, [docId])

  const active = live && (live.status === 'pending' || live.status === 'processing')
  useEffect(() => {
    if (!docId || !active) return undefined
    const t = setInterval(() => {
      api.getDocument(docId)
        .then((d) => { setLive(d); onDocUpdate(d) })
        .catch(() => {})
    }, 3000)
    return () => clearInterval(t)
  }, [docId, active, onDocUpdate])

  const kb = kbs.find((k) => k.id === live?.knowledge_base_id)
  const ready = live?.status === 'ready'

  return (
    <Drawer
      open={!!doc}
      onClose={onClose}
      title={live?.filename || '文档详情'}
      sub={live ? `${live.id} · ${kb ? kb.name : '未知知识库'}` : ''}
      foot={live && (
        <>
          <button type="button" className="button primary sm" disabled={active}
            onClick={() => onReingest(live)}>↻ 重建索引</button>
          <a className="button sm" href={api.downloadOriginalUrl(live.id)} download>⇩ 原文</a>
          {ready
            ? <a className="button sm" href={api.downloadMarkdownUrl(live.id)} download>⇩ Markdown</a>
            : <button type="button" className="button sm" disabled title="处理完成后可下载">⇩ Markdown</button>}
          <button type="button" className="button danger sm" onClick={() => onDelete(live)}>删除文档</button>
        </>
      )}
    >
      {live && (
        <>
          <div className="meta-row"><label>状态</label><span><StatusPill status={live.status} /></span></div>
          <div className="meta-row"><label>所属知识库</label><span>{kb ? kb.name : live.knowledge_base_id}</span></div>
          <div className="meta-row"><label>解析器</label><span>{live.parser_name || '—'}</span></div>
          <div className="meta-row"><label>OCR</label><span>{live.ocr_used ? <span className="tag mcp">已启用</span> : '未使用'}</span></div>
          <div className="meta-row"><label>大小</label><span>{fmtSize(live.size_bytes)}</span></div>
          <div className="meta-row"><label>MIME</label><span>{live.content_type || '—'}</span></div>
          <div className="meta-row"><label>上传时间</label><span>{fmtTime(live.created_at)}</span></div>
          <div className="meta-row"><label>更新时间</label><span>{fmtTime(live.updated_at)}</span></div>
          {live.error && (
            <div className="error-banner" style={{ marginTop: 12, marginBottom: 0 }}>
              <span className="glyph">⚠</span><span style={{ flex: 1 }}>{live.error}</span>
            </div>
          )}
          <div className="mini-card" style={{ marginTop: 15 }}>
            <div className="mini-head">处理作业记录</div>
            {jobsError && <div style={{ padding: '10px 12px' }}><ErrorBanner msg={jobsError} /></div>}
            {!jobs && !jobsError && <Loading label="加载作业记录…" />}
            {jobs && jobs.length === 0 && <div className="kv"><span>暂无作业记录</span></div>}
            {jobs && jobs.map((j) => (
              <div className="kv" key={j.id} style={{ flexDirection: 'column', alignItems: 'stretch', gap: 4 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <b>{j.kind === 'reingest' ? '重建索引' : '入库处理'}</b>
                  <StatusPill status={j.status === 'done' ? 'ready' : j.status === 'running' ? 'processing' : j.status} />
                </div>
                <span>{fmtTime(j.created_at)}{j.finished_at ? ` → ${fmtTime(j.finished_at)}` : ''}</span>
                {j.error && <span style={{ color: '#b0532f' }}>{j.error}</span>}
              </div>
            ))}
          </div>
        </>
      )}
    </Drawer>
  )
}

/* ---------- bases view ---------- */

const PAGE = 8

function BasesView({ kbs, kbId, setKbId, docsVersion, bumpDocs, onNewKB, onDeleteKB, onDeleteDoc, onReingest, openDoc }) {
  const toast = useToast()
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('all')
  const [sort, setSort] = useState('newest')
  const [page, setPage] = useState(1)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)
  const kbIdRef = useRef(kbId)
  kbIdRef.current = kbId

  const load = useCallback(async (silent) => {
    const id = kbIdRef.current
    if (!id) { setDocs([]); return }
    if (!silent) { setLoading(true); setError(null) }
    try {
      const list = await api.listDocuments(id)
      if (kbIdRef.current === id) setDocs(list)
    } catch (e) {
      if (kbIdRef.current === id && !silent) setError(api.errMsg(e))
    } finally {
      if (kbIdRef.current === id && !silent) setLoading(false)
    }
  }, [])

  useEffect(() => { setPage(1); load() }, [kbId, docsVersion, load])

  const busy = docs.filter((d) => d.status === 'pending' || d.status === 'processing').length
  useEffect(() => {
    if (!busy) return undefined
    const t = setInterval(() => load(true), 4000)
    return () => clearInterval(t)
  }, [busy, load])

  const cur = kbs.find((k) => k.id === kbId)
  const ready = docs.filter((d) => d.status === 'ready').length
  const failed = docs.filter((d) => d.status === 'failed').length

  let list = docs
  if (q.trim()) {
    const needle = q.trim().toLowerCase()
    list = list.filter((d) => d.filename.toLowerCase().includes(needle))
  }
  if (status !== 'all') list = list.filter((d) => d.status === status)
  list = [...list].sort((a, b) => {
    if (sort === 'name') return a.filename.localeCompare(b.filename, 'zh-CN')
    if (sort === 'size') return b.size_bytes - a.size_bytes
    return new Date(b.created_at) - new Date(a.created_at)
  })
  const pages = Math.max(1, Math.ceil(list.length / PAGE))
  const safePage = Math.min(page, pages)
  const rows = list.slice((safePage - 1) * PAGE, safePage * PAGE)

  const doUpload = async (files) => {
    if (!files.length || !kbId) return
    setUploading(true)
    let ok = 0
    const errs = []
    for (const f of files) {
      try {
        await api.uploadDocument(kbId, f)
        ok += 1
      } catch (e) {
        errs.push(`${f.name}：${api.errMsg(e)}`)
      }
    }
    setUploading(false)
    if (ok) toast(`已上传 ${ok} 个文档，进入处理队列`, 'ok')
    if (errs.length) toast(`上传失败 ${errs.length} 个：${errs[0]}`, 'err')
    bumpDocs()
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">KNOWLEDGE HUB</div>
          <h1>{cur ? cur.name : '知识库'}</h1>
          <div className="subheading">
            {cur?.description || '选择一个知识库开始管理文档。'}
            {'　·　上传 → 解析 / OCR → Markdown → 切块 → 索引，每条命中可追溯到原文。'}
          </div>
        </div>
        <div className="toolbar">
          <button type="button" className="button" disabled={!kbId || uploading} onClick={() => fileRef.current?.click()}>
            {uploading ? <><span className="spinner" style={{ width: 11, height: 11 }} />上传中…</> : '⇧ 上传文档'}
          </button>
          <button type="button" className="button primary" onClick={onNewKB}>＋ 新建知识库</button>
          {cur && <button type="button" className="button danger" onClick={() => onDeleteKB(cur)}>删除当前库</button>}
        </div>
      </div>

      <input
        ref={fileRef}
        type="file"
        multiple
        style={{ display: 'none' }}
        onChange={(e) => { const files = [...e.target.files]; e.target.value = ''; doUpload(files) }}
      />

      {kbs.length > 0 && (
        <div className="kb-chips">
          {kbs.map((k) => (
            <button key={k.id} type="button" className={`kb-chip ${k.id === kbId ? 'on' : ''}`} onClick={() => setKbId(k.id)}>
              <strong><i className="kb-dot" style={{ background: kbHue(kbs, k.id) }} />{k.name}</strong>
              <small>{k.description || '暂无描述'}</small>
            </button>
          ))}
        </div>
      )}

      <div className="catalog-stats">
        <div className="stat-chip"><strong>{kbs.length}</strong>知识库</div>
        <div className="stat-chip"><strong>{docs.length}</strong>本文档库文档</div>
        <div className="stat-chip"><strong>{ready}</strong>已就绪</div>
        <div className={`stat-chip ${busy ? 'warn' : ''}`}><strong>{busy}</strong>处理中作业</div>
        {failed > 0 && <div className="stat-chip bad"><strong>{failed}</strong>失败待重建</div>}
      </div>

      {error && <ErrorBanner msg={error} onRetry={() => load()} />}

      <section className="card">
        <div className="card-head wrap">
          <h2>文档列表</h2>
          <div className="toolbar">
            <div className="search-box">
              <span className="glyph">⌕</span>
              <input value={q} placeholder="按文件名筛选…" aria-label="按文件名筛选" onChange={(e) => { setQ(e.target.value); setPage(1) }} />
            </div>
            <select className="select" value={status} aria-label="状态筛选" onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
              <option value="all">全部状态</option>
              <option value="pending">排队中</option>
              <option value="processing">处理中</option>
              <option value="ready">已就绪</option>
              <option value="failed">失败</option>
            </select>
            <select className="select" value={sort} aria-label="排序" onChange={(e) => setSort(e.target.value)}>
              <option value="newest">最新上传</option>
              <option value="name">名称</option>
              <option value="size">大小</option>
            </select>
            <button type="button" className="button sm" onClick={() => load()}>↻ 刷新</button>
          </div>
        </div>

        {loading && <Loading label="加载文档…" />}
        {!loading && !kbId && (
          <Empty glyph="▤" action={<button type="button" className="button primary" onClick={onNewKB}>＋ 新建知识库</button>}>
            还没有知识库。创建一个知识库，上传文档后即可检索。
          </Empty>
        )}
        {!loading && kbId && list.length === 0 && (
          <Empty glyph="⇧" action={docs.length === 0
            ? <button type="button" className="button primary" disabled={uploading} onClick={() => fileRef.current?.click()}>⇧ 上传第一个文档</button>
            : <button type="button" className="button" onClick={() => { setQ(''); setStatus('all') }}>清除筛选</button>}>
            {docs.length === 0 ? '这个知识库还是空的，上传 PDF / Word / Excel / Markdown 等文档开始构建索引。' : '没有符合筛选条件的文档。'}
          </Empty>
        )}
        {!loading && rows.length > 0 && (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>文档</th>
                  <th>状态</th>
                  <th className="hide-mobile">解析器</th>
                  <th className="hide-mobile">OCR</th>
                  <th className="hide-mobile">大小</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <div className="tool-title">
                        <span className="tool-symbol">{extGlyph(d.filename)}</span>
                        <span>
                          {d.filename}
                          <small className="tool-sub">{d.content_type || '未知类型'} · {fmtTime(d.created_at)}</small>
                        </span>
                      </div>
                    </td>
                    <td><StatusPill status={d.status} />{d.error && <small className="tool-sub" style={{ color: '#b0532f', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.error}>{d.error}</small>}</td>
                    <td className="hide-mobile">{d.parser_name || '—'}</td>
                    <td className="hide-mobile">{d.ocr_used ? <span className="tag mcp">OCR</span> : '—'}</td>
                    <td className="hide-mobile">{fmtSize(d.size_bytes)}</td>
                    <td>
                      <div className="row-actions">
                        <button type="button" className="text-link" onClick={() => openDoc(d)}>查看</button>
                        <button type="button" className="text-link" disabled={d.status === 'pending' || d.status === 'processing'}
                          style={(d.status === 'pending' || d.status === 'processing') ? { opacity: .4, cursor: 'default' } : undefined}
                          onClick={() => onReingest(d)}>重建</button>
                        <button type="button" className="text-link danger" onClick={() => onDeleteDoc(d)}>删除</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && list.length > 0 && <Pager page={safePage} pages={pages} total={list.length} onPage={setPage} />}
      </section>
    </div>
  )
}

/* ---------- search lab view ---------- */

const MODE_OPTIONS = [
  { value: 'hybrid', label: '混合检索' },
  { value: 'vector', label: '纯向量' },
  { value: 'keyword', label: '纯关键词' },
]
const MODE_LABEL = { hybrid: '混合检索', vector: '纯向量', keyword: '纯关键词' }

function ScoreChip({ kind, label, value, max }) {
  const pct = max > 0 ? Math.max(4, Math.min(100, (value / max) * 100)) : 0
  return (
    <span className={`score ${kind || ''}`} title={`${label} ${value.toFixed(4)}`}>
      {label} <b>{value.toFixed(3)}</b>
      <i style={{ width: `${pct}%` }} />
    </span>
  )
}

function SearchView({ kbs, openDocByRef }) {
  const toast = useToast()
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('hybrid')
  const [rerank, setRerank] = useState(true)
  const [topK, setTopK] = useState(8)
  const [sel, setSel] = useState([])
  const [searching, setSearching] = useState(false)
  const [result, setResult] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState(null)
  const [compare, setCompare] = useState(null)
  const [comparing, setComparing] = useState(false)

  useEffect(() => {
    setSel((prev) => {
      const ids = kbs.map((k) => k.id)
      const kept = prev.filter((id) => ids.includes(id))
      return kept.length ? kept : ids
    })
  }, [kbs])

  const toggleKb = (id) => setSel((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const run = async () => {
    const q = query.trim()
    if (!q) { toast('请输入检索问题', 'err'); return }
    setSearching(true)
    setError(null)
    setCompare(null)
    const t0 = performance.now()
    try {
      const res = await api.search({ query: q, kb_ids: sel, top_k: topK, rerank, mode })
      setResult(res)
      setElapsed(performance.now() - t0)
    } catch (e) {
      setError(api.errMsg(e))
    } finally {
      setSearching(false)
    }
  }

  const runCompare = async () => {
    const q = query.trim()
    if (!q) { toast('请输入检索问题', 'err'); return }
    setComparing(true)
    const variants = [
      { label: '纯向量', mode: 'vector', rerank: false },
      { label: '纯关键词', mode: 'keyword', rerank: false },
      { label: '混合 RRF', mode: 'hybrid', rerank: false },
      { label: '混合 + 重排', mode: 'hybrid', rerank: true },
    ]
    const out = []
    for (const v of variants) {
      const t0 = performance.now()
      try {
        const res = await api.search({ query: q, kb_ids: sel, top_k: topK, rerank: v.rerank, mode: v.mode })
        out.push({ ...v, count: res.chunks.length, top1: res.chunks[0]?.filename || '—', ms: performance.now() - t0, ok: true })
      } catch (e) {
        out.push({ ...v, count: 0, top1: api.errMsg(e), ms: performance.now() - t0, ok: false })
      }
    }
    setCompare(out)
    setComparing(false)
  }

  const copyContext = async () => {
    if (!result?.context) return
    try {
      await navigator.clipboard.writeText(result.context)
      toast('上下文已复制到剪贴板', 'ok')
    } catch {
      toast('复制失败，请手动选择文本复制', 'err')
    }
  }

  const chunks = result?.chunks || []
  const terms = result ? [...(result.analysis?.terms || []), ...(result.analysis?.quoted || [])] : []
  const maxOf = (field) => Math.max(0, ...chunks.map((c) => c[field] || 0))
  const maxDense = maxOf('dense_score')
  const maxSparse = maxOf('sparse_score')
  const maxFused = maxOf('fused_score')
  const maxRerank = maxOf('rerank_score')
  const ctxChars = result?.context?.length || 0

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">RETRIEVAL LAB</div>
          <h1>检索实验室</h1>
          <div className="subheading">Query Analyzer → 向量召回 + BM25 → RRF 融合 → 重排 → Context Builder，逐参数验证检索效果。</div>
        </div>
      </div>

      <div className="deck">
        <div className="deck-query">
          <div className="search-box">
            <span className="glyph">⌕</span>
            <input
              value={query}
              placeholder="输入检索问题，例如：Q3 营收口径…"
              aria-label="检索问题"
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') run() }}
            />
          </div>
          <button type="button" className="button primary" disabled={searching} onClick={run}>
            {searching ? <><span className="spinner" style={{ width: 11, height: 11, borderTopColor: '#fff' }} />检索中…</> : '⌕ 检索'}
          </button>
          <button type="button" className="button" disabled={comparing || searching} onClick={runCompare}>
            {comparing ? '对比中…' : '⇄ 模式对比'}
          </button>
        </div>
        <div className="deck-controls">
          <div className="ctl">
            <span className="ctl-label">模式</span>
            <Segmented value={mode} options={MODE_OPTIONS} onChange={setMode} />
          </div>
          <div className="ctl">
            <span className="ctl-label">重排</span>
            <Switch on={rerank} onChange={setRerank} label="启用重排" />
          </div>
          <div className="ctl">
            <span className="ctl-label">TOP-K</span>
            <Stepper value={topK} min={1} max={50} onChange={setTopK} />
          </div>
          <div className="ctl" style={{ flexWrap: 'wrap' }}>
            <span className="ctl-label">知识库</span>
            {kbs.length === 0 && <span style={{ color: '#93a2ab' }}>暂无知识库</span>}
            {kbs.map((k) => (
              <button key={k.id} type="button" className={`kb-toggle ${sel.includes(k.id) ? 'on' : ''}`} onClick={() => toggleKb(k.id)}>
                <i className="kb-dot" style={{ width: 7, height: 7, borderRadius: 2, background: kbHue(kbs, k.id), display: 'inline-block' }} />
                {k.name}
              </button>
            ))}
          </div>
        </div>
        {result?.analysis && (
          <div className="analyzer">
            <span className="lbl">ANALYZER</span>
            <span>策略 {result.analysis.strategy || '—'}</span>
            <span>·</span>
            <span>分词</span>
            {(result.analysis.terms || []).slice(0, 12).map((t, i) => <span key={i} className="tag">{t}</span>)}
            {(result.analysis.quoted || []).length > 0 && (
              <>
                <span>·</span>
                <span>精确短语</span>
                {result.analysis.quoted.map((t, i) => <span key={i} className="tag violet">{t}</span>)}
              </>
            )}
          </div>
        )}
      </div>

      {error && <ErrorBanner msg={error} onRetry={run} />}

      <section className="card">
        <div className="card-head">
          <h2>检索结果{result ? ` · ${chunks.length} 条命中 · ${elapsed.toFixed(0)} ms` : ''}</h2>
          {result && <span className="tag">{MODE_LABEL[result.mode] || result.mode}{result.rerank_applied ? ' · 已重排' : ''}</span>}
        </div>

        {searching && <Loading label="检索中…" />}
        {!searching && !result && !error && (
          <Empty glyph="⌕">输入问题并点击「检索」。命中结果附带稠密 / 稀疏 / 融合 / 重排分数，可追溯原文位置。</Empty>
        )}
        {!searching && result && chunks.length === 0 && (
          <Empty glyph="∅">没有命中任何切块。尝试更换关键词、扩大知识库范围或调高 Top-K。</Empty>
        )}

        {!searching && result && chunks.length > 0 && (
          <div className="lab-grid">
            <div className="result-list">
              {chunks.map((c, i) => {
                const vectorMiss = result.mode === 'hybrid' && c.dense_score < 0.05 && c.sparse_score > 0
                return (
                  <div className="result" key={c.id} style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}>
                    <div className="result-top">
                      <span className="rank-badge">{i + 1}</span>
                      <div className="result-head">
                        <span>{c.filename}{c.heading_path ? ` · ${c.heading_path}` : ''}</span>
                        <small>chars {c.start_offset}–{c.end_offset}</small>
                      </div>
                    </div>
                    <div className="result-text"><Highlight text={c.text} terms={terms} /></div>
                    <div className="result-foot">
                      <div className="scores">
                        <ScoreChip label="dense" value={c.dense_score} max={maxDense} />
                        <ScoreChip kind="sp" label="sparse" value={c.sparse_score} max={maxSparse} />
                        <ScoreChip kind="fu" label="fused" value={c.fused_score} max={maxFused} />
                        {result.rerank_applied && <ScoreChip kind="rr" label="rerank" value={c.rerank_score} max={maxRerank} />}
                        {vectorMiss && <span className="tag red">BM25 命中 · 纯向量漏检</span>}
                      </div>
                      <button type="button" className="text-link" onClick={() => openDocByRef(c.document_id)}>查看原文 →</button>
                    </div>
                  </div>
                )
              })}
            </div>
            <div className="side-col">
              <div className="mini-card">
                <div className="mini-head">检索概况</div>
                <div className="kv"><span>模式</span><b>{MODE_LABEL[result.mode] || result.mode}</b></div>
                <div className="kv"><span>重排</span><b>{result.rerank_applied ? '已应用' : '未应用'}</b></div>
                <div className="kv"><span>命中切块</span><b>{chunks.length}</b></div>
                <div className="kv"><span>请求 Top-K</span><b>{topK}</b></div>
                <div className="kv"><span>耗时</span><b>{elapsed.toFixed(0)} ms</b></div>
                <div className="kv"><span>知识库范围</span><b>{sel.length || '全部'}</b></div>
              </div>
              <div className="mini-card">
                <div className="mini-head">命中来源</div>
                {[...new Map(chunks.map((c) => [c.document_id, c])).values()].slice(0, 6).map((c) => (
                  <div className="kv" key={c.document_id}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.filename}</span>
                    <b>{chunks.filter((x) => x.document_id === c.document_id).length} 块</b>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>

      {compare && (
        <section className="card" style={{ marginTop: 15 }}>
          <div className="card-head"><h2>模式对比 · 同一查询</h2><span className="tag violet">A/B</span></div>
          <div className="table-scroll">
            <table className="table">
              <thead><tr><th>模式</th><th>命中数</th><th>Top-1 文档</th><th>耗时</th></tr></thead>
              <tbody>
                {compare.map((v) => (
                  <tr key={v.label}>
                    <td><span className={`tag ${v.rerank ? 'violet' : v.mode === 'hybrid' ? 'mcp' : ''}`}>{v.label}</span></td>
                    <td>{v.ok ? v.count : '失败'}</td>
                    <td style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={v.top1}>{v.top1}</td>
                    <td>{v.ms.toFixed(0)} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {result && (
        <section className="card" style={{ marginTop: 15 }}>
          <div className="card-head">
            <h2>Context Builder · 注入 LLM 的上下文</h2>
            <div className="toolbar">
              <span className="tag">{ctxChars.toLocaleString()} 字符 · ≈{Math.ceil(ctxChars / 2).toLocaleString()} tokens</span>
              <button type="button" className="button sm" disabled={!ctxChars} onClick={copyContext}>⧉ 复制上下文</button>
            </div>
          </div>
          {ctxChars
            ? <pre className="ctx-pre">{result.context}</pre>
            : <Empty glyph="∅">本次检索没有生成上下文。</Empty>}
        </section>
      )}
    </div>
  )
}

/* ---------- jobs view ---------- */

function JobsView({ kbs, docsVersion, bumpDocs, openDoc, onReingest }) {
  const toast = useToast()
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [processing, setProcessing] = useState(false)

  const load = useCallback(async (silent) => {
    if (!silent) { setLoading(true); setError(null) }
    try {
      const lists = await Promise.all(kbs.map((k) => api.listDocuments(k.id).catch(() => [])))
      setDocs(lists.flat())
    } catch (e) {
      if (!silent) setError(api.errMsg(e))
    } finally {
      if (!silent) setLoading(false)
    }
  }, [kbs])

  useEffect(() => { load() }, [load, docsVersion])

  const pending = docs.filter((d) => d.status === 'pending')
  const running = docs.filter((d) => d.status === 'processing')
  const failed = docs.filter((d) => d.status === 'failed')
  const readyDocs = docs.filter((d) => d.status === 'ready')
  const active = pending.length + running.length

  useEffect(() => {
    if (!active) return undefined
    const t = setInterval(() => load(true), 4000)
    return () => clearInterval(t)
  }, [active, load])

  const processNow = async () => {
    setProcessing(true)
    try {
      const res = await api.processJobs()
      toast(`已处理 ${res.processed} 个作业`, 'ok')
      bumpDocs()
      load(true)
    } catch (e) {
      toast(api.errMsg(e), 'err')
    } finally {
      setProcessing(false)
    }
  }

  const kbName = (id) => kbs.find((k) => k.id === id)?.name || id
  const recent = [...readyDocs].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at)).slice(0, 8)

  const jobRow = (d, showBar) => (
    <div className="job" key={d.id}>
      <div className="job-top">
        <strong>{d.filename}</strong>
        <div className="toolbar">
          <StatusPill status={d.status} />
          <button type="button" className="text-link" onClick={() => openDoc(d)}>查看</button>
        </div>
      </div>
      <div className="job-meta">
        <span className="tag">{kbName(d.knowledge_base_id)}</span>
        <span>{fmtSize(d.size_bytes)}</span>
        <span>上传 {fmtTime(d.created_at)}</span>
        {d.parser_name && <span>解析器 {d.parser_name}</span>}
      </div>
      {showBar && <div className="job-bar"><i /></div>}
      {d.status === 'failed' && d.error && <div className="job-meta" style={{ color: '#b0532f' }}>{d.error}</div>}
    </div>
  )

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">PIPELINE</div>
          <h1>作业队列</h1>
          <div className="subheading">解析 → OCR → 切块 → 向量化 → 入库，失败可一键重建；处理中自动刷新。</div>
        </div>
        <div className="toolbar">
          <button type="button" className="button" onClick={() => load()}>↻ 刷新</button>
          <button type="button" className="button primary" disabled={processing} onClick={processNow}>
            {processing ? <><span className="spinner" style={{ width: 11, height: 11, borderTopColor: '#fff' }} />处理中…</> : '▶ 立即处理作业'}
          </button>
        </div>
      </div>

      <div className="metrics">
        <div className="metric">
          <div className="metric-top"><span>排队中</span><span className="metric-icon">◷</span></div>
          <strong>{pending.length}</strong>
          <div className="metric-foot">等待 worker 领取</div>
        </div>
        <div className="metric">
          <div className="metric-top"><span>处理中</span><span className="metric-icon" style={{ color: '#9a6d32', background: '#fbf2df' }}>⟳</span></div>
          <strong>{running.length}</strong>
          <div className="metric-foot">解析 / 切块 / 向量化</div>
        </div>
        <div className="metric">
          <div className="metric-top"><span>失败</span><span className="metric-icon" style={{ color: '#b0532f', background: '#fdeee7' }}>⚠</span></div>
          <strong>{failed.length}</strong>
          <div className="metric-foot">可一键重建索引</div>
        </div>
        <div className="metric">
          <div className="metric-top"><span>已就绪</span><span className="metric-icon">✓</span></div>
          <strong>{readyDocs.length}</strong>
          <div className="metric-foot">可被检索命中</div>
        </div>
      </div>

      {error && <ErrorBanner msg={error} onRetry={() => load()} />}
      {loading && <Loading label="汇总各知识库作业…" />}

      {!loading && (
        <div className="dashboard-grid">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 15, minWidth: 0 }}>
            <section className="card">
              <div className="card-head"><h2>进行中的作业</h2><span className="tag workflow">{active} 个</span></div>
              {active === 0 && <Empty glyph="✓">队列已清空，没有排队或处理中的文档。</Empty>}
              {running.map((d) => jobRow(d, true))}
              {pending.map((d) => jobRow(d, false))}
            </section>
            <section className="card">
              <div className="card-head"><h2>失败待重建</h2><span className="tag red">{failed.length} 个</span></div>
              {failed.length === 0 && <Empty glyph="✓">没有失败作业。</Empty>}
              {failed.map((d) => (
                <div className="job" key={d.id}>
                  <div className="job-top">
                    <strong>{d.filename}</strong>
                    <div className="toolbar">
                      <StatusPill status={d.status} />
                      <button type="button" className="text-link" onClick={() => onReingest(d)}>↻ 重建</button>
                      <button type="button" className="text-link" onClick={() => openDoc(d)}>查看</button>
                    </div>
                  </div>
                  <div className="job-meta">
                    <span className="tag">{kbName(d.knowledge_base_id)}</span>
                    <span>更新 {fmtTime(d.updated_at)}</span>
                  </div>
                  {d.error && <div className="job-meta" style={{ color: '#b0532f' }}>{d.error}</div>}
                </div>
              ))}
            </section>
          </div>
          <section className="card" style={{ alignSelf: 'start' }}>
            <div className="card-head"><h2>最近完成</h2></div>
            {recent.length === 0 && <Empty glyph="◷">还没有处理完成的文档。</Empty>}
            {recent.map((d) => (
              <div className="hist" key={d.id}>
                <i />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <strong style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.filename}</strong>
                  <small>{kbName(d.knowledge_base_id)} · {d.parser_name || '解析完成'} · {fmtTime(d.updated_at)}</small>
                </div>
                <button type="button" className="text-link" onClick={() => openDoc(d)}>查看</button>
              </div>
            ))}
          </section>
        </div>
      )}
    </div>
  )
}

/* ---------- new KB modal ---------- */

function NewKBModal({ open, onClose, onCreated }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => { if (open) { setName(''); setDesc(''); setErr(null) } }, [open])

  const submit = async () => {
    const n = name.trim()
    if (!n) { setErr('请填写知识库名称'); return }
    setSaving(true)
    setErr(null)
    try {
      const kb = await api.createKnowledgeBase(n, desc.trim())
      toast(`已创建知识库「${kb.name}」`, 'ok')
      onCreated(kb)
      onClose()
    } catch (e) {
      setErr(api.errMsg(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新建知识库"
      foot={(
        <>
          <button type="button" className="button" onClick={onClose}>取消</button>
          <button type="button" className="button primary" disabled={saving} onClick={submit}>
            {saving ? '创建中…' : '创建知识库'}
          </button>
        </>
      )}
    >
      {err && <ErrorBanner msg={err} />}
      <div className="field">
        <label htmlFor="kb-name">名称 *</label>
        <input id="kb-name" className="input" value={name} maxLength={60} placeholder="例如：信贷制度库"
          onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') submit() }} />
      </div>
      <div className="field">
        <label htmlFor="kb-desc">描述</label>
        <textarea id="kb-desc" className="textarea" value={desc} maxLength={200} placeholder="这个知识库收录什么内容、供谁检索…"
          onChange={(e) => setDesc(e.target.value)} />
        <small>创建后可上传 PDF / Word / Excel / PPT / Markdown 等文档，自动完成解析与索引。</small>
      </div>
    </Modal>
  )
}

/* ---------- app shell ---------- */

const NAV = [
  { key: 'bases', icon: '▤', label: '知识库' },
  { key: 'lab', icon: '⌕', label: '检索实验室' },
  { key: 'jobs', icon: '◷', label: '作业队列' },
]

export default function App() {
  const [view, setView] = useState('bases')
  const [kbs, setKbs] = useState([])
  const [kbsError, setKbsError] = useState(null)
  const [kbId, setKbId] = useState(null)
  const [healthOk, setHealthOk] = useState(null)
  const [clock, setClock] = useState('')
  const [docsVersion, setDocsVersion] = useState(0)
  const [drawerDoc, setDrawerDoc] = useState(null)
  const [modal, setModal] = useState(null)
  const [toasts, setToasts] = useState([])
  const toastId = useRef(0)
  const [activeCount, setActiveCount] = useState(0)

  const dismiss = useCallback((id) => setToasts((prev) => prev.filter((t) => t.id !== id)), [])
  const toast = useCallback((msg, kind, action) => {
    toastId.current += 1
    const id = toastId.current
    setToasts((prev) => [...prev.slice(-3), { id, msg, kind, action }])
    setTimeout(() => dismiss(id), action ? 7000 : 4200)
  }, [dismiss])

  const bumpDocs = useCallback(() => setDocsVersion((v) => v + 1), [])

  const loadKBs = useCallback(async (selectId) => {
    try {
      const list = await api.listKnowledgeBases()
      setKbs(list)
      setKbsError(null)
      setKbId((prev) => {
        if (selectId) return selectId
        if (prev && list.some((k) => k.id === prev)) return prev
        return list[0]?.id || null
      })
    } catch (e) {
      setKbsError(api.errMsg(e))
    }
  }, [])

  useEffect(() => { loadKBs() }, [loadKBs])

  useEffect(() => {
    let alive = true
    const check = () => api.health().then(() => { if (alive) setHealthOk(true) }).catch(() => { if (alive) setHealthOk(false) })
    check()
    const t = setInterval(check, 15000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  useEffect(() => {
    const tickClock = () => {
      const d = new Date()
      const p = (x) => String(x).padStart(2, '0')
      setClock(`${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`)
    }
    tickClock()
    const t = setInterval(tickClock, 1000)
    return () => clearInterval(t)
  }, [])

  // Track active jobs across all KBs for the nav badge (lightweight poll).
  useEffect(() => {
    if (!kbs.length) { setActiveCount(0); return undefined }
    let alive = true
    const count = async () => {
      try {
        const lists = await Promise.all(kbs.map((k) => api.listDocuments(k.id).catch(() => [])))
        if (alive) setActiveCount(lists.flat().filter((d) => d.status === 'pending' || d.status === 'processing').length)
      } catch { /* ignore */ }
    }
    count()
    const t = setInterval(count, 8000)
    return () => { alive = false; clearInterval(t) }
  }, [kbs, docsVersion])

  const openDoc = useCallback((doc) => setDrawerDoc(doc), [])
  const openDocById = useCallback(async (id) => {
    try {
      const d = await api.getDocument(id)
      setDrawerDoc(d)
    } catch (e) {
      toast(api.errMsg(e), 'err')
    }
  }, [toast])

  const onDocUpdate = useCallback((d) => {
    setDrawerDoc((prev) => (prev && prev.id === d.id ? d : prev))
  }, [])

  const reingest = useCallback(async (doc) => {
    try {
      await api.reingestDocument(doc.id)
      toast(`「${doc.filename}」已重新进入处理队列`, 'ok')
      bumpDocs()
      setDrawerDoc((prev) => (prev && prev.id === doc.id ? { ...prev, status: 'pending', error: '' } : prev))
    } catch (e) {
      toast(api.errMsg(e), 'err')
    }
  }, [toast, bumpDocs])

  const confirmDeleteKB = async () => {
    const kb = modal?.kb
    if (!kb) return
    try {
      await api.deleteKnowledgeBase(kb.id)
      toast(`已删除知识库「${kb.name}」及其全部文档与索引`, 'ok')
      setModal(null)
      setDrawerDoc((prev) => (prev && prev.knowledge_base_id === kb.id ? null : prev))
      loadKBs()
      bumpDocs()
    } catch (e) {
      toast(api.errMsg(e), 'err')
    }
  }

  const confirmDeleteDoc = async () => {
    const doc = modal?.doc
    if (!doc) return
    try {
      await api.deleteDocument(doc.id)
      toast(`已删除文档「${doc.filename}」`, 'ok')
      setModal(null)
      setDrawerDoc((prev) => (prev && prev.id === doc.id ? null : prev))
      bumpDocs()
    } catch (e) {
      toast(api.errMsg(e), 'err')
    }
  }

  const crumb = NAV.find((n) => n.key === view)?.label || '知识库'

  return (
    <ToastCtx.Provider value={toast}>
      <div className="prototype-bar">
        <div className="prototype-brand">
          <span className="brand-mark">K</span>
          smartagent · Knowledge Hub
          <span className="prototype-hint">上传 → 解析 / OCR → 切块 → 索引 → 混合检索</span>
        </div>
        <div className="bar-right">
          <span className={`bar-health ${healthOk ? 'ok' : healthOk === false ? 'bad' : ''}`}>
            <i className={`dot ${healthOk === false ? 'bad' : ''}`} />
            {healthOk === null ? '连接中…' : healthOk ? '后端已连接' : '后端不可达'}
          </span>
          <span className="clock">{clock}</span>
        </div>
      </div>

      <div className="shell">
        <aside>
          <div className="workspace">
            <span className="workspace-avatar">知</span>
            <div>
              <strong>Knowledge Hub</strong>
              <small>RAG · 混合检索工作台</small>
            </div>
          </div>
          <div className="nav-label">KNOWLEDGE</div>
          {NAV.map((n) => (
            <button key={n.key} type="button" className={`nav-item ${view === n.key ? 'active' : ''}`} onClick={() => setView(n.key)}>
              <span className="icon">{n.icon}</span>
              <span className="nav-text">{n.label}</span>
              {n.key === 'bases' && kbs.length > 0 && <span className="nav-count">{kbs.length}</span>}
              {n.key === 'jobs' && activeCount > 0 && <span className="nav-count">{activeCount}</span>}
            </button>
          ))}
          <div className="aside-bottom">
            Knowledge Hub v0.2<br />
            BM25 + 向量 · RRF 融合<br />
            每条命中可追溯原文
          </div>
        </aside>

        <main>
          <div className="topbar">
            <div className="breadcrumbs">Knowledge　/　<b>{crumb}</b></div>
            <div className="top-actions">
              <span className={`top-status ${healthOk === false ? 'bad' : ''}`}>
                <i className={`dot ${healthOk === false ? 'bad' : ''}`} />
                {healthOk === false ? '服务异常' : '服务正常'}
              </span>
              <span className="clock hide-mobile">{clock}</span>
            </div>
          </div>

          {kbsError && (
            <div className="page" style={{ paddingBottom: 0 }}>
              <ErrorBanner msg={`知识库列表加载失败：${kbsError}`} onRetry={() => loadKBs()} />
            </div>
          )}

          {view === 'bases' && (
            <BasesView
              kbs={kbs}
              kbId={kbId}
              setKbId={setKbId}
              docsVersion={docsVersion}
              bumpDocs={bumpDocs}
              onNewKB={() => setModal({ kind: 'new-kb' })}
              onDeleteKB={(kb) => setModal({ kind: 'del-kb', kb })}
              onDeleteDoc={(doc) => setModal({ kind: 'del-doc', doc })}
              onReingest={reingest}
              openDoc={openDoc}
            />
          )}
          {view === 'lab' && <SearchView kbs={kbs} openDocByRef={openDocById} />}
          {view === 'jobs' && (
            <JobsView kbs={kbs} docsVersion={docsVersion} bumpDocs={bumpDocs} openDoc={openDoc} onReingest={reingest} />
          )}
        </main>
      </div>

      <DocDrawer
        doc={drawerDoc}
        kbs={kbs}
        onClose={() => setDrawerDoc(null)}
        onReingest={reingest}
        onDelete={(doc) => setModal({ kind: 'del-doc', doc })}
        onDocUpdate={onDocUpdate}
      />

      <NewKBModal
        open={modal?.kind === 'new-kb'}
        onClose={() => setModal(null)}
        onCreated={(kb) => loadKBs(kb.id)}
      />

      <Modal
        open={modal?.kind === 'del-kb'}
        onClose={() => setModal(null)}
        title="删除知识库"
        foot={(
          <>
            <button type="button" className="button" onClick={() => setModal(null)}>取消</button>
            <button type="button" className="button primary" style={{ background: '#b0532f', borderColor: '#b0532f' }} onClick={confirmDeleteKB}>确认删除</button>
          </>
        )}
      >
        <p style={{ margin: 0, color: '#536775', fontSize: 11, lineHeight: 1.8 }}>
          将永久删除「<b>{modal?.kb?.name}</b>」及其全部文档、切块与向量索引，<b style={{ color: '#b0532f' }}>此操作不可恢复</b>。确定继续吗？
        </p>
      </Modal>

      <Modal
        open={modal?.kind === 'del-doc'}
        onClose={() => setModal(null)}
        title="删除文档"
        foot={(
          <>
            <button type="button" className="button" onClick={() => setModal(null)}>取消</button>
            <button type="button" className="button primary" style={{ background: '#b0532f', borderColor: '#b0532f' }} onClick={confirmDeleteDoc}>确认删除</button>
          </>
        )}
      >
        <p style={{ margin: 0, color: '#536775', fontSize: 11, lineHeight: 1.8 }}>
          将永久删除「<b>{modal?.doc?.filename}</b>」的原文、Markdown、切块与索引，<b style={{ color: '#b0532f' }}>此操作不可恢复</b>。确定继续吗？
        </p>
      </Modal>

      <ToastHost toasts={toasts} dismiss={dismiss} />
    </ToastCtx.Provider>
  )
}