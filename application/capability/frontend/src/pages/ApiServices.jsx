import { useEffect, useState } from 'react'
import { Alert, Button, Checkbox, Form, Input, InputNumber, Modal, Popconfirm, Popover, Select, Space, Table, Tag, message } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { createApiService, deleteApiService, listApiServices, updateApiService } from '../api'

const AUTH_TYPES = [
  { value: 'none', label: '无认证' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'api_key_header', label: 'API Key（Header）' },
  { value: 'api_key_query', label: 'API Key（Query）' },
  { value: 'basic', label: 'Basic Auth' },
  { value: 'custom_headers', label: '自定义 Headers' },
  { value: 'custom_query_params', label: '自定义 Query 参数' },
  { value: 'oauth2_client_credentials', label: 'OAuth 2.0 Client Credentials' },
]

// 这些键不能预填进 JSON：要么是元信息，要么是 <redacted> 占位——
// 一旦预填，用户顺手保存就会把占位符写成真实值。
const NON_DRAFT_SUMMARY_KEYS = [
  'auth_type', 'configured_secrets', 'token_hint', 'error', 'headers', 'query_params', 'secrets',
]

function buildAuthConfigDraft(summary) {
  if (!summary) return ''
  const draft = Object.fromEntries(
    Object.entries(summary).filter(([key]) => !NON_DRAFT_SUMMARY_KEYS.includes(key)),
  )
  return Object.keys(draft).length ? JSON.stringify(draft, null, 2) : ''
}

/** 认证配置回显：非敏感字段 + 密钥形态诊断，永不显示密钥明文。 */
function AuthSummary({ summary }) {
  if (!summary || Object.keys(summary).length === 0) {
    return <span style={{ color: '#8c8c8c' }}>未配置</span>
  }
  const configured = summary.configured_secrets || []
  const hint = summary.token_hint
  return (
    <div style={{ maxWidth: 320, lineHeight: 1.7 }}>
      {summary.error
        ? <div style={{ color: '#cf1322' }}>{summary.error}</div>
        : <div>已配置密钥字段：{configured.length ? configured.join('、') : '—'}</div>}
      {hint && (
        <div>
          token：{hint.length} 字符 · {hint.is_jwt ? 'JWT' : '非 JWT'}
          {hint.has_bearer_prefix ? ' · ⚠ 含 "Bearer " 前缀（保存时自动去除）' : ''}
          {hint.expires_at ? ` · 到期 ${new Date(hint.expires_at).toLocaleString()}` : ''}
        </div>
      )}
      {summary.token_endpoint && <div>自动获取：{summary.token_endpoint}</div>}
      {summary.header_name && <div>header_name：{summary.header_name}</div>}
      {summary.parameter_name && <div>parameter_name：{summary.parameter_name}</div>}
      {summary.token_url && <div>token_url：{summary.token_url}</div>}
      {summary.client_id && <div>client_id：{summary.client_id}</div>}
      <div style={{ color: '#8c8c8c' }}>密钥明文不通过接口返回；表单里留空即保留现有值。</div>
    </div>
  )
}

export default function ApiServices() {
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(null)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      setServices(await listApiServices())
    } catch {
      message.error('加载 API 服务失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openForm = (service = null) => {
    setEditing(service)
    form.resetFields()
    form.setFieldsValue(service ? {
      name: service.name,
      base_url: service.base_url,
      auth_type: service.auth_type || 'none',
      auth_config: buildAuthConfigDraft(service.auth_config_summary),
      allow_private_network: service.allow_private_network,
      request_timeout_seconds: service.request_timeout_seconds || 30,
      enabled: service.enabled,
    } : {
      auth_type: 'none',
      auth_config: '',
      allow_private_network: false,
      request_timeout_seconds: 30,
      enabled: true,
    })
    setOpen(true)
  }

  const onSave = async (values) => {
    let auth_config = {}
    if (values.auth_config?.trim()) {
      try {
        auth_config = JSON.parse(values.auth_config)
        if (!auth_config || Array.isArray(auth_config) || typeof auth_config !== 'object') throw new Error()
      } catch {
        message.error('认证配置必须是 JSON 对象')
        return
      }
    }
    // 从接口文档里复制整行 Authorization 是最常见的填错方式；后端也会兜底去除，这里先提示
    if (typeof auth_config.token === 'string' && /^\s*bearer\s+/i.test(auth_config.token)) {
      auth_config = { ...auth_config, token: auth_config.token.replace(/^\s*bearer\s+/i, '') }
      message.info('token 已自动去除 "Bearer " 前缀，只保留 token 本身')
    }
    const data = { ...values, auth_config }
    delete data.auth_config_text
    try {
      if (editing) await updateApiService(editing.id, data)
      else await createApiService(data)
      message.success(editing ? 'API 服务已更新' : 'API 服务已创建')
      setOpen(false)
      load()
    } catch (error) {
      message.error(error?.response?.data?.detail || '保存 API 服务失败')
    }
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 180, ellipsis: true },
    { title: 'Base URL', dataIndex: 'base_url', key: 'base_url', ellipsis: true },
    {
      title: '认证',
      dataIndex: 'auth_type',
      key: 'auth_type',
      width: 180,
      render: (value, service) => (
        <Popover
          title="认证配置（不回显明文）"
          content={<AuthSummary summary={service.auth_config_summary} />}
          placement="right"
        >
          <Tag color={value === 'none' ? 'default' : service.has_authentication ? 'blue' : 'orange'}>
            {value === 'none' ? '无认证' : service.has_authentication ? value : `${value}（未配置）`}
          </Tag>
        </Popover>
      ),
    },
    {
      title: '网络访问',
      dataIndex: 'allow_private_network',
      key: 'allow_private_network',
      width: 160,
      render: (value) => value ? <Tag color="orange">允许私网（可信目标）</Tag> : <Tag color="green">仅公网 HTTPS</Tag>,
    },
    { title: '超时', dataIndex: 'request_timeout_seconds', key: 'timeout', width: 90, render: (value) => `${value}s` },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 90,
      render: (value) => value ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_, service) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openForm(service)}>编辑</Button>
          <Popconfirm
            title="删除 API 服务？"
            description="该服务下配置的 API Tools 也会一并删除。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              try {
                await deleteApiService(service.id)
                message.success('API 服务及关联 Tools 已删除')
                load()
              } catch (error) {
                message.error(error?.response?.data?.detail || '删除失败')
              }
            }}
          >
            <Button type="link" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <div><h2 style={{ margin: 0 }}>API Services</h2><p style={{ margin: '6px 0 0', color: '#64748b' }}>管理 API Base URL 与加密保存的服务级认证凭据。</p></div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openForm()}>添加 API 服务</Button>
      </div>
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message="安全提示"
        description="默认仅允许访问公网 HTTPS 地址。仅对确认可信的内网服务开启私网访问；认证凭据由后端加密，读取接口不会返回明文。"
      />
      <Table rowKey="id" columns={columns} dataSource={services} loading={loading} scroll={{ x: 1150 }} />
      <Modal
        title={editing ? `编辑 API 服务：${editing.name}` : '添加 API 服务'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        okText="保存"
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={onSave}>
          <Form.Item name="name" label="服务名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如 weather-api" />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="Base URL"
            rules={[{ required: true, message: '请输入 Base URL' }]}
            extra="不要把 API Key 放在 URL 查询参数中；工具 path 应为相对路径，例如 /v1/weather。"
          >
            <Input placeholder="https://api.example.com" />
          </Form.Item>
          <Form.Item name="auth_type" label="认证方式" rules={[{ required: true }]}>
            <Select options={AUTH_TYPES} />
          </Form.Item>
          <Form.Item
            name="auth_config"
            label="认证配置（JSON）"
            extra={
              editing?.has_authentication
                ? '已预填非敏感字段；密钥留空即保留现有值，变更认证方式时需重新填写。'
                : '示例：Bearer {"token":"..."}；API Key Header {"header_name":"X-API-Key","api_key":"..."}。'
            }
          >
            <Input.TextArea rows={4} placeholder='{"token":"..."}' autoComplete="off" />
          </Form.Item>
          {editing?.has_authentication && (
            <Alert
              type={editing?.auth_config_summary?.token_hint?.has_bearer_prefix ? 'warning' : 'info'}
              showIcon
              style={{ marginBottom: 16 }}
              message="当前存储的凭据（不回显明文）"
              description={<AuthSummary summary={editing.auth_config_summary} />}
            />
          )}
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="Bearer token 填写说明"
            description={
              <>
                <div>
                  <code>token</code> 只填 token 本身，<b>不要带 <code>Bearer </code> 前缀</b>（带了会自动去除），也
                  不要带换行。
                </div>
                <div style={{ marginTop: 8 }}>
                  不想手工维护会过期的 token，可改为自动获取：
                  <code>{' {"token_endpoint":"https://.../token","token_body":{"grant_type":"client_credentials","client_id":"$secret.client_id","client_secret":"$secret.client_secret"},"secrets":{"client_id":"...","client_secret":"..."}} '}</code>
                  ，可选 <code>token_method</code>（GET/POST）、<code>token_content_type</code>（json/form）、
                  <code>token_headers</code>、<code>token_response_path</code>（默认 access_token）、
                  <code>token_expires_in_path</code>（默认 expires_in）。取到的 token 会缓存，过期自动重取。
                </div>
              </>
            }
          />
          <Form.Item name="request_timeout_seconds" label="请求超时（秒）" rules={[{ required: true }]}>
            <InputNumber min={1} max={120} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="allow_private_network" valuePropName="checked">
            <Checkbox>允许访问内网、localhost 与 HTTP 服务（只用于可信 API）</Checkbox>
          </Form.Item>
          <Form.Item name="enabled" valuePropName="checked">
            <Checkbox>启用此服务及其 API Tools</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
