import axios from 'axios'

const API_BASE = 'http://localhost:8000/api'

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const uploadResume = (formData) => {
  return api.post('/resume/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}

export const healthCheck = () => {
  return api.get('/health')
}

export const getDashboardOverview = () => {
  return api.get('/dashboard/overview')
}

export const getApplications = (params = {}) => {
  return api.get('/hr/applications', { params })
}

export const exportApplications = (params = {}) => {
  return api.get('/hr/applications/export', {
    params,
    responseType: 'blob',
  })
}

export const getApplicationDetail = (id) => {
  return api.get(`/hr/applications/${id}`)
}

export const updateApplicationStatus = (id, status) => {
  return api.patch(`/hr/applications/${id}/status`, { status })
}

export const updateApplicationResumeScore = (id, resume_score) => {
  return api.patch(`/hr/applications/${id}/resume_score`, { resume_score })
}

export const addCandidateNote = (id, comment) => {
  return api.post(`/hr/applications/${id}/notes`, { comment })
}

export const deleteCandidate = (id) => {
  return api.delete(`/hr/applications/${id}`)
}

export const deleteNote = (applicationId, noteId) => {
  return api.delete(`/hr/applications/${applicationId}/notes/${noteId}`)
}

export const deleteAllNotes = (applicationId) => {
  return api.delete(`/hr/applications/${applicationId}/notes`)
}

export const reprocessCandidate = (id) => {
  return api.post(`/hr/candidates/${id}/reprocess`)
}

export const getSkillDictionary = (kind = 'hard') => {
  return api.get('/hr/skills/dictionary', { params: { kind } })
}

export const addSkillsToDictionary = (payload) => {
  return api.post('/hr/skills/dictionary', payload)
}

export const getSkillSuggestions = (params = {}) => {
  return api.get('/hr/skills/enrichment', { params })
}

export const listSynonyms = () => api.get('/hr/synonyms')

export const createSynonymApi = (payload) => api.post('/hr/synonyms', payload)

export const updateSynonymApi = (id, payload) => api.patch(`/hr/synonyms/${id}`, payload)

export const deleteSynonymApi = (id) => api.delete(`/hr/synonyms/${id}`)

export const getRoles = () => api.get('/hr/roles')

export const createRole = (payload) => api.post('/hr/roles', payload)

export const getRoleDetail = (id) => api.get(`/hr/roles/${id}`)

export const updateRoleJD = (id, jd_text) => api.patch(`/hr/roles/${id}/jd`, { jd_text })

export const setRoleVisibility = (id, is_open) =>
  api.patch(`/hr/roles/${id}/visibility`, { is_open })

export const saveRoleKeyword = (roleId, payload) =>
  api.post(`/hr/roles/${roleId}/keywords`, payload)

export const deleteRoleKeyword = (keywordId) =>
  api.delete(`/hr/roles/keywords/${keywordId}`)

export const getAnalytics = (params = {}) => api.get('/hr/analytics', { params })

export const getInterviewSessions = () => api.get('/hr/interviews/sessions')

export const inviteAIInterview = (payload) => api.post('/hr/interviews/invite', payload)

export const bulkInviteAIInterviews = (payload) => api.post('/hr/interviews/bulk-invite', payload)

export const getInterviewPortal = (sessionId) => api.get(`/interviews/${sessionId}`)

export const startInterviewPortal = (sessionId) => api.post(`/interviews/${sessionId}/start`)

export const completeInterviewPortal = (sessionId, payload = {}) =>
  api.post(`/interviews/${sessionId}/complete`, payload)

export const inviteInterviewEmail = (payload) => api.post('/interviews/invite', payload)

export const getInterviewPortalByToken = (token) => api.get('/interviews/by-token', { params: { token } })

export const startInterviewByToken = (token) => api.post('/interviews/by-token/start', null, { params: { token } })

export const completeInterviewByToken = (token, payload = {}) =>
  api.post('/interviews/by-token/complete', payload, { params: { token } })

export const sendHrEmail = (payload) => api.post('/hr/email/send', payload)

export const startInterviewByTokenWithBot = (token) =>
  api.post('/interviews/by-token/start', null, { params: { token } })

export const sendInterviewMessage = (token, payload) =>
  api.post('/interviews/by-token/message', payload, { params: { token } })
