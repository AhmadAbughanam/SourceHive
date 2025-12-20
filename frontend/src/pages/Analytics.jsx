import { useEffect, useMemo, useState } from 'react'
import { Bar, Doughnut, Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { getAnalytics, getRoles } from '../api/client'
import './Analytics.css'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler
)

const STATUS_COLORS = {
  hired: '#10b981',
  shortlisted: '#6366f1',
  applied: '#3b82f6',
  new: '#0ea5e9',
  rejected: '#ef4444',
}

const CHART_PALETTE = [
  '#fbbf24',
  '#f59e0b',
  '#10b981',
  '#3b82f6',
  '#6366f1',
  '#ef4444',
  '#14b8a6',
  '#a855f7',
]

const CHART_OPTIONS = {
  common: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#a3a3a3',
          padding: 16,
          font: { size: 12, weight: '500' },
        },
      },
      tooltip: {
        backgroundColor: '#1a1a1a',
        titleColor: '#ffffff',
        bodyColor: '#a3a3a3',
        borderColor: '#2a2a2a',
        borderWidth: 1,
        padding: 12,
        displayColors: true,
        cornerRadius: 8,
      },
    },
  },
  scales: {
    dark: {
      x: {
        grid: { color: '#2a2a2a', drawBorder: false },
        ticks: { color: '#737373', font: { size: 11 } },
      },
      y: {
        grid: { color: '#2a2a2a', drawBorder: false },
        ticks: { color: '#737373', font: { size: 11 } },
        beginAtZero: true,
      },
    },
  },
}

function formatISODate(dateObj) {
  const year = dateObj.getFullYear()
  const month = String(dateObj.getMonth() + 1).padStart(2, '0')
  const day = String(dateObj.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function movingAverage(values, windowSize) {
  if (!Array.isArray(values) || values.length === 0) return []
  const result = []
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - windowSize + 1)
    const slice = values.slice(start, i + 1)
    const avg = slice.reduce((sum, v) => sum + v, 0) / slice.length
    result.push(Number(avg.toFixed(2)))
  }
  return result
}

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState(null)
  const [roles, setRoles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [rangePreset, setRangePreset] = useState('90')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [roleFilter, setRoleFilter] = useState('')

  const effectiveRange = useMemo(() => {
    const end = new Date()
    const preset = String(rangePreset)
    if (preset === 'custom') {
      return { start: startDate, end: endDate }
    }
    const days = Number(preset || 90)
    const start = new Date(end)
    start.setDate(end.getDate() - (Number.isFinite(days) ? days - 1 : 89))
    return { start: formatISODate(start), end: formatISODate(end) }
  }, [rangePreset, startDate, endDate])

  useEffect(() => {
    getRoles()
      .then((res) => setRoles(res.data.roles || []))
      .catch(() => setRoles([]))
  }, [])

  const fetchAnalytics = async () => {
    try {
      setLoading(true)
      setError('')
      const res = await getAnalytics({
        start_date: effectiveRange.start,
        end_date: effectiveRange.end,
        role: roleFilter || '',
      })
      setAnalytics(res.data.analytics)
    } catch {
      setAnalytics(null)
      setError('Unable to load analytics.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAnalytics()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rangePreset, roleFilter])

  useEffect(() => {
    if (rangePreset !== 'custom') return
    if (startDate && endDate) {
      fetchAnalytics()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startDate, endDate, rangePreset])

  const derived = useMemo(() => {
    const empty = {
      total: 0,
      hired: 0,
      shortlisted: 0,
      last7: 0,
      hireRate: 0,
      avgJD: 0,
      avgResume: 0,
      topRole: 'N/A',
      statusBreakdown: [],
      overTime: [],
      topRoles: [],
      jdDist: [],
      expDist: [],
      docKinds: [],
    }
    if (!analytics) return empty

    const statusBreakdown = analytics.status_breakdown || []
    const statusMap = statusBreakdown.reduce((acc, cur) => {
      acc[String(cur.status || 'unknown').toLowerCase()] = Number(cur.count || 0)
      return acc
    }, {})

    const overTime = analytics.applications_over_time || []
    const last7 = overTime.slice(-7).reduce((sum, row) => sum + Number(row.count || 0), 0)

    const total = Number(analytics.totals?.total_applications || 0)
    const hired = statusMap.hired || 0
    const shortlisted = statusMap.shortlisted || 0
    const hireRate = total ? Math.round((hired / total) * 1000) / 10 : 0

    const topRoles = analytics.top_roles || []
    const topRole = topRoles[0]?.role || 'N/A'

    return {
      total,
      hired,
      shortlisted,
      last7,
      hireRate,
      avgJD: Number(analytics.totals?.avg_jd_match_score || 0),
      avgResume: Number(analytics.totals?.avg_resume_score || 0),
      topRole,
      statusBreakdown,
      overTime,
      topRoles,
      jdDist: analytics.jd_match_distribution || [],
      expDist: analytics.experience_distribution || [],
      docKinds: analytics.doc_kind_breakdown || [],
    }
  }, [analytics])

  if (loading) {
    return (
      <div className="analytics-page">
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#737373' }}>
          Loading analytics...
        </div>
      </div>
    )
  }

  if (error || !analytics) {
    return (
      <div className="analytics-page">
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#ef4444' }}>
          {error || 'Unable to load analytics.'}
        </div>
      </div>
    )
  }

  const statusLabels = derived.statusBreakdown.map((row) => String(row.status || 'unknown'))
  const statusCounts = derived.statusBreakdown.map((row) => Number(row.count || 0))
  const statusColors = statusLabels.map(
    (label, i) =>
      STATUS_COLORS[String(label).toLowerCase()] || CHART_PALETTE[i % CHART_PALETTE.length]
  )

  const timeLabels = derived.overTime.map((row) => row.date)
  const timeCounts = derived.overTime.map((row) => Number(row.count || 0))
  const timeAvg7 = movingAverage(timeCounts, 7)

  const topRoles = (derived.topRoles || []).slice(0, 10)
  const topRoleLabels = topRoles.map((row) => row.role || 'N/A')
  const topRoleCounts = topRoles.map((row) => Number(row.count || 0))

  const jdOrder = ['0-9', '10-19', '20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80-89', '90-100']
  const jdMap = (derived.jdDist || []).reduce((acc, row) => {
    acc[row.bucket] = Number(row.count || 0)
    return acc
  }, {})
  const jdCounts = jdOrder.map((bucket) => jdMap[bucket] || 0)

  const expLabels = (derived.expDist || []).map((row) => row.bucket)
  const expCounts = (derived.expDist || []).map((row) => Number(row.count || 0))

  const docKinds = (derived.docKinds || []).filter((row) => row && (row.doc_kind || row.doc_kind === null))
  const docLabels = docKinds.map((row) => row.doc_kind || 'unknown')
  const docCounts = docKinds.map((row) => Number(row.count || 0))

  return (
    <div className="analytics-page">
      <header className="analytics-header">
        <div>
          <h2>Analytics Dashboard</h2>
          <p>Track hiring metrics and gain insights across your pipeline</p>
        </div>
        <div className="analytics-filters">
          <div className="filter-row">
            <label>
              Date range
              <select value={rangePreset} onChange={(e) => setRangePreset(e.target.value)}>
                <option value="30">Last 30 days</option>
                <option value="90">Last 90 days</option>
                <option value="365">Last 12 months</option>
                <option value="custom">Custom</option>
              </select>
            </label>

            <label>
              Role
              <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
                <option value="">All roles</option>
                {roles.map((role) => (
                  <option key={role.id} value={role.role_name}>
                    {role.role_name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {rangePreset === 'custom' ? (
            <div className="filter-row">
              <label>
                Start
                <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </label>
              <label>
                End
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </label>
              <button type="button" className="primary-btn" onClick={fetchAnalytics} disabled={!startDate || !endDate}>
                Apply
              </button>
            </div>
          ) : (
            <div className="filter-hint">
              Showing <strong>{effectiveRange.start}</strong> → <strong>{effectiveRange.end}</strong>
              {roleFilter && (
                <>
                  {' '}
                  for <strong>{roleFilter}</strong>
                </>
              )}
            </div>
          )}
        </div>
      </header>

      <section className="metrics-grid">
        <article className="metric-card">
          <p>Total Applications</p>
          <h3>{derived.total}</h3>
          <small>Within selected scope</small>
        </article>
        <article className="metric-card">
          <p>Shortlisted</p>
          <h3>{derived.shortlisted}</h3>
          <small>Strong candidates</small>
        </article>
        <article className="metric-card">
          <p>Hired</p>
          <h3>{derived.hired}</h3>
          <small>Hiring rate: {derived.hireRate}%</small>
        </article>
        <article className="metric-card">
          <p>Last 7 Days</p>
          <h3>{derived.last7}</h3>
          <small>New applications</small>
        </article>
        <article className="metric-card">
          <p>Avg JD Match</p>
          <h3>{Math.round(derived.avgJD)}%</h3>
          <small>Job description fit</small>
        </article>
        <article className="metric-card">
          <p>Avg Resume Score</p>
          <h3>{Math.round(derived.avgResume)}%</h3>
          <small>Overall quality</small>
        </article>
      </section>

      <section className="analytics-grid">
        <article className="chart-card">
          <div className="chart-header">
            <div>
              <h3>Status Distribution</h3>
              <p>Pipeline breakdown by candidate status</p>
            </div>
          </div>
          <div className="chart-canvas">
            <Doughnut
              data={{
                labels: statusLabels,
                datasets: [
                  {
                    data: statusCounts,
                    backgroundColor: statusColors,
                    borderWidth: 3,
                    borderColor: '#1a1a1a',
                  },
                ],
              }}
              options={{
                ...CHART_OPTIONS.common,
                cutout: '65%',
              }}
            />
          </div>
        </article>

        <article className="chart-card">
          <div className="chart-header">
            <div>
              <h3>Top Roles</h3>
              <p>Most active positions</p>
            </div>
            <div className="pill-highlight">{derived.topRole}</div>
          </div>
          <div className="chart-canvas">
            <Bar
              data={{
                labels: topRoleLabels,
                datasets: [
                  {
                    label: 'Applications',
                    data: topRoleCounts,
                    backgroundColor: '#fbbf24',
                    borderRadius: 8,
                    borderSkipped: false,
                  },
                ],
              }}
              options={{
                ...CHART_OPTIONS.common,
                indexAxis: 'y',
                scales: CHART_OPTIONS.scales.dark,
                plugins: {
                  ...CHART_OPTIONS.common.plugins,
                  legend: { display: false },
                },
              }}
            />
          </div>
        </article>

        <article className="chart-card span-2">
          <div className="chart-header">
            <div>
              <h3>Applications Over Time</h3>
              <p>Daily volume with 7-day moving average</p>
            </div>
          </div>
          <div className="chart-canvas tall">
            <Line
              data={{
                labels: timeLabels,
                datasets: [
                  {
                    label: 'Daily',
                    data: timeCounts,
                    borderColor: '#fbbf24',
                    backgroundColor: 'rgba(251, 191, 36, 0.15)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 6,
                    pointHoverBackgroundColor: '#fbbf24',
                    borderWidth: 2,
                  },
                  {
                    label: '7-day avg',
                    data: timeAvg7,
                    borderColor: '#a3a3a3',
                    borderDash: [8, 4],
                    tension: 0.4,
                    pointRadius: 0,
                    borderWidth: 2,
                  },
                ],
              }}
              options={{
                ...CHART_OPTIONS.common,
                scales: {
                  x: {
                    display: false,
                  },
                  y: {
                    ...CHART_OPTIONS.scales.dark.y,
                  },
                },
                plugins: {
                  ...CHART_OPTIONS.common.plugins,
                  tooltip: {
                    ...CHART_OPTIONS.common.plugins.tooltip,
                    callbacks: {
                      title: (items) => {
                        const label = items?.[0]?.label
                        if (!label) return ''
                        return new Date(label).toLocaleDateString()
                      },
                    },
                  },
                },
              }}
            />
          </div>
        </article>

        <article className="chart-card">
          <div className="chart-header">
            <div>
              <h3>JD Match Distribution</h3>
              <p>Keyword alignment scores</p>
            </div>
          </div>
          <div className="chart-canvas">
            <Bar
              data={{
                labels: jdOrder,
                datasets: [
                  {
                    label: 'Candidates',
                    data: jdCounts,
                    backgroundColor: '#10b981',
                    borderRadius: 8,
                    borderSkipped: false,
                  },
                ],
              }}
              options={{
                ...CHART_OPTIONS.common,
                scales: CHART_OPTIONS.scales.dark,
                plugins: {
                  ...CHART_OPTIONS.common.plugins,
                  legend: { display: false },
                },
              }}
            />
          </div>
        </article>

        <article className="chart-card">
          <div className="chart-header">
            <div>
              <h3>Experience Distribution</h3>
              <p>Years of experience breakdown</p>
            </div>
          </div>
          <div className="chart-canvas">
            <Bar
              data={{
                labels: expLabels,
                datasets: [
                  {
                    label: 'Candidates',
                    data: expCounts,
                    backgroundColor: '#f59e0b',
                    borderRadius: 8,
                    borderSkipped: false,
                  },
                ],
              }}
              options={{
                ...CHART_OPTIONS.common,
                scales: CHART_OPTIONS.scales.dark,
                plugins: {
                  ...CHART_OPTIONS.common.plugins,
                  legend: { display: false },
                },
              }}
            />
          </div>
        </article>

        <article className="chart-card">
          <div className="chart-header">
            <div>
              <h3>Resume File Types</h3>
              <p>Document format breakdown</p>
            </div>
          </div>
          <div className="chart-canvas">
            {docLabels.length ? (
              <Doughnut
                data={{
                  labels: docLabels,
                  datasets: [
                    {
                      data: docCounts,
                      backgroundColor: CHART_PALETTE.slice(0, docLabels.length),
                      borderWidth: 3,
                      borderColor: '#1a1a1a',
                    },
                  ],
                }}
                options={{
                  ...CHART_OPTIONS.common,
                  cutout: '60%',
                }}
              />
            ) : (
              <div className="chart-empty">No document data available</div>
            )}
          </div>
        </article>
      </section>
    </div>
  )
}