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

export const getAnalytics = () => api.get('/hr/analytics')
