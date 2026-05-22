/**
 * NeedsMePane — the operator "needs-me" queue (GP-230 O1, L1/L2).
 *
 * Replaces the placeholder "Gate Review Queue" panel. Fetches the
 * operator's routed attention feed from GET /api/attention/<actor_id>
 * (a thin daemon proxy to the kernel's GET /kernel/attention/{actor_id})
 * and renders it as one consolidated, urgency-ordered action list.
 *
 * The pane is read-only. It surfaces — for each routed signal — a
 * plain-language headline and its single primary action; it does not
 * itself mutate kernel state (that stays with the typed intent panes).
 *
 * Grouping order (spec §4.5 F-11): blocking-now → approvals-pending →
 * informational.
 */
import { useEffect, useState } from 'react'

// Mirrors RoutedSignal from src/cognitive_firm/userland/attention_router.py
interface RoutedSignal {
  signal_id: string
  signal_class: string
  urgency: string // blocking_now | approval_pending | informational
  headline: string
  primary_action: string // approve | claim | review | none
  source_ref: string
  age_seconds: number
  pace_layer?: string
  target_actor_id?: string | null
  target_role_id?: string | null
}

interface AttentionFeed {
  actor_id: string
  signals: RoutedSignal[]
}

interface Props {
  // The operator identity Orbit reaches the kernel as. Matches the
  // hardcoded actor used by the daemon write path (git-sync.ts).
  actorId?: string
  refreshIntervalMs?: number
}

// Ordered urgency tiers. Anything unrecognized falls through to informational.
const URGENCY_ORDER = ['blocking_now', 'approval_pending', 'informational'] as const
type Urgency = (typeof URGENCY_ORDER)[number]

const URGENCY_LABEL: Record<Urgency, string> = {
  blocking_now: 'Blocking now',
  approval_pending: 'Approvals pending',
  informational: 'Informational',
}

const URGENCY_ACCENT: Record<Urgency, string> = {
  blocking_now: '#ef4444',
  approval_pending: '#f59e0b',
  informational: '#4f8ff7',
}

function normalizeUrgency(u: string): Urgency {
  return (URGENCY_ORDER as readonly string[]).includes(u) ? (u as Urgency) : 'informational'
}

function fmtAge(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return ''
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`
  return `${Math.round(seconds / 86400)}d`
}

function actionLabel(action: string): string {
  switch (action) {
    case 'approve': return 'Approve'
    case 'claim': return 'Claim'
    case 'review': return 'Review'
    case 'none': return ''
    default: return action
  }
}

export function NeedsMePane({
  actorId = 'human.principal',
  refreshIntervalMs = 5000,
}: Props) {
  const [feed, setFeed] = useState<AttentionFeed | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const fetchOnce = async () => {
      try {
        const r = await fetch(`/api/attention/${encodeURIComponent(actorId)}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const j = await r.json()
        if (!alive) return
        setFeed({ actor_id: j.actor_id ?? actorId, signals: j.signals ?? [] })
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
      🔔 Needs Me
    </h2>
  )

  if (loading && !feed) {
    return (
      <div>
        {header}
        <div style={{ color: '#4a5070', fontSize: 12, textAlign: 'center', padding: 20 }}>
          Loading attention feed…
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div>
        {header}
        <div style={{ color: '#ef4444', fontSize: 12, textAlign: 'center', padding: 20 }}>
          Attention feed unavailable: {error}
          <div style={{ color: '#4a5070', fontSize: 11, marginTop: 6 }}>
            (the kernel service must be running for the routed feed)
          </div>
        </div>
      </div>
    )
  }

  const signals = feed?.signals ?? []

  // Group by normalized urgency, preserving the kernel's within-group order.
  const groups: Record<Urgency, RoutedSignal[]> = {
    blocking_now: [],
    approval_pending: [],
    informational: [],
  }
  for (const s of signals) {
    groups[normalizeUrgency(s.urgency)].push(s)
  }

  const total = signals.length
  const blocking = groups.blocking_now.length
  const waitingLine =
    total === 0
      ? 'The firm is not waiting on you. Nothing in your queue.'
      : `The firm is waiting on you: ${total} item${total !== 1 ? 's' : ''}, ${blocking} blocking.`

  return (
    <div>
      {header}

      {/* Plain-language status header */}
      <div style={{
        background: blocking > 0 ? '#3a1d1d' : (total > 0 ? '#2d2410' : '#161822'),
        border: `1px solid ${blocking > 0 ? '#7c2d12' : '#1e2030'}`,
        borderRadius: 8, padding: '8px 12px', marginBottom: 12,
        fontSize: 12, color: blocking > 0 ? '#fecaca' : (total > 0 ? '#fef3c7' : '#9aa0b8'),
      }}>
        {waitingLine}
      </div>

      {total === 0 ? (
        <div style={{ color: '#4a5070', fontSize: 12, textAlign: 'center', padding: 16 }}>
          No routed signals. All agents operating within mandate.
        </div>
      ) : (
        URGENCY_ORDER.map(urgency => {
          const items = groups[urgency]
          if (items.length === 0) return null
          return (
            <div key={urgency} style={{ marginBottom: 14 }}>
              <div style={{
                fontSize: 10, textTransform: 'uppercase', letterSpacing: 1,
                color: URGENCY_ACCENT[urgency], marginBottom: 6,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: URGENCY_ACCENT[urgency], display: 'inline-block',
                }} />
                {URGENCY_LABEL[urgency]} ({items.length})
              </div>
              {items.map(sig => (
                <SignalRow key={sig.signal_id} signal={sig} accent={URGENCY_ACCENT[urgency]} />
              ))}
            </div>
          )
        })
      )}
    </div>
  )
}

function SignalRow({ signal, accent }: { signal: RoutedSignal; accent: string }) {
  const action = actionLabel(signal.primary_action)
  const age = fmtAge(signal.age_seconds)
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 10px', marginBottom: 6,
      background: '#161822', border: '1px solid #1e2030',
      borderLeft: `3px solid ${accent}`, borderRadius: 6,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12, color: '#e8eaf0',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {signal.headline}
        </div>
        <div style={{ fontSize: 10, color: '#6b7394', marginTop: 2 }}>
          {signal.signal_class}
          {age && <span> · {age} old</span>}
        </div>
      </div>
      {action && (
        <span style={{
          fontSize: 10, color: accent,
          border: `1px solid ${accent}`, borderRadius: 6,
          padding: '2px 8px', whiteSpace: 'nowrap',
        }}>
          {action}
        </span>
      )}
    </div>
  )
}
