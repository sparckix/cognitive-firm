/**
 * Git-sync daemon — reads org/ directory, serves state via HTTP + WebSocket.
 *
 * The dashboard's backend. Watches the org/ directory for changes,
 * parses YAML/JSON files into typed OrgState, and serves it:
 *   - GET /api/state → full OrgState JSON
 *   - WebSocket /ws → push updates on file changes
 *
 * This is the local/solo control-plane projection. It reads org/ and
 * the configured workspace, exposes state to Orbit, and writes approved governance
 * decisions back into the canonical filesystem backend. Git is audit/sync/
 * rollback, not the low-latency coordination substrate.
 */

import { readFileSync, readdirSync, existsSync, statSync } from 'fs'
import { join, resolve } from 'path'
import { createServer } from 'http'
import { parse as parseYaml } from 'yaml'
import { WebSocketServer, WebSocket } from 'ws'
import { watch } from 'chokidar'
import { loadAppSurfacePolicy, surfaceWriteAllowed, type SurfaceWriteClass } from './app-surface-policy.js'

import type {
  OrgState, Member, Role, Assignment, Session, DamageSignal, WorkCandidate,
  Objective, KeyResult, Task, Gate, AgentMessage, HumanWorkSession
} from '../types/org.js'

const REPO_ROOT = resolve(import.meta.dirname, '..', '..', '..')
const ORG_DIR = resolve(process.env.ORG_ROOT || join(REPO_ROOT, 'org'))
const WORKSPACE_DIR = resolve(
  process.env.COGNITIVE_FIRM_WORKSPACE ||
  join(REPO_ROOT, 'cognitive_firm_workspace'),
)
const GATES_DIR = resolve(process.env.GATES_DIR || join(WORKSPACE_DIR, 'gates', 'pending'))
const CHANNELS_DIR = join(ORG_DIR, 'channels')
const HUMAN_WORK_LOG = join(ORG_DIR, 'human_work', 'human_work.jsonl')
const PORT = Number(process.env.ORBIT_BACKEND_PORT || 3001)
const HOST = process.env.ORBIT_BACKEND_HOST || '127.0.0.1'
const CORS_ORIGIN = process.env.ORBIT_CORS_ORIGIN || 'http://localhost:5173'
const API_TOKEN = process.env.ORBIT_API_TOKEN || ''
const SURFACE_POLICY = loadAppSurfacePolicy()
const KERNEL_SERVICE_URL = (process.env.COGNITIVE_FIRM_KERNEL_SERVICE_URL || 'http://127.0.0.1:8765').replace(/\/+$/, '')
const KERNEL_SERVICE_TOKEN = process.env.COGNITIVE_FIRM_KERNEL_TOKEN || ''

// ── Markdown frontmatter reader (GP-168 OKR layer uses md+YAML) ─────

const FM_RE = /^---\n([\s\S]*?)\n---\n?/

function readFrontmatter<T extends Record<string, any>>(path: string): T | null {
  try {
    const text = readFileSync(path, 'utf-8')
    const m = text.match(FM_RE)
    if (!m) return null
    const fm = parseYaml(m[1])
    return (fm && typeof fm === 'object') ? (fm as T) : null
  } catch { return null }
}

// ── YAML/JSON file readers ─────────────────────────────────────────

function readYaml<T>(path: string): T | null {
  try {
    return parseYaml(readFileSync(path, 'utf-8')) as T
  } catch { return null }
}

function readJson<T>(path: string): T | null {
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as T
  } catch { return null }
}

function readJsonl<T>(path: string): T[] {
  if (!existsSync(path)) return []
  try {
    return readFileSync(path, 'utf-8')
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean)
      .map(line => {
        try { return JSON.parse(line) as T } catch { return null }
      })
      .filter((row): row is T => !!row)
  } catch { return [] }
}

// ── Org state builder ──────────────────────────────────────────────

function buildState(): OrgState {
  const members: Member[] = []
  const roles: Role[] = []
  const sessions: Session[] = []
  const damageSignals: DamageSignal[] = []

  // Members
  const membersDir = join(ORG_DIR, 'members')
  if (existsSync(membersDir)) {
    for (const f of readdirSync(membersDir).filter(f => f.endsWith('.yaml'))) {
      const m = readYaml<any>(join(membersDir, f))
      if (m) members.push({
        member_id: m.member_id,
        kind: m.kind,
        display_name: m.display_name,
        description: m.description || '',
        substrates: m.substrates || [],
        capabilities: m.capabilities || [],
      })
    }
  }

  // Roles
  const rolesDir = join(ORG_DIR, 'roles')
  if (existsSync(rolesDir)) {
    for (const f of readdirSync(rolesDir).filter(f => f.endsWith('.yaml'))) {
      const r = readYaml<any>(join(rolesDir, f))
      if (r) roles.push({
        role_id: r.role_id,
        role_class: r.role_class || r.role_id,
        description: r.description || '',
        authorized_paths: r.authorized_paths || [],
        forbidden_paths: r.forbidden_paths || [],
        delegates_to: r.delegates_to || [],
        escalates_to: r.escalates_to || [],
        budget: r.budget || { daily_cap_usd: 0, session_cap_usd: 0, single_action_cap_usd: 0, warn_threshold_frac: 0.8 },
        // 2026-05-02: optional agent-CLI utilization caps. Pass through if present
        // in the role yaml; consumed by Orbit's MetaConfigPane (Settings) for editing
        // and visualized in the GovernancePane utilization bar.
        ...(r.agent_utilization ? { agent_utilization: r.agent_utilization } : {}),
        mandate_path: r.mandate_path || '',
      })
    }
  }

  // Assignments
  const assignmentsFile = join(ORG_DIR, 'assignments.yaml')
  const assignmentsRaw = readYaml<any>(assignmentsFile)
  const assignments: Assignment[] = (assignmentsRaw?.assignments || []).map((a: any) => ({
    member: a.member,
    role: a.role,
    substrate: a.substrate,
    is_primary: a.is_primary ?? true,
    valid_from: a.valid_from,
    valid_until: a.valid_until,
    notes: a.notes || '',
  }))

  // Sessions (walk org/sessions/**/meta.json)
  const sessionsDir = join(ORG_DIR, 'sessions')
  if (existsSync(sessionsDir)) {
    walkDir(sessionsDir, (path) => {
      if (path.endsWith('meta.json')) {
        const s = readJson<any>(path)
        if (s) sessions.push({
          session_id: s.session_id,
          member_id: s.member_id,
          role_id: s.role_id,
          substrate: s.substrate,
          start_utc: s.start_utc,
          end_utc: s.end_utc,
          mandate_hash: s.mandate_hash || '',
        })
      }
    })
  }

  // Damage signals (walk org/signals/damage/)
  const damageDir = join(ORG_DIR, 'signals', 'damage')
  if (existsSync(damageDir)) {
    walkDir(damageDir, (path) => {
      if (path.endsWith('.json') && !path.includes('_reason')) {
        const d = readJson<any>(path)
        if (d) damageSignals.push({
          timestamp_utc: d.timestamp_utc,
          source: d.source || '',
          kind: d.kind || 'unknown',
          detail: d.detail || '',
          session_id: d.session_id || '',
          severity: d.severity || 'info',
          resolved: path.includes('_cleared'),
        })
      }
    })
  }

  // Sort damage signals newest first
  damageSignals.sort((a, b) => b.timestamp_utc.localeCompare(a.timestamp_utc))

  // GP-168 addendum (2026-04-27): OKR tree from org/objectives/, org/key_results/, org/tasks/
  const objectives: Objective[] = []
  const objectivesDir = join(ORG_DIR, 'objectives')
  if (existsSync(objectivesDir)) {
    for (const f of readdirSync(objectivesDir).filter(f => f.endsWith('.md') && f !== 'README.md')) {
      const o = readFrontmatter<Objective>(join(objectivesDir, f))
      if (o && o.objective_id) objectives.push(o)
    }
  }

  const keyResults: KeyResult[] = []
  const krDir = join(ORG_DIR, 'key_results')
  if (existsSync(krDir)) {
    for (const f of readdirSync(krDir).filter(f => f.endsWith('.md') && f !== 'README.md')) {
      const k = readFrontmatter<KeyResult>(join(krDir, f))
      if (k && k.kr_id) keyResults.push(k)
    }
  }

  // Tasks: walk pending/, active/, done/ — set status from the directory
  const tasks: Task[] = []
  const tasksRoot = join(ORG_DIR, 'tasks')
  for (const stateDir of ['pending', 'active', 'done'] as const) {
    const d = join(tasksRoot, stateDir)
    if (!existsSync(d)) continue
    for (const f of readdirSync(d).filter(f => f.endsWith('.md'))) {
      const t = readFrontmatter<Task>(join(d, f))
      if (!t) continue
      // Directory wins over frontmatter status (filesystem is authoritative)
      const taskWithStatus: Task = { ...t, task_id: t.task_id || f.replace(/\.md$/, ''), status: stateDir }
      tasks.push(taskWithStatus)
    }
  }

  // GP-168 single executive inbox at workspace/gates/pending/
  const gates: Gate[] = []
  if (existsSync(GATES_DIR)) {
    for (const f of readdirSync(GATES_DIR).filter(f => f.endsWith('.json'))) {
      const g = readJson<Gate>(join(GATES_DIR, f))
      if (g) {
        gates.push({
          ...g,
          gate_id: g.gate_id || f.replace(/\.json$/, ''),
          status: g.status || 'pending',
        })
      }
    }
  }

  const agentMessages: AgentMessage[] = []
  if (existsSync(CHANNELS_DIR)) {
    walkDir(CHANNELS_DIR, (path) => {
      if (!path.endsWith('.json')) return
      if (!path.includes('/inbox/')) return
      const msg = readJson<AgentMessage>(path)
      if (msg && msg.message_id && msg.status !== 'closed') {
        agentMessages.push(msg)
      }
    })
  }
  agentMessages.sort((a, b) => b.created_utc.localeCompare(a.created_utc))

  const humanWorkSessions = readJsonl<HumanWorkSession>(HUMAN_WORK_LOG)
    .sort((a, b) => b.updated_at_utc.localeCompare(a.updated_at_utc))

  return {
    members,
    roles,
    assignments,
    sessions,
    damage_signals: damageSignals.slice(0, 50), // last 50
    work_candidates: [], // populated by work_discovery.py call
    objectives,
    key_results: keyResults,
    tasks,
    gates,
    agent_messages: agentMessages.slice(0, 50),
    human_work_sessions: humanWorkSessions.slice(0, 100),
    last_sync: new Date().toISOString(),
  }
}

function walkDir(dir: string, cb: (path: string) => void) {
  try {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) walkDir(full, cb)
      else cb(full)
    }
  } catch { /* permission or broken symlink */ }
}

// ── HTTP server ────────────────────────────────────────────────────

let cachedState: OrgState = buildState()

function requestAuthorized(req: any, res: any): boolean {
  if (!API_TOKEN) {
    res.writeHead(401, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ ok: false, error: 'ORBIT_API_TOKEN is required for write requests' }))
    return false
  }
  const expected = `Bearer ${API_TOKEN}`
  if (req.headers.authorization === expected) return true
  res.writeHead(401, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify({ ok: false, error: 'unauthorized' }))
  return false
}

function surfaceWriteAuthorized(res: any, writeClass: SurfaceWriteClass): boolean {
  const verdict = surfaceWriteAllowed(SURFACE_POLICY, writeClass)
  if (verdict.ok) return true
  res.writeHead(409, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify({
    ok: false,
    error: verdict.reason,
    app_surface_policy: SURFACE_POLICY,
  }))
  return false
}

function validGateId(gateId: unknown): gateId is string {
  return typeof gateId === 'string' && /^[A-Za-z0-9_.:-]+$/.test(gateId)
}

function validHumanWorkId(sessionId: unknown): sessionId is string {
  return typeof sessionId === 'string' && /^hws_[A-Za-z0-9_.:-]+$/.test(sessionId)
}

const VALID_HUMAN_WORK_STATES = new Set([
  'requested', 'claimed', 'in_progress', 'blocked', 'handed_off', 'completed', 'abandoned', 'integrated',
])
const VALID_HUMAN_WORK_MODES = new Set([
  'source_check', 'edit', 'external_action', 'judgment', 'relationship', 'data_entry', 'taste_call', 'other',
])
const VALID_BOTTLENECKS = new Set([
  'authority', 'access', 'taste', 'relationship', 'cognition', 'labor', 'safety', 'other',
])
const VALID_OBSERVABILITY = new Set([
  'digital_artifact', 'external_system', 'human_attested', 'unobservable',
])
const VALID_RECEIPT_TYPES = new Set([
  'note', 'artifact_ref', 'external_ref', 'witness', 'none',
])
const VALID_INTERACTION_SURFACES = new Set([
  'offline', 'cli', 'orbit', 'telegram', 'external_system', 'mixed',
])
function parseRequestBody(req: any): Promise<any> {
  return new Promise((resolveBody, rejectBody) => {
    let body = ''
    req.on('data', (chunk: Buffer) => { body += chunk })
    req.on('end', () => {
      try { resolveBody(JSON.parse(body || '{}')) }
      catch (err) { rejectBody(err) }
    })
  })
}

async function getKernelService(path: string): Promise<any> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (KERNEL_SERVICE_TOKEN) headers.Authorization = `Bearer ${KERNEL_SERVICE_TOKEN}`
  const response = await fetch(`${KERNEL_SERVICE_URL}${path}`, {
    method: 'GET',
    headers,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok || body.ok === false) {
    throw new Error(String(body.error || `kernel service returned HTTP ${response.status}`))
  }
  return body
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
        surface: 'orbit',
      },
    }),
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok || body.ok === false) {
    throw new Error(String(body.error || `kernel service returned HTTP ${response.status}`))
  }
  return body
}

const server = createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', CORS_ORIGIN)
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')

  if (req.method === 'OPTIONS') {
    res.writeHead(204)
    res.end()
    return
  }

  if (req.url === '/api/state') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify(cachedState))
    return
  }

  if (req.url === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ ok: true, last_sync: cachedState.last_sync, app_surface_policy: SURFACE_POLICY }))
    return
  }

  if (req.url === '/api/app_surface') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ ok: true, policy: SURFACE_POLICY }))
    return
  }

  // ── /api/chat/* — per-role two-way chat (Orbit v2 ChatPane) ──────
  // GET /api/chat/:role_id?day=YYYY-MM-DD → list messages for that role+day
  // POST /api/chat/send body: { role_id, text } → append principal message
  //   to org/sessions/<role_id>/chat/<today>.jsonl. Daemon picks it up next
  //   tick and generates a cheap-tier reply (subscription via claude/gemini).
  if (req.url && req.url.startsWith('/api/chat/') && req.method === 'GET') {
    const m = req.url.match(/^\/api\/chat\/([A-Za-z0-9_]+)(?:\?day=([0-9-]+))?/)
    if (!m) {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: 'bad url' }))
      return
    }
    const roleId = m[1]
    const day = m[2] || new Date().toISOString().slice(0, 10)
    const chatFile = join(REPO_ROOT, 'org', 'sessions', roleId, 'chat', `${day}.jsonl`)
    if (!existsSync(chatFile)) {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ role_id: roleId, day, messages: [] }))
      return
    }
    try {
      const lines = readFileSync(chatFile, 'utf-8').split('\n').filter((l: string) => l.trim())
      const messages = lines.map((l: string) => { try { return JSON.parse(l) } catch { return null } }).filter(Boolean)
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ role_id: roleId, day, messages }))
    } catch (err) {
      res.writeHead(500, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(err) }))
    }
    return
  }

  if (req.url === '/api/chat/send' && req.method === 'POST') {
    if (!requestAuthorized(req, res)) return
    if (!surfaceWriteAuthorized(res, 'kernel_intent')) return
    parseRequestBody(req).then(async payload => {
      try {
        const { role_id, text } = payload
        if (!role_id || typeof role_id !== 'string' || !/^[A-Za-z0-9_]+$/.test(role_id)) {
          res.writeHead(400, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ ok: false, error: 'invalid role_id' }))
          return
        }
        if (!text || typeof text !== 'string' || text.length > 4000) {
          res.writeHead(400, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ ok: false, error: 'text required (≤4000 chars)' }))
          return
        }
        const kernel = await callKernelService('/kernel/chat/messages', {
          role_id,
          text,
          sender: 'principal',
        })
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: true, message: kernel.result.message }))
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: String(err) }))
      }
    })
    return
  }

  // ── /api/spend/today — Orbit v2 SpendPane ─────────────────────────
  // Reads workspace/spend/<today>.json and aggregates by category +
  // by model. Frontend can compare against per-role budget caps from cachedState.roles.
  if (req.url === '/api/spend/today') {
    const today = new Date().toISOString().slice(0, 10) // YYYY-MM-DD
    const spendFile = join(WORKSPACE_DIR, 'spend', `${today}.json`)
    if (!existsSync(spendFile)) {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ date: today, total_usd: 0, entries: [], by_category: {}, by_model: {} }))
      return
    }
    try {
      const raw: { date: string; entries: any[] } = JSON.parse(readFileSync(spendFile, 'utf-8'))
      const entries = raw.entries || []
      const byCategory: Record<string, { count: number; usd: number }> = {}
      const byModel: Record<string, { count: number; usd: number }> = {}
      let total = 0
      for (const e of entries) {
        const usd = Number(e.cost_usd) || 0
        total += usd
        const cat = e.category || 'unknown'
        byCategory[cat] = byCategory[cat] || { count: 0, usd: 0 }
        byCategory[cat].count += 1
        byCategory[cat].usd += usd
        const model = e.model_name || 'unknown'
        byModel[model] = byModel[model] || { count: 0, usd: 0 }
        byModel[model].count += 1
        byModel[model].usd += usd
      }
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({
        date: today,
        total_usd: total,
        entries_count: entries.length,
        by_category: byCategory,
        by_model: byModel,
        // Most recent 10 entries — frontend renders as a feed
        recent: entries.slice(-10).reverse(),
      }))
    } catch (err) {
      res.writeHead(500, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(err) }))
    }
    return
  }

  // ── ACTION ENDPOINTS (write to canonical filesystem backend) ──────

  if (req.url === '/api/human_work/create' && req.method === 'POST') {
    if (!requestAuthorized(req, res)) return
    if (!surfaceWriteAuthorized(res, 'kernel_intent')) return
    parseRequestBody(req).then(async payload => {
      const objective = String(payload.objective || '').trim()
      const requestedBy = String(payload.requested_by || 'principal').trim()
      const humanActor = String(payload.human_actor || 'principal').trim()
      const workMode = String(payload.work_mode || 'other')
      const bottleneckClass = String(payload.bottleneck_class || 'other')
      const observability = String(payload.observability || 'human_attested')
      const receiptType = String(payload.receipt_type || 'none')
      const interactionSurface = String(payload.interaction_surface || 'mixed')
      const coordinationPattern = String(payload.coordination_pattern || '')
      const isA2H = coordinationPattern === 'a2h_work_request'
      const humanDeliverable = String(payload.human_deliverable || '').trim()
      if (!objective || objective.length > 1000) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: 'objective required (<=1000 chars)' }))
        return
      }
      if (isA2H && (!requestedBy.startsWith('role.') || !humanDeliverable)) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: 'A2H requests require role.* requested_by and human_deliverable' }))
        return
      }
      if (
        !VALID_HUMAN_WORK_MODES.has(workMode) ||
        !VALID_BOTTLENECKS.has(bottleneckClass) ||
        !VALID_OBSERVABILITY.has(observability) ||
        !VALID_RECEIPT_TYPES.has(receiptType) ||
        !VALID_INTERACTION_SURFACES.has(interactionSurface)
      ) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: 'invalid human work enum value' }))
        return
      }
      const kernel = await callKernelService('/kernel/human-work', {
        coordination_pattern: isA2H ? 'a2h_work_request' : undefined,
        requested_by: requestedBy,
        human_actor: humanActor,
        objective,
        work_mode: workMode,
        bottleneck_class: bottleneckClass,
        human_deliverable: humanDeliverable || undefined,
        observability,
        receipt_required: Boolean(payload.receipt_required),
        receipt_type: receiptType,
        interaction_surface: interactionSurface,
        sample_for_review: Boolean(payload.sample_for_review),
        tenant_id: payload.tenant_id,
        project_id: payload.project_id,
        collaborating_roles: payload.collaborating_roles,
        artifact_refs: payload.artifact_refs,
        obligation_id: payload.obligation_id,
        deadline_utc: payload.deadline_utc,
        confidence: payload.confidence,
        agent_followup_ref: payload.agent_followup_ref,
        receipt: payload.receipt,
        agent_counterparty_role: payload.agent_counterparty_role,
        agent_followup_required: Boolean(payload.agent_followup_required),
      })
      const session = kernel.session as HumanWorkSession
      cachedState = buildState()
      broadcast(cachedState)
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true, session }))
    }).catch(err => {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(err) }))
    })
    return
  }

  if (req.url === '/api/human_work/update-state' && req.method === 'POST') {
    if (!requestAuthorized(req, res)) return
    if (!surfaceWriteAuthorized(res, 'kernel_intent')) return
    parseRequestBody(req).then(async payload => {
      const sessionId = payload.session_id
      const nextState = String(payload.state || '')
      if (!validHumanWorkId(sessionId) || !VALID_HUMAN_WORK_STATES.has(nextState)) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: 'invalid session_id or state' }))
        return
      }
      const rows = readJsonl<HumanWorkSession>(HUMAN_WORK_LOG)
      let updated: HumanWorkSession | null = null
      if (!rows.some(row => row.session_id === sessionId)) {
        res.writeHead(404, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: 'session not found' }))
        return
      }
      const kernel = await callKernelService(`/kernel/human-work/${sessionId}/state`, {
        state: nextState,
        completion_summary: payload.completion_summary,
        integration_ref: payload.integration_ref,
        receipt: payload.receipt,
        confidence: payload.confidence,
        agent_followup_ref: payload.agent_followup_ref,
        agent_followup_required: payload.agent_followup_required,
      })
      updated = kernel.session as HumanWorkSession
      cachedState = buildState()
      broadcast(cachedState)
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true, session: updated }))
    }).catch(err => {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(err) }))
    })
    return
  }

  if (req.url === '/api/human_work/interaction' && req.method === 'POST') {
    if (!requestAuthorized(req, res)) return
    if (!surfaceWriteAuthorized(res, 'kernel_intent')) return
    parseRequestBody(req).then(async payload => {
      const sessionId = payload.session_id
      const actor = String(payload.actor || '').trim()
      const eventType = String(payload.event_type || '').trim()
      const summary = String(payload.summary || '').trim()
      const surface = String(payload.surface || 'mixed')
      if (!validHumanWorkId(sessionId) || !actor || !eventType || !summary || !VALID_INTERACTION_SURFACES.has(surface)) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: 'invalid interaction payload' }))
        return
      }
      const rows = readJsonl<HumanWorkSession>(HUMAN_WORK_LOG)
      let updated: HumanWorkSession | null = null
      if (!rows.some(row => row.session_id === sessionId)) {
        res.writeHead(404, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: 'session not found' }))
        return
      }
      const kernel = await callKernelService(`/kernel/human-work/${sessionId}/interaction`, {
        actor,
        event_type: eventType,
        summary,
        surface,
        artifact_refs: payload.artifact_refs,
        blocker: payload.blocker,
        agent_followup_required: payload.agent_followup_required,
      })
      updated = kernel.session as HumanWorkSession
      cachedState = buildState()
      broadcast(cachedState)
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true, session: updated }))
    }).catch(err => {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(err) }))
    })
    return
  }

  // Gate approval: POST /api/gate/resolve
  if (req.url === '/api/gate/resolve' && req.method === 'POST') {
    if (!requestAuthorized(req, res)) return
    if (!surfaceWriteAuthorized(res, 'kernel_intent')) return
    parseRequestBody(req).then(async payload => {
      try {
        const { gate_id, option_id, verdict, reason } = payload
        if (!validGateId(gate_id)) {
          res.writeHead(400, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ ok: false, error: 'invalid gate_id' }))
          return
        }
        const chosen = option_id ?? verdict ?? 'resolved'
        const kernel = await callKernelService(`/kernel/gates/${gate_id}/resolve`, {
          chosen_option: chosen,
          reason: reason ?? '',
          resolved_by: 'orbit',
        })
        cachedState = buildState()
        broadcast(cachedState)
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({
          ok: true,
          path: kernel.result.path,
          already_resolved: Boolean(kernel.result.already_resolved),
        }))
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: String(e) }))
      }
    }).catch(err => {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(err) }))
    })
    return
  }

  // Directive: POST /api/directive
  if (req.url === '/api/directive' && req.method === 'POST') {
    if (!requestAuthorized(req, res)) return
    if (!surfaceWriteAuthorized(res, 'kernel_intent')) return
    parseRequestBody(req).then(async payload => {
      try {
        const { target_role, message } = payload
        const kernel = await callKernelService('/kernel/directives', {
          target_role,
          message,
          from: 'principal',
        })
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: true, path: kernel.result.path }))
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: String(e) }))
      }
    }).catch(err => {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(err) }))
    })
    return
  }

  // Control: POST /api/control (STOP/PAUSE/RESUME)
  if (req.url === '/api/control' && req.method === 'POST') {
    if (!requestAuthorized(req, res)) return
    if (!surfaceWriteAuthorized(res, 'kernel_intent')) return
    parseRequestBody(req).then(async payload => {
      try {
        const { target_role, action } = payload
        if (!['STOP', 'PAUSE', 'RESUME'].includes(action)) {
          res.writeHead(400)
          res.end(JSON.stringify({ ok: false, error: 'action must be STOP, PAUSE, or RESUME' }))
          return
        }
        const kernel = await callKernelService('/kernel/controls', {
          action,
          target_role,
          issued_by: 'principal',
        })
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: true, action, target_role, path: kernel.result.path }))
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: String(e) }))
      }
    }).catch(err => {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(err) }))
    })
    return
  }

  // Pending gates: GET /api/gates/pending
  if (req.url === '/api/gates/pending') {
    const gates: any[] = []
    if (existsSync(GATES_DIR)) {
      walkDir(GATES_DIR, (path) => {
        if (path.endsWith('.json')) {
          const g = readJson<any>(path)
          if (g) gates.push(g)
        }
      })
    }
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify(gates))
    return
  }

  // ── Frontier-state (RD-1.12, 2026-05-02) ─────────────────────────
  // Reads workspace/frontier_state/<slug>.json so the FrontierStatePane
  // can render route ranking / obstruction counters / pending actions / history.

  // GET /api/frontier_state → { projects: [{ slug, state }] }
  if (req.url === '/api/frontier_state' || req.url?.startsWith('/api/frontier_state?')) {
    const dir = join(WORKSPACE_DIR, 'frontier_state')
    const projects: Array<{ slug: string, state: any }> = []
    if (existsSync(dir)) {
      try {
        for (const f of readdirSync(dir)) {
          if (!f.endsWith('.json')) continue
          const slug = f.replace(/\.json$/, '')
          try {
            const state = readJson<any>(join(dir, f))
            if (state) projects.push({ slug, state })
          } catch { /* skip unreadable */ }
        }
      } catch { /* dir empty or unreadable */ }
    }
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ projects }))
    return
  }

  // GET /api/frontier_state/<slug> → single-project state
  if (req.url?.startsWith('/api/frontier_state/')) {
    const m = req.url.match(/^\/api\/frontier_state\/([a-z0-9_\-]+)$/)
    if (!m) {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: 'invalid slug' }))
      return
    }
    const slug = m[1]
    const path = join(WORKSPACE_DIR, 'frontier_state', `${slug}.json`)
    if (!existsSync(path)) {
      res.writeHead(404, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: 'not found', slug }))
      return
    }
    try {
      const state = readJson<any>(path)
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ slug, state }))
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(e) }))
    }
    return
  }

  // ── Operator attention feed (O1 L1, GP-230) ──────────────────────
  // GET /api/attention/<actor_id> → thin read proxy to the kernel's
  // GET /kernel/attention/{actor_id} route. The routed-signal feed is a
  // kernel-computed read (not a filesystem projection), so — consistent
  // with the write path — it goes through the kernel service rather than
  // being reconstructed in the daemon. Read-only; no surface-policy gate.
  if (req.url?.startsWith('/api/attention/') && req.method === 'GET') {
    const m = req.url.match(/^\/api\/attention\/([A-Za-z0-9_.:-]+)$/)
    if (!m) {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: 'invalid actor_id' }))
      return
    }
    const actorId = m[1]
    getKernelService(`/kernel/attention/${actorId}`)
      .then(body => {
        const result = body.result ?? body
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({
          actor_id: result.actor_id ?? actorId,
          signals: result.signals ?? [],
        }))
      })
      .catch(err => {
        res.writeHead(502, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: String(err) }))
      })
    return
  }

  // ── Member-human work inbox (O1 L2, GP-230) ──────────────────────
  // GET /api/work-inbox/<actor_id> → thin read proxy to the kernel's
  // GET /kernel/work-inbox/{actor_id} route. The member-human's bounded
  // task inbox is a kernel-computed read model over human_work.jsonl
  // (not a filesystem projection rebuilt here), so — like /api/attention
  // — it goes through the kernel service. Read-only; no surface-policy
  // gate. Distinct from /api/attention: that is the operator's escalation
  // feed, this is the member-human's work-to-do list.
  if (req.url?.startsWith('/api/work-inbox/') && req.method === 'GET') {
    const m = req.url.match(/^\/api\/work-inbox\/([A-Za-z0-9_.:-]+)$/)
    if (!m) {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: 'invalid actor_id' }))
      return
    }
    const actorId = m[1]
    getKernelService(`/kernel/work-inbox/${actorId}`)
      .then(body => {
        const result = body.result ?? body
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({
          actor_id: result.actor_id ?? actorId,
          items: result.items ?? [],
        }))
      })
      .catch(err => {
        res.writeHead(502, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: String(err) }))
      })
    return
  }

  // ── Agent-utilization (2026-05-02) ───────────────────────────────
  // Snapshot of today's per-role / per-cli utilization, plus an editor
  // for the agent_utilization caps in org/roles/<role>.yaml.

  // GET /api/agent_utilization/snapshot[?date=YYYY-MM-DD]
  if (req.url?.startsWith('/api/agent_utilization/snapshot')) {
    const url = new URL(req.url, `http://${req.headers.host}`)
    const dateParam = url.searchParams.get('date')
    const date = dateParam || new Date().toISOString().slice(0, 10)
    const utilPath = join(WORKSPACE_DIR, 'agent_utilization', `${date}.json`)
    if (!existsSync(utilPath)) {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({
        date,
        entries: [],
        totals: { by_role: {}, by_cli: {}, by_role_cli: {} },
      }))
      return
    }
    try {
      const payload = readJson<any>(utilPath)
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(payload || { date, entries: [] }))
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(e) }))
    }
    return
  }

  // POST /api/role/<role_id>/agent_utilization
  // Body: AgentUtilization (the cap block). Delegates the write to kernel service.
  if (req.url?.startsWith('/api/role/') && req.url.endsWith('/agent_utilization') && req.method === 'POST') {
    if (!requestAuthorized(req, res)) return
    if (!surfaceWriteAuthorized(res, 'kernel_intent')) return
    const m = req.url.match(/^\/api\/role\/([a-z_]+)\/agent_utilization$/)
    if (!m) {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: 'invalid role_id in url' }))
      return
    }
    const roleId = m[1]
    const rolePath = join(ORG_DIR, 'roles', `${roleId}.yaml`)
    if (!existsSync(rolePath)) {
      res.writeHead(404, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: `role ${roleId} not found` }))
      return
    }
    parseRequestBody(req).then(async caps => {
      try {
        // Validate required numeric keys
        const required = [
          'daily_cap_seconds', 'daily_cap_output_tokens', 'daily_cap_turn_count',
          'session_cap_seconds', 'absolute_ceiling_seconds', 'warn_threshold_frac',
        ]
        for (const k of required) {
          if (typeof caps[k] !== 'number') {
            res.writeHead(400, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify({ ok: false, error: `missing or non-numeric field: ${k}` }))
            return
          }
        }
        const kernel = await callKernelService(`/kernel/roles/${roleId}/agent-utilization`, {
          agent_utilization: caps,
          updated_by: 'orbit',
        })
        cachedState = buildState()
        broadcast(cachedState)
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({
          ok: true,
          path: kernel.result.path,
          agent_utilization: kernel.result.payload.agent_utilization,
        }))
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: false, error: String(e) }))
      }
    }).catch(err => {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false, error: String(err) }))
    })
    return
  }

  res.writeHead(404)
  res.end('Not found')
})

// ── WebSocket for push updates ─────────────────────────────────────

const wss = new WebSocketServer({ server, path: '/ws' })
const clients = new Set<WebSocket>()

wss.on('connection', (ws) => {
  clients.add(ws)
  ws.send(JSON.stringify({ type: 'state', data: cachedState }))
  ws.on('close', () => clients.delete(ws))
})

function broadcast(state: OrgState) {
  const msg = JSON.stringify({ type: 'state', data: state })
  for (const ws of clients) {
    if (ws.readyState === WebSocket.OPEN) ws.send(msg)
  }
}

// ── File watcher ───────────────────────────────────────────────────

const watcher = watch([ORG_DIR, GATES_DIR], {
  ignoreInitial: true,
  persistent: true,
  depth: 10,
  awaitWriteFinish: { stabilityThreshold: 500 },
})

let debounceTimer: ReturnType<typeof setTimeout> | null = null

watcher.on('all', (event, path) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    console.log(`[sync] ${event}: ${path.replace(REPO_ROOT, '')}`)
    cachedState = buildState()
    broadcast(cachedState)
  }, 1000)
})

// ── Start ──────────────────────────────────────────────────────────

server.listen(PORT, HOST, () => {
  console.log(`[git-sync] Serving org/ state at http://${HOST}:${PORT}`)
  console.log(`[git-sync] WebSocket at ws://${HOST}:${PORT}/ws`)
  console.log(`[git-sync] Watching ${ORG_DIR} and ${GATES_DIR} for changes`)
  console.log(`[git-sync] Members: ${cachedState.members.map(m => m.member_id).join(', ')}`)
  console.log(`[git-sync] Roles: ${cachedState.roles.map(r => r.role_id).join(', ')}`)
  console.log(`[git-sync] Sessions: ${cachedState.sessions.length} (${cachedState.sessions.filter(s => !s.end_utc).length} active)`)
  console.log(`[git-sync] Damage signals: ${cachedState.damage_signals.length} (${cachedState.damage_signals.filter(d => !d.resolved).length} unresolved)`)
})
