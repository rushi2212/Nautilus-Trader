import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BookOpen, Bot, ChevronDown, CircleHelp, Command, ExternalLink, Gauge, Layers3, LoaderCircle, MessageCircle, Minus, Plus, RefreshCw, Send, ShieldCheck, Sparkles, Terminal, X } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

type Leg = { symbol: string; side: 'call' | 'put'; strike: number; expiry: string; bid: number | null; ask: number | null; mark: number | null; iv: number | null }
type Overview = { reference_price: number; pair: { call: Leg; put: Leg }; updated_at: string; source: string; is_stale: boolean; warning?: string }
type Message = { role: 'user' | 'assistant'; content: string; error?: boolean }
const API = '/api'
const fmt = (n?: number | null, digits = 2) => n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
const dateFmt = (value?: string) => value ? new Date(value).toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '—'
const chartData = Array.from({ length: 24 }, (_, i) => ({ time: `${String(i).padStart(2, '0')}:00`, btc: 67400 + Math.sin(i * .43) * 310 + Math.cos(i * .18) * 180 + i * 14 }))

export default function App() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)
  const [quantity, setQuantity] = useState(1)
  const [risk, setRisk] = useState(false)
  const [paperPreview, setPaperPreview] = useState(false)
  const [showGuide, setShowGuide] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'activity'>('overview')
  const [chatOpen, setChatOpen] = useState(() => window.innerWidth > 1150)
  const [messages, setMessages] = useState<Message[]>([{ role: 'assistant', content: 'Hey! I’m your Straddle Lab guide. Ask me about the assignment, ATM selection, NautilusTrader, or the risk rules.' }])
  const [draft, setDraft] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const chatEnd = useRef<HTMLDivElement>(null)
  const refreshInFlight = useRef(false)

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return
    refreshInFlight.current = true
    setLoading(true)
    try {
      const response = await fetch(`${API}/market/overview`, { cache: 'no-store' })
      const data = await response.json().catch(() => ({ detail: `Market API returned HTTP ${response.status}` }))
      if (!response.ok) throw new Error(data.detail || 'Market data unavailable')
      setOverview(data); setLoadError(data.warning || '')
    } catch (error) { setLoadError(error instanceof Error ? error.message : 'Could not reach the API') }
    finally { setLoading(false); refreshInFlight.current = false }
  }, [])
  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void refresh() }, 15_000)
    const refreshOnFocus = () => { if (document.visibilityState === 'visible') void refresh() }
    window.addEventListener('focus', refreshOnFocus)
    document.addEventListener('visibilitychange', refreshOnFocus)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refreshOnFocus); document.removeEventListener('visibilitychange', refreshOnFocus) }
  }, [refresh])
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, chatBusy])

  const sendMessage = async (event?: FormEvent, starter?: string) => {
    event?.preventDefault()
    const content = (starter ?? draft).trim()
    if (!content || chatBusy) return
    const next = [...messages, { role: 'user' as const, content }]
    setMessages(next); setDraft(''); setChatBusy(true)
    try {
      const response = await fetch(`${API}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ messages: next.slice(-12) }) })
      const data = await response.json().catch(() => ({ detail: `Chat API returned HTTP ${response.status}` }))
      if (!response.ok) throw new Error(data.detail || 'Chat request failed')
      setMessages([...next, { role: 'assistant', content: data.reply }])
    } catch (error) { setMessages([...next, { role: 'assistant', error: true, content: `${error instanceof Error ? error.message : 'Chat service unavailable'} Check that FastAPI is running and that GROQ_API_KEY is valid.` }]) }
    finally { setChatBusy(false) }
  }

  const pair = overview?.pair
  const quotesReady = !!pair?.call.bid && !!pair?.put.bid && !!pair?.call.ask && !!pair?.put.ask
  const entryCall = pair?.call.bid ?? 0
  const entryPut = pair?.put.bid ?? 0
  const buyback = (pair?.call.ask ?? 0) + (pair?.put.ask ?? 0)
  const entry = quotesReady ? (entryCall + entryPut) * quantity : 0
  const pnl = quotesReady ? entry - buyback * quantity : 0
  const pnlPct = entry ? pnl / entry * 100 : 0
  const signal = risk && entry && (buyback * quantity >= entry * 1.01 ? 'Stop loss threshold reached' : buyback * quantity <= entry * .98 ? 'Take profit threshold reached' : '')

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Command size={19} strokeWidth={1.8} /></div><div><strong>NAUTILUS</strong><span>STRADDLE LAB</span></div></div>
      <div className="workspace-label">WORKSPACE <ChevronDown size={13}/></div>
      <button className="side-link selected"><Activity size={17}/><span>Strategy desk</span><span className="side-dot"/></button>
      <button className="side-link" onClick={() => setActiveTab('positions')}><Layers3 size={17}/><span>Positions</span></button>
      <button className="side-link" onClick={() => setActiveTab('activity')}><Terminal size={17}/><span>Event log</span></button>
      <div className="sidebar-bottom"><div className="environment"><span className="pulse"/><div><b>Paper environment</b><small>Execution disabled</small></div><ShieldCheck size={16}/></div><div className="user-row"><div className="avatar">RL</div><div><b>Research desk</b><small>Intern challenge</small></div><button className="icon-button"><ChevronDown size={15}/></button></div></div>
    </aside>

    <main className="main-area">
      <header className="topbar"><div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><b>Strategy desk</b></div><div className="top-actions"><div className={`live-status ${overview?.is_stale || (!overview && !loading) ? 'status-warning' : ''}`}><span className="pulse"/> MARKET DATA <span className="status-sub">{loading && !overview ? 'CONNECTING' : overview ? overview.is_stale ? 'STALE DATA' : 'CONNECTED' : 'OFFLINE'}</span></div><button className="icon-button" onClick={() => void refresh()} title="Refresh market data" aria-label="Refresh market data"><RefreshCw size={16} className={loading ? 'spin' : ''}/></button><button className="help-button" onClick={() => setChatOpen(!chatOpen)}><CircleHelp size={16}/> Help</button></div></header>

      <div className="content-wrap">
        <div className="page-title-row"><div><div className="eyebrow"><span className="eyebrow-line"/> OPTIONS STRATEGY <span className="version-pill">LEVEL 2</span></div><h1>BTC short straddle</h1><p className="subtitle">Monitor your ATM option pair and understand every move.</p></div><div className="title-actions"><span className="paper-tag"><span className="pulse"/> PAPER MODE</span><button className="how-to-button" aria-expanded={showGuide} onClick={() => setShowGuide(!showGuide)}><BookOpen size={14}/> How to use</button><button className="primary-button" onClick={() => document.getElementById('strategy-card')?.scrollIntoView({ behavior: 'smooth' })}>Configure strategy <ArrowDownRight size={15}/></button></div></div>
        {showGuide && <section className="quick-start panel" aria-label="How to use the app"><div className="quick-start-head"><div><div className="section-kicker">QUICK START</div><h2>From market data to a paper preview</h2></div><button className="icon-button" onClick={() => setShowGuide(false)} aria-label="Close quick start"><X size={15}/></button></div><div className="quick-steps"><div><span>01</span><b>Start the app</b><small>Run <code>start.ps1</code> from the project folder. Keep both service windows open.</small></div><div><span>02</span><b>Check the option pair</b><small>BTC and the matched ATM call/put update every 15 seconds. The footer shows the last refresh.</small></div><div><span>03</span><b>Set paper parameters</b><small>Choose quantity and optionally enable the 1% stop / 2% take-profit monitor.</small></div><div><span>04</span><b>Preview and ask</b><small>Select “Preview paper position” to inspect both legs. Use Straddle guide for assignment questions.</small></div></div><p className="quick-note"><ShieldCheck size={14}/> Paper-only: the preview does not send orders to Bybit. A red banner means the API failed; amber means cached data is shown.</p></section>}
        {loadError && <div className={`notice ${overview ? 'stale-notice' : 'error-notice'}`} role="alert"><div className="notice-icon"><AlertTriangle size={17}/></div><div className="notice-copy"><strong>{overview ? 'Showing last available market data' : 'Market data could not load'}</strong><span>{loadError}</span><small>{overview ? `Last successful snapshot: ${new Date(overview.updated_at).toLocaleString()}` : 'Check your internet connection, Bybit availability, and that the FastAPI server is running.'}</small></div><button onClick={() => void refresh()} disabled={loading}>{loading ? <><LoaderCircle size={13} className="spin"/> Retrying</> : <><RefreshCw size={13}/> Retry</>}</button></div>}
        <section className="metric-grid">
          <Metric title="BTC reference price" value={overview ? `$${fmt(overview.reference_price, 0)}` : '—'} note="Bybit spot · BTCUSDT" icon={<span className="btc-icon">₿</span>} loading={loading && !overview} />
          <Metric title="ATM strike" value={pair ? `$${fmt(pair.call.strike, 0)}` : '—'} note={pair ? `Nearest available · ${dateFmt(pair.call.expiry)}` : 'Waiting for option chain'} icon={<Gauge size={17}/>} loading={loading && !overview} />
          <Metric title="Straddle premium" value={entry ? fmt(entry, 4) : '—'} note="Bid-side entry · per selected quantity" icon={<Layers3 size={17}/>} loading={loading && !overview} />
          <Metric title="Paper P&L" value={entry ? `${pnl >= 0 ? '+' : ''}${fmt(pnl, 4)}` : '—'} note={entry ? `${pnlPct >= 0 ? '+' : ''}${fmt(pnlPct, 2)}% · ask-side buyback` : 'Updates with quotes'} icon={pnl >= 0 ? <ArrowUpRight size={17}/> : <ArrowDownRight size={17}/>} positive={pnl >= 0} loading={loading && !overview} />
        </section>

        <div className="dashboard-grid">
          <section className="panel chart-panel"><div className="panel-heading"><div><div className="section-kicker">MARKET OVERVIEW</div><h2>BTC / USDT <span className="market-chip">SPOT</span></h2></div><div className="chart-price">${fmt(overview?.reference_price, 2)}<span className="chart-tag">LIVE REFERENCE</span></div></div><div className="chart-legend"><span/><b>Illustrative BTC path</b><span className="chart-period">Sample series <ChevronDown size={13}/></span></div><div className="chart-area"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{ top: 12, right: 7, left: 0, bottom: 0 }}><defs><linearGradient id="fillBtc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#315be8" stopOpacity={0.16}/><stop offset="95%" stopColor="#315be8" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#dce3ed" strokeDasharray="3 6" vertical={false}/><XAxis dataKey="time" tick={{ fill: '#707c78', fontSize: 10 }} tickLine={false} axisLine={false} interval={5}/><YAxis orientation="right" domain={['dataMin - 400', 'dataMax + 400']} tick={{ fill: '#707c78', fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} width={42}/><Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #dce3ed', borderRadius: 8, color: '#25334a', fontSize: 12 }} labelStyle={{ color: '#68768a' }} formatter={(value) => [`$${fmt(Number(value), 2)}`, 'Illustrative BTC']}/><Area type="monotone" dataKey="btc" stroke="#315be8" strokeWidth={2} fill="url(#fillBtc)" dot={false} activeDot={{ r: 4, fill: '#315be8', stroke: '#fff', strokeWidth: 2 }}/></AreaChart></ResponsiveContainer></div><div className="chart-foot"><span><span className="pulse"/> Illustrative sample series · not historical data</span><span>{overview ? `Updated ${new Date(overview.updated_at).toLocaleTimeString()} · refresh every 15s` : 'Waiting for first market snapshot'}</span></div></section>

          <section className="panel strategy-panel" id="strategy-card"><div className="panel-heading"><div><div className="section-kicker">STRATEGY SETUP</div><h2>ATM straddle</h2></div><button className="more-button"><span/><span/><span/></button></div><div className="strategy-description">Short one call and one put at the same strike and expiry.</div><div className="contract-pair"><OptionRow label="CALL" leg={pair?.call} loading={loading && !pair}/><OptionRow label="PUT" leg={pair?.put} loading={loading && !pair}/></div><div className="quantity-row"><div><b>Contract quantity</b><small>Per leg · matched pair</small></div><div className="stepper"><button onClick={() => setQuantity(Math.max(.1, +(quantity - .1).toFixed(1)))}><Minus size={13}/></button><strong>{quantity.toFixed(1)}</strong><button onClick={() => setQuantity(+(quantity + .1).toFixed(1))}><Plus size={13}/></button></div></div><label className="risk-toggle"><div><b>Risk management</b><small>Stop loss 1% <i/> Take profit 2%</small></div><input type="checkbox" checked={risk} onChange={e => setRisk(e.target.checked)}/><span className="toggle-ui"/></label>{signal && <div className={`signal ${signal.includes('Stop') ? 'danger' : 'success'}`}>{signal.includes('Stop') ? 'STOP' : 'TAKE PROFIT'} threshold reached · paper signal</div>}<button className="paper-button" disabled={!quotesReady} onClick={() => { setPaperPreview(true); setActiveTab('positions') }}><Activity size={15}/>{quotesReady ? 'Preview paper position' : 'Waiting for complete bid / ask quotes'} <ArrowUpRight size={14}/></button><div className="execution-note"><ShieldCheck size={14}/> Simulated view · no orders are sent</div></section>
        </div>

        <section className="panel lower-panel"><div className="lower-top"><div className="tabs"><button className={activeTab === 'overview' ? 'active' : ''} onClick={() => setActiveTab('overview')}>Option pair</button><button className={activeTab === 'positions' ? 'active' : ''} onClick={() => setActiveTab('positions')}>Positions <span className="tab-count">{paperPreview ? 'PAPER' : '—'}</span></button><button className={activeTab === 'activity' ? 'active' : ''} onClick={() => setActiveTab('activity')}>Activity</button></div><button className="text-button" onClick={() => void refresh()}>Refresh data <RefreshCw size={13}/></button></div>{activeTab === 'overview' ? <div className="table-wrap"><table><thead><tr><th>CONTRACT</th><th>TYPE</th><th>STRIKE</th><th>EXPIRY</th><th>BID / ENTRY</th><th>ASK / BUYBACK</th><th>MARK IV</th></tr></thead><tbody><LegRow leg={pair?.call}/><LegRow leg={pair?.put}/></tbody></table></div> : activeTab === 'positions' ? paperPreview && pair ? <div className="table-wrap"><table><thead><tr><th>CONTRACT</th><th>POSITION</th><th>QTY</th><th>ENTRY BID</th><th>BUYBACK ASK</th><th>UNREALIZED P&L</th><th>MODE</th></tr></thead><tbody><tr><td className="contract-cell"><span className="mini-type">C</span><b>{pair.call.symbol}</b></td><td>SHORT CALL</td><td>{quantity}</td><td>{fmt(pair.call.bid ?? pair.call.mark, 4)}</td><td>{fmt(pair.call.ask ?? pair.call.mark, 4)}</td><td>{fmt(((pair.call.bid ?? pair.call.mark ?? 0) - (pair.call.ask ?? pair.call.mark ?? 0)) * quantity, 4)}</td><td><span className="type-badge">PAPER</span></td></tr><tr><td className="contract-cell"><span className="mini-type put">P</span><b>{pair.put.symbol}</b></td><td>SHORT PUT</td><td>{quantity}</td><td>{fmt(pair.put.bid ?? pair.put.mark, 4)}</td><td>{fmt(pair.put.ask ?? pair.put.mark, 4)}</td><td>{fmt(((pair.put.bid ?? pair.put.mark ?? 0) - (pair.put.ask ?? pair.put.mark ?? 0)) * quantity, 4)}</td><td><span className="type-badge">PAPER</span></td></tr></tbody></table></div> : <div className="empty-state"><div className="empty-icon"><Layers3 size={18}/></div><b>No paper preview yet</b><span>Use “Preview paper position” to calculate the two legs from current quotes.</span></div> : <div className="event-list"><div><span className="event-dot green"/><b>Dashboard ready</b><small>Waiting for strategy events</small><time>Now</time></div><div><span className="event-dot"/><b>Market data</b><small>{overview ? `Option chain snapshot · ${pair?.call.symbol || 'BTC'}` : 'Waiting for Bybit API'}</small><time>{overview ? 'Live' : '—'}</time></div></div>}</section>
        <footer className="page-footer"><span>NAUTILUS TRADER · BTC OPTIONS ASSIGNMENT</span><span><a href="https://nautilustrader.io/docs/latest/integrations/bybit/" target="_blank" rel="noreferrer">Bybit integration docs <ExternalLink size={11}/></a><i/> Built for learning · Not financial advice</span></footer>
      </div>
    </main>

    {chatOpen ? <aside className="chat-panel"><div className="chat-header"><div className="chat-avatar"><Sparkles size={17}/></div><div className="chat-title"><b>Straddle guide</b><span><span className="pulse"/> Ready to help</span></div><button className="icon-button" onClick={() => setChatOpen(false)} aria-label="Close chat"><X size={16}/></button></div><div className="chat-context"><Bot size={14}/> Assignment assistant <span>·</span> Groq when configured</div><div className="chat-messages">{messages.map((message, i) => <div key={i} className={`chat-message ${message.role} ${message.error ? 'message-error' : ''}`}><div className="message-avatar">{message.error ? <AlertTriangle size={12}/> : message.role === 'assistant' ? <Sparkles size={12}/> : 'RL'}</div><div className="message-bubble">{message.error && <b className="error-label">CHAT ERROR</b>}<MarkdownMessage content={message.content}/></div></div>)}{chatBusy && <div className="chat-message assistant"><div className="message-avatar"><Sparkles size={12}/></div><div className="message-bubble typing"><i/><i/><i/></div></div>}<div ref={chatEnd}/></div>{messages.length < 3 && <div className="suggestions"><span>QUICK PROMPTS</span><button onClick={() => void sendMessage(undefined, 'How does ATM selection work?')}>How does ATM selection work? <ArrowUpRight size={12}/></button><button onClick={() => void sendMessage(undefined, 'Explain the Level 2 risk rules')}>Explain the risk rules <ArrowUpRight size={12}/></button></div>}<form className="chat-compose" onSubmit={sendMessage}><input value={draft} onChange={e => setDraft(e.target.value)} placeholder="Ask about your strategy…" aria-label="Message Straddle guide"/><button disabled={!draft.trim() || chatBusy} aria-label="Send message">{chatBusy ? <LoaderCircle size={16} className="spin"/> : <Send size={16}/>}</button><div className="compose-hint"><span>AI can make mistakes</span><span><MessageCircle size={11}/> Enter to send</span></div></form></aside> : <button className="chat-launcher" onClick={() => setChatOpen(true)}><Sparkles size={18}/><span>Ask the guide</span></button>}
  </div>
}

function Metric({ title, value, note, icon, positive, loading }: { title: string; value: string; note: string; icon: ReactNode; positive?: boolean; loading?: boolean }) { return <div className="metric-card"><div className="metric-top"><span>{title}</span><span className="metric-icon">{icon}</span></div><strong className={positive ? 'metric-positive' : ''}>{loading ? <span className="skeleton"/> : value}</strong><small>{note}</small></div> }
function OptionRow({ label, leg, loading }: { label: string; leg?: Leg; loading?: boolean }) { return <div className="option-row"><div className={`option-icon ${label.toLowerCase()}`}>{label === 'CALL' ? <ArrowUpRight size={15}/> : <ArrowDownRight size={15}/>}</div><div className="option-info"><b>{label} <span>{leg?.strike ? `$${fmt(leg.strike, 0)}` : ''}</span></b><small>{leg?.symbol || (loading ? 'Loading contract…' : 'Contract unavailable')}</small></div><div className="option-mark"><b>{leg?.mark ? fmt(leg.mark, 4) : '—'}</b><small>MARK</small></div></div> }
function LegRow({ leg }: { leg?: Leg }) { return <tr><td className="contract-cell"><span className={`mini-type ${leg?.side || 'call'}`}>{leg?.side === 'put' ? 'P' : 'C'}</span><b>{leg?.symbol || 'Waiting for market data'}</b></td><td><span className="type-badge">{leg?.side?.toUpperCase() || '—'}</span></td><td>{leg?.strike ? `$${fmt(leg.strike, 0)}` : '—'}</td><td>{dateFmt(leg?.expiry)}</td><td>{fmt(leg?.bid, 4)}</td><td>{fmt(leg?.ask, 4)}</td><td>{leg?.iv ? `${fmt(leg.iv * 100, 1)}%` : '—'}</td></tr> }

function inlineMarkdown(text: string): ReactNode[] {
  const tokens = /(\[[^\]]+\]\(https?:\/\/[^\s)]+\)|`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_)/g
  const output: ReactNode[] = []
  let cursor = 0
  let match: RegExpExecArray | null
  while ((match = tokens.exec(text)) !== null) {
    if (match.index > cursor) output.push(text.slice(cursor, match.index))
    const token = match[0]
    const key = `inline-${match.index}`
    if (token.startsWith('`')) output.push(<code key={key}>{token.slice(1, -1)}</code>)
    else if (token.startsWith('**') || token.startsWith('__')) output.push(<strong key={key}>{inlineMarkdown(token.slice(2, -2))}</strong>)
    else if (token.startsWith('*') || token.startsWith('_')) output.push(<em key={key}>{inlineMarkdown(token.slice(1, -1))}</em>)
    else {
      const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/)
      output.push(link ? <a key={key} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a> : token)
    }
    cursor = match.index + token.length
  }
  if (cursor < text.length) output.push(text.slice(cursor))
  return output
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = content.replace(/\r\n?/g, '\n').trim().split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  const isList = (line: string) => /^\s*(?:[-*+•]\s+|\d+[.)]\s+)/.test(line)
  const isBlockStart = (line: string) => /^(\s*```|#{1,6}\s|\s*>|\s*(?:[-*+•]\s+|\d+[.)]\s+)|\s*(?:---+|\*\*\*+)\s*$)/.test(line)
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }
    if (/^\s*```/.test(line)) {
      const language = line.trim().slice(3).trim()
      const code: string[] = []
      i++
      while (i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i++])
      if (i < lines.length) i++
      blocks.push(<pre key={`block-${i}`} data-language={language || undefined}><code>{code.join('\n')}</code></pre>)
      continue
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      const level = heading[1].length
      const children = inlineMarkdown(heading[2])
      blocks.push(level === 1 ? <h3 key={`block-${i}`}>{children}</h3> : level === 2 ? <h4 key={`block-${i}`}>{children}</h4> : <h5 key={`block-${i}`}>{children}</h5>)
      i++; continue
    }
    if (/^\s*(?:---+|\*\*\*+)\s*$/.test(line)) { blocks.push(<hr key={`block-${i++}`}/>); continue }
    if (line.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
      const cells = (row: string) => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
      const headers = cells(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].includes('|')) rows.push(cells(lines[i++]))
      blocks.push(<div className="markdown-table" key={`block-${i}`}><table><thead><tr>{headers.map((cell, index) => <th key={index}>{inlineMarkdown(cell)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{headers.map((_, columnIndex) => <td key={columnIndex}>{inlineMarkdown(row[columnIndex] || '')}</td>)}</tr>)}</tbody></table></div>)
      continue
    }
    if (/^\s*>/.test(line)) {
      const quote: string[] = []
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ''))
      blocks.push(<blockquote key={`block-${i}`}>{inlineMarkdown(quote.join(' '))}</blockquote>)
      continue
    }
    if (isList(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line)
      const items: ReactNode[] = []
      while (i < lines.length && isList(lines[i]) && /^\s*\d+[.)]\s+/.test(lines[i]) === ordered) {
        const match = lines[i].match(/^\s*(?:[-*+•]\s+|\d+[.)]\s+)(.*)$/)
        if (match) items.push(<li key={`item-${i}`}>{inlineMarkdown(match[1])}</li>)
        i++
      }
      blocks.push(ordered ? <ol key={`block-${i}`}>{items}</ol> : <ul key={`block-${i}`}>{items}</ul>)
      continue
    }
    const paragraph = [line]
    i++
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) paragraph.push(lines[i++])
    blocks.push(<p key={`block-${i}`}>{inlineMarkdown(paragraph.join(' '))}</p>)
  }
  return <div className="markdown-content">{blocks}</div>
}
