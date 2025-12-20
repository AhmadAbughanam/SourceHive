import { useEffect, useState } from 'react'
import {
  getRoles,
  createRole,
  getRoleDetail,
  updateRoleJD,
  saveRoleKeyword,
  deleteRoleKeyword,
  setRoleVisibility,
  getSkillDictionary,
  addSkillsToDictionary,
  getSkillSuggestions,
  listSynonyms,
  createSynonymApi,
  updateSynonymApi,
  deleteSynonymApi,
} from '../api/client'
import './RolesManagement.css'

const IMPORTANCE_OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'preferred', label: 'Preferred' },
]

const SYNONYM_CATEGORIES = [
  { value: 'skill', label: 'Skill' },
  { value: 'tool', label: 'Tool' },
  { value: 'certification', label: 'Certification' },
  { value: 'methodology', label: 'Methodology' },
  { value: 'other', label: 'Other' },
]

export default function RolesManagement() {
  const [activeTab, setActiveTab] = useState('roles')
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
  const [dictionaryKind, setDictionaryKind] = useState('hard')
  const [dictionarySkills, setDictionarySkills] = useState([])
  const [dictionaryLoading, setDictionaryLoading] = useState(false)
  const [newSkillInput, setNewSkillInput] = useState('')
  const [appendingSkills, setAppendingSkills] = useState(false)
  const [enrichmentRole, setEnrichmentRole] = useState('')
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [enrichmentResults, setEnrichmentResults] = useState([])
  const [synonyms, setSynonyms] = useState([])
  const [synonymLoading, setSynonymLoading] = useState(false)
  const [synonymForm, setSynonymForm] = useState({ token: '', expands_to: '', category: 'skill' })
  const [synonymSaving, setSynonymSaving] = useState(false)
  const [editingSynonymId, setEditingSynonymId] = useState(null)

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

  const loadDictionary = async (kind) => {
    try {
      setDictionaryLoading(true)
      const res = await getSkillDictionary(kind)
      setDictionarySkills(res.data.dictionary?.skills || [])
    } catch {
      setDictionarySkills([])
    } finally {
      setDictionaryLoading(false)
    }
  }

  useEffect(() => {
    loadDictionary(dictionaryKind)
  }, [dictionaryKind])

  const loadSynonyms = async () => {
    try {
      setSynonymLoading(true)
      const res = await listSynonyms()
      setSynonyms(res.data.synonyms || [])
    } catch {
      setSynonyms([])
    } finally {
      setSynonymLoading(false)
    }
  }

  useEffect(() => {
    loadSynonyms()
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
      setMessage('Job description saved successfully.')
      setTimeout(() => setMessage(''), 3000)
    } catch {
      setMessage('Unable to save JD.')
      setTimeout(() => setMessage(''), 3000)
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
      setMessage(editingKeywordId ? 'Keyword updated.' : 'Keyword added.')
      setTimeout(() => setMessage(''), 3000)
    } catch {
      setMessage('Unable to save keyword.')
      setTimeout(() => setMessage(''), 3000)
    }
  }

  const handleCreateRole = async (e) => {
    e.preventDefault()
    if (!newRoleName.trim()) {
      setMessage('Role name is required.')
      setTimeout(() => setMessage(''), 3000)
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
      setMessage('Role created successfully.')
      setTimeout(() => setMessage(''), 3000)
      await refreshRoles(createdRole?.id)
    } catch {
      setMessage('Unable to create role.')
      setTimeout(() => setMessage(''), 3000)
    } finally {
      setCreatingRole(false)
    }
  }

  const handleKeywordDelete = async (keywordId) => {
    try {
      await deleteRoleKeyword(keywordId)
      const refreshed = await getRoleDetail(selectedRoleId)
      setRoleDetail(refreshed.data)
      setMessage('Keyword deleted.')
      setTimeout(() => setMessage(''), 3000)
    } catch {
      setMessage('Unable to delete keyword.')
      setTimeout(() => setMessage(''), 3000)
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
      setMessage(checked ? 'Role is now open for applications.' : 'Role closed for applications.')
      setTimeout(() => setMessage(''), 3000)
    } catch {
      setMessage('Unable to update role visibility.')
      setTimeout(() => setMessage(''), 3000)
    }
  }

  const filteredRoles = roles.filter((role) =>
    (role.role_name || '').toLowerCase().includes(searchTerm.toLowerCase())
  )
  const keywords = roleDetail?.keywords || []
  const isRoleOpen = roleDetail?.role?.is_open !== 0 && roleDetail?.role?.is_open !== false
  const currentRoleName = roleDetail?.role?.role_name || ''

  const handleAddSkillToDictionary = async () => {
    if (!newSkillInput.trim()) return
    const skills = newSkillInput
      .split(/[\n,]+/)
      .map((skill) => skill.trim())
      .filter(Boolean)
    if (!skills.length) return
    try {
      setAppendingSkills(true)
      await addSkillsToDictionary({ kind: dictionaryKind, skills })
      setNewSkillInput('')
      loadDictionary(dictionaryKind)
      setMessage('Skills added to dictionary successfully.')
      setTimeout(() => setMessage(''), 3000)
    } catch {
      setMessage('Unable to add skills.')
      setTimeout(() => setMessage(''), 3000)
    } finally {
      setAppendingSkills(false)
    }
  }

  const handleFetchSuggestions = async () => {
    try {
      setLoadingSuggestions(true)
      const res = await getSkillSuggestions({
        role: enrichmentRole || undefined,
        limit: 300,
        max_phrases: 120,
      })
      setEnrichmentResults(res.data.suggestions || [])
      setMessage('')
    } catch {
      setMessage('Unable to fetch suggestions.')
      setTimeout(() => setMessage(''), 3000)
      setEnrichmentResults([])
    } finally {
      setLoadingSuggestions(false)
    }
  }

  const handleAddSuggestion = async (skill) => {
    if (!skill) return
    try {
      await addSkillsToDictionary({ kind: dictionaryKind, skills: [skill] })
      loadDictionary(dictionaryKind)
      setMessage(`Added "${skill}" to ${dictionaryKind} dictionary.`)
      setTimeout(() => setMessage(''), 3000)
    } catch {
      setMessage('Unable to add suggestion.')
      setTimeout(() => setMessage(''), 3000)
    }
  }

  const handleSynonymSubmit = async (e) => {
    e.preventDefault()
    if (!synonymForm.token.trim() || !synonymForm.expands_to.trim()) {
      setMessage('Token and canonical value are required.')
      setTimeout(() => setMessage(''), 3000)
      return
    }
    try {
      setSynonymSaving(true)
      if (editingSynonymId) {
        await updateSynonymApi(editingSynonymId, {
          token: synonymForm.token.trim(),
          expands_to: synonymForm.expands_to.trim(),
          category: synonymForm.category,
        })
      } else {
        await createSynonymApi({
          token: synonymForm.token.trim(),
          expands_to: synonymForm.expands_to.trim(),
          category: synonymForm.category,
        })
      }
      setSynonymForm({ token: '', expands_to: '', category: 'skill' })
      setEditingSynonymId(null)
      loadSynonyms()
      setMessage('Synonym saved successfully.')
      setTimeout(() => setMessage(''), 3000)
    } catch {
      setMessage('Unable to save synonym.')
      setTimeout(() => setMessage(''), 3000)
    } finally {
      setSynonymSaving(false)
    }
  }

  const handleSynonymDelete = async (id) => {
    if (!id) return
    try {
      await deleteSynonymApi(id)
      loadSynonyms()
      setMessage('Synonym deleted.')
      setTimeout(() => setMessage(''), 3000)
    } catch {
      setMessage('Unable to delete synonym.')
      setTimeout(() => setMessage(''), 3000)
    }
  }

  const handleTabChange = (nextTab) => {
    setActiveTab(nextTab)
    if (nextTab === 'skills' && !enrichmentRole && currentRoleName) {
      setEnrichmentRole(currentRoleName)
    }
  }

  return (
    <div className="roles-page">
      <div className="roles-layout">
        <aside className="roles-sidebar">
          <div className="roles-sidebar-header">
            <h3>HR Console</h3>
            <p>
              {activeTab === 'roles'
                ? 'Pick a role to manage its JD and keyword weighting.'
                : activeTab === 'skills'
                  ? 'Manage skill dictionaries and discover trending skills.'
                  : 'Manage synonym mappings used by the parser.'}
            </p>
          </div>
          <form className="new-role-form" onSubmit={handleCreateRole}>
            <h4>Add New Role</h4>
            <input
              type="text"
              placeholder="Role name (e.g., Senior Developer)"
              value={newRoleName}
              onChange={(e) => setNewRoleName(e.target.value)}
            />
            <textarea
              placeholder="Job description (optional)"
              value={newRoleJD}
              onChange={(e) => setNewRoleJD(e.target.value)}
            />
            <button type="submit" className="primary-btn" disabled={creatingRole}>
              {creatingRole ? 'Creating...' : 'Add Role'}
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
              <p className="muted">No roles match "{searchTerm}".</p>
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
                    <small className="muted"> · Closed</small>
                  ) : null}
                </div>
                <small>{new Date(role.updated_at).toLocaleDateString()}</small>
              </button>
            ))}
          </div>
        </aside>

        <div className="roles-content">
          <div className="roles-topbar">
            <div className="roles-tabs" role="tablist" aria-label="HR management tabs">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'roles'}
                className={`roles-tab ${activeTab === 'roles' ? 'active' : ''}`}
                onClick={() => handleTabChange('roles')}
              >
                Roles & JD
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'skills'}
                className={`roles-tab ${activeTab === 'skills' ? 'active' : ''}`}
                onClick={() => handleTabChange('skills')}
              >
                Skills Dictionary
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'synonyms'}
                className={`roles-tab ${activeTab === 'synonyms' ? 'active' : ''}`}
                onClick={() => handleTabChange('synonyms')}
              >
                Synonyms
              </button>
            </div>

            <div className="roles-metrics">
              <div className="roles-metric">
                <p className="muted">Total Roles</p>
                <strong>{roles.length}</strong>
              </div>
              <div className="roles-metric">
                <p className="muted">Open Roles</p>
                <strong>{roles.filter((role) => role.is_open !== 0 && role.is_open !== false).length}</strong>
              </div>
              <div className="roles-metric">
                <p className="muted">{dictionaryKind === 'hard' ? 'Hard' : 'Soft'} Skills</p>
                <strong>{dictionarySkills.length}</strong>
              </div>
              <div className="roles-metric">
                <p className="muted">Synonyms</p>
                <strong>{synonyms.length}</strong>
              </div>
            </div>
          </div>

          {message && <div className="roles-alert">{message}</div>}
          
          {activeTab !== 'roles' || roleDetail ? (
            <>
              {activeTab === 'roles' && roleDetail && (
                <>
                  <section className="card role-overview">
                    <div>
                      <p className="muted">Selected Role</p>
                      <h2>{roleDetail.role.role_name}</h2>
                    </div>
                    <div className="role-meta">
                      <label className="role-toggle">
                        <input
                          type="checkbox"
                          checked={isRoleOpen}
                          onChange={(e) => handleVisibilityChange(e.target.checked)}
                        />
                        <span>{isRoleOpen ? 'Accepting applications' : 'Closed to applications'}</span>
                      </label>
                      <div>
                        <p className="muted">Last Updated</p>
                        <strong>{new Date(roleDetail.role.updated_at).toLocaleDateString()}</strong>
                      </div>
                      <div>
                        <p className="muted">Keywords</p>
                        <strong>{keywords.length}</strong>
                      </div>
                    </div>
                  </section>

                  <section className="card">
                    <div className="section-header">
                      <div>
                        <h3>Job Description</h3>
                        <p>Keep your JD accurate for better automated matching</p>
                      </div>
                      <button className="primary-btn" onClick={handleSaveJD}>
                        Save JD
                      </button>
                    </div>
                    <textarea
                      value={jdText}
                      onChange={(e) => setJdText(e.target.value)}
                      placeholder="Describe the role expectations, required skills, and responsibilities..."
                    />
                  </section>

                  <section className="card">
                    <div className="section-header">
                      <div>
                        <h3>Keywords</h3>
                        <p>Importance and weight help the parser score candidates accurately</p>
                      </div>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Keyword</th>
                            <th>Importance</th>
                            <th>Weight</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {keywords.length === 0 && (
                            <tr>
                              <td colSpan={4} className="muted" style={{ textAlign: 'center', padding: '20px' }}>
                                No keywords defined yet. Add your first keyword below.
                              </td>
                            </tr>
                          )}
                          {keywords.map((kw) => (
                            <tr key={kw.id}>
                              <td><strong>{kw.keyword}</strong></td>
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
                        placeholder="Keyword (e.g., Python, React)"
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
                        placeholder="Weight"
                        value={keywordForm.weight}
                        onChange={(e) => setKeywordForm((prev) => ({ ...prev, weight: Number(e.target.value) }))}
                      />
                      <button className="primary-btn" onClick={handleKeywordSubmit}>
                        {editingKeywordId ? 'Update' : 'Add Keyword'}
                      </button>
                    </div>
                  </section>
                </>
              )}

              {activeTab === 'skills' && (
                <>
                  <section className="card">
                    <div className="section-header">
                      <div>
                        <h3>Skill Dictionaries</h3>
                        <p>Manage canonical hard/soft skills the parser matches against</p>
                      </div>
                      <div className="dictionary-toggle">
                        <button
                          type="button"
                          className={dictionaryKind === 'hard' ? 'chip active' : 'chip'}
                          onClick={() => setDictionaryKind('hard')}
                        >
                          Hard Skills
                        </button>
                        <button
                          type="button"
                          className={dictionaryKind === 'soft' ? 'chip active' : 'chip'}
                          onClick={() => setDictionaryKind('soft')}
                        >
                          Soft Skills
                        </button>
                      </div>
                    </div>
                    <div className="dictionary-panel">
                      <div className="dictionary-list">
                        <div className="dictionary-header">
                          <strong>{dictionaryKind === 'hard' ? 'Hard' : 'Soft'} Skills</strong>
                          <small>{dictionarySkills.length} entries</small>
                        </div>
                        <div className="dictionary-scroll">
                          {dictionaryLoading ? (
                            <p className="muted">Loading dictionary...</p>
                          ) : dictionarySkills.length === 0 ? (
                            <p className="muted">No skills found in dictionary.</p>
                          ) : (
                            dictionarySkills.map((skill) => (
                              <span key={skill} className="chip dictionary-chip">
                                {skill}
                              </span>
                            ))
                          )}
                        </div>
                      </div>
                      <div className="dictionary-form">
                        <textarea
                          placeholder="Add skills (comma or newline separated)&#10;Example: Python, JavaScript, React&#10;Machine Learning, Data Analysis"
                          value={newSkillInput}
                          onChange={(e) => setNewSkillInput(e.target.value)}
                        />
                        <button
                          type="button"
                          className="primary-btn"
                          onClick={handleAddSkillToDictionary}
                          disabled={appendingSkills}
                        >
                          {appendingSkills ? 'Adding...' : 'Add to Dictionary'}
                        </button>
                      </div>
                    </div>
                  </section>

                  <section className="card">
                    <div className="section-header">
                      <div>
                        <h3>Skill Enrichment</h3>
                        <p>Scan recent resumes to discover trending skills for roles</p>
                      </div>
                      <button
                        type="button"
                        className="primary-btn"
                        onClick={handleFetchSuggestions}
                        disabled={loadingSuggestions}
                      >
                        {loadingSuggestions ? 'Scanning...' : 'Find Suggestions'}
                      </button>
                    </div>
                    <div className="enrichment-controls">
                      <label>
                        Source Role
                        <select
                          value={enrichmentRole}
                          onChange={(e) => setEnrichmentRole(e.target.value)}
                        >
                          <option value="">All roles</option>
                          {roles.map((role) => (
                            <option key={role.id} value={role.role_name}>
                              {role.role_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <p className="muted">
                        Analyzes recent resumes to identify skills not yet in your dictionary
                      </p>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Skill</th>
                            <th>Documents</th>
                            <th>In JD</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {enrichmentResults.length === 0 ? (
                            <tr>
                              <td colSpan={4} className="muted" style={{ textAlign: 'center', padding: '20px' }}>
                                {loadingSuggestions ? 'Gathering suggestions...' : 'Click "Find Suggestions" to scan resumes'}
                              </td>
                            </tr>
                          ) : (
                            enrichmentResults.map((row) => (
                              <tr key={row.skill}>
                                <td>
                                  <strong>{row.skill}</strong>
                                  {row.example && <p className="muted" style={{ fontSize: '0.85rem', margin: '4px 0 0' }}>{row.example}</p>}
                                </td>
                                <td>{row.docs}</td>
                                <td>{row.in_jd ? 'Yes' : 'No'}</td>
                                <td className="action-cell">
                                  <button onClick={() => handleAddSuggestion(row.skill)}>Add</button>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </>
              )}
              
              {activeTab === 'synonyms' && (
                <section className="card">
                  <div className="section-header">
                    <div>
                      <h3>Synonym Mappings</h3>
                      <p>Map variants to canonical tokens for uniform parsing</p>
                    </div>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Token</th>
                          <th>Canonical</th>
                          <th>Category</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {synonymLoading ? (
                          <tr>
                            <td colSpan={4} className="muted" style={{ textAlign: 'center', padding: '20px' }}>
                              Loading synonyms...
                            </td>
                          </tr>
                        ) : synonyms.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="muted" style={{ textAlign: 'center', padding: '20px' }}>
                              No synonym mappings yet. Add your first mapping below.
                            </td>
                          </tr>
                        ) : (
                          synonyms.map((syn) => (
                            <tr key={syn.id}>
                              <td><strong>{syn.token}</strong></td>
                              <td>{syn.expands_to}</td>
                              <td>{syn.category}</td>
                              <td className="action-cell">
                                <button
                                  onClick={() => {
                                    setEditingSynonymId(syn.id)
                                    setSynonymForm({
                                      token: syn.token,
                                      expands_to: syn.expands_to,
                                      category: syn.category || 'skill',
                                    })
                                  }}
                                >
                                  Edit
                                </button>
                                <button className="danger" onClick={() => handleSynonymDelete(syn.id)}>
                                  Delete
                                </button>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                  <form className="synonym-form" onSubmit={handleSynonymSubmit}>
                    <input
                      type="text"
                      placeholder="Variant (e.g., ML Engineer)"
                      value={synonymForm.token}
                      onChange={(e) => setSynonymForm((prev) => ({ ...prev, token: e.target.value }))}
                    />
                    <input
                      type="text"
                      placeholder="Canonical (e.g., Machine Learning Engineer)"
                      value={synonymForm.expands_to}
                      onChange={(e) => setSynonymForm((prev) => ({ ...prev, expands_to: e.target.value }))}
                    />
                    <select
                      value={synonymForm.category}
                      onChange={(e) => setSynonymForm((prev) => ({ ...prev, category: e.target.value }))}
                    >
                      {SYNONYM_CATEGORIES.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <button type="submit" className="primary-btn" disabled={synonymSaving}>
                      {synonymSaving ? 'Saving...' : editingSynonymId ? 'Update' : 'Add Mapping'}
                    </button>
                    {editingSynonymId && (
                      <button
                        type="button"
                        className="danger-outline-btn subtle"
                        onClick={() => {
                          setEditingSynonymId(null)
                          setSynonymForm({ token: '', expands_to: '', category: 'skill' })
                        }}
                      >
                        Cancel
                      </button>
                    )}
                  </form>
                </section>
              )}
            </>
          ) : (
            <div className="empty-state card">
              <h3>Select a Role</h3>
              <p>Choose a role from the sidebar to manage JD and keyword settings</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}