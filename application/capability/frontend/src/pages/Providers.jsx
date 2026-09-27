import { useEffect, useState } from 'react'
import { Button, Form, Input, Modal, Space, Table, Tag, message } from 'antd'
import { PlusOutlined, SyncOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { createProvider, listProviders, syncProvider } from '../api'

export default function Providers() {
  const navigate = useNavigate()
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [syncing, setSyncing] = useState(null)
  const [form] = Form.useForm()

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

  const onConnect = async (values) => {
    try {
      await createProvider(values)
      message.success('已连接')
      setOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '连接失败')
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

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: 'Endpoint', dataIndex: 'endpoint', key: 'endpoint', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v) =>
        v === 'online' ? <Tag color="green">online</Tag> : <Tag color="default">offline</Tag>,
    },
    {
      title: '最后同步',
      dataIndex: 'last_sync_at',
      key: 'last_sync_at',
      render: (v) => (v ? new Date(v).toLocaleString() : '—'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, r) => (
        <Space>
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
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>MCP Providers</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          Connect
        </Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={data} loading={loading} />

      <Modal
        title="Connect MCP Server"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        okText="连接"
      >
        <Form form={form} layout="vertical" onFinish={onConnect}>
          <Form.Item name="name" label="Name" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如 hr-mcp" />
          </Form.Item>
          <Form.Item
            name="endpoint"
            label="Endpoint"
            rules={[{ required: true, message: '必填' }]}
          >
            <Input placeholder="http://localhost:9000/mcp" />
          </Form.Item>
          <Form.Item name="credential_ref" label="Credential Ref（可选）">
            <Input placeholder="密钥引用，不落明文" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
