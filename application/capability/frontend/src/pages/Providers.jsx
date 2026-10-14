import { useEffect, useState } from 'react'
import { Alert, Button, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, message } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, SyncOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  createProvider,
  deleteProvider,
  listProviders,
  syncProvider,
  updateProvider,
} from '../api'

const AUTH_TYPES = [
  { value: 'none', label: '无认证' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'api_key_header', label: 'API Key（Header）' },
  { value: 'api_key_query', label: 'API Key（Query）' },
  { value: 'custom_headers', label: '自定义 Headers' },
  { value: 'custom_query_params', label: '自定义 Query 参数' },
  { value: 'basic', label: 'Basic Auth' },
  { value: 'oauth2_client_credentials', label: 'OAuth 2.0 Client Credentials' },
]

const AUTH_LABELS = Object.fromEntries(AUTH_TYPES.map(({ value, label }) => [value, label]))

export default function Providers() {
  const navigate = useNavigate()
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [syncing, setSyncing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [form] = Form.useForm()
  const authType = Form.useWatch('auth_type', form)

  const load = async () => {
    setLoading(true)
    try {
      setData(await listProviders())
    } catch {
      message.error('加载失败，请确认后端已启动')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({
      auth_type: 'none',
      header_name: 'X-API-Key',
      parameter_name: 'key',
      client_auth_method: 'client_secret_basic',
      auth_headers: '',
      auth_query_params: '',
    })
    setOpen(true)
  }

  const openEdit = (provider) => {
    setEditing(provider)
    form.resetFields()
    form.setFieldsValue({
      name: provider.name,
      endpoint: provider.endpoint,
      auth_type: provider.auth_type || 'none',
      auth_headers: '',
      auth_query_params: '',
    })
    setOpen(true)
  }

  const onSave = async (values) => {
    const auth_config = {}
    const fieldsByType = {
      bearer: ['token'],
      api_key_header: ['header_name', 'api_key'],
      api_key_query: ['parameter_name', 'api_key'],
      basic: ['username', 'password'],
      oauth2_client_credentials: [
        'token_url',
        'client_id',
        'client_secret',
        'scope',
        'audience',
        'client_auth_method',
      ],
    }
    for (const field of fieldsByType[values.auth_type] || []) {
      if (values[field] !== undefined && values[field] !== '') auth_config[field] = values[field]
    }
    try {
      if (values.auth_type === 'custom_headers') {
        const headers = JSON.parse(values.auth_headers || '{}')
        if (Object.keys(headers).length > 0) auth_config.headers = headers
      } else if (values.auth_type === 'custom_query_params') {
        const queryParams = JSON.parse(values.auth_query_params || '{}')
        if (Object.keys(queryParams).length > 0) auth_config.query_params = queryParams
      }
    } catch {
      message.error('Headers / Query 参数必须是合法 JSON 对象')
      return
    }

    const payload = {
      name: values.name,
      endpoint: values.endpoint,
      auth_type: values.auth_type,
      auth_config,
    }
    try {
      if (editing) {
        await updateProvider(editing.id, payload)
        message.success('Provider 配置已更新')
      } else {
        await createProvider(payload)
        message.success('已连接')
      }
      setOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || (editing ? '更新失败' : '连接失败'))
    }
  }

  const onSync = async (id) => {
    setSyncing(id)
    try {
      const r = await syncProvider(id)
      message.success(`同步完成：${r.synced} 个 Tool，${r.missing} 个远端已删除`)
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '同步失败')
    } finally {
      setSyncing(null)
    }
  }

  const onDelete = async (id) => {
    setDeleting(id)
    try {
      await deleteProvider(id)
      message.success('MCP Provider 及其同步的 Tool 已删除')
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '删除失败')
    } finally {
      setDeleting(null)
    }
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 160, ellipsis: true },
    { title: 'Endpoint', dataIndex: 'endpoint', key: 'endpoint', width: 320, ellipsis: true },
    {
      title: '认证方式',
      dataIndex: 'auth_type',
      key: 'auth_type',
      width: 190,
      render: (v, r) =>
        v === 'none' || !v ? (
          <Tag>无认证</Tag>
        ) : (
          <Tag color={r.has_authentication ? 'blue' : 'orange'}>
            {r.has_authentication ? AUTH_LABELS[v] || v : `${AUTH_LABELS[v] || v}（未配置）`}
          </Tag>
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (v) =>
        v === 'online' ? <Tag color="green">online</Tag> : <Tag color="default">offline</Tag>,
    },
    {
      title: '最后同步',
      dataIndex: 'last_sync_at',
      key: 'last_sync_at',
      width: 190,
      ellipsis: true,
      render: (v) => (v ? new Date(v).toLocaleString() : '—'),
    },
    {
      title: '操作',
      key: 'action',
      width: 310,
      render: (_, r) => (
        <Space size={0} wrap={false}>
          <Button type="link" onClick={() => navigate(`/providers/${r.id}`)}>
            详情
          </Button>
          <Button
            type="link"
            icon={<SyncOutlined />}
            loading={syncing === r.id}
            onClick={() => onSync(r.id)}
          >
            Sync
          </Button>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => openEdit(r)}
          >
            配置认证
          </Button>
          <Popconfirm
            title="删除 MCP Provider？"
            description="该 Provider 同步的所有 Tool 也会被永久删除。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true, loading: deleting === r.id }}
            onConfirm={() => onDelete(r.id)}
          >
            <Button type="link" danger icon={<DeleteOutlined />} loading={deleting === r.id}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ minWidth: 0, width: '100%' }}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <h2 style={{ margin: 0 }}>MCP Providers</h2>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={openCreate}
          style={{ flexShrink: 0 }}
        >
          Connect
        </Button>
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        tableLayout="fixed"
        scroll={{ x: 1240 }}
      />

      <Modal
        title={editing ? `配置「${editing.name}」的 MCP 认证` : 'Connect MCP Server'}
        open={open}
        onCancel={() => {
          setOpen(false)
          setEditing(null)
          form.resetFields()
        }}
        onOk={() => form.submit()}
        okText={editing ? '保存' : '连接'}
      >
        {editing && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={`以下认证配置仅用于 MCP 服务「${editing.name}」，不会影响其他 Provider。`}
          />
        )}
        <Form form={form} layout="vertical" onFinish={onSave}>
          <Form.Item name="name" label="Name" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如 hr-mcp" />
          </Form.Item>
          <Form.Item
            name="endpoint"
            label="Endpoint"
            rules={[{ required: true, message: '必填' }]}
            extra="Docker Compose 后端连接宿主机服务时用 host.docker.internal；本地运行后端时用 localhost。"
          >
            <Input placeholder="https://example.com/mcp" />
          </Form.Item>
          <Form.Item name="auth_type" label="认证方式" rules={[{ required: true }]}>
            <Select options={AUTH_TYPES} />
          </Form.Item>
          {authType === 'bearer' && (
            <Form.Item name="token" label="Bearer Token" rules={[{ required: !editing }]}>
              <Input.Password placeholder={editing ? '留空则保留现有凭据' : '输入访问令牌'} />
            </Form.Item>
          )}
          {authType === 'api_key_header' && (
            <>
              <Form.Item
                name="header_name"
                label="Header 名称"
                rules={[{ required: !editing || editing.auth_type !== 'api_key_header' }]}
              >
                <Input placeholder="X-API-Key" />
              </Form.Item>
              <Form.Item name="api_key" label="API Key" rules={[{ required: !editing }]}>
                <Input.Password placeholder={editing ? '留空则保留现有 Key' : '输入 API Key'} />
              </Form.Item>
            </>
          )}
          {authType === 'api_key_query' && (
            <>
              <Form.Item
                name="parameter_name"
                label="Query 参数名"
                rules={[{ required: !editing || editing.auth_type !== 'api_key_query' }]}
              >
                <Input placeholder="key" />
              </Form.Item>
              <Form.Item name="api_key" label="API Key" rules={[{ required: !editing }]}>
                <Input.Password placeholder={editing ? '留空则保留现有 Key' : '输入 API Key'} />
              </Form.Item>
            </>
          )}
          {authType === 'custom_headers' && (
            <Form.Item name="auth_headers" label="HTTP Headers（JSON 对象）">
              <Input.TextArea rows={4} placeholder={'{"X-API-Key":"..."}'} />
            </Form.Item>
          )}
          {authType === 'custom_query_params' && (
            <Form.Item name="auth_query_params" label="Query 参数（JSON 对象）">
              <Input.TextArea rows={4} placeholder={'{"key":"..."}'} />
            </Form.Item>
          )}
          {authType === 'basic' && (
            <>
              <Form.Item name="username" label="用户名" rules={[{ required: !editing }]}>
                <Input placeholder={editing ? '留空则保留现有用户名' : ''} />
              </Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: !editing }]}>
                <Input.Password placeholder={editing ? '留空则保留现有密码' : ''} />
              </Form.Item>
            </>
          )}
          {authType === 'oauth2_client_credentials' && (
            <>
              <Form.Item name="token_url" label="Token URL" rules={[{ required: !editing }]}>
                <Input placeholder="https://auth.example.com/oauth/token" />
              </Form.Item>
              <Form.Item name="client_id" label="Client ID" rules={[{ required: !editing }]}>
                <Input placeholder={editing ? '留空则保留现有 Client ID' : ''} />
              </Form.Item>
              <Form.Item name="client_secret" label="Client Secret" rules={[{ required: !editing }]}>
                <Input.Password placeholder={editing ? '留空则保留现有 Secret' : ''} />
              </Form.Item>
              <Form.Item name="scope" label="Scope">
                <Input placeholder="可选" />
              </Form.Item>
              <Form.Item name="audience" label="Audience">
                <Input placeholder="可选" />
              </Form.Item>
              <Form.Item name="client_auth_method" label="Client 认证位置">
                <Select
                  options={[
                    { value: 'client_secret_basic', label: 'Authorization Header' },
                    { value: 'client_secret_post', label: 'Form Body' },
                  ]}
                />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  )
}
