import { useEffect, useMemo, useState } from 'react'
import { getAnalytics } from '../api/client'
import './Analytics.css'

export default function AnalyticsPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getAnalytics()
      .then((res) => {
        setData(res.data.analytics)
      })
      .catch(() => {
        setData(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const metrics = useMemo(() => {
    if (!data) {
      return {
        total: 0,
        hired: 0,
        shortlisted: 0,
        last7: 0,
        topRole: 'N/A',
        trend: [],
      }
    }

    const statusMap = data.status_breakdown.reduce((acc, cur) => {
      acc[cur.status] = cur.count
      return acc
    }, {})

    const totalApps = data.status_breakdown.reduce((acc, cur) => acc + cur.count, 0)
    const hires = statusMap.hired || 0
    const shortlisted = statusMap.shortlisted || 0

    const sevenDaysAgo = new Date()
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7)
    const last7 = data.applications_over_time
      .filter((point) => new Date(point.date) >= sevenDaysAgo)
      .reduce((sum, point) => sum + point.count, 0)

    const topRole = data.top_roles[0]?.role || 'N/A'

    return {
      total: totalApps,
      hired: hires,
      shortlisted,
      last7,
      topRole,
      trend: data.applications_over_time,
    }
  }, [data])

  if (loading) {
    return <div className="analytics-page">Loading analytics…</div>
  }

  if (!data) {
    return <div className="analytics-page">Unable to load analytics.</div>
  }

  const maxStatus = Math.max(...data.status_breakdown.map((item) => item.count), 1)
  const maxRole = Math.max(...data.top_roles.map((item) => item.count), 1)
  const maxOverTime = Math.max(...metrics.trend.map((item) => item.count), 1)

  return (
    <div className="analytics-page">
      <header className="analytics-header">
        <div>
          <h2>Analytics</h2>
          <p>System-wide view of application flow.</p>
        </div>
      </header>

      <section className="metrics-grid">
        <article className="metric-card">
          <p>Total applications</p>
          <h3>{metrics.total}</h3>
          <small>Across every status</small>
        </article>
        <article className="metric-card">
          <p>Shortlisted</p>
          <h3>{metrics.shortlisted}</h3>
          <small>Ready for interviews</small>
        </article>
        <article className="metric-card">
          <p>Hired</p>
          <h3>{metrics.hired}</h3>
          <small>Offers accepted</small>
        </article>
        <article className="metric-card">
          <p>Last 7 days</p>
          <h3>{metrics.last7}</h3>
          <small>New applications</small>
        </article>
      </section>

      <section className="analytics-grid">
        <article className="card chart-card">
          <div className="chart-header">
            <div>
              <h3>Applications by status</h3>
              <p>Stage concentrations for every candidate.</p>
            </div>
          </div>
          <div className="chart-vertical">
            {data.status_breakdown.map((item) => (
              <div key={item.status} className="chart-row">
                <span className="label">{item.status}</span>
                <div className="bar">
                  <div style={{ width: `${(item.count / maxStatus) * 100}%` }} />
                </div>
                <span className="value">{item.count}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="card chart-card">
          <div className="chart-header">
            <div>
              <h3>Top roles</h3>
              <p>Role demand by application volume.</p>
            </div>
            <div className="pill-highlight">Top: {metrics.topRole}</div>
          </div>
          <div className="chart-vertical">
            {data.top_roles.map((item) => (
              <div key={item.role || 'unknown'} className="chart-row">
                <span className="label">{item.role || 'N/A'}</span>
                <div className="bar">
                  <div style={{ width: `${(item.count / maxRole) * 100}%` }} />
                </div>
                <span className="value">{item.count}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="card chart-card span-2">
          <div className="chart-header">
            <div>
              <h3>Applications over time (30 days)</h3>
              <p>Track daily throughput and spikes.</p>
            </div>
          </div>
          <div className="line-chart">
            {metrics.trend.map((point) => (
              <div key={point.date} className="line-point">
                <div
                  className="line-value"
                  style={{ height: `${(point.count / maxOverTime) * 140}px` }}
                />
                <span>{new Date(point.date).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="card chart-card">
          <div className="chart-header">
            <div>
              <h3>JD match distribution</h3>
              <p>How candidates align to JD scoring buckets.</p>
            </div>
          </div>
          <div className="chart-pills">
            {data.match_distribution.map((bucket) => (
              <div key={bucket.bucket} className="pill">
                <strong>{bucket.bucket}</strong>
                <span>{bucket.count} candidates</span>
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  )
}
