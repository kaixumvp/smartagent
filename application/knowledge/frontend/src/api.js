import axios from 'axios'

const api = axios.create({ baseURL: '/v1' })

export const listKnowledgeBases = () => api.get('/knowledge-bases').then((r) => r.data)
export const createKnowledgeBase = (name) =>
  api.post('/knowledge-bases', { name, description: '' }).then((r) => r.data)
export const listDocuments = (kbId) =>
  api.get(`/knowledge-bases/${kbId}/documents`).then((r) => r.data)
export const uploadDocument = (kbId, file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/knowledge-bases/${kbId}/documents`, form).then((r) => r.data)
}
export const deleteDocument = (documentId) =>
  api.delete(`/documents/${documentId}`).then((r) => r.data)
export const reingestDocument = (documentId) =>
  api.post(`/documents/${documentId}/reingest`).then((r) => r.data)
export const search = (body) => api.post('/search', body).then((r) => r.data)
export const processJobs = () => api.post('/jobs/process').then((r) => r.data)
