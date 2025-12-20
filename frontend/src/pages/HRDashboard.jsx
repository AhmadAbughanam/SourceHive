import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getApplications, getDashboardOverview, getRoles } from '../api/client'
import './HRDashboard.css'

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'new', label: 'Applied' },
  { value: 'shortlisted', label: 'Shortlisted' },
  { value: 'interviewed', label: 'Interviewed' },
  { value: 'hired', label: 'Hired' },
  { value: 'rejected', label: 'Rejected' },
]

const SORT_OPTIONS = [
  { value: 'created_at', label: 'Newest' },
  { value: 'updated_at', label: 'Last updated' },
  { value: 'resume_score', label: 'Resume score' },
  { value: 'jd_match_score', label: 'JD match' },
]

const formatPercent = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '0%'
  return `${Math.round(num)}%`
}

export default function HRDashboard() {
  const [filters, setFilters] = useState({
    status: '',
    role: '',
    start_date: '',
    end_date: '',
    keyword: '',
    sort_by: 'created_at',
    sort_dir: 'desc',
    page: 1,
    page_size: 10,
  })
  const [applications, setApplications] = useState([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState({})
  const [roles, setRoles] = useState([])
  const [overview, setOverview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    getRoles()
      .then((res) => setRoles(res.data.roles || []))
      .catch(() => setRoles([]))
  }, [])

  useEffect(() => {
    getDashboardOverview()
      .then((res) => setOverview(res.data.overview))
      .catch(() => setOverview(null))
  }, [])

  useEffect(() => {
    setLoading(true)
    setError('')
    getApplications(filters)
      .then((res) => {
        setApplications(res.data.applications || [])
        setTotal(res.data.total || 0)
        setStats(res.data.stats || {})
      })
      .catch(() => {
        setError('Unable to load applications.')
        setApplications([])
        setTotal(0)
        setStats({})
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters)])

  const cards = useMemo(() => {
    const totalApplications = Object.values(stats).reduce((sum, value) => sum + (value || 0), 0)
    return [
      {
        label: 'Total Applications',
        value: totalApplications,
        helper: 'Across all statuses',
      },
      {
        label: 'Shortlisted',
        value: stats.shortlisted || 0,
        helper: 'Ready for interview',
      },
      {
        label: 'Hired',
        value: stats.hired || 0,
        helper: 'Offers accepted',
      },
      {
        label: 'Avg Resume Score',
        value:
          typeof overview?.avg_resume_score === 'number'
            ? overview.avg_resume_score.toFixed(1) + '%'
            : '0.0%',
        helper: 'Based on parsed CV scores',
      },
    ]
  }, [stats, overview])

  const totalPages = Math.max(1, Math.ceil(total / filters.page_size))

  const handleFilterChange = (field, value) => {
    setFilters((prev) => ({
      ...prev,
      [field]: value,
      page: field === 'page' ? value : 1,
    }))
  }

  const renderScoreCell = (app) => {
    const jdMatch = app.jd_match || {}
    const jdScore = jdMatch.score ?? app.jd_match_score ?? 0
    const resumeScore = app.resume_score ?? 0
    const matchedCount = jdMatch.matched_count ?? 0
    const missingCount = jdMatch.missing_count ?? 0
    const jdReason = jdMatch.reason || ''
    const jdKeywordCount = jdMatch.jd_keyword_count ?? null

    return (
      <div className="score-cell">
        <div className="score-row">
          <span className="score-label">Resume</span>
          <strong>{formatPercent(resumeScore)}</strong>
        </div>
        <div className="score-row">
          <span className="score-label">JD</span>
          <strong>{formatPercent(jdScore)}</strong>
        </div>
        {(matchedCount > 0 || missingCount > 0) && (
          <div className="score-sub">
            Matched <strong>{matchedCount}</strong> / Missing <strong>{missingCount}</strong>
          </div>
        )}
        {(jdReason || jdKeywordCount !== null) && (
          <div className="score-sub">
            {jdKeywordCount !== null ? (
              <>
                Keywords <strong>{jdKeywordCount}</strong>
                {jdReason ? <> · {jdReason}</> : null}
              </>
            ) : (
              jdReason
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <div>
          <h2>HR Dashboard</h2>
          <p>Monitor your talent pipeline and manage applications with powerful filters</p>
        </div>
      </div>

      <section className="metric-panel">
        {cards.map((card) => (
          <article key={card.label} className="metric-card">
            <p className="metric-label">{card.label}</p>
            <h3>{card.value}</h3>
            <p className="metric-helper">{card.helper}</p>
          </article>
        ))}
      </section>

      <section className="filter-panel">
        <div className="filter-panel-header">
          <div>
            <h3>Filter Applications</h3>
            <p>Refine your view by status, role, date range, and keywords</p>
          </div>
        </div>
        <div className="filter-grid">
          <label>
            Status
            <select value={filters.status} onChange={(e) => handleFilterChange('status', e.target.value)}>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Role
            <select value={filters.role} onChange={(e) => handleFilterChange('role', e.target.value)}>
              <option value="">All roles</option>
              {roles.map((role) => (
                <option key={role.id} value={role.role_name}>
                  {role.role_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Start date
            <input
              type="date"
              value={filters.start_date}
              onChange={(e) => handleFilterChange('start_date', e.target.value)}
            />
          </label>
          <label>
            End date
            <input
              type="date"
              value={filters.end_date}
              onChange={(e) => handleFilterChange('end_date', e.target.value)}
            />
          </label>
          <label className="full-width">
            Keyword search
            <input
              type="text"
              placeholder="Search by name, email, or role..."
              value={filters.keyword}
              onChange={(e) => handleFilterChange('keyword', e.target.value)}
            />
          </label>
          <label>
            Sort by
            <select value={filters.sort_by} onChange={(e) => handleFilterChange('sort_by', e.target.value)}>
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Direction
            <select value={filters.sort_dir} onChange={(e) => handleFilterChange('sort_dir', e.target.value)}>
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>
        </div>
      </section>

      <section className="applications-table">
        <div className="table-header">
          <div>
            <h3>Applications</h3>
            <p>
              Showing <strong>{applications.length}</strong> of <strong>{total}</strong> results
            </p>
          </div>
          <div className="status-badges">
            {Object.keys(stats).map((key) => (
              <span key={key} className={`status-pill status-${key}`}>
                {key} · {stats[key]}
              </span>
            ))}
          </div>
        </div>
        
        {error && <div className="table-error">{error}</div>}
        
        {loading ? (
          <p className="table-empty">Loading applications...</p>
        ) : applications.length === 0 ? (
          <p className="table-empty">No applications found for the selected filters.</p>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Scores</th>
                    <th>Applied</th>
                    <th>Updated</th>
                    <th>Notes</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {applications.map((app) => (
                    <tr key={app.id}>
                      <td>
                        <div className="candidate-cell">
                          <strong>{app.name || 'Unknown'}</strong>
                        </div>
                      </td>
                      <td>
                        <span style={{ color: 'var(--text-secondary)' }}>{app.email || 'N/A'}</span>
                      </td>
                      <td>
                        <span style={{ color: 'var(--text-secondary)' }}>{app.selected_role || '—'}</span>
                      </td>
                      <td>
                        <span className={`status-pill status-${app.status}`}>{app.status}</span>
                      </td>
                      <td>{renderScoreCell(app)}</td>
                      <td>
                        <div className="date-cell">
                          <span>Applied</span>
                          <strong>{new Date(app.created_at).toLocaleDateString()}</strong>
                        </div>
                      </td>
                      <td>
                        <div className="date-cell">
                          <span>Updated</span>
                          <strong>{new Date(app.updated_at).toLocaleDateString()}</strong>
                        </div>
                      </td>
                      <td>
                        <div className="notes-badge">{app.notes_count || 0}</div>
                      </td>
                      <td>
                        <div className="action-stack">
                          <Link to={`/hr/candidates/${app.id}`} className="primary-btn small">
                            View Profile
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="table-pagination">
              <button
                onClick={() => handleFilterChange('page', Math.max(1, filters.page - 1))}
                disabled={filters.page <= 1}
              >
                Previous
              </button>
              <span>
                Page {filters.page} of {totalPages}
              </span>
              <button
                onClick={() => handleFilterChange('page', Math.min(totalPages, filters.page + 1))}
                disabled={filters.page >= totalPages}
              >
                Next
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  )
}