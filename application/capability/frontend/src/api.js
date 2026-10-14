import axios from 'axios'

const api = axios.create({ baseURL: '' })

export const listTools = (params) =>
  api.get('/tools', { params }).then((r) => r.data)

export const getTool = (id) => api.get(`/tools/${id}`).then((r) => r.data)

export const createTool = (data) => api.post('/tools', data).then((r) => r.data)

export const updateTool = (id, data) => api.put(`/tools/${id}`, data).then((r) => r.data)

export const deleteTool = (id) => api.delete(`/tools/${id}`)

export const testTool = (id, arguments_) =>
  api.post(`/tools/${id}/test`, { arguments: arguments_ }).then((r) => r.data)

export const listApiServices = () => api.get('/api-services').then((r) => r.data)

export const createApiService = (data) => api.post('/api-services', data).then((r) => r.data)

export const updateApiService = (id, data) => api.put(`/api-services/${id}`, data).then((r) => r.data)

export const deleteApiService = (id) => api.delete(`/api-services/${id}`)

export const createApiTool = (data) => api.post('/api-tools', data).then((r) => r.data)

export const updateApiTool = (id, data) => api.put(`/api-tools/${id}`, data).then((r) => r.data)

export const testApiTool = (id, arguments_) =>
  api.post(`/api-tools/${id}/test`, { arguments: arguments_ }).then((r) => r.data)

export const listProviders = () => api.get('/providers').then((r) => r.data)

export const getProvider = (id) => api.get(`/providers/${id}`).then((r) => r.data)

export const createProvider = (data) => api.post('/providers', data).then((r) => r.data)

export const updateProvider = (id, data) => api.put(`/providers/${id}`, data).then((r) => r.data)

export const syncProvider = (id) => api.post(`/providers/${id}/sync`).then((r) => r.data)

export const deleteProvider = (id) => api.delete(`/providers/${id}`)
