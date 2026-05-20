/**
 * Telegram bot — push channel for the principal (GP-168 addendum 2026-04-27).
 *
 * Watches the configured workspace gates inbox (the single executive inbox per
 * Panel A synthesis) and pushes notifications to the principal. Renders
 * a daily/on-demand OKR tree digest by joining `org/objectives/`,
 * `org/key_results/`, and `org/tasks/`.
 *
 * The bot owns only local polling cursor state. Governance mutations are
 * delegated to the kernel service.
 *
 * Verbs accepted:
 *   /digest, digest             → OKR tree summary
 *   /pressure, pressure         → list of imminent items
 *   /help                       → command list
 *   inline-button taps          → resolve a specific gate
 *
 * Verbs explicitly NOT accepted (these belong in Orbit):
 *   - mandate edits
 *   - role changes
 *   - new Objective / KR authoring
 *   - free-form chat (no LLM here — fixed verbs only)
 *
 * Env vars required:
 *   TELEGRAM_BOT_TOKEN   — from @BotFather
 *   TELEGRAM_CHAT_ID     — your chat with the bot (private)
 *   ORG_ROOT             — path to org/ (default: ./org)
 *   GATES_DIR            — path to executive inbox (default: ./cognitive_firm_workspace/gates/pending)
 *   COGNITIVE_FIRM_KERNEL_SERVICE_URL — kernel service URL (default: http://127.0.0.1:8765)
 *
 * Run:
 *   tsx orbit/src/server/telegram-bot.ts
 */
import {
  readFileSync,
  readdirSync,
  writeFileSync,
  existsSync,
} from 'fs'
import { join } from 'path'

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN
const CHAT_ID = process.env.TELEGRAM_CHAT_ID
const ORG_ROOT = process.env.ORG_ROOT || './org'
const WORKSPACE_DIR = process.env.COGNITIVE_FIRM_WORKSPACE || './cognitive_firm_workspace'
const GATES_DIR = process.env.GATES_DIR || join(WORKSPACE_DIR, 'gates', 'pending')
const KERNEL_SERVICE_URL = (process.env.COGNITIVE_FIRM_KERNEL_SERVICE_URL || 'http://127.0.0.1:8765').replace(/\/+$/, '')
const KERNEL_SERVICE_TOKEN = process.env.COGNITIVE_FIRM_KERNEL_TOKEN || ''
const POLL_SECONDS = Number(process.env.POLL_SECONDS || 30)
const LONG_POLL_TIMEOUT = Number(process.env.LONG_POLL_TIMEOUT || 25)
const STATE_PATH = join(ORG_ROOT, '.telegram_bot_state.json')

// Drop inbound messages and callbacks that are not from the configured operator
// chat. Replies always go to CHAT_ID (operator) regardless of sender, so this
// is not a confidentiality fix — it is an abuse / resource-waste guard. See
// Provider adapter: delivery errors stay visible and do not mutate kernel state.
function isAuthorizedChatId(chatId: number | string | undefined | null): boolean {
  if (chatId == null || CHAT_ID == null) return false
  return String(chatId) === String(CHAT_ID)
}

async function callKernelService(path: string, payload: Record<string, unknown>): Promise<any> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (KERNEL_SERVICE_TOKEN) headers.Authorization = `Bearer ${KERNEL_SERVICE_TOKEN}`
  const response = await fetch(`${KERNEL_SERVICE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      ...payload,
      actor_context: {
        actor_id: 'human.principal',
        actor_kind: 'human',
        surface: 'telegram',
      },
    }),
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok || body.ok === false) {
    throw new Error(String(body.error || `kernel service returned HTTP ${response.status}`))
  }
  return body
}

// Escape Telegram Markdown (legacy mode, used by parse_mode: 'Markdown'). The
// legacy mode escapes only `_`, `*`, `` ` ``, and `[`. We do not use MarkdownV2
// because its escape list is much larger and not needed here. See audit S3.
function escapeMd(s: string | undefined | null): string {
  if (s == null) return ''
  return String(s).replace(/([_*`\[])/g, '\\$1')
}

interface BotState {
  notified_gates: string[]
  last_update_id: number
  last_digest_utc: string | null
}

interface Gate {
  gate_id: string
  kind: string
  subject?: string
  summary?: string
  options?: { id: string; consequence: string }[]
  default_after_days?: number
  auto_resolution_on_default?: string
  task_path?: string
  kr_path?: string
  objective_path?: string
  honesty?: { score: number; measured: number; total: number }
  owner?: string
  created_utc: string
  status: 'pending' | 'resolved'
}

interface ObjectiveFM {
  objective_id: string
  title?: string
  status?: string
  closure_deadline?: string
  target_date?: string
}

interface KRFM {
  kr_id: string
  objective_id?: string
  description?: string
  status?: string
  measurement_locus?: 'self' | 'world'
  kr_type?: string
  last_measured_utc?: string | null
  review_overdue_threshold_days?: number
}

interface TaskFM {
  task_id?: string
  objective_id?: string
  kr_id?: string
  title?: string
  status?: string
  closure_deadline?: string
  budget_cap_usd?: number
  budget_spent_usd?: number
}

// ---------- state ----------

function loadState(): BotState {
  if (existsSync(STATE_PATH)) {
    try { return JSON.parse(readFileSync(STATE_PATH, 'utf8')) } catch {}
  }
  return { notified_gates: [], last_update_id: 0, last_digest_utc: null }
}

function saveState(s: BotState): void {
  writeFileSync(STATE_PATH, JSON.stringify(s, null, 2))
}

// ---------- frontmatter ----------

function readJson<T>(path: string): T | null {
  try { return JSON.parse(readFileSync(path, 'utf8')) as T } catch { return null }
}

const FM_RE = /^---\n([\s\S]*?)\n---\n?/

function parseFrontmatter(text: string): Record<string, any> {
  const m = text.match(FM_RE)
  if (!m) return {}
  const out: Record<string, any> = {}
  let inArray: string | null = null
  for (const rawLine of m[1].split('\n')) {
    const line = rawLine
    if (!line.trim() || line.trim().startsWith('#')) continue
    if (inArray) {
      if (line.startsWith('  -') || line.startsWith('-')) {
        out[inArray].push(line.replace(/^[-\s]+/, '').trim())
        continue
      }
      inArray = null
    }
    const colonIdx = line.indexOf(':')
    if (colonIdx < 0 || line.startsWith(' ')) continue
    const key = line.slice(0, colonIdx).trim()
    let val = line.slice(colonIdx + 1).trim()
    if (val === '' || val.toLowerCase() === 'null') {
      out[key] = null
      continue
    }
    if (val === '[]') { out[key] = []; continue }
    if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1)
    if (val.startsWith("'") && val.endsWith("'")) val = val.slice(1, -1)
    if (val === 'true') out[key] = true
    else if (val === 'false') out[key] = false
    else if (/^-?\d+(\.\d+)?$/.test(val)) out[key] = Number(val)
    else out[key] = val
  }
  return out
}

function readFM<T extends Record<string, any>>(path: string): T | null {
  try {
    return parseFrontmatter(readFileSync(path, 'utf8')) as T
  } catch { return null }
}

// ---------- telegram ----------

async function tg(method: string, body: object): Promise<any> {
  const res = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json()
}

function gateInlineKeyboard(gate: Gate): any {
  const opts = gate.options ?? [{ id: 'open_orbit', consequence: 'open in Orbit' }]
  const keyboard: any[][] = []
  let row: any[] = []
  for (const opt of opts.slice(0, 6)) {
    row.push({ text: opt.id, callback_data: `gate:${gate.gate_id}:${opt.id}` })
    if (row.length === 3) { keyboard.push(row); row = [] }
  }
  if (row.length) keyboard.push(row)
  keyboard.push([{ text: '🔍 Orbit', callback_data: `open:${gate.gate_id}` }])
  return { inline_keyboard: keyboard }
}

function gateMessage(gate: Gate): string {
  const lines: string[] = []
  const icon =
    gate.kind?.startsWith('task_') ? '📋' :
    gate.kind?.startsWith('kr_') ? '📊' :
    gate.kind?.startsWith('objective_') ? '🎯' : '⚙️'
  const kindLabel = escapeMd((gate.kind || 'gate').toUpperCase())
  const subject = escapeMd(gate.subject || gate.gate_id)
  lines.push(`${icon} *${kindLabel}* — ${subject}`)
  if (gate.summary) lines.push('', escapeMd(gate.summary))
  if (gate.honesty) {
    lines.push('', `Honesty: ${gate.honesty.score.toFixed(2)} (${gate.honesty.measured}/${gate.honesty.total} world-KRs measured)`)
  }
  if (gate.default_after_days != null) {
    lines.push('', `_Default after ${gate.default_after_days}d: ${escapeMd(gate.auto_resolution_on_default)}_`)
  }
  return lines.join('\n')
}

async function sendGate(gate: Gate): Promise<void> {
  await tg('sendMessage', {
    chat_id: CHAT_ID,
    text: gateMessage(gate),
    parse_mode: 'Markdown',
    reply_markup: gateInlineKeyboard(gate),
  })
}

// ---------- OKR tree digest ----------

function safeReaddir(dir: string): string[] {
  try { return readdirSync(dir) } catch { return [] }
}

function buildOKRTreeDigest(): string {
  const lines: string[] = ['*OKR digest*', '']

  // Objectives
  const objDir = join(ORG_ROOT, 'objectives')
  const objs: { fm: ObjectiveFM; path: string }[] = []
  for (const f of safeReaddir(objDir)) {
    if (!f.endsWith('.md') || f === 'README.md') continue
    const fm = readFM<ObjectiveFM>(join(objDir, f))
    if (fm && fm.status === 'active') objs.push({ fm, path: join(objDir, f) })
  }

  // KRs grouped by objective_id
  const krDir = join(ORG_ROOT, 'key_results')
  const krsByObj: Record<string, KRFM[]> = {}
  for (const f of safeReaddir(krDir)) {
    if (!f.endsWith('.md') || f === 'README.md') continue
    const fm = readFM<KRFM>(join(krDir, f))
    if (!fm || !fm.objective_id) continue
    ;(krsByObj[fm.objective_id] ||= []).push(fm)
  }

  // Tasks grouped by objective_id (active only)
  const taskActiveDir = join(ORG_ROOT, 'tasks', 'active')
  const tasksByObj: Record<string, TaskFM[]> = {}
  let unattachedTasks = 0
  for (const f of safeReaddir(taskActiveDir)) {
    if (!f.endsWith('.md')) continue
    const fm = readFM<TaskFM>(join(taskActiveDir, f))
    if (!fm) continue
    if (fm.objective_id) (tasksByObj[fm.objective_id] ||= []).push(fm)
    else unattachedTasks++
  }

  // Imminent counts
  const now = Date.now()
  let imminentTasks = 0
  for (const list of Object.values(tasksByObj)) {
    for (const t of list) {
      if (!t.closure_deadline) continue
      const d = Date.parse(t.closure_deadline)
      const created = now - 24 * 3600 * 1000  // assume <1d if no created
      const pct = (now - created) / (d - created)
      if (pct >= 0.7) imminentTasks++
    }
  }

  if (objs.length === 0) {
    lines.push('_No active Objectives. Author one in `org/objectives/`._')
    return lines.join('\n')
  }

  for (const { fm } of objs) {
    const krs = krsByObj[fm.objective_id] || []
    const onTrack = krs.filter(k => k.status === 'on_track').length
    const atRisk = krs.filter(k => k.status === 'at_risk').length
    const done = krs.filter(k => k.status === 'done').length
    const tasks = tasksByObj[fm.objective_id] || []
    lines.push(`🎯 *${fm.title || fm.objective_id}*`)
    lines.push(`   KRs: ${krs.length} (${onTrack} on-track, ${atRisk} at-risk, ${done} done)`)
    if (tasks.length > 0) lines.push(`   Tasks active: ${tasks.length}`)
    if (fm.closure_deadline || fm.target_date) {
      lines.push(`   Deadline: ${fm.closure_deadline || fm.target_date}`)
    }
    lines.push('')
  }

  if (unattachedTasks > 0) {
    lines.push(`_${unattachedTasks} unattached task${unattachedTasks === 1 ? '' : 's'} (no objective_id)_`)
  }
  if (imminentTasks > 0) {
    lines.push(`_${imminentTasks} task${imminentTasks === 1 ? '' : 's'} approaching deadline_`)
  }

  return lines.join('\n')
}

// ---------- gate inbox watcher ----------

function listPendingGates(): Gate[] {
  const out: Gate[] = []
  for (const f of safeReaddir(GATES_DIR)) {
    if (!f.endsWith('.json')) continue
    const g = readJson<Gate>(join(GATES_DIR, f))
    if (g) out.push(g)
  }
  return out
}

async function pushNew(state: BotState): Promise<void> {
  for (const gate of listPendingGates()) {
    if (state.notified_gates.includes(gate.gate_id)) continue
    try {
      await sendGate(gate)
      state.notified_gates.push(gate.gate_id)
    } catch (err) {
      console.error('[telegram-bot] sendGate failed:', err)
    }
  }
}

async function handleCallback(callback_query: any, _state: BotState): Promise<void> {
  const fromChatId = callback_query?.message?.chat?.id ?? callback_query?.from?.id
  if (!isAuthorizedChatId(fromChatId)) {
    // Acknowledge silently so Telegram clears the loading state on the
    // attacker's client; do nothing else. No reply, no audit row.
    try { await tg('answerCallbackQuery', { callback_query_id: callback_query.id }) } catch {}
    return
  }
  const data: string = callback_query.data || ''
  await tg('answerCallbackQuery', { callback_query_id: callback_query.id, text: 'Recorded.' })
  const [kind, id, action] = data.split(':')
  if (kind === 'gate' && id && action) {
    const src = join(GATES_DIR, `${id}.json`)
    if (!existsSync(src)) {
      await tg('sendMessage', { chat_id: CHAT_ID, text: `Gate ${id} no longer pending.` })
      return
    }
    const gate = readJson<Gate>(src)
    if (!gate) return
    await callKernelService(`/kernel/gates/${id}/resolve`, {
      chosen_option: action,
      resolved_by: 'telegram',
    })
    await tg('sendMessage', { chat_id: CHAT_ID, text: `Recorded: ${id} → ${action}` })
  } else if (kind === 'open') {
    await tg('sendMessage', { chat_id: CHAT_ID, text: `Open Orbit: http://localhost:5173 (search "${id}")` })
  }
}

async function handleMessage(msg: any): Promise<void> {
  if (!isAuthorizedChatId(msg?.chat?.id)) return  // silent drop; do not advertise the bot
  const text: string = (msg.text || '').trim()
  if (text === '/digest' || text === 'digest') {
    await tg('sendMessage', { chat_id: CHAT_ID, text: buildOKRTreeDigest(), parse_mode: 'Markdown' })
  } else if (text === '/pressure' || text === 'pressure') {
    const gates = listPendingGates()
    const lines = ['*Pending pressure*', '', `${gates.length} gate(s) awaiting decision.`, '']
    for (const g of gates.slice(0, 10)) {
      lines.push(`• [${escapeMd(g.kind)}] ${escapeMd(g.subject || g.gate_id)}`)
    }
    if (gates.length > 10) lines.push(`... and ${gates.length - 10} more`)
    await tg('sendMessage', { chat_id: CHAT_ID, text: lines.join('\n'), parse_mode: 'Markdown' })
  } else if (text === '/help' || text === 'help' || text === '/start') {
    await tg('sendMessage', {
      chat_id: CHAT_ID,
      text: 'Commands: /digest /pressure /help. Inline-button taps on gates resolve them.',
    })
  }
}

async function pollUpdates(state: BotState): Promise<void> {
  // Long-poll: blocks up to LONG_POLL_TIMEOUT seconds inside the Telegram API
  // until an update arrives. Reduces command latency from ~POLL_SECONDS to
  // near zero. See audit S4.
  const r: any = await tg('getUpdates', {
    offset: state.last_update_id + 1,
    timeout: LONG_POLL_TIMEOUT,
  })
  if (!r || !r.ok || !Array.isArray(r.result)) return
  for (const update of r.result) {
    state.last_update_id = update.update_id
    if (update.callback_query) await handleCallback(update.callback_query, state)
    if (update.message) await handleMessage(update.message)
  }
}

async function main() {
  if (!BOT_TOKEN || !CHAT_ID) {
    console.error('[telegram-bot] TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set')
    process.exit(1)
  }
  console.log(
    `[telegram-bot] starting (org_root=${ORG_ROOT}, gates=${GATES_DIR}, ` +
    `kernel=${KERNEL_SERVICE_URL}, long_poll=${LONG_POLL_TIMEOUT}s, ` +
    `gate_scan=${POLL_SECONDS}s)`,
  )
  const state = loadState()
  let lastGateScanMs = 0
  while (true) {
    try {
      // Long-poll for messages/callbacks (blocks up to LONG_POLL_TIMEOUT inside
      // Telegram's API). Returns immediately when an update arrives.
      await pollUpdates(state)
      // Throttle gate filesystem scan: at most once per POLL_SECONDS, even if
      // updates are arriving rapidly.
      const nowMs = Date.now()
      if (nowMs - lastGateScanMs >= POLL_SECONDS * 1000) {
        await pushNew(state)
        lastGateScanMs = nowMs
      }
      saveState(state)
    } catch (err) {
      console.error('[telegram-bot] cycle error:', err)
      // brief backoff so a persistent error does not hot-loop
      await new Promise(r => setTimeout(r, 5000))
    }
  }
}

main().catch(err => {
  console.error('[telegram-bot] fatal:', err)
  process.exit(1)
})
