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
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (!file) {
      setError('Please select a file')
      return
    }
    if (!selectedRole) {
      setError('Please select a role')
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
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="upload-container">
      <h2>Upload Resume</h2>
      
      <form onSubmit={handleSubmit}>
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

        <div className="form-group">
          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="john@example.com"
          />
        </div>

        <div className="form-group">
          <label>Phone</label>
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+1234567890"
          />
        </div>

        <div className="form-group">
          <label>Role</label>
          <select
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value)}
            disabled={roles.filter((role) => role.is_open !== 0 && role.is_open !== false).length === 0}
          >
            {roles.filter((role) => role.is_open !== 0 && role.is_open !== false).length === 0 && (
              <option value="">No open roles available</option>
            )}
            {roles
              .filter((role) => role.is_open !== 0 && role.is_open !== false)
              .map((role) => (
                <option key={role.id} value={role.role_name}>
                  {role.role_name}
                </option>
              ))}
          </select>
        </div>

        <div className="form-group">
          <label>Resume File (PDF)</label>
          <input
            type="file"
            accept=".pdf,.doc,.docx"
            onChange={handleFileChange}
          />
          {file && <p className="file-name">Selected: {file.name}</p>}
        </div>

        <button type="submit" disabled={loading}>
          {loading ? 'Processing...' : 'Upload & Process'}
        </button>
      </form>

      {error && <div className="error-message">{error}</div>}
      
      {success && (
        <div className="success-message">
          <p>✅ Resume processed successfully!</p>
          <div className="result-summary">
            <h3>Parsed Information:</h3>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  )
}
