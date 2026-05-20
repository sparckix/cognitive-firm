import { useMemo, useState } from 'react'
import type { HumanWorkSession, Role } from '../types/org'

interface Props {
  sessions: HumanWorkSession[]
  roles: Role[]
  apiPost: (path: string, body: unknown) => Promise<Response>
}

const STATE_COLOR: Record<string, string> = {
  requested: '#f59e0b',
  claimed: '#4f8ff7',
  in_progress: '#4f8ff7',
  blocked: '#ef4444',
  handed_off: '#a78bfa',
  completed: '#34d399',
  integrated: '#34d399',
  abandoned: '#6b7394',
}

const NEXT_STATES: Record<string, string[]> = {
  requested: ['claimed', 'in_progress', 'abandoned'],
  claimed: ['in_progress', 'blocked', 'handed_off', 'abandoned'],
  in_progress: ['blocked', 'handed_off', 'completed', 'abandoned'],
  blocked: ['in_progress', 'handed_off', 'abandoned'],
  handed_off: ['claimed', 'in_progress', 'completed', 'abandoned'],
  completed: ['integrated', 'in_progress'],
  abandoned: [],
  integrated: [],
}

export function HumanWorkPane({ sessions, roles, apiPost }: Props) {
  const [objective, setObjective] = useState('')
  const [workMode, setWorkMode] = useState('source_check')
  const [bottleneckClass, setBottleneckClass] = useState('access')
  const [requestedBy, setRequestedBy] = useState(roles[0]?.role_id ? `role.${roles[0].role_id}` : 'principal')
  const [observability, setObservability] = useState('human_attested')
  const [receiptRequired, setReceiptRequired] = useState(false)
  const [agentRequested, setAgentRequested] = useState(true)
  const [humanDeliverable, setHumanDeliverable] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const active = useMemo(
    () => sessions.filter(s => !['integrated', 'abandoned'].includes(s.state)),
    [sessions],
  )
  const a2hWaiting = useMemo(
    () => active.filter(s =>
      (s.agent_followup_required || s.metadata?.coordination_pattern === 'a2h_work_request') &&
      ['requested', 'claimed', 'in_progress', 'blocked'].includes(s.state),
    ),
    [active],
  )
  const a2hFollowup = useMemo(
    () => active.filter(s =>
      (s.agent_followup_required || s.metadata?.coordination_pattern === 'a2h_work_request') &&
      ['handed_off', 'completed'].includes(s.state),
    ),
    [active],
  )
  const missingReceipts = useMemo(
    () => active.filter(s => s.receipt_required && !s.receipt),
    [active],
  )
  const completed = useMemo(
    () => sessions.filter(s => ['integrated', 'abandoned'].includes(s.state)),
    [sessions],
  )

  const createSession = async () => {
    if (!objective.trim() || busy) return
    if (agentRequested && (!requestedBy.startsWith('role.') || !humanDeliverable.trim())) {
      setError('A2H requests require a role requester and a human deliverable.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await apiPost('/api/human_work/create', {
        requested_by: requestedBy,
        human_actor: 'principal',
        objective: objective.trim(),
        work_mode: workMode,
        bottleneck_class: bottleneckClass,
        observability,
        receipt_required: agentRequested ? true : receiptRequired,
        receipt_type: (agentRequested || receiptRequired) ? 'note' : 'none',
        coordination_pattern: agentRequested ? 'a2h_work_request' : undefined,
        agent_counterparty_role: agentRequested ? requestedBy : undefined,
        human_deliverable: agentRequested ? humanDeliverable.trim() : undefined,
        agent_followup_required: agentRequested,
      })
      if (!res.ok) {
        const text = await res.text()
        setError(text || `create failed: ${res.status}`)
      } else {
        setObjective('')
        setHumanDeliverable('')
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  const updateState = async (session: HumanWorkSession, state: string) => {
    setError(null)
    let receipt: string | undefined
    if (state === 'integrated' && session.receipt_required && !session.receipt) {
      const value = window.prompt('Receipt required before integration')
      if (!value?.trim()) {
        setError('Receipt required before integration.')
        return
      }
      receipt = value.trim()
    }
    const res = await apiPost('/api/human_work/update-state', {
      session_id: session.session_id,
      state,
      receipt,
    })
    if (!res.ok) {
      const text = await res.text()
      setError(text || `update failed: ${res.status}`)
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <h2 style={{
        fontSize: 11, textTransform: 'uppercase', letterSpacing: 1.5,
        color: '#6b7394', marginBottom: 12,
      }}>
        Human Work
      </h2>

      <div style={{
        background: '#161822',
        border: '1px solid #1e2030',
        borderRadius: 8,
        padding: 10,
        marginBottom: 12,
      }}>
        <div style={{ fontSize: 11, color: '#c8cdd8', marginBottom: 8 }}>
          Create bounded human work
        </div>
        <label style={{ display: 'flex', gap: 7, alignItems: 'center', color: '#9aa3bd', fontSize: 11, marginBottom: 8 }}>
          <input
            type="checkbox"
            checked={agentRequested}
            onChange={e => {
              setAgentRequested(e.target.checked)
              if (e.target.checked) setReceiptRequired(true)
            }}
          />
          Agent-requested human work
        </label>
        <textarea
          value={objective}
          onChange={e => setObjective(e.target.value)}
          rows={3}
          placeholder="Objective, e.g. verify the source and attach citation"
          style={{
            width: '100%',
            boxSizing: 'border-box',
            background: '#0f1117',
            color: '#e8eaf0',
            border: '1px solid #1e2030',
            borderRadius: 6,
            padding: 8,
            resize: 'vertical',
            fontFamily: 'inherit',
            fontSize: 12,
          }}
        />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
          <select value={workMode} onChange={e => setWorkMode(e.target.value)} style={selectStyle}>
            <option value="source_check">source check</option>
            <option value="edit">edit</option>
            <option value="external_action">external action</option>
            <option value="judgment">judgment</option>
            <option value="relationship">relationship</option>
            <option value="data_entry">data entry</option>
            <option value="taste_call">taste call</option>
            <option value="other">other</option>
          </select>
          <select value={bottleneckClass} onChange={e => setBottleneckClass(e.target.value)} style={selectStyle}>
            <option value="access">access</option>
            <option value="authority">authority</option>
            <option value="taste">taste</option>
            <option value="relationship">relationship</option>
            <option value="cognition">cognition</option>
            <option value="labor">labor</option>
            <option value="safety">safety</option>
            <option value="other">other</option>
          </select>
        </div>
        <select value={requestedBy} onChange={e => setRequestedBy(e.target.value)} style={{ ...selectStyle, marginTop: 8 }}>
          <option value="principal">principal</option>
          {roles.map(role => (
            <option key={role.role_id} value={`role.${role.role_id}`}>role.{role.role_id}</option>
          ))}
        </select>
        {agentRequested && (
          <input
            value={humanDeliverable}
            onChange={e => setHumanDeliverable(e.target.value)}
            placeholder="Human deliverable, e.g. source support claim"
            style={{
              ...selectStyle,
              marginTop: 8,
              boxSizing: 'border-box',
            }}
          />
        )}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'center', marginTop: 8 }}>
          <select value={observability} onChange={e => setObservability(e.target.value)} style={selectStyle}>
            <option value="human_attested">human attested</option>
            <option value="digital_artifact">digital artifact</option>
            <option value="external_system">external system</option>
            <option value="unobservable">unobservable</option>
          </select>
          <label style={{ color: '#9aa3bd', fontSize: 11, whiteSpace: 'nowrap' }}>
            <input
              type="checkbox"
              checked={agentRequested || receiptRequired}
              disabled={agentRequested}
              onChange={e => setReceiptRequired(e.target.checked)}
              style={{ marginRight: 5 }}
            />
            receipt
          </label>
        </div>
        <button
          onClick={createSession}
          disabled={!objective.trim() || (agentRequested && !humanDeliverable.trim()) || busy}
          style={{
            marginTop: 8,
            width: '100%',
            background: objective.trim() && (!agentRequested || humanDeliverable.trim()) && !busy ? '#2563eb' : '#1e293b',
            color: '#fff',
            border: 0,
            borderRadius: 6,
            padding: '7px 10px',
            fontSize: 12,
            cursor: objective.trim() && (!agentRequested || humanDeliverable.trim()) && !busy ? 'pointer' : 'not-allowed',
          }}
        >
          {busy ? 'creating...' : 'Create session'}
        </button>
        {error && <div style={{ marginTop: 8, color: '#fca5a5', fontSize: 11 }}>{error}</div>}
      </div>

      <SessionList title="A2H Waiting On Human" sessions={a2hWaiting} onUpdate={updateState} />
      <SessionList title="A2H Follow-Up" sessions={a2hFollowup} onUpdate={updateState} />
      <SessionList title="Missing Receipts" sessions={missingReceipts} onUpdate={updateState} />
      <SessionList title="Active" sessions={active} onUpdate={updateState} />
      <SessionList title="Closed" sessions={completed.slice(0, 8)} onUpdate={updateState} />
    </div>
  )
}

function SessionList({ title, sessions, onUpdate }: {
  title: string
  sessions: HumanWorkSession[]
  onUpdate: (session: HumanWorkSession, state: string) => void
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 10, color: '#6b7394', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>
        {title} ({sessions.length})
      </div>
      {sessions.length === 0 && (
        <div style={{ fontSize: 11, color: '#4a5070', padding: '8px 0' }}>None.</div>
      )}
      {sessions.map(session => (
        <div key={session.session_id} style={{
          background: '#161822',
          border: '1px solid #1e2030',
          borderLeft: `3px solid ${STATE_COLOR[session.state] || '#6b7394'}`,
          borderRadius: 8,
          padding: '9px 10px',
          marginBottom: 7,
          fontSize: 11,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
            <span style={{ color: STATE_COLOR[session.state] || '#e8eaf0', fontWeight: 600 }}>
              {session.state}
            </span>
            <span style={{ color: '#6b7394', fontFamily: 'monospace', fontSize: 9 }}>
              {session.session_id}
            </span>
          </div>
          <div style={{ color: '#e8eaf0', lineHeight: 1.35, marginBottom: 5 }}>
            {session.objective}
          </div>
          <div style={{ color: '#6b7394', marginBottom: 7 }}>
            {session.work_mode} · {session.bottleneck_class} · requested by {session.requested_by}
          </div>
          {(session.agent_followup_required || session.human_deliverable) && (
            <div style={{
              color: '#facc15',
              background: '#26210f',
              border: '1px solid #3f3514',
              borderRadius: 5,
              padding: '4px 6px',
              marginBottom: 7,
              lineHeight: 1.35,
            }}>
              {['handed_off', 'completed'].includes(session.state) ? 'A2H follow-up' : 'A2H waiting on human'}
              {session.agent_counterparty_role ? ` · ${session.agent_counterparty_role}` : ''}
              {session.human_deliverable ? ` · ${session.human_deliverable}` : ''}
            </div>
          )}
          <div style={{ color: '#6b7394', marginBottom: 7 }}>
            {session.observability || 'human_attested'}
            {session.receipt_required ? ' · receipt required' : ''}
            {session.receipt ? ` · receipt: ${session.receipt.slice(0, 60)}` : ''}
          </div>
          {(NEXT_STATES[session.state] || []).length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {NEXT_STATES[session.state].map(next => (
                <button
                  key={next}
                  onClick={() => onUpdate(session, next)}
                  style={{
                    background: 'transparent',
                    border: '1px solid #334155',
                    color: '#c8cdd8',
                    borderRadius: 5,
                    padding: '3px 6px',
                    fontSize: 10,
                    cursor: 'pointer',
                  }}
                >
                  {next}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

const selectStyle: React.CSSProperties = {
  width: '100%',
  background: '#0f1117',
  color: '#e8eaf0',
  border: '1px solid #1e2030',
  borderRadius: 6,
  padding: '6px 7px',
  fontSize: 11,
}
