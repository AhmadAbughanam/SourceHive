import { useEffect, useMemo, useState } from 'react'
import { bulkInviteAIInterviews, getInterviewSessions, getRoles } from '../api/client'
import './AIInterviews.css'

const STATUS_OPTIONS = ['All', 'invited', 'in_progress', 'completed', 'expired', 'canceled']

const fmtDateTime = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
}

const fmtScore = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '0%'
  return `${Math.round(num)}%`
}

export default function AIInterviews() {
  const [sessions, setSessions] = useState([])
  const [stats, setStats] = useState({ invited: 0, in_progress: 0, completed: 0, avg_score: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [statusFilter, setStatusFilter] = useState('All')
  const [roleFilter, setRoleFilter] = useState('All')
  const [query, setQuery] = useState('')

  const [roles, setRoles] = useState([])
  const [bulkRole, setBulkRole] = useState('')
  const [bulkTopN, setBulkTopN] = useState(10)
  const [bulkMinJd, setBulkMinJd] = useState(70)
  const [bulkExpires, setBulkExpires] = useState(72)
  const [bulkLoading, setBulkLoading] = useState(false)
  const [bulkResult, setBulkResult] = useState('')

  const load = () => {
    setLoading(true)
    setError('')
    getInterviewSessions()
      .then((res) => {
        setSessions(res.data.sessions || [])
        setStats(res.data.stats || { invited: 0, in_progress: 0, completed: 0, avg_score: 0 })
      })
      .catch(() => {
        setError('Unable to load interview sessions.')
        setSessions([])
        setStats({ invited: 0, in_progress: 0, completed: 0, avg_score: 0 })
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    getRoles()
      .then((res) => {
        const next = res.data.roles || []
        setRoles(next)
        if (!bulkRole && next.length) setBulkRole(next[0]?.role_name || '')
      })
      .catch(() => setRoles([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const roleChoices = useMemo(() => {
    const fromSessions = new Set()
    for (const row of sessions) {
      if (row?.interview_role) fromSessions.add(row.interview_role)
    }
    return ['All', ...Array.from(fromSessions).sort((a, b) => a.localeCompare(b))]
  }, [sessions])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (sessions || []).filter((row) => {
      if (statusFilter !== 'All' && row?.interview_status !== statusFilter) return false
      if (roleFilter !== 'All' && row?.interview_role !== roleFilter) return false
      if (!q) return true
      const blob = `${row?.candidate_name || ''} ${row?.email || ''} ${row?.invite_email || ''}`.toLowerCase()
      return blob.includes(q)
    })
  }, [sessions, statusFilter, roleFilter, query])

  const handleBulkInvite = async () => {
    if (!bulkRole) return
    try {
      setBulkLoading(true)
      setBulkResult('')
      const res = await bulkInviteAIInterviews({
        role_name: bulkRole,
        top_n: Number(bulkTopN || 10),
        min_jd: Number(bulkMinJd || 0),
        expires_in_hours: Number(bulkExpires || 72),
      })
      const created = res.data.created ?? 0
      const skipped = res.data.skipped ?? 0
      const errors = res.data.errors ?? 0
      setBulkResult(`Created ${created} invites • skipped ${skipped} • errors ${errors}`)
      load()
    } catch {
      setBulkResult('Unable to bulk invite candidates.')
    } finally {
      setBulkLoading(false)
    }
  }

  return (
    <div className="interviews-page">
      <header className="interviews-header">
        <div>
          <h2>AI Interviews</h2>
          <p>Track interview invites, status changes, and outcomes.</p>
        </div>
        <button type="button" className="secondary-btn" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      <section className="interviews-metrics">
        <div className="card metric-card">
          <p className="metric-label">Invited</p>
          <strong className="metric-value">{stats.invited || 0}</strong>
        </div>
        <div className="card metric-card">
          <p className="metric-label">In Progress</p>
          <strong className="metric-value">{stats.in_progress || 0}</strong>
        </div>
        <div className="card metric-card">
          <p className="metric-label">Completed</p>
          <strong className="metric-value">{stats.completed || 0}</strong>
        </div>
        <div className="card metric-card">
          <p className="metric-label">Avg Score</p>
          <strong className="metric-value">{fmtScore(stats.avg_score)}</strong>
        </div>
      </section>

      <section className="card interviews-filters">
        <div className="filters-grid">
          <label>
            Status
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </label>

          <label>
            Role
            <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
              {roleChoices.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </label>

          <label className="filters-search">
            Search name/email
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Type to search…" />
          </label>
        </div>
      </section>

      <section className="card interviews-table-card">
        <div className="table-top">
          <div>
            <h3>Interview Sessions</h3>
            <p className="muted">
              Showing <strong>{filtered.length}</strong> sessions
            </p>
          </div>
        </div>

        {error && <div className="table-error">{error}</div>}

        {loading ? (
          <p className="table-empty">Loading sessions…</p>
        ) : filtered.length === 0 ? (
          <p className="table-empty">No interview sessions yet. Use “Invite AI Interview” from a candidate profile.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Session</th>
                  <th>Candidate</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Portal</th>
                  <th>Invite sent</th>
                  <th>Expires</th>
                  <th>Started</th>
                  <th>Completed</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.session_id}>
                    <td className="mono">{(row.session_id || '').slice(0, 10)}</td>
                    <td>{row.candidate_name || '—'}</td>
                    <td>{row.email || row.invite_email || '—'}</td>
                    <td>{row.interview_role || '—'}</td>
                    <td>
                      <span className={`status-pill status-${row.interview_status || 'invited'}`}>
                        {row.interview_status || 'invited'}
                      </span>
                    </td>
                    <td>{fmtScore(row.interview_score)}</td>
                    <td>
                      <a className="portal-link" href={`/interview/${row.session_id}`} target="_blank" rel="noreferrer">
                        Open
                      </a>
                    </td>
                    <td>{fmtDateTime(row.invite_sent_at)}</td>
                    <td>{fmtDateTime(row.expires_at)}</td>
                    <td>{fmtDateTime(row.started_at)}</td>
                    <td>{fmtDateTime(row.completed_at)}</td>
                    <td>{fmtDateTime(row.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <details className="card bulk-invite" open={false}>
        <summary>Bulk Invite Best Fits</summary>
        <div className="bulk-body">
          <p className="muted">Invite the best JD matches for a role in one click.</p>
          <div className="bulk-grid">
            <label>
              Role
              <select value={bulkRole} onChange={(e) => setBulkRole(e.target.value)}>
                {roles.map((r) => (
                  <option key={r.id} value={r.role_name}>
                    {r.role_name}
                    {r.is_open === 0 ? ' (closed)' : ''}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Top N
              <input
                type="number"
                min="1"
                max="200"
                value={bulkTopN}
                onChange={(e) => setBulkTopN(e.target.value)}
              />
            </label>

            <label>
              Min JD Match %
              <input
                type="number"
                min="0"
                max="100"
                step="5"
                value={bulkMinJd}
                onChange={(e) => setBulkMinJd(e.target.value)}
              />
            </label>

            <label>
              Link expires in (hours)
              <input
                type="number"
                min="1"
                max="720"
                value={bulkExpires}
                onChange={(e) => setBulkExpires(e.target.value)}
              />
            </label>
          </div>

          <div className="bulk-actions">
            <button type="button" className="primary-btn" onClick={handleBulkInvite} disabled={bulkLoading || !bulkRole}>
              {bulkLoading ? 'Inviting…' : 'Invite Top Candidates (1 click)'}
            </button>
            {bulkResult && <span className="bulk-result">{bulkResult}</span>}
          </div>
        </div>
      </details>
    </div>
  )
}
