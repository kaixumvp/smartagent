import { useEffect, useState } from 'react'
import { Button, Input, Popconfirm, Space, Table, Tag, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { deleteTool, listTools } from '../api'

export default function ToolCatalog() {
  const navigate = useNavigate()
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [q, setQ] = useState('')

  const load = async (query) => {
    setLoading(true)
    try {
      setData(await listTools(query ? { q: query } : {}))
    } catch {
      message.error('加载失败，请确认后端已启动')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(q)
  }, [q])

  const columns = [
    { title: '名称', dataIndex: 'display_name', key: 'display_name' },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      render: (v) => (v === 'mcp' ? <Tag color="blue">MCP</Tag> : <Tag>本地</Tag>),
    },
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
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v) => new Date(v).toLocaleString(),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, r) => (
        <Space>
          <Button type="link" onClick={() => navigate(`/edit/${r.id}`)}>编辑</Button>
          <Popconfirm
            title="确认删除该 Tool？"
            onConfirm={async () => {
              await deleteTool(r.id)
              message.success('已删除')
              load(q)
            }}
          >
            <Button type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Input.Search
          placeholder="搜索名称 / 描述"
          allowClear
          style={{ maxWidth: 320 }}
          onSearch={setQ}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/new')}>
          新建 Tool
        </Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={data} loading={loading} />
    </div>
  )
}
