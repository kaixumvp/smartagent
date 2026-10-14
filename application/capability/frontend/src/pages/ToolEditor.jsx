import { useEffect, useState } from 'react'
import { Alert, Button, Checkbox, Collapse, Form, Input, Radio, Select, Space, Tabs, message } from 'antd'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { createApiTool, createTool, getTool, listApiServices, updateApiTool, updateTool } from '../api'

const { TextArea } = Input
const PARAMETER_TYPES = ['string', 'integer', 'number', 'boolean', 'object', 'array']

function parseJson(text, fallback = {}) {
  try {
    return text ? JSON.parse(text) : fallback
  } catch {
    return fallback
  }
}

function buildInputSchema(parameters = []) {
  const properties = {}
  const required = []
  parameters.forEach((parameter) => {
    const name = parameter?.name?.trim()
    if (!name) return
    properties[name] = {
      type: PARAMETER_TYPES.includes(parameter.type) ? parameter.type : 'string',
      ...(parameter.description?.trim() ? { description: parameter.description.trim() } : {}),
    }
    if (parameter.required || parameter.location === 'path') required.push(name)
  })
  return { type: 'object', properties, ...(required.length ? { required } : {}) }
}

function buildRequestTemplates(parameters = [], values = {}) {
  const query = parseJson(values.query_template)
  const headers = parseJson(values.header_template)
  const body = parseJson(values.body_template, null)
  const generatedBody = {}

  parameters.forEach((parameter) => {
    const name = parameter?.name?.trim()
    if (!name) return
    const requestName = parameter.request_name?.trim() || name
    const reference = `$input.${name}`
    if (parameter.location === 'query') query[requestName] = reference
    if (parameter.location === 'header') headers[requestName] = reference
    if (parameter.location === 'body') generatedBody[requestName] = reference
  })

  return {
    query_template: query,
    header_template: headers,
    body_template: Object.keys(generatedBody).length
      ? { ...(body && typeof body === 'object' && !Array.isArray(body) ? body : {}), ...generatedBody }
      : body,
  }
}

function inferApiParameters(inputSchema, execution = {}) {
  const properties = inputSchema?.properties || {}
  const required = new Set(inputSchema?.required || [])
  const parameterLocations = new Map()
  const pathParameters = [...(execution.path || '').matchAll(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g)]
  pathParameters.forEach((match) => parameterLocations.set(match[1], { location: 'path', request_name: match[1] }))

  const recordReferences = (template, location, nested = false) => {
    if (!template || typeof template !== 'object' || Array.isArray(template)) return
    Object.entries(template).forEach(([requestName, value]) => {
      if (typeof value === 'string') {
        const match = value.match(/^\$input\.([A-Za-z_][A-Za-z0-9_]*)$/)
        if (match && properties[match[1]]) {
          parameterLocations.set(match[1], { location, request_name: nested ? match[1] : requestName })
        }
      } else if (location === 'body' && value && typeof value === 'object') {
        recordReferences(value, location, true)
      }
    })
  }
  recordReferences(execution.query_template, 'query')
  recordReferences(execution.header_template, 'header')
  recordReferences(execution.body_template, 'body')

  return Object.entries(properties).map(([name, definition]) => {
    const mapping = parameterLocations.get(name) || {}
    return {
      name,
      description: definition?.description || '',
      type: PARAMETER_TYPES.includes(definition?.type) ? definition.type : 'string',
      required: required.has(name) || mapping.location === 'path',
      location: mapping.location || 'body',
      request_name: mapping.request_name || name,
    }
  })
}

function buildManifest(values, source) {
  const apiTool = source === 'api'
  const inputSchema = apiTool
    ? buildInputSchema(values.api_parameters)
    : parseJson(values.input_schema)
  const requestTemplates = apiTool ? buildRequestTemplates(values.api_parameters, values) : {}
  const manifest = {
    identity: {
      name: values.display_name,
      display_name: values.display_name,
      version: values.version || '1.0.0',
    },
    provider: null,
    metadata: {
      description: values.description || '',
      owner: null,
      tags: values.tags || [],
      keywords: values.keywords || [],
    },
    discovery: { enabled: false, intents: [] },
    permission: null,
    contract: {
      input_schema: inputSchema,
      output_schema: parseJson(values.output_schema),
    },
  }
  if (apiTool) {
    manifest.provider = {
      kind: 'api_service',
      api_service_id: values.api_service_id || null,
    }
    manifest.execution = {
      kind: 'http',
      method: values.method || 'GET',
      path: values.path || '/',
      query_template: requestTemplates.query_template,
      header_template: requestTemplates.header_template,
      body_template: requestTemplates.body_template,
    }
  }
  return manifest
}

export default function ToolEditor() {
  const { id } = useParams()
  const isEdit = !!id
  const navigate = useNavigate()
  const location = useLocation()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [manifest, setManifest] = useState({})
  const [source, setSource] = useState(new URLSearchParams(location.search).get('source') === 'api' ? 'api' : 'local')
  const [apiServices, setApiServices] = useState([])
  const [loadingApiServices, setLoadingApiServices] = useState(true)

  const recompute = () => setManifest(buildManifest(form.getFieldsValue(true), source))

  useEffect(() => {
    listApiServices()
      .then(setApiServices)
      .catch(() => message.error('API 服务列表加载失败'))
      .finally(() => setLoadingApiServices(false))
  }, [])

  useEffect(() => {
    if (!isEdit) {
      const nextSource = new URLSearchParams(location.search).get('source') === 'api' ? 'api' : 'local'
      setSource(nextSource)
      if (nextSource === 'api') {
        form.setFieldsValue({
          api_parameters: [],
          input_schema: '',
          output_schema: '{}',
          query_template: '',
          header_template: '',
          body_template: '',
        })
        setManifest(buildManifest(form.getFieldsValue(true), nextSource))
      }
      return
    }
    ;(async () => {
      setLoading(true)
      try {
        const t = await getTool(id)
        const m = t.manifest || {}
        const nextSource = t.source === 'api' ? 'api' : 'local'
        setSource(nextSource)
        const initialValues = {
          display_name: t.display_name,
          description: t.description,
          lifecycle_state: t.lifecycle_state,
          version: m.identity?.version || '1.0.0',
          tags: m.metadata?.tags || [],
          keywords: m.metadata?.keywords || [],
          input_schema: JSON.stringify(m.contract?.input_schema || {}, null, 2),
          output_schema: JSON.stringify(m.contract?.output_schema || {}, null, 2),
          api_service_id: t.api_service_id,
          method: m.execution?.method || 'GET',
          path: m.execution?.path || '/',
          query_template: JSON.stringify(m.execution?.query_template || {}, null, 2),
          header_template: JSON.stringify(m.execution?.header_template || {}, null, 2),
          body_template: m.execution?.body_template === undefined ? '' : JSON.stringify(m.execution.body_template, null, 2),
          api_parameters: inferApiParameters(m.contract?.input_schema, m.execution),
        }
        form.setFieldsValue(initialValues)
        setManifest(buildManifest(initialValues, nextSource))
      } catch {
        message.error('加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [id, location.search])

  const onFinish = async (values) => {
    const apiTool = source === 'api'
    let input_schema
    let output_schema
    let requestTemplates = {}
    try {
      input_schema = apiTool
        ? buildInputSchema(values.api_parameters)
        : values.input_schema?.trim() ? JSON.parse(values.input_schema) : {}
      output_schema = values.output_schema?.trim() ? JSON.parse(values.output_schema) : {}
      if (apiTool) {
        requestTemplates = buildRequestTemplates(values.api_parameters, values)
        for (const field of ['query_template', 'header_template', 'body_template']) {
          if (values[field]?.trim()) {
            const parsed = JSON.parse(values[field])
            if (field === 'query_template' || field === 'header_template') {
              if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                throw new Error(`${field} 必须是 JSON 对象`)
              }
              const target = field === 'query_template' ? 'query_template' : 'header_template'
              requestTemplates[target] = { ...parsed, ...requestTemplates[target] }
            } else if (requestTemplates.body_template && typeof requestTemplates.body_template === 'object') {
              if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                throw new Error('Body 参数与高级模板合并时，高级模板必须是 JSON 对象')
              }
              requestTemplates.body_template = { ...parsed, ...requestTemplates.body_template }
            } else {
              requestTemplates.body_template = parsed
            }
          }
        }
      }
    } catch (error) {
      message.error(error.message || 'Contract 或 HTTP 映射不是合法 JSON')
      return
    }

    if (apiTool) {
      const parameters = values.api_parameters || []
      const names = parameters.map((parameter) => parameter.name?.trim()).filter(Boolean)
      if (new Set(names).size !== names.length) {
        message.error('参数名称不能重复')
        return
      }
      const pathParameters = [...(values.path || '').matchAll(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g)].map((match) => match[1])
      const pathNames = new Set(parameters.filter((parameter) => parameter.location === 'path').map((parameter) => parameter.name?.trim()))
      if (pathParameters.some((name) => !names.includes(name) || !pathNames.has(name))) {
        message.error('Path 中的每个 {参数} 都必须在参数列表中定义为 Path 参数')
        return
      }
      if (parameters.some((parameter) => parameter.location === 'path' && !pathParameters.includes(parameter.name?.trim()))) {
        message.error('标记为 Path 的参数必须出现在相对 Path 中，例如 /users/{user_id}')
        return
      }
      const requestKeys = parameters
        .filter((parameter) => parameter.location !== 'path')
        .map((parameter) => `${parameter.location}:${parameter.request_name?.trim() || parameter.name?.trim()}`)
      if (new Set(requestKeys).size !== requestKeys.length) {
        message.error('同一 HTTP 位置下的接口参数名不能重复')
        return
      }
      if (parameters.some((parameter) => parameter.location !== 'body' && ['object', 'array'].includes(parameter.type))) {
        message.error('object 和 array 类型仅支持放在 Body 中')
        return
      }
    }

    const payload = {
      display_name: values.display_name,
      description: values.description || '',
      lifecycle_state: values.lifecycle_state || 'draft',
      version: values.version || '1.0.0',
      tags: values.tags || [],
      keywords: values.keywords || [],
      input_schema,
      output_schema,
    }
    const apiPayload = {
      ...payload,
      api_service_id: values.api_service_id,
      method: values.method || 'GET',
      path: values.path || '/',
      query_template: requestTemplates.query_template || {},
      header_template: requestTemplates.header_template || {},
      body_template: requestTemplates.body_template,
    }

    try {
      if (source === 'api') {
        if (!apiPayload.api_service_id) {
          message.error('请选择 API 服务')
          return
        }
        if (isEdit) await updateApiTool(id, apiPayload)
        else await createApiTool(apiPayload)
      } else if (isEdit) await updateTool(id, payload)
      else await createTool(payload)
      message.success(isEdit ? '已保存' : '已创建')
      navigate('/')
    } catch (error) {
      message.error(error?.response?.data?.detail || error.message || '保存失败')
    }
  }

  const items = [
    {
      key: 'basic',
      label: 'Basic',
      children: (
        <>
          <Form.Item
            name="display_name"
            label="Display Name"
            rules={[{ required: true, message: '必填' }]}
          >
            <Input placeholder="展示名称" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <TextArea rows={3} placeholder="描述" />
          </Form.Item>
          <Form.Item name="lifecycle_state" label="状态" initialValue="draft">
            <Radio.Group>
              <Radio.Button value="draft">draft</Radio.Button>
              <Radio.Button value="active">active</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="version" label="Version" initialValue="1.0.0">
            <Input />
          </Form.Item>
          <Form.Item name="tags" label="Tags">
            <Select mode="tags" placeholder="回车添加标签" />
          </Form.Item>
          <Form.Item name="keywords" label="Keywords">
            <Select mode="tags" placeholder="回车添加关键词" />
          </Form.Item>
        </>
      ),
    },
    {
      key: 'contract',
      label: 'Contract',
      children: (
        <>
          {source === 'api' ? (
            <Alert
              type="success"
              showIcon
              message="input_schema 由 HTTP Request 参数自动生成"
              description={
                <pre style={{ margin: '8px 0 0', maxHeight: 240, overflow: 'auto' }}>
                  {JSON.stringify(buildInputSchema(form.getFieldValue('api_parameters')), null, 2)}
                </pre>
              }
            />
          ) : (
            <Form.Item name="input_schema" label="input_schema" extra="JSON Schema，输入参数定义">
              <TextArea rows={8} style={{ fontFamily: 'monospace' }} />
            </Form.Item>
          )}
          <Form.Item name="output_schema" label="output_schema" extra="JSON Schema，输出定义">
            <TextArea rows={8} style={{ fontFamily: 'monospace' }} />
          </Form.Item>
        </>
      ),
    },
    {
      key: 'manifest',
      label: 'Manifest',
      children: (
        <pre
          style={{
            background: '#0f172a',
            color: '#e2e8f0',
            padding: 16,
            borderRadius: 8,
            overflow: 'auto',
            maxHeight: 480,
          }}
        >
          {JSON.stringify(manifest, null, 2)}
        </pre>
      ),
    },
  ]
  if (source === 'api') {
    items.splice(1, 0, {
      key: 'request',
      label: 'HTTP Request',
      children: (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="Agent 只会看到下面定义的 Tool Schema；HTTP 地址、认证与请求映射由 Capability 后端处理。"
            description="添加参数并选择 Path、Query、Header 或 Body。Contract 的 input_schema 和下方 Manifest 会根据参数配置自动生成。"
          />
          {!loadingApiServices && apiServices.length === 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message="请先添加 API 服务"
              description="自定义接口工具需要绑定 API 服务的 Base URL 和认证配置。"
              action={<Button type="link" onClick={() => navigate('/api-services')}>添加 API 服务</Button>}
            />
          )}
          <Form.Item name="api_service_id" label="API Service" rules={[{ required: true, message: '请选择 API 服务' }]}>
            <Select
              placeholder="选择 API 服务"
              options={apiServices.map((service) => ({
                value: service.id,
                label: `${service.name} — ${service.base_url}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="method" label="HTTP Method" rules={[{ required: true }]}>
            <Select options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((method) => ({ value: method, label: method }))} />
          </Form.Item>
          <Form.Item name="path" label="相对 Path" rules={[{ required: true }]} extra="不能填写 host 或 query；将自动安全拼接到 API Service 的 Base URL。">
            <Input placeholder="/v1/weather/{city}" />
          </Form.Item>
          <Form.List name="api_parameters">
            {(fields, { add, remove }) => (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '20px 0 8px' }}>
                  <strong>接口参数</strong>
                  <Button
                    icon={<PlusOutlined />}
                    onClick={() => add({ name: '', description: '', type: 'string', required: false, location: 'query', request_name: '' })}
                  >
                    添加参数
                  </Button>
                </div>
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  {fields.map((field, index) => (
                    <div
                      key={field.key}
                      style={{
                        border: '1px solid #e5e7eb',
                        borderRadius: 8,
                        padding: 16,
                        background: '#fff',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <strong>参数 {index + 1}</strong>
                        <Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(field.name)}>删除</Button>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0 16px' }}>
                        <Form.Item
                          name={[field.name, 'name']}
                          label="参数名称"
                          rules={[
                            { required: true, message: '请输入参数名称' },
                            { pattern: /^[A-Za-z_][A-Za-z0-9_]*$/, message: '使用字母、数字、下划线，且不能以数字开头' },
                          ]}
                        >
                          <Input placeholder="例如 city" />
                        </Form.Item>
                        <Form.Item name={[field.name, 'type']} label="参数类型" rules={[{ required: true }]}>
                          <Select options={PARAMETER_TYPES.map((type) => ({ value: type, label: type }))} />
                        </Form.Item>
                        <Form.Item name={[field.name, 'location']} label="HTTP 位置" rules={[{ required: true }]}>
                          <Select
                            options={[
                              { value: 'path', label: 'Path 路径' },
                              { value: 'query', label: 'Query 查询参数' },
                              { value: 'header', label: 'Header 请求头' },
                              { value: 'body', label: 'Body 请求体' },
                            ]}
                            onChange={(location) => {
                              if (location === 'path') {
                                form.setFieldValue(['api_parameters', field.name, 'required'], true)
                              }
                            }}
                          />
                        </Form.Item>
                        <Form.Item
                          name={[field.name, 'request_name']}
                          label="接口参数名"
                          extra="留空时与参数名称相同"
                        >
                          <Input placeholder="例如 q / X-Region" />
                        </Form.Item>
                        <Form.Item
                          name={[field.name, 'description']}
                          label="参数说明"
                          style={{ gridColumn: '1 / -1' }}
                        >
                          <Input placeholder="告诉 Agent 该参数的用途" />
                        </Form.Item>
                        <Form.Item
                          noStyle
                          shouldUpdate={(previous, current) => (
                            previous.api_parameters?.[field.name]?.location
                            !== current.api_parameters?.[field.name]?.location
                          )}
                        >
                          {() => {
                            const isPath = form.getFieldValue(['api_parameters', field.name, 'location']) === 'path'
                            return (
                              <Form.Item
                                name={[field.name, 'required']}
                                valuePropName="checked"
                                style={{ marginBottom: 0 }}
                              >
                                <Checkbox disabled={isPath}>
                                  必填{isPath ? '（Path 参数必须提供）' : ''}
                                </Checkbox>
                              </Form.Item>
                            )
                          }}
                        </Form.Item>
                      </div>
                    </div>
                  ))}
                  {fields.length === 0 && (
                    <Alert type="warning" showIcon message="尚未定义接口参数" description="点击“添加参数”配置 Agent 可传入的字段。" />
                  )}
                </Space>
              </>
            )}
          </Form.List>
          <Collapse
            style={{ marginTop: 16 }}
            items={[{
              key: 'advanced',
              label: '高级：补充固定或复杂 HTTP 映射（可选）',
              children: (
                <>
                  <Form.Item name="query_template" label="额外 Query 映射（JSON）">
                    <TextArea rows={3} style={{ fontFamily: 'monospace' }} placeholder={'{"units":"metric"}'} />
                  </Form.Item>
                  <Form.Item name="header_template" label="额外 Header 映射（JSON）" extra="认证 Header 由 API Service 管理，不能覆盖 Authorization、Host 或 Cookie。">
                    <TextArea rows={3} style={{ fontFamily: 'monospace' }} placeholder={'{"X-Region":"west"}'} />
                  </Form.Item>
                  <Form.Item name="body_template" label="额外 Body 模板（JSON）" extra="复杂嵌套请求体可在此补充；参数表单中的 Body 字段会自动合并。">
                    <TextArea rows={5} style={{ fontFamily: 'monospace' }} placeholder={'{"options":{"units":"metric"}}'} />
                  </Form.Item>
                </>
              ),
            }]}
          />
        </>
      ),
    })
  }

  return (
    <div>
      <h2>{isEdit ? '编辑 Tool' : source === 'api' ? '新建自定义接口工具' : '新建 Tool'}</h2>
      <Form form={form} layout="vertical" onFinish={onFinish} onValuesChange={recompute}>
        <Tabs items={items} />
        <Space style={{ marginTop: 16 }}>
          <Button onClick={() => navigate('/')}>取消</Button>
          <Button type="primary" htmlType="submit" loading={loading}>
            {isEdit ? '保存' : '创建'}
          </Button>
        </Space>
      </Form>
    </div>
  )
}
