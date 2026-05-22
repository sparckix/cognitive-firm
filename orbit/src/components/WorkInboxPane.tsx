/**
 * WorkInboxPane — the member-human "work inbox" (GP-230 O1, L2).
 *
 * The member-human's face: a bounded-task inbox, distinct from the
 * operator's escalation pager (`NeedsMePane`). Fetches the member-human's
 * assigned work from GET /api/work-inbox/<actor_id> (a thin daemon proxy
 * to the kernel's GET /kernel/work-inbox/{actor_id}) and renders it as a
 * to-do list of bounded tasks: objective, named deliverable, state,
 * deadline, and whether a typed receipt is required on submit.
 *
 * The pane is read-only. It surfaces what the firm has asked this human
 * to produce; it does not itself mutate kernel state (claim/submit stay
 * with the typed intent panes — see design §2.5).
 *
 * Sort order: blocked tasks first (they are stuck on the human), then by
 * deadline (soonest first; undated last).
 */
import { useEffect, useState } from 'react'

// Mirrors one item of the kernel's GET /kernel/work-inbox/{actor_id}
// payload (design §2.5, WorkInboxItem) — governance-interpretation
// fields only, never raw JSONL.
interface WorkInboxItem {
  session_id: string
  objective: string
  human_deliverable: string
  work_mode: string
  bottleneck_class: string
  state: string // requested | claimed | in_progress | blocked
  deadline_utc: string | null
  receipt_required: boolean
  receipt_type: string // note | artifact_ref | external_ref | witness | none
  requested_by: string
}

interface WorkInbox {
  actor_id: string
  items: WorkInboxItem[]
}

interface Props {
  // The member-human identity Orbit fetches the inbox for. Defaults to the
  // single-operator principal, consistent with the daemon write path.
  actorId?: string
  refreshIntervalMs?: number
}

// Plain-language labels for the human-work state machine
// (human_work.py ALLOWED_TRANSITIONS, non-terminal subset).
const STATE_LABEL: Record<string, string> = {
  requested: 'New — not yet claimed',
  claimed: 'Claimed',
  in_progress: 'In progress',
  blocked: 'Blocked',
}

const STATE_ACCENT: Record<string, string> = {
  requested: '#4f8ff7',
  claimed: '#a78bfa',
  in_progress: '#34d399',
  blocked: '#ef4444',
}

function stateLabel(s: string): string {
  return STATE_LABEL[s] ?? s
}

function stateAccent(s: string): string {
  return STATE_ACCENT[s] ?? '#6b7394'
}

// Deadline formatting + a relative urgency hint.
function fmtDeadline(iso: string | null): { text: string; overdue: boolean } | null {
  if (!iso) return null
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return null
  const deltaMs = t - Date.now()
  const overdue = deltaMs < 0
  const absH = Math.abs(deltaMs) / 3600000
  let rel: string
  if (absH < 1) rel = `${Math.round(Math.abs(deltaMs) / 60000)}m`
  else if (absH < 48) rel = `${Math.round(absH)}h`
  else rel = `${Math.round(absH / 24)}d`
  const when = new Date(t).toLocaleString()
  return { text: overdue ? `overdue ${rel} (${when})` : `due in ${rel} (${when})`, overdue }
}

// Sort: blocked first, then by deadline ascending, undated last.
function sortItems(items: WorkInboxItem[]): WorkInboxItem[] {
  return [...items].sort((a, b) => {
    const aBlocked = a.state === 'blocked' ? 0 : 1
    const bBlocked = b.state === 'blocked' ? 0 : 1
    if (aBlocked !== bBlocked) return aBlocked - bBlocked
    const aT = a.deadline_utc ? Date.parse(a.deadline_utc) : Infinity
    const bT = b.deadline_utc ? Date.parse(b.deadline_utc) : Infinity
    return aT - bT
  })
}

export function WorkInboxPane({
  actorId = 'human.principal',
  refreshIntervalMs = 5000,
}: Props) {
  const [inbox, setInbox] = useState<WorkInbox | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const fetchOnce = async () => {
      try {
        const r = await fetch(`/api/work-inbox/${encodeURIComponent(actorId)}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const j = await r.json()
        if (!alive) return
        setInbox({ actor_id: j.actor_id ?? actorId, items: j.items ?? [] })
        setError(null)
      } catch (e: any) {
        if (!alive) return
        setError(e?.message || String(e))
      } finally {
        if (alive) setLoading(false)
      }
    }
    fetchOnce()
    const id = setInterval(fetchOnce, refreshIntervalMs)
    return () => { alive = false; clearInterval(id) }
  }, [actorId, refreshIntervalMs])

  const header = (
    <h2 style={{
      fontSize: 11, textTransform: 'uppercase', letterSpacing: 1.5,
      color: '#6b7394', marginBottom: 12,
      display: 'flex', alignItems: 'center', gap: 8,
    }}>
      📥 Work Inbox
    </h2>
  )

  if (loading && !inbox) {
    return (
      <div>
        {header}
        <div style={{ color: '#4a5070', fontSize: 12, textAlign: 'center', padding: 20 }}>
          Loading work inbox…
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div>
        {header}
        <div style={{ color: '#ef4444', fontSize: 12, textAlign: 'center', padding: 20 }}>
          Work inbox unavailable: {error}
          <div style={{ color: '#4a5070', fontSize: 11, marginTop: 6 }}>
            (the kernel service must be running for the work inbox)
          </div>
        </div>
      </div>
    )
  }

  const items = sortItems(inbox?.items ?? [])
  const total = items.length
  const blocked = items.filter(i => i.state === 'blocked').length
  const summaryLine =
    total === 0
      ? 'Nothing assigned to you. Your work inbox is empty.'
      : `${total} task${total !== 1 ? 's' : ''} assigned to you${blocked > 0 ? `, ${blocked} blocked` : ''}.`

  return (
    <div>
      {header}

      {/* Plain-language status header */}
      <div style={{
        background: blocked > 0 ? '#3a1d1d' : (total > 0 ? '#161822' : '#161822'),
        border: `1px solid ${blocked > 0 ? '#7c2d12' : '#1e2030'}`,
        borderRadius: 8, padding: '8px 12px', marginBottom: 12,
        fontSize: 12, color: blocked > 0 ? '#fecaca' : '#9aa0b8',
      }}>
        {summaryLine}
      </div>

      {total === 0 ? (
        <div style={{ color: '#4a5070', fontSize: 12, textAlign: 'center', padding: 16 }}>
          No bounded tasks waiting on you.
        </div>
      ) : (
        items.map(item => <WorkRow key={item.session_id} item={item} />)
      )}
    </div>
  )
}

function WorkRow({ item }: { item: WorkInboxItem }) {
  const accent = stateAccent(item.state)
  const deadline = fmtDeadline(item.deadline_utc)
  return (
    <div style={{
      padding: '10px 12px', marginBottom: 8,
      background: '#161822', border: '1px solid #1e2030',
      borderLeft: `3px solid ${accent}`, borderRadius: 6,
    }}>
      {/* Objective + state badge */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, color: '#e8eaf0', lineHeight: 1.4 }}>
            {item.objective || '(no objective stated)'}
          </div>
        </div>
        <span style={{
          fontSize: 10, color: accent,
          border: `1px solid ${accent}`, borderRadius: 6,
          padding: '2px 8px', whiteSpace: 'nowrap',
        }}>
          {stateLabel(item.state)}
        </span>
      </div>

      {/* Named deliverable — what the firm expects this human to produce */}
      {item.human_deliverable && (
        <div style={{ fontSize: 11, color: '#9aa0b8', marginTop: 6 }}>
          Deliverable: <span style={{ color: '#c8cdd8' }}>{item.human_deliverable}</span>
        </div>
      )}

      {/* Meta row: requester, work mode, bottleneck */}
      <div style={{ fontSize: 10, color: '#6b7394', marginTop: 6 }}>
        {item.requested_by && <span>from {item.requested_by}</span>}
        {item.work_mode && <span> · {item.work_mode}</span>}
        {item.bottleneck_class && <span> · {item.bottleneck_class}</span>}
      </div>

      {/* Deadline + receipt requirement */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        marginTop: 6, flexWrap: 'wrap',
      }}>
        {deadline && (
          <span style={{
            fontSize: 10, color: deadline.overdue ? '#fecaca' : '#9aa0b8',
            background: deadline.overdue ? '#3a1d1d' : 'transparent',
            border: `1px solid ${deadline.overdue ? '#7c2d12' : '#1e2030'}`,
            borderRadius: 6, padding: '2px 8px',
          }}>
            ⏱ {deadline.text}
          </span>
        )}
        {item.receipt_required && (
          <span style={{
            fontSize: 10, color: '#fef3c7',
            border: '1px solid #7c5a12', borderRadius: 6, padding: '2px 8px',
          }}>
            🧾 receipt required{item.receipt_type && item.receipt_type !== 'none'
              ? ` (${item.receipt_type})` : ''}
          </span>
        )}
      </div>
    </div>
  )
}
