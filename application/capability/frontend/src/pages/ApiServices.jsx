import { useEffect, useState } from 'react'
import { Alert, Button, Checkbox, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag, message } from 'antd'
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
      auth_config: '',
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
        <Tag color={value === 'none' ? 'default' : service.has_authentication ? 'blue' : 'orange'}>
          {value === 'none' ? '无认证' : service.has_authentication ? value : `${value}（未配置）`}
        </Tag>
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
            extra={editing?.has_authentication ? '留空保留现有密钥；变更认证方式时需填写新配置。' : '示例：Bearer {"token":"..."}；API Key Header {"header_name":"X-API-Key","api_key":"..."}。'}
          >
            <Input.TextArea rows={4} placeholder='{"token":"..."}' autoComplete="off" />
          </Form.Item>
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
