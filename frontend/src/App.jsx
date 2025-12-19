import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, Link, NavLink, useLocation } from 'react-router-dom'
import UploadResume from './components/UploadResume'
import HRDashboard from './pages/HRDashboard'
import CandidateProfile from './pages/CandidateProfile'
import RolesManagement from './pages/RolesManagement'
import AnalyticsPage from './pages/Analytics'
import { healthCheck } from './api/client'
import './App.css'

const NAV_LINKS = [
  { path: '/hr/dashboard', label: 'Dashboard' },
  { path: '/resume/upload', label: 'Upload' },
  { path: '/hr/roles', label: 'Roles' },
  { path: '/hr/analytics', label: 'Analytics' },
]

function AppShell() {
  const [apiStatus, setApiStatus] = useState('checking')
  const location = useLocation()

  useEffect(() => {
    const checkHealth = async () => {
      try {
        await healthCheck()
        setApiStatus('connected')
      } catch {
        setApiStatus('disconnected')
      }
    }

    checkHealth()
    const interval = setInterval(checkHealth, 5000)
    return () => clearInterval(interval)
  }, [])

  const currentNav = NAV_LINKS.find((link) => location.pathname.startsWith(link.path))
  const pageTitle = currentNav?.label || (location.pathname.includes('/hr/candidates') ? 'Candidate Profile' : 'Workspace')

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">SH</div>
          <div>
            <p className="brand-title">SourceHive</p>
            <p className="brand-subtitle">HR Suite</p>
          </div>
        </div>
        <nav className="sidebar-nav">
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.path}
              to={link.path}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-status">
          <p>API Status</p>
          <span className={`status-dot ${apiStatus}`} />
          <span className="status-label">{apiStatus}</span>
        </div>
      </aside>

      <div className="workspace">
        <header className="page-header">
          <div>
            <p className="page-subtitle">SourceHive platform</p>
            <h1>{pageTitle}</h1>
          </div>
          <div className="breadcrumbs">
            <Link to="/">Home</Link>
            <span>/</span>
            <span>{pageTitle}</span>
          </div>
        </header>

        {apiStatus === 'disconnected' && (
          <div className="connection-warning">
            Unable to connect to API. Ensure the backend is running at http://localhost:8000
          </div>
        )}

        <main className="main-area">
          <Routes>
            <Route path="/" element={<Navigate to="/hr/dashboard" replace />} />
            <Route path="/hr/dashboard" element={<HRDashboard />} />
            <Route path="/resume/upload" element={<UploadResume />} />
            <Route path="/hr/candidates/:id" element={<CandidateProfile />} />
            <Route path="/hr/roles" element={<RolesManagement />} />
            <Route path="/hr/analytics" element={<AnalyticsPage />} />
            <Route path="*" element={<div className="not-found">Page not found.</div>} />
          </Routes>
        </main>

        <footer className="app-footer">
          <p>SourceHive © 2024 — Built with FastAPI & React</p>
        </footer>
      </div>
    </div>
  )
}

export default function App() {
  return <AppShell />
}
