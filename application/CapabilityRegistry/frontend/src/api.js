import axios from 'axios'

const api = axios.create({ baseURL: '' })

export const listTools = (params) =>
  api.get('/tools', { params }).then((r) => r.data)

export const getTool = (id) => api.get(`/tools/${id}`).then((r) => r.data)

export const createTool = (data) => api.post('/tools', data).then((r) => r.data)

export const updateTool = (id, data) => api.put(`/tools/${id}`, data).then((r) => r.data)

export const deleteTool = (id) => api.delete(`/tools/${id}`)

export const listProviders = () => api.get('/providers').then((r) => r.data)

export const getProvider = (id) => api.get(`/providers/${id}`).then((r) => r.data)

export const createProvider = (data) => api.post('/providers', data).then((r) => r.data)

export const syncProvider = (id) => api.post(`/providers/${id}/sync`).then((r) => r.data)
