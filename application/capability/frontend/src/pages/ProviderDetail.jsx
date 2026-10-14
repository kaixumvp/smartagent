import { useEffect, useState } from 'react'
import { Button, Descriptions, Popconfirm, Space, Table, Tag, message } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined, SyncOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { deleteProvider, getProvider, listTools, syncProvider } from '../api'

export default function ProviderDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [provider, setProvider] = useState(null)
  const [tools, setTools] = useState([])
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      setProvider(await getProvider(id))
      setTools(await listTools({ provider_id: id }))
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [id])

  const onSync = async () => {
    setSyncing(true)
    try {
      const r = await syncProvider(id)
      message.success(`同步完成：${r.synced} 个 Tool，${r.missing} 个远端已删除`)
      load()
    } catch (e) {
      message.error(e?.response?.data?.detail || '同步失败')
    } finally {
      setSyncing(false)
    }
  }

  const onDelete = async () => {
    setDeleting(true)
    try {
      await deleteProvider(id)
      message.success('MCP Provider 及其同步的 Tool 已删除')
      navigate('/providers')
    } catch (e) {
      message.error(e?.response?.data?.detail || '删除失败')
    } finally {
      setDeleting(false)
    }
  }

  const columns = [
    { title: '远端名称', dataIndex: 'remote_tool_name', key: 'remote_tool_name' },
    { title: '展示名', dataIndex: 'display_name', key: 'display_name' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'lifecycle_state',
      key: 'lifecycle_state',
      render: (v) => {
        if (v === 'active') return <Tag color="green">active</Tag>
        if (v === 'remote_missing') return <Tag color="red">remote_missing</Tag>
        return <Tag>draft</Tag>
      },
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (v) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/providers')}>
          返回
        </Button>
        <h2 style={{ margin: 0 }}>{provider?.name || 'Provider'}</h2>
      </Space>
      <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
        <Descriptions.Item label="Endpoint">{provider?.endpoint}</Descriptions.Item>
        <Descriptions.Item label="认证方式">
          {provider?.has_authentication ? (
            <Tag color="blue">{provider.auth_type}</Tag>
          ) : provider?.auth_type && provider.auth_type !== 'none' ? (
            <Tag color="orange">{provider.auth_type}（未配置）</Tag>
          ) : (
            <Tag>无认证</Tag>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          {provider?.status === 'online' ? <Tag color="green">online</Tag> : <Tag>offline</Tag>}
        </Descriptions.Item>
        <Descriptions.Item label="最后同步">
          {provider?.last_sync_at ? new Date(provider.last_sync_at).toLocaleString() : '—'}
        </Descriptions.Item>
        <Descriptions.Item label="Tool 数量">{tools.length}</Descriptions.Item>
      </Descriptions>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<SyncOutlined />} loading={syncing} onClick={onSync}>
          Sync
        </Button>
        <Popconfirm
          title="删除 MCP Provider？"
          description="该 Provider 同步的所有 Tool 也会被永久删除。"
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true, loading: deleting }}
          onConfirm={onDelete}
        >
          <Button danger icon={<DeleteOutlined />} loading={deleting}>
            删除 Provider
          </Button>
        </Popconfirm>
      </Space>
      <Table rowKey="id" columns={columns} dataSource={tools} loading={loading} />
    </div>
  )
}
