import axios from 'axios'

const api = axios.create({ baseURL: './v1', timeout: 30000 })

export const errMsg = (e) =>
  e?.response?.data?.detail || e?.message || '请求失败，请稍后重试'

export const health = () => axios.get('./health', { timeout: 8000 }).then((r) => r.data)

export const listKnowledgeBases = () => api.get('/knowledge-bases').then((r) => r.data)
export const createKnowledgeBase = (name, description = '') =>
  api.post('/knowledge-bases', { name, description }).then((r) => r.data)
export const deleteKnowledgeBase = (kbId) =>
  api.delete(`/knowledge-bases/${kbId}`).then((r) => r.data)

export const listDocuments = (kbId) =>
  api.get(`/knowledge-bases/${kbId}/documents`).then((r) => r.data)
export const getDocument = (documentId) =>
  api.get(`/documents/${documentId}`).then((r) => r.data)
export const uploadDocument = (kbId, file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/knowledge-bases/${kbId}/documents`, form).then((r) => r.data)
}
export const deleteDocument = (documentId) =>
  api.delete(`/documents/${documentId}`).then((r) => r.data)
export const reingestDocument = (documentId) =>
  api.post(`/documents/${documentId}/reingest`).then((r) => r.data)
export const documentJobs = (documentId) =>
  api.get(`/documents/${documentId}/jobs`).then((r) => r.data)
export const downloadOriginalUrl = (documentId) => `./v1/documents/${documentId}/download`
export const downloadMarkdownUrl = (documentId) => `./v1/documents/${documentId}/markdown`

export const search = (body) => api.post('/search', body).then((r) => r.data)
export const processJobs = () => api.post('/jobs/process').then((r) => r.data)