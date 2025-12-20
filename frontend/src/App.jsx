import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import UploadResume from './components/UploadResume'
import { healthCheck } from './api/client'
import CandidateProfile from './pages/CandidateProfile'
import HRDashboard from './pages/HRDashboard'
import AnalyticsPage from './pages/Analytics'
import RolesManagement from './pages/RolesManagement'
import AIInterviews from './pages/AIInterviews'
import InterviewPortal from './pages/InterviewPortal'
import logo from '../imgs/logo.jpg'
import './App.css'

function NavIcon({ children }) {
  return (
    <span className="nav-icon" aria-hidden="true">
      {children}
    </span>
  )
}

function IconDashboard(props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M3 13.5h8V3H3v10.5Z" />
      <path d="M13 21h8V10H13v11Z" />
      <path d="M13 3h8v5.5h-8V3Z" />
      <path d="M3 17.5h8V21H3v-3.5Z" />
    </svg>
  )
}

function IconUpload(props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M12 3v12" />
      <path d="M7 8l5-5 5 5" />
      <path d="M4 21h16" />
    </svg>
  )
}

function IconBriefcase(props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M8 7V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v1" />
      <path d="M3 7h18v11a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V7Z" />
      <path d="M3 12h18" />
    </svg>
  )
}

function IconChart(props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M7.5 15.5l4-4 3 3 5-6" />
    </svg>
  )
}

function IconSpark(props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z" />
      <path d="M8.5 10.5h7" />
      <path d="M8.5 14h4.5" />
    </svg>
  )
}

const NAV_LINKS = [
  { path: '/hr/dashboard', label: 'Dashboard', Icon: IconDashboard },
  { path: '/resume/upload', label: 'Upload', Icon: IconUpload },
  { path: '/hr/roles', label: 'Roles', Icon: IconBriefcase },
  { path: '/hr/interviews', label: 'AI Interviews', Icon: IconSpark },
  { path: '/hr/analytics', label: 'Analytics', Icon: IconChart },
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
    const interval = setInterval(checkHealth, 10000)
    return () => clearInterval(interval)
  }, [])

  const currentNav = NAV_LINKS.find((link) => location.pathname.startsWith(link.path))
  const pageTitle = currentNav?.label || (location.pathname.includes('/hr/candidates') ? 'Candidate Profile' : 'Workspace')

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">
            <img className="brand-logo" src={logo} alt="SourceHive" />
          </div>
          <div>
            <p className="brand-title">SourceHive</p>
            <p className="brand-subtitle">HR Suite</p>
          </div>
        </div>

        <nav className="sidebar-nav">
          {NAV_LINKS.map((link) => (
            <NavLink key={link.path} to={link.path} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <NavIcon>
                <link.Icon />
              </NavIcon>
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-status">
          <p>API</p>
          <span className={`status-dot ${apiStatus}`} />
          <span className="status-label">{apiStatus}</span>
        </div>
      </aside>

      <div className="workspace">
        <header className="page-header">
          <div>
            <p className="page-subtitle">SourceHive Platform</p>
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
            <Route path="/hr/admin" element={<Navigate to="/hr/roles" replace />} />
            <Route path="/hr/interviews" element={<AIInterviews />} />
            <Route path="/hr/analytics" element={<AnalyticsPage />} />
            <Route
              path="*"
              element={
                <div className="not-found card">
                  <h2>404</h2>
                  <p>Page not found</p>
                  <Link
                    to="/hr/dashboard"
                    style={{ color: 'var(--yellow-primary)', marginTop: '20px', display: 'inline-block' }}
                  >
                    Return to Dashboard
                  </Link>
                </div>
              }
            />
          </Routes>
        </main>

        <footer className="app-footer">
          <p>SourceHive © {new Date().getFullYear()} • Built with FastAPI & React</p>
        </footer>
      </div>
    </div>
  )
}

function CandidateShell() {
  return (
    <div className="candidate-shell">
      <Routes>
        <Route path="/interview" element={<InterviewPortal />} />
        <Route path="/interview/:sessionId" element={<InterviewPortal />} />
        <Route path="*" element={<Navigate to="/interview" replace />} />
      </Routes>
    </div>
  )
}

export default function App() {
  const location = useLocation()
  const isCandidatePortal = location.pathname.startsWith('/interview')
  return isCandidatePortal ? <CandidateShell /> : <AppShell />
}
