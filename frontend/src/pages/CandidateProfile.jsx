import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  getApplicationDetail,
  updateApplicationStatus,
  updateApplicationResumeScore,
  addCandidateNote,
  deleteCandidate,
  deleteNote,
  deleteAllNotes,
  reprocessCandidate,
  inviteInterviewEmail,
  sendHrEmail,
} from '../api/client'
import './CandidateProfile.css'

const STATUS_OPTIONS = ['new', 'shortlisted', 'interviewed', 'hired', 'rejected']

export default function CandidateProfile() {
  const { id } = useParams()
  const navigate = useNavigate()
  
  // Candidate Data State
  const [candidate, setCandidate] = useState(null)
  const [notes, setNotes] = useState([])
  const [jdMatch, setJdMatch] = useState({ matched: [], missing: [] })
  
  // Form State
  const [statusValue, setStatusValue] = useState('new')
  const [resumeScore, setResumeScore] = useState(0)
  const [noteText, setNoteText] = useState('')
  
  // Email Composer State
  const [emailComposerOpen, setEmailComposerOpen] = useState(false)
  const [emailSubject, setEmailSubject] = useState('')
  const [emailBody, setEmailBody] = useState('')
  
  // Loading States
  const [loading, setLoading] = useState(true)
  const [savingScore, setSavingScore] = useState(false)
  const [deletingCandidate, setDeletingCandidate] = useState(false)
  const [deletingNoteId, setDeletingNoteId] = useState(null)
  const [clearingNotes, setClearingNotes] = useState(false)
  const [reprocessing, setReprocessing] = useState(false)
  const [invitingInterview, setInvitingInterview] = useState(false)
  const [sendingEmail, setSendingEmail] = useState(false)
  
  // Message State
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  // Load candidate data
  const loadCandidate = () => {
    setLoading(true)
    getApplicationDetail(id)
      .then((res) => {
        setCandidate(res.data.candidate)
        setNotes(res.data.notes || [])
        setJdMatch(res.data.jd_match || { matched: [], missing: [] })
        setStatusValue(res.data.candidate?.status || 'new')
        setResumeScore(Number(res.data.candidate?.resume_score || 0))
        setError('')
      })
      .catch(() => {
        setError('Unable to load candidate.')
        setCandidate(null)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (id) loadCandidate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // Helper function to show temporary messages
  const showMessage = (msg, duration = 3000) => {
    setMessage(msg)
    setTimeout(() => setMessage(''), duration)
  }

  // Status Update Handler
  const handleStatusUpdate = async () => {
    try {
      await updateApplicationStatus(id, statusValue)
      showMessage('Status updated successfully')
      loadCandidate()
    } catch {
      showMessage('Unable to update status')
    }
  }

  // Resume Score Handler
  const handleResumeScoreSave = async () => {
    if (savingScore) return
    try {
      setSavingScore(true)
      await updateApplicationResumeScore(id, Number(resumeScore || 0))
      showMessage('Evaluation score updated')
      loadCandidate()
    } catch {
      showMessage('Unable to update evaluation score')
    } finally {
      setSavingScore(false)
    }
  }

  // Notes Handlers
  const handleAddNote = async () => {
    if (!noteText.trim()) return
    try {
      await addCandidateNote(id, noteText.trim())
      setNoteText('')
      showMessage('Note added successfully')
      loadCandidate()
    } catch {
      showMessage('Unable to add note')
    }
  }

  const handleDeleteNote = async (noteId) => {
    if (!noteId || deletingNoteId === noteId) return
    try {
      setDeletingNoteId(noteId)
      await deleteNote(id, noteId)
      setNotes((prev) => prev.filter((note) => note.id !== noteId))
      showMessage('Note deleted')
    } catch {
      showMessage('Unable to delete note')
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
      showMessage('All notes deleted')
    } catch {
      showMessage('Unable to delete notes')
    } finally {
      setClearingNotes(false)
    }
  }

  // Candidate Actions
  const handleDeleteCandidate = async () => {
    if (deletingCandidate) return
    const confirmed = window.confirm('Remove this candidate and all associated data?')
    if (!confirmed) return
    try {
      setDeletingCandidate(true)
      await deleteCandidate(id)
      alert('Candidate removed successfully.')
      navigate('/hr/dashboard')
    } catch {
      showMessage('Unable to delete candidate')
    } finally {
      setDeletingCandidate(false)
    }
  }

  const handleReprocessResume = async () => {
    if (reprocessing) return
    try {
      setReprocessing(true)
      await reprocessCandidate(id)
      showMessage('Resume reprocessed successfully')
      loadCandidate()
    } catch {
      showMessage('Unable to reprocess resume')
    } finally {
      setReprocessing(false)
    }
  }

  // Email Handlers
  const handleOpenEmailComposer = () => {
    const to = (candidate?.email || '').trim()
    if (!to) {
      alert('Candidate email is missing.')
      return
    }

    const fullName = `${candidate?.first_name || ''} ${candidate?.last_name || ''}`.trim() || 'Candidate'
    const role = (candidate?.selected_role || '').trim() || 'the role'
    const subject = `Interview Invitation — ${role}`
    const body = [
      `Hello ${fullName},`,
      '',
      `Thank you for applying for ${role} at SourceHive.`,
      '',
      'We would like to invite you to an interview. Please reply with your availability for the next few days and your preferred time slots.',
      '',
      'We look forward to speaking with you.',
      '',
      'Best regards,',
      'SourceHive HR Team',
    ].join('\n')

    setEmailSubject(subject)
    setEmailBody(body)
    setEmailComposerOpen(true)
  }

  const handleSendEmail = async () => {
    const to = (candidate?.email || '').trim()
    if (!to) {
      showMessage('Candidate email is missing')
      return
    }
    if (!emailSubject.trim() || !emailBody.trim()) {
      showMessage('Subject and message are required')
      return
    }
    if (sendingEmail) return

    try {
      setSendingEmail(true)
      await sendHrEmail({ 
        to_email: to, 
        subject: emailSubject.trim(), 
        body: emailBody 
      })
      setEmailComposerOpen(false)
      showMessage('Email sent successfully')
    } catch {
      showMessage('Unable to send email (check SMTP settings)', 4000)
    } finally {
      setSendingEmail(false)
    }
  }

  const handleInviteAIInterview = async () => {
    if (!candidate || invitingInterview) return
    try {
      setInvitingInterview(true)

      const roleName = (candidate.selected_role || candidate.parsed_role || 'General').trim() || 'General'
      const candidateName =
        (candidate.name || `${candidate.first_name || ''} ${candidate.last_name || ''}`.trim()).trim() || 'Candidate'

      const res = await inviteInterviewEmail({
        candidate_email: candidate.email || '',
        candidate_name: candidateName,
        role_name: roleName,
        expires_hours: 72,
      })

      if (res.data.invite_sent === false && res.data.fallback_url) {
        try {
          await navigator.clipboard.writeText(res.data.fallback_url)
          showMessage('SMTP failed. Fallback interview link copied to clipboard.', 6000)
        } catch {
          showMessage(`SMTP failed. Fallback interview link: ${res.data.fallback_url}`, 6000)
        }
      } else {
        showMessage('AI interview invite sent to candidate.', 6000)
      }
    } catch {
      showMessage('Unable to create AI interview invite')
    } finally {
      setInvitingInterview(false)
    }
  }

  // Loading State
  if (loading) {
    return (
      <div className="profile-page">
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#737373' }}>
          Loading candidate profile...
        </div>
      </div>
    )
  }

  // Error State
  if (!candidate) {
    return (
      <div className="profile-page">
        <div className="card" style={{ textAlign: 'center', padding: '40px' }}>
          <p style={{ marginBottom: '20px' }}>{error || 'Candidate not found.'}</p>
          <Link to="/hr/dashboard" className="profile-back-link">
            Back to dashboard
          </Link>
        </div>
      </div>
    )
  }

  // Computed Values
  const resumeName = candidate.resume_display_name || candidate.cv_filename || 'Resume'
  const jdScore = typeof jdMatch.score === 'number' ? jdMatch.score : candidate.jd_match_score || 0
  const jdCoverage = jdMatch.coverage ? Math.round(jdMatch.coverage * 100) : jdScore
  const matchedCount = jdMatch.matched?.length || 0
  const missingCount = jdMatch.missing?.length || 0
  const jdTotal = jdMatch.total || matchedCount + missingCount

  return (
    <div className="profile-page">
      {/* Header */}
      <header className="profile-header">
        <div>
          <h2>
            {candidate.first_name} {candidate.last_name}
          </h2>
          <p>{candidate.selected_role || 'Role not specified'}</p>
        </div>
        <div className="profile-header-actions">
          <span className={`status-pill status-${candidate.status}`}>
            {candidate.status}
          </span>
          <div className="profile-action-buttons">
            <Link to="/hr/dashboard" className="profile-back-link">
              ← Back
            </Link>
            <button 
              type="button" 
              className="secondary-outline-btn" 
              onClick={handleOpenEmailComposer}
            >
              Send Email
            </button>
            <button 
              type="button" 
              className="secondary-outline-btn" 
              onClick={handleInviteAIInterview} 
              disabled={invitingInterview}
            >
              {invitingInterview ? 'Creating...' : 'AI Interview'}
            </button>
            <button
              type="button"
              className="danger-outline-btn"
              onClick={handleDeleteCandidate}
              disabled={deletingCandidate}
            >
              {deletingCandidate ? 'Removing...' : 'Remove'}
            </button>
          </div>
        </div>
      </header>

      {/* Message Alert */}
      {message && <div className="profile-alert">{message}</div>}

      {/* Email Composer Modal */}
      {emailComposerOpen && (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => {
          if (e.target.classList.contains('modal-overlay')) {
            setEmailComposerOpen(false)
          }
        }}>
          <div className="modal-card card">
            <div className="modal-header">
              <h3>Send Email</h3>
              <button 
                type="button" 
                className="secondary-outline-btn" 
                onClick={() => setEmailComposerOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="modal-body">
              <p className="muted">
                To: <strong>{candidate.email || 'N/A'}</strong>
              </p>
              <label className="modal-field">
                Subject
                <input 
                  value={emailSubject} 
                  onChange={(e) => setEmailSubject(e.target.value)}
                  placeholder="Enter email subject..."
                />
              </label>
              <label className="modal-field">
                Message
                <textarea 
                  value={emailBody} 
                  onChange={(e) => setEmailBody(e.target.value)} 
                  rows={10}
                  placeholder="Enter your message..."
                />
              </label>
              <div className="modal-actions">
                <button 
                  type="button" 
                  className="primary-btn" 
                  onClick={handleSendEmail} 
                  disabled={sendingEmail}
                >
                  {sendingEmail ? 'Sending...' : 'Send Email'}
                </button>
                <button 
                  type="button" 
                  className="secondary-btn" 
                  onClick={() => setEmailComposerOpen(false)} 
                  disabled={sendingEmail}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Profile Grid */}
      <section className="profile-grid">
        <div className="card">
          <h3>Contact Information</h3>
          <p><strong>Email:</strong> {candidate.email || 'N/A'}</p>
          <p><strong>Phone:</strong> {candidate.phone || 'N/A'}</p>
          <p><strong>Applied:</strong> {new Date(candidate.created_at).toLocaleDateString()}</p>
          <p><strong>Last updated:</strong> {new Date(candidate.updated_at).toLocaleDateString()}</p>
        </div>

        <div className="card">
          <h3>Application Status</h3>
          <select value={statusValue} onChange={(e) => setStatusValue(e.target.value)}>
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </option>
            ))}
          </select>
          <button onClick={handleStatusUpdate}>Update Status</button>
        </div>

        <div className="card">
          <h3>Evaluation Score</h3>
          <p className="muted">Manual HR evaluation score (0-100)</p>
          <div className="score-editor">
            <input
              type="range"
              min="0"
              max="100"
              step="1"
              value={Number(resumeScore || 0)}
              onChange={(e) => setResumeScore(Number(e.target.value))}
            />
            <div className="score-editor-row">
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                value={Number(resumeScore || 0)}
                onChange={(e) => setResumeScore(Number(e.target.value))}
              />
              <span className="muted">/ 100</span>
              <button type="button" onClick={handleResumeScoreSave} disabled={savingScore}>
                {savingScore ? 'Saving...' : 'Save Score'}
              </button>
            </div>
          </div>
        </div>

        <div className="card">
          <h3>Resume</h3>
          {candidate.cv_filename || candidate.resume_display_name ? (
            <p><strong>File:</strong> {resumeName}</p>
          ) : (
            <p className="muted">No file stored</p>
          )}
          <button type="button" className="secondary-btn" onClick={handleReprocessResume} disabled={reprocessing}>
            {reprocessing ? 'Reprocessing...' : 'Reprocess Resume'}
          </button>
        </div>
      </section>

      {/* Notes Section */}
      <section className="card">
        <div className="notes-header">
          <h3>Notes & Comments</h3>
          {notes.length > 0 && (
            <button
              type="button"
              className="danger-outline-btn subtle"
              onClick={handleDeleteAllNotes}
              disabled={clearingNotes}
            >
              {clearingNotes ? 'Removing...' : 'Delete All'}
            </button>
          )}
        </div>
        <div className="notes-list">
          {notes.length === 0 ? (
            <p className="muted">No notes yet. Add your first note below.</p>
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
            placeholder="Add a note about this candidate..." 
            value={noteText} 
            onChange={(e) => setNoteText(e.target.value)} 
          />
          <button onClick={handleAddNote}>Add Note</button>
        </div>
      </section>

      {/* Skills Section */}
      <section className="card skills-card">
        <div>
          <h3>Hard Skills</h3>
          <div className="chip-list">
            {(candidate.skills_hard || []).map((skill) => (
              <span key={skill} className="chip">{skill}</span>
            ))}
            {(!candidate.skills_hard || candidate.skills_hard.length === 0) && (
              <span className="muted">No hard skills parsed</span>
            )}
          </div>
        </div>
        <div>
          <h3>Soft Skills</h3>
          <div className="chip-list">
            {(candidate.skills_soft || []).map((skill) => (
              <span key={skill} className="chip soft">{skill}</span>
            ))}
            {(!candidate.skills_soft || candidate.skills_soft.length === 0) && (
              <span className="muted">No soft skills parsed</span>
            )}
          </div>
        </div>
      </section>

      {/* JD Match Section */}
      <section className="card">
        <h3>Job Description Match Analysis</h3>
        <div className="jd-score-card">
          <div className="jd-score-value">
            <p>Match Score</p>
            <strong>{jdScore?.toFixed ? jdScore.toFixed(1) : Number(jdScore || 0).toFixed(1)}%</strong>
          </div>
          <div className="jd-score-progress">
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${Math.min(100, Math.max(0, jdCoverage))}%` }} />
            </div>
            <small>
              {matchedCount} of {jdTotal || '0'} keywords matched
            </small>
          </div>
        </div>
        <div className="jd-grid">
          <div>
            <h4>Matched Keywords</h4>
            <div className="chip-list">
              {jdMatch.matched.length ? (
                jdMatch.matched.map((kw) => (
                  <span key={kw} className="chip match">{kw}</span>
                ))
              ) : (
                <span className="muted">No keywords matched</span>
              )}
            </div>
          </div>
          <div>
            <h4>Missing Keywords</h4>
            <div className="chip-list">
              {jdMatch.missing.length ? (
                jdMatch.missing.map((kw) => (
                  <span key={kw} className="chip missing">{kw}</span>
                ))
              ) : (
                <span className="muted">All keywords matched</span>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}