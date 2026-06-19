/**
 * ProvenanceTimelinePane — read-only "why did this happen?" projection.
 *
 * Fetches GET /api/provenance-timeline and /api/provenance-report with an
 * explicit selector and renders the kernel's joined governance timeline. This
 * is intentionally not an action surface: no ranking, approval, assignment, or
 * workflow mutation.
 */
import { useState } from 'react'

type SelectorKey = 'run_id' | 'ref' | 'tenant_id'

interface TimelineEvent {
  occurred_at_utc?: string
  event_kind?: string
  object_ref?: string
  summary?: string
  source?: string
  actor?: string | null
  related_refs?: string[]
  tenant_id?: string | null
  project_id?: string | null
}

interface TimelinePayload {
  query?: Record<string, string | null>
  counts?: Record<string, number>
  caveats?: string[]
  events?: TimelineEvent[]
  read_only?: boolean
}

interface FollowThroughPayload {
  status?: string
  decision_events?: number
  outcome_links?: number
  routine_reviews?: number
  learning_events?: number
  learning_use_receipts?: number
  human_work_sessions?: number
  latest_refs?: string[]
  read_only?: boolean
  projection_only?: boolean
}

interface ProvenanceReportPayload {
  follow_through?: FollowThroughPayload
  coverage?: { status?: string; gaps?: string[] }
  review_questions?: string[]
  read_only?: boolean
}

const SELECTOR_LABEL: Record<SelectorKey, string> = {
  run_id: 'Run',
  ref: 'Reference',
  tenant_id: 'Tenant',
}

function fmtTime(iso?: string): string {
  if (!iso) return 'time unknown'
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return iso
  return new Date(t).toLocaleString()
}

function nonEmptyRefs(event: TimelineEvent): string[] {
  const refs = [
    event.object_ref,
    ...(event.related_refs ?? []),
    event.tenant_id ? `tenant:${event.tenant_id}` : '',
    event.project_id ? `project:${event.project_id}` : '',
  ].filter((v): v is string => !!v)
  return Array.from(new Set(refs)).slice(0, 5)
}

export function ProvenanceTimelinePane() {
  const [selectorKey, setSelectorKey] = useState<SelectorKey>('run_id')
  const [selectorValue, setSelectorValue] = useState('')
  const [timeline, setTimeline] = useState<TimelinePayload | null>(null)
  const [report, setReport] = useState<ProvenanceReportPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadTimeline = async () => {
    const value = selectorValue.trim()
    if (!value) {
      setTimeline(null)
      setReport(null)
      setError('Choose a run, reference, or tenant.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ [selectorKey]: value })
      const reportParams = new URLSearchParams(params)
      reportParams.set('event_limit', '6')
      const [timelineResponse, reportResponse] = await Promise.all([
        fetch(`/api/provenance-timeline?${params.toString()}`),
        fetch(`/api/provenance-report?${reportParams.toString()}`),
      ])
      const timelineJson = await timelineResponse.json().catch(() => ({}))
      const reportJson = await reportResponse.json().catch(() => ({}))
      if (!timelineResponse.ok) {
        throw new Error(timelineJson?.error || `HTTP ${timelineResponse.status}`)
      }
      if (!reportResponse.ok) {
        throw new Error(reportJson?.error || `HTTP ${reportResponse.status}`)
      }
      setTimeline(timelineJson.timeline ?? timelineJson)
      setReport(reportJson.report ?? reportJson)
    } catch (e: any) {
      setTimeline(null)
      setReport(null)
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  const events = timeline?.events ?? []
  const counts = timeline?.counts ?? {}
  const sourceCount = Object.keys(counts).length

  return (
    <div>
      <h2 style={{
        fontSize: 11, textTransform: 'uppercase', letterSpacing: 1.5,
        color: '#6b7394', marginBottom: 12,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        Provenance Timeline
      </h2>

      <div style={{
        background: '#161822',
        border: '1px solid #1e2030',
        borderRadius: 8,
        padding: 12,
        marginBottom: 12,
      }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            value={selectorKey}
            onChange={e => setSelectorKey(e.target.value as SelectorKey)}
            style={{
              background: '#0f1117',
              border: '1px solid #2a2d3f',
              borderRadius: 6,
              color: '#c8cdd8',
              fontSize: 12,
              padding: '6px 8px',
            }}
            title="Timeline selector"
          >
            {Object.entries(SELECTOR_LABEL).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
          <input
            value={selectorValue}
            onChange={e => setSelectorValue(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') loadTimeline() }}
            placeholder={
              selectorKey === 'run_id' ? 'run_...' :
              selectorKey === 'ref' ? 'learning_event:...' :
              `${selectorKey.replace('_id', '')} id`
            }
            style={{
              flex: '1 1 220px',
              minWidth: 160,
              background: '#0f1117',
              border: '1px solid #2a2d3f',
              borderRadius: 6,
              color: '#e8eaf0',
              fontSize: 12,
              padding: '7px 9px',
              overflowWrap: 'anywhere',
            }}
            title="Run id, object reference, or tenant id"
          />
          <button
            onClick={loadTimeline}
            disabled={loading}
            style={{
              background: loading ? '#1e2030' : '#203152',
              border: '1px solid #2e4a7a',
              borderRadius: 6,
              color: loading ? '#6b7394' : '#dbeafe',
              cursor: loading ? 'default' : 'pointer',
              fontSize: 12,
              padding: '7px 12px',
            }}
            title="Load the read-only provenance timeline"
          >
            {loading ? 'Loading' : 'Load'}
          </button>
        </div>

        <div style={{ fontSize: 11, color: '#6b7394', marginTop: 8, lineHeight: 1.4 }}>
          Read-only kernel projection. Use an explicit selector to avoid an
          unbounded event dump.
        </div>
      </div>

      {error && (
        <div style={{
          color: '#fecaca',
          background: '#3a1d1d',
          border: '1px solid #7c2d12',
          borderRadius: 6,
          fontSize: 12,
          padding: '8px 10px',
          marginBottom: 12,
        }}>
          {error}
        </div>
      )}

      {timeline && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          marginBottom: 10,
          fontSize: 11,
          color: '#9aa0b8',
        }}>
          <span style={{ color: '#e8eaf0' }}>
            {events.length} event{events.length === 1 ? '' : 's'}
          </span>
          <span>from {sourceCount} source{sourceCount === 1 ? '' : 's'}</span>
          {report?.coverage?.status && (
            <span>coverage {report.coverage.status}</span>
          )}
          {timeline.read_only !== false && (
            <span style={{
              color: '#34d399',
              border: '1px solid #1f6f52',
              borderRadius: 6,
              padding: '2px 7px',
            }}>
              read-only
            </span>
          )}
        </div>
      )}

      {report?.follow_through && (
        <FollowThroughSummary followThrough={report.follow_through} />
      )}

      {(timeline?.caveats ?? []).map((caveat, idx) => (
        <div
          key={`${idx}-${caveat}`}
          style={{ fontSize: 11, color: '#fef3c7', marginBottom: 8, overflowWrap: 'anywhere' }}
        >
          {caveat}
        </div>
      ))}

      {timeline && events.length === 0 && (
        <div style={{ color: '#4a5070', fontSize: 12, textAlign: 'center', padding: 16 }}>
          No matching provenance records.
        </div>
      )}

      {events.length > 0 && (
        <div style={{ maxHeight: 380, overflowY: 'auto', paddingRight: 2 }}>
          {events.map((event, idx) => (
            <TimelineRow key={`${event.occurred_at_utc || idx}-${event.object_ref || idx}`} event={event} />
          ))}
        </div>
      )}
    </div>
  )
}

function fmtCount(value?: number): number {
  return Number.isFinite(value) ? Number(value) : 0
}

function statusColor(status?: string): string {
  if (status === 'closed_loop_observed') return '#34d399'
  if (status === 'decision_observed') return '#93c5fd'
  if (status === 'proposal_only') return '#fbbf24'
  if (status === 'evidence_only') return '#c4b5fd'
  return '#9aa0b8'
}

function labelStatus(status?: string): string {
  return (status || 'no_records').replaceAll('_', ' ')
}

function FollowThroughSummary({ followThrough }: { followThrough: FollowThroughPayload }) {
  const status = followThrough.status || 'no_records'
  const latestRefs = (followThrough.latest_refs ?? []).slice(0, 4)
  const cells = [
    ['decisions', fmtCount(followThrough.decision_events)],
    ['outcomes', fmtCount(followThrough.outcome_links)],
    ['reviews', fmtCount(followThrough.routine_reviews)],
    ['learning-use', fmtCount(followThrough.learning_use_receipts)],
  ]

  return (
    <div style={{
      background: '#111827',
      border: '1px solid #263247',
      borderRadius: 8,
      padding: 12,
      marginBottom: 12,
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 12,
        alignItems: 'center',
        flexWrap: 'wrap',
        marginBottom: 10,
      }}>
        <div style={{
          color: '#e8eaf0',
          fontSize: 12,
          fontWeight: 600,
        }}>
          Follow-through
        </div>
        <span style={{
          color: statusColor(status),
          border: `1px solid ${statusColor(status)}66`,
          borderRadius: 6,
          padding: '2px 7px',
          fontSize: 11,
          textTransform: 'capitalize',
        }}>
          {labelStatus(status)}
        </span>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(86px, 1fr))',
        gap: 8,
      }}>
        {cells.map(([label, value]) => (
          <div key={label} style={{
            background: '#0f1117',
            border: '1px solid #1e2030',
            borderRadius: 6,
            padding: '7px 8px',
            minWidth: 0,
          }}>
            <div style={{ color: '#6b7394', fontSize: 10, marginBottom: 3 }}>
              {label}
            </div>
            <div style={{ color: '#e8eaf0', fontSize: 13 }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {latestRefs.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
          {latestRefs.map(ref => (
            <span key={ref} style={{
              color: '#9aa0b8',
              border: '1px solid #2a2d3f',
              borderRadius: 6,
              padding: '2px 6px',
              fontSize: 10,
              maxWidth: '100%',
              overflowWrap: 'anywhere',
            }}>
              {ref}
            </span>
          ))}
        </div>
      )}

      {(followThrough.read_only !== false || followThrough.projection_only !== false) && (
        <div style={{ fontSize: 10, color: '#6b7394', marginTop: 9 }}>
          read-only projection over selected records
        </div>
      )}
    </div>
  )
}

function TimelineRow({ event }: { event: TimelineEvent }) {
  const refs = nonEmptyRefs(event)
  return (
    <div style={{
      padding: '10px 12px',
      marginBottom: 8,
      background: '#161822',
      border: '1px solid #1e2030',
      borderLeft: '3px solid #4f8ff7',
      borderRadius: 6,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{
            color: '#e8eaf0',
            fontSize: 12,
            lineHeight: 1.35,
            overflowWrap: 'anywhere',
          }}>
            {event.summary || event.event_kind || '(event)'}
          </div>
          <div style={{ color: '#6b7394', fontSize: 10, marginTop: 5, overflowWrap: 'anywhere' }}>
            {event.source || 'source unknown'}
            {event.event_kind ? ` · ${event.event_kind}` : ''}
            {event.actor ? ` · ${event.actor}` : ''}
          </div>
        </div>
        <div style={{ color: '#6b7394', fontSize: 10, whiteSpace: 'nowrap' }}>
          {fmtTime(event.occurred_at_utc)}
        </div>
      </div>

      {refs.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
          {refs.map(ref => (
            <span key={ref} style={{
              color: '#9aa0b8',
              border: '1px solid #2a2d3f',
              borderRadius: 6,
              padding: '2px 6px',
              fontSize: 10,
              maxWidth: '100%',
              overflowWrap: 'anywhere',
            }}>
              {ref}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
