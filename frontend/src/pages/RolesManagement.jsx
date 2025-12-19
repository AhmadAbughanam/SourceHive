import { useEffect, useState } from 'react'
import {
  getRoles,
  createRole,
  getRoleDetail,
  updateRoleJD,
  saveRoleKeyword,
  deleteRoleKeyword,
  setRoleVisibility,
} from '../api/client'
import './RolesManagement.css'

const IMPORTANCE_OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'preferred', label: 'Preferred' },
]

export default function RolesManagement() {
  const [roles, setRoles] = useState([])
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedRoleId, setSelectedRoleId] = useState(null)
  const [roleDetail, setRoleDetail] = useState(null)
  const [jdText, setJdText] = useState('')
  const [keywordForm, setKeywordForm] = useState({ keyword: '', importance: 'preferred', weight: 1 })
  const [editingKeywordId, setEditingKeywordId] = useState(null)
  const [message, setMessage] = useState('')
  const [newRoleName, setNewRoleName] = useState('')
  const [newRoleJD, setNewRoleJD] = useState('')
  const [creatingRole, setCreatingRole] = useState(false)

  const refreshRoles = async (preferredId = null) => {
    try {
      const res = await getRoles()
      const list = res.data.roles || []
      setRoles(list)
      if (preferredId) {
        setSelectedRoleId(preferredId)
      } else if (!preferredId && list.length && !selectedRoleId) {
        setSelectedRoleId(list[0].id)
      }
    } catch {
      setRoles([])
    }
  }

  useEffect(() => {
    refreshRoles()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedRoleId) return
    getRoleDetail(selectedRoleId)
      .then((res) => {
        setRoleDetail(res.data)
        setJdText(res.data.role.jd_text || '')
        setKeywordForm({ keyword: '', importance: 'preferred', weight: 1 })
        setEditingKeywordId(null)
        setMessage('')
      })
      .catch(() => {
        setRoleDetail(null)
        setMessage('Unable to load role.')
      })
  }, [selectedRoleId])

  const handleSaveJD = async () => {
    if (!selectedRoleId) return
    try {
      await updateRoleJD(selectedRoleId, jdText)
      setMessage('Job description saved.')
    } catch {
      setMessage('Unable to save JD.')
    }
  }

  const handleKeywordSubmit = async () => {
    if (!keywordForm.keyword.trim()) return
    try {
      await saveRoleKeyword(selectedRoleId, {
        ...keywordForm,
        keyword_id: editingKeywordId,
      })
      setKeywordForm({ keyword: '', importance: 'preferred', weight: 1 })
      setEditingKeywordId(null)
      const refreshed = await getRoleDetail(selectedRoleId)
      setRoleDetail(refreshed.data)
    } catch {
      setMessage('Unable to save keyword.')
    }
  }

  const handleCreateRole = async (e) => {
    e.preventDefault()
    if (!newRoleName.trim()) {
      setMessage('Role name is required.')
      return
    }
    try {
      setCreatingRole(true)
      setMessage('')
      const payload = { role_name: newRoleName.trim(), jd_text: newRoleJD }
      const res = await createRole(payload)
      const createdRole = res.data.role
      setNewRoleName('')
      setNewRoleJD('')
      setMessage('Role created.')
      await refreshRoles(createdRole?.id)
    } catch {
      setMessage('Unable to create role.')
    } finally {
      setCreatingRole(false)
    }
  }

  const handleKeywordDelete = async (keywordId) => {
    try {
      await deleteRoleKeyword(keywordId)
      const refreshed = await getRoleDetail(selectedRoleId)
      setRoleDetail(refreshed.data)
    } catch {
      setMessage('Unable to delete keyword.')
    }
  }

  const handleVisibilityChange = async (checked) => {
    if (!selectedRoleId) return
    try {
      await setRoleVisibility(selectedRoleId, checked)
      setRoleDetail((prev) =>
        prev
          ? {
              ...prev,
              role: { ...prev.role, is_open: checked ? 1 : 0 },
            }
          : prev
      )
      refreshRoles(selectedRoleId)
      setMessage(checked ? 'Role is open for uploads.' : 'Role closed for uploads.')
    } catch {
      setMessage('Unable to update role visibility.')
    }
  }

  const filteredRoles = roles.filter((role) =>
    (role.role_name || '').toLowerCase().includes(searchTerm.toLowerCase())
  )
  const keywords = roleDetail?.keywords || []
  const isRoleOpen = roleDetail?.role?.is_open !== 0 && roleDetail?.role?.is_open !== false

  return (
    <div className="roles-page">
      <div className="roles-layout">
        <aside className="roles-sidebar card">
          <div className="roles-sidebar-header">
            <h3>Roles</h3>
            <p>Pick a role to manage its JD and keywords.</p>
          </div>
          <form className="new-role-form" onSubmit={handleCreateRole}>
            <h4>Add new role</h4>
            <input
              type="text"
              placeholder="Role name"
              value={newRoleName}
              onChange={(e) => setNewRoleName(e.target.value)}
            />
            <textarea
              placeholder="Job description"
              value={newRoleJD}
              onChange={(e) => setNewRoleJD(e.target.value)}
            />
            <button type="submit" className="primary-btn" disabled={creatingRole}>
              {creatingRole ? 'Creating...' : 'Add role'}
            </button>
          </form>
          <input
            type="text"
            placeholder="Search roles..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <div className="roles-list">
            {filteredRoles.length === 0 && (
              <p className="muted">No roles match “{searchTerm}”.</p>
            )}
            {filteredRoles.map((role) => (
              <button
                key={role.id}
                className={`roles-list-item ${role.id === selectedRoleId ? 'active' : ''}`}
                onClick={() => setSelectedRoleId(role.id)}
              >
                <div>
                  <span>{role.role_name}</span>
                  {role.is_open === 0 || role.is_open === false ? (
                    <small className="muted">Closed</small>
                  ) : null}
                </div>
                <small>{new Date(role.updated_at).toLocaleDateString()}</small>
              </button>
            ))}
          </div>
        </aside>

        <div className="roles-content">
          {message && <div className="roles-alert">{message}</div>}
          {roleDetail ? (
            <>
              <section className="card role-overview">
                <div>
                  <p className="muted">Selected role</p>
                  <h2>{roleDetail.role.role_name}</h2>
                </div>
                <div className="role-meta">
                  <label className="role-toggle">
                    <input
                      type="checkbox"
                      checked={isRoleOpen}
                      onChange={(e) => handleVisibilityChange(e.target.checked)}
                    />
                    <span>{isRoleOpen ? 'Accepting uploads' : 'Closed to uploads'}</span>
                  </label>
                  <div>
                    <p className="muted">Last updated</p>
                    <strong>{new Date(roleDetail.role.updated_at).toLocaleString()}</strong>
                  </div>
                  <div>
                    <p className="muted">Keyword count</p>
                    <strong>{keywords.length}</strong>
                  </div>
                </div>
              </section>

              <section className="card">
                <div className="section-header">
                  <div>
                    <h3>Job Description</h3>
                    <p>Keep your JD accurate for the automation rules.</p>
                  </div>
                  <button className="primary-btn" onClick={handleSaveJD}>
                    Save JD
                  </button>
                </div>
                <textarea
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  placeholder="Describe the role expectations..."
                />
              </section>

              <section className="card">
                <div className="section-header">
                  <div>
                    <h3>Keywords</h3>
                    <p>Importance + weight help the parser score correctly.</p>
                  </div>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Keyword</th>
                        <th>Importance</th>
                        <th>Weight</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {keywords.length === 0 && (
                        <tr>
                          <td colSpan={4} className="muted">
                            No keywords defined yet.
                          </td>
                        </tr>
                      )}
                      {keywords.map((kw) => (
                        <tr key={kw.id}>
                          <td>{kw.keyword}</td>
                          <td>{kw.importance}</td>
                          <td>{kw.weight}</td>
                          <td className="action-cell">
                            <button
                              onClick={() => {
                                setEditingKeywordId(kw.id)
                                setKeywordForm({
                                  keyword: kw.keyword,
                                  importance: kw.importance,
                                  weight: kw.weight,
                                })
                              }}
                            >
                              Edit
                            </button>
                            <button className="danger" onClick={() => handleKeywordDelete(kw.id)}>
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="keyword-form">
                  <input
                    type="text"
                    placeholder="Keyword"
                    value={keywordForm.keyword}
                    onChange={(e) => setKeywordForm((prev) => ({ ...prev, keyword: e.target.value }))}
                  />
                  <select
                    value={keywordForm.importance}
                    onChange={(e) => setKeywordForm((prev) => ({ ...prev, importance: e.target.value }))}
                  >
                    {IMPORTANCE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    step="0.1"
                    value={keywordForm.weight}
                    onChange={(e) => setKeywordForm((prev) => ({ ...prev, weight: Number(e.target.value) }))}
                  />
                  <button className="primary-btn" onClick={handleKeywordSubmit}>
                    {editingKeywordId ? 'Update keyword' : 'Add keyword'}
                  </button>
                </div>
              </section>
            </>
          ) : (
            <div className="empty-state card">
              <h3>Select a role</h3>
              <p>Pick a role from the list to edit JD and keyword weighting.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
