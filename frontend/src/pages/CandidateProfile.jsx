import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  getApplicationDetail,
  updateApplicationStatus,
  addCandidateNote,
  deleteCandidate,
  deleteNote,
  deleteAllNotes,
} from '../api/client'
import './CandidateProfile.css'

const STATUS_OPTIONS = ['new', 'shortlisted', 'interviewed', 'hired', 'rejected']

export default function CandidateProfile() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [candidate, setCandidate] = useState(null)
  const [notes, setNotes] = useState([])
  const [jdMatch, setJdMatch] = useState({ matched: [], missing: [] })
  const [statusValue, setStatusValue] = useState('new')
  const [noteText, setNoteText] = useState('')
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [deletingCandidate, setDeletingCandidate] = useState(false)
  const [deletingNoteId, setDeletingNoteId] = useState(null)
  const [clearingNotes, setClearingNotes] = useState(false)

  const loadCandidate = () => {
    setLoading(true)
    getApplicationDetail(id)
      .then((res) => {
        setCandidate(res.data.candidate)
        setNotes(res.data.notes || [])
        setJdMatch(res.data.jd_match || { matched: [], missing: [] })
        setStatusValue(res.data.candidate?.status || 'new')
        setError('')
      })
      .catch(() => {
        setError('Unable to load candidate.')
        setCandidate(null)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (id) {
      loadCandidate()
    }
  }, [id])

  const handleStatusUpdate = async () => {
    try {
      await updateApplicationStatus(id, statusValue)
      setMessage('Status updated')
      loadCandidate()
    } catch {
      setMessage('Unable to update status')
    }
  }

  const handleAddNote = async () => {
    if (!noteText.trim()) return
    try {
      await addCandidateNote(id, noteText.trim())
      setNoteText('')
      loadCandidate()
    } catch {
      setMessage('Unable to add note')
    }
  }

  const handleDeleteCandidate = async () => {
    if (deletingCandidate) return
    const confirmed = window.confirm('Remove this candidate and all associated data?')
    if (!confirmed) return
    try {
      setDeletingCandidate(true)
      await deleteCandidate(id)
      alert('Candidate removed.')
      navigate('/hr/dashboard')
    } catch {
      setMessage('Unable to delete candidate')
    } finally {
      setDeletingCandidate(false)
    }
  }

  const handleDeleteNote = async (noteId) => {
    if (!noteId || deletingNoteId === noteId) return
    try {
      setDeletingNoteId(noteId)
      await deleteNote(id, noteId)
      setNotes((prev) => prev.filter((note) => note.id !== noteId))
    } catch {
      setMessage('Unable to delete note')
    } finally {
      setDeletingNoteId(null)
    }
  }

  const handleDeleteAllNotes = async () => {
    if (!notes.length || clearingNotes) return
    const confirmed = window.confirm('Delete all notes for this candidate?')
    if (!confirmed) return
    try {
      setClearingNotes(true)
      await deleteAllNotes(id)
      setNotes([])
    } catch {
      setMessage('Unable to delete notes')
    } finally {
      setClearingNotes(false)
    }
  }

  if (loading) {
    return <div className="profile-page">Loading candidate...</div>
  }

  if (!candidate) {
    return (
      <div className="profile-page">
        <p>{error || 'Candidate not found.'}</p>
        <Link to="/hr/dashboard" className="link-btn">
          Back to dashboard
        </Link>
      </div>
    )
  }

  const resumeName =
    candidate.resume_display_name || candidate.cv_filename || 'Resume'

  return (
    <div className="profile-page">
      <header className="profile-header">
        <div>
          <h2>
            {candidate.first_name} {candidate.last_name}
          </h2>
          <p>{candidate.selected_role || 'Role not specified'}</p>
        </div>
        <div className="profile-header-actions">
          <span className={`status-pill status-${candidate.status}`}>{candidate.status}</span>
          <div className="profile-action-buttons">
            <Link to="/hr/dashboard" className="profile-back-link">
              Back to dashboard
            </Link>
            <button
              type="button"
              className="danger-outline-btn"
              onClick={handleDeleteCandidate}
              disabled={deletingCandidate}
            >
              {deletingCandidate ? 'Removing...' : 'Remove candidate'}
            </button>
          </div>
        </div>
      </header>

      {message && <div className="profile-alert">{message}</div>}

      <section className="profile-grid">
        <div className="card">
          <h3>Contact</h3>
          <p><strong>Email:</strong> {candidate.email || 'N/A'}</p>
          <p><strong>Phone:</strong> {candidate.phone || 'N/A'}</p>
          <p><strong>Applied:</strong> {new Date(candidate.created_at).toLocaleString()}</p>
          <p><strong>Last updated:</strong> {new Date(candidate.updated_at).toLocaleString()}</p>
        </div>
        <div className="card">
          <h3>Status</h3>
          <select value={statusValue} onChange={(e) => setStatusValue(e.target.value)}>
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
          <button onClick={handleStatusUpdate}>Save status</button>
        </div>
        <div className="card">
          <h3>Resume</h3>
          {candidate.cv_filename || candidate.resume_display_name ? (
            <p>{resumeName}</p>
          ) : (
            <p>No file stored.</p>
          )}
        </div>
      </section>

      <section className="card">
        <div className="notes-header">
          <h3>Notes</h3>
          {notes.length > 0 && (
            <button
              type="button"
              className="danger-outline-btn subtle"
              onClick={handleDeleteAllNotes}
              disabled={clearingNotes}
            >
              {clearingNotes ? 'Removing...' : 'Delete all'}
            </button>
          )}
        </div>
        <div className="notes-list">
          {notes.length === 0 ? (
            <p className="muted">No notes yet.</p>
          ) : (
            notes.map((note) => (
              <article key={note.id}>
                <div className="note-item-header">
                  <small>{new Date(note.updated_at).toLocaleString()}</small>
                  <button
                    type="button"
                    className="note-delete-btn"
                    onClick={() => handleDeleteNote(note.id)}
                    disabled={deletingNoteId === note.id}
                  >
                    {deletingNoteId === note.id ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
                <p>{note.comment}</p>
              </article>
            ))
          )}
        </div>
        <div className="note-form">
          <textarea
            placeholder="Add note..."
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
          />
          <button onClick={handleAddNote}>Add note</button>
        </div>
      </section>

      <section className="card skills-card">
        <div>
          <h3>Hard skills</h3>
          <div className="chip-list">
            {(candidate.skills_hard || []).map((skill) => (
              <span key={skill} className="chip">
                {skill}
              </span>
            ))}
            {(!candidate.skills_hard || candidate.skills_hard.length === 0) && (
              <span className="muted">No hard skills parsed.</span>
            )}
          </div>
        </div>
        <div>
          <h3>Soft skills</h3>
          <div className="chip-list">
            {(candidate.skills_soft || []).map((skill) => (
              <span key={skill} className="chip soft">
                {skill}
              </span>
            ))}
            {(!candidate.skills_soft || candidate.skills_soft.length === 0) && (
              <span className="muted">No soft skills parsed.</span>
            )}
          </div>
        </div>
      </section>

      <section className="card">
        <h3>JD Keyword Match</h3>
        <div className="jd-grid">
          <div>
            <h4>Matched</h4>
            <div className="chip-list">
              {jdMatch.matched.length ? (
                jdMatch.matched.map((kw) => (
                  <span key={kw} className="chip match">
                    {kw}
                  </span>
                ))
              ) : (
                <span className="muted">No keywords matched.</span>
              )}
            </div>
          </div>
          <div>
            <h4>Missing</h4>
            <div className="chip-list">
              {jdMatch.missing.length ? (
                jdMatch.missing.map((kw) => (
                  <span key={kw} className="chip missing">
                    {kw}
                  </span>
                ))
              ) : (
                <span className="muted">No missing keywords.</span>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
