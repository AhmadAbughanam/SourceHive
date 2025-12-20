import { useEffect, useState } from 'react'
import { uploadResume, getRoles } from '../api/client'
import './UploadResume.css'

const STORAGE_KEY = 'sourcehive_upload_form'

export default function UploadResume() {
  const [file, setFile] = useState(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [selectedRole, setSelectedRole] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [roles, setRoles] = useState([])

  // Load saved form data from localStorage
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
      if (saved.firstName) setFirstName(saved.firstName)
      if (saved.lastName) setLastName(saved.lastName)
      if (saved.email) setEmail(saved.email)
      if (saved.phone) setPhone(saved.phone)
      if (saved.selectedRole) setSelectedRole(saved.selectedRole)
    } catch {
      /* ignore parse errors */
    }
  }, [])

  // Save form data to localStorage
  useEffect(() => {
    const payload = {
      firstName,
      lastName,
      email,
      phone,
      selectedRole,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  }, [firstName, lastName, email, phone, selectedRole])

  // Fetch available roles
  useEffect(() => {
    getRoles()
      .then((res) => {
        const fetched = res.data.roles || []
        setRoles(fetched)
        const openRoles = fetched.filter((role) => role.is_open !== 0 && role.is_open !== false)
        if ((!selectedRole || !openRoles.find((role) => role.role_name === selectedRole)) && openRoles.length) {
          setSelectedRole(openRoles[0].role_name)
        }
      })
      .catch(() => setRoles([]))
  }, [])

  const handleFileChange = (e) => {
    setFile(e.target.files[0])
    setError('')
    setSuccess(false)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (!file) {
      setError('Please select a resume file to upload')
      return
    }
    if (!selectedRole) {
      setError('Please select a role to apply for')
      return
    }

    setLoading(true)
    setError('')
    setSuccess(false)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('first_name', firstName)
      formData.append('last_name', lastName)
      formData.append('email', email)
      formData.append('phone', phone)
      formData.append('selected_role', selectedRole)

      const response = await uploadResume(formData)
      
      if (response.data.success) {
        setSuccess(true)
        setResult(response.data.data)
        setFile(null)
        // Reset file input
        const fileInput = document.querySelector('input[type="file"]')
        if (fileInput) fileInput.value = ''
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const openRoles = roles.filter((role) => role.is_open !== 0 && role.is_open !== false)

  return (
    <div className="upload-container">
      <h2>Upload Resume</h2>

      {openRoles.length === 0 && (
        <div className="upload-info">
          No open roles are currently available. Please contact HR or check back later.
        </div>
      )}
      
      <form onSubmit={handleSubmit} className="upload-form-card">
        <div className="form-row">
          <div className="form-group">
            <label>First Name</label>
            <input
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="John"
            />
          </div>

          <div className="form-group">
            <label>Last Name</label>
            <input
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Doe"
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="john.doe@example.com"
            />
          </div>

          <div className="form-group">
            <label>Phone</label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1 (555) 123-4567"
            />
          </div>
        </div>

        <div className="form-group required">
          <label>Role</label>
          <select
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value)}
            disabled={openRoles.length === 0}
            required
          >
            {openRoles.length === 0 && (
              <option value="">No open roles available</option>
            )}
            {openRoles.map((role) => (
              <option key={role.id} value={role.role_name}>
                {role.role_name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group required">
          <label>Resume File</label>
          <input
            type="file"
            accept=".pdf,.doc,.docx"
            onChange={handleFileChange}
            required
          />
          {file && <p className="file-name">{file.name}</p>}
        </div>

        <button type="submit" disabled={loading || openRoles.length === 0}>
          {loading ? 'Processing Resume...' : 'Upload & Process Resume'}
        </button>
      </form>

      {error && <div className="error-message">{error}</div>}
      
      {success && (
        <div className="success-message">
          <p>✅ Resume processed successfully!</p>
          <div className="result-summary">
            <h3>Parsed Information</h3>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  )
}