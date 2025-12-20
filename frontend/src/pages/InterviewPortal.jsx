import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import {
  getInterviewPortal,
  getInterviewPortalByToken,
  sendInterviewMessage,
  startInterviewByToken,
  startInterviewPortal,
} from '../api/client'
import './InterviewPortal.css'

const fmtDateTime = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
}

export default function InterviewPortal() {
  const { sessionId } = useParams()
  const location = useLocation()
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [acting, setActing] = useState(false)
  const [turns, setTurns] = useState([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [debug, setDebug] = useState({ lastStart: null, lastMessage: null })
  const didAutoStartRef = useRef(false)
  const chatEndRef = useRef(null)

  const token = useMemo(() => {
    const params = new URLSearchParams(location.search || '')
    return (params.get('token') || '').trim()
  }, [location.search])

  const debugEnabled = useMemo(() => {
    const params = new URLSearchParams(location.search || '')
    return params.get('debug') === '1'
  }, [location.search])

  const currentQuestion = session?.current_question || ''
  const questionCount = Number(session?.question_count || 0)
  const maxQuestions = Number(session?.max_questions || 6)
  const status = session?.interview_status || 'invited'
  const isStarted = status === 'in_progress' || Boolean(session?.started_at)
  const isCompleted = status === 'completed' || Boolean(session?.completed_at)
  const isAtLimit = isStarted && questionCount >= maxQuestions
  const composeDisabled = !token || sending || !isStarted || isCompleted

  const load = () => {
    setLoading(true)
    setError('')
    const request = token ? getInterviewPortalByToken(token) : sessionId ? getInterviewPortal(sessionId) : null
    if (!request) {
      setError('Missing interview link token.')
      setSession(null)
      setLoading(false)
      return
    }

    request
      .then((res) => setSession(res.data.session))
      .catch(() => {
        setError('Interview link is invalid or expired.')
        setSession(null)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, token])

  // Seed the chat with the current question if we have one.
  useEffect(() => {
    if (!currentQuestion) return
    if (turns.length > 0) return
    setTurns([{ role: 'bot', ack: '', feedback: [], question: currentQuestion }])
  }, [currentQuestion, turns.length])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns.length])

  const handleStart = async () => {
    if (acting) return
    try {
      setActing(true)
      setActionMsg('')

      if (token) {
        const res = await startInterviewByToken(token)
        setDebug((prev) => ({ ...prev, lastStart: res?.data || null }))

        const warning = res?.data?.warning || ''
        const ack = res?.data?.ack || ''
        const feedback = res?.data?.feedback || []
        const question = res?.data?.question || ''

        if (warning) setActionMsg(warning)
        if (ack || question || (Array.isArray(feedback) && feedback.length)) {
          setTurns([{ role: 'bot', ack, feedback, question }])
        }

        const refreshed = await getInterviewPortalByToken(token)
        setSession(refreshed.data.session)
        const q = question || refreshed.data.session?.current_question || ''
        if (q) {
          setTurns((prev) => (prev.length ? prev : [{ role: 'bot', ack, feedback, question: q }]))
        }
      } else if (sessionId) {
        await startInterviewPortal(sessionId)
        setActionMsg('Interview started.')
        load()
      } else {
        throw new Error('Missing session')
      }

      setActionMsg((prev) => prev || 'Interview started.')
    } catch {
      setActionMsg('Unable to start interview. Please refresh and try again.')
    } finally {
      setActing(false)
    }
  }

  // Auto-start once when candidate opens the link.
  useEffect(() => {
    if (!token) return
    if (loading || error) return
    if (didAutoStartRef.current) return
    if (isCompleted) return
    if (turns.length > 0) return
    if (currentQuestion) {
      didAutoStartRef.current = true
      return
    }
    didAutoStartRef.current = true
    handleStart()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, loading, error, isCompleted, currentQuestion, turns.length])

  const handleSend = async () => {
    if (!token || sending || isCompleted) return
    const text = draft.trim()
    if (!text) return

    try {
      setSending(true)
      setTurns((prev) => [...prev, { role: 'candidate', text }])
      setDraft('')

      const res = await sendInterviewMessage(token, { message: text })
      setDebug((prev) => ({ ...prev, lastMessage: res?.data || null }))

      const warning = res.data.warning || ''
      if (warning) setActionMsg(warning)

      const next = {
        role: 'bot',
        ack: res.data.ack || '',
        feedback: res.data.feedback || [],
        question: res.data.question || '',
      }

      if (res.data.completed) {
        setActionMsg('Interview complete. Thank you!')
        setTurns((prev) => [
          ...prev,
          {
            ...next,
            question: '',
            feedback: Array.isArray(next.feedback) && next.feedback.length ? next.feedback : ['Interview complete. Thank you!'],
          },
        ])
      } else {
        setTurns((prev) => [...prev, next])
      }

      const refreshed = await getInterviewPortalByToken(token)
      setSession(refreshed.data.session)
    } catch {
      setActionMsg('Unable to send message. Please try again.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="portal-shell">
      <div className="portal-card card">
        <div className="portal-top">
          <div>
            <h2>AI Interview</h2>
            <p className="muted">Answer each question clearly. There are {maxQuestions} questions total.</p>
          </div>
        </div>

        {loading ? (
          <p className="muted">Loading interview session…</p>
        ) : error ? (
          <div className="portal-error">{error}</div>
        ) : (
          <>
            <div className="portal-status">
              <span className={`status-pill status-${status}`}>{status}</span>
              <span className="muted">
                {isCompleted ? 'Interview completed.' : isStarted ? 'Interview in progress.' : 'Ready to start.'}
              </span>
              <span className="muted">
                {questionCount > 0 ? `Question ${Math.min(questionCount, maxQuestions)} / ${maxQuestions}` : `Up to ${maxQuestions} questions`}
              </span>
            </div>

            <div className="portal-progress" aria-label="Interview progress">
              <div
                className="portal-progress-bar"
                style={{ width: `${maxQuestions ? Math.min(100, (Math.min(questionCount, maxQuestions) / maxQuestions) * 100) : 0}%` }}
              />
            </div>

            {actionMsg && <p className="portal-msg">{actionMsg}</p>}

            <div className="portal-grid">
              <div>
                <p className="portal-label">Candidate</p>
                <strong>{session?.candidate_name || '—'}</strong>
              </div>
              <div>
                <p className="portal-label">Role</p>
                <strong>{session?.interview_role || '—'}</strong>
              </div>
              <div>
                <p className="portal-label">Expires</p>
                <strong>{fmtDateTime(session?.expires_at)}</strong>
              </div>
            </div>

            <div className="portal-actions">
              <button type="button" className="primary-btn" onClick={handleStart} disabled={acting || isStarted || isCompleted}>
                {acting ? 'Starting…' : isStarted ? 'Started' : 'Start interview'}
              </button>
            </div>

            {currentQuestion && (
              <div className="portal-question card">
                <p className="portal-label">Current question</p>
                <p className="portal-question-text">{currentQuestion}</p>
              </div>
            )}

            {isAtLimit && !isCompleted ? (
              <div className="portal-hint">
                <strong>Final step</strong>
                <p className="muted" style={{ margin: '6px 0 0' }}>
                  You’ve reached the final question. Submit your answer to finish the interview.
                </p>
              </div>
            ) : null}

            <div className="portal-chat card">
              <div className="chat-log">
                {turns.length === 0 ? (
                  <p className="muted">The interview will begin automatically.</p>
                ) : (
                  turns.map((turn, idx) => (
                    <div key={idx} className={`chat-bubble ${turn.role === 'candidate' ? 'me' : 'bot'}`}>
                      {turn.role === 'candidate' ? (
                        <p>{turn.text}</p>
                      ) : (
                        <>
                          {turn.ack ? <p className="chat-ack">{turn.ack}</p> : null}
                          {Array.isArray(turn.feedback) && turn.feedback.length ? (
                            <ul className="chat-feedback">
                              {turn.feedback.slice(0, 4).map((b) => (
                                <li key={b}>{b}</li>
                              ))}
                            </ul>
                          ) : null}
                          {turn.question ? <p className="chat-q">{turn.question}</p> : null}
                        </>
                      )}
                    </div>
                  ))
                )}
                <div ref={chatEndRef} />
              </div>

              <div className="chat-compose">
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={isCompleted ? 'Interview complete.' : isStarted ? 'Type your answer…' : 'Click “Start interview” to begin.'}
                  rows={4}
                  disabled={composeDisabled}
                />
                <button type="button" className="primary-btn" onClick={handleSend} disabled={composeDisabled}>
                  {sending ? 'Sending…' : 'Send'}
                </button>
              </div>
            </div>

            {debugEnabled && (
              <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap', color: 'var(--text-muted)' }}>
                {JSON.stringify(
                  {
                    tokenPresent: Boolean(token),
                    sessionId,
                    currentQuestion,
                    status,
                    questionCount,
                    maxQuestions,
                    turns: turns.length,
                    lastStart: debug.lastStart,
                    lastMessage: debug.lastMessage,
                  },
                  null,
                  2
                )}
              </pre>
            )}
          </>
        )}
      </div>
    </div>
  )
}
