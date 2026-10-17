import { useEffect, useState } from 'react'
import { Button, Card, Empty, Input, Modal, Space, Table, Tag, Typography, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { createWorkflow, listWorkflows } from '../api'

const initialDefinition = {
  schema_version: 1,
  input_schema: { type: 'object', properties: {}, additionalProperties: false },
  output_schema: { type: 'object', properties: {}, additionalProperties: true },
  nodes: [
    { id: 'start', type: 'start' },
    { id: 'end', type: 'end', output_mapping: {} },
  ],
  edges: [{ from: 'start', to: 'end' }],
}

export default function Workflows() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const validName = /^[a-zA-Z][a-zA-Z0-9_-]{0,99}$/.test(name)

  const load = async () => {
    setLoading(true)
    try {
      setItems(await listWorkflows())
    } catch (error) {
      message.error(error?.response?.data?.detail || '加载 Workflow 失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const create = async () => {
    try {
      const workflow = await createWorkflow({
        name,
        display_name: displayName,
        definition: initialDefinition,
      })
      setCreateOpen(false)
      navigate(`/workflows/${workflow.id}`)
    } catch (error) {
      message.error(error?.response?.data?.detail || '创建 Workflow 失败')
    }
  }

  const columns = [
    { title: '名称', dataIndex: 'display_name', key: 'display_name' },
    { title: '标识', dataIndex: 'name', key: 'name' },
    {
      title: '版本',
      key: 'version',
      render: (_, item) => item.active_version ? `v${item.active_version.version_no}` : '未发布',
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled) => <Tag color={enabled ? 'green' : 'default'}>{enabled ? '已启用' : '草稿/停用'}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, item) => <Button type="link" onClick={() => navigate(`/workflows/${item.id}`)}>编辑 / 执行</Button>,
    },
  ]

  return (
    <Card
      title="Workflows"
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建 Workflow</Button>}
    >
      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        locale={{ emptyText: <Empty description="尚未创建 Workflow" /> }}
        pagination={{ pageSize: 10 }}
      />
      <Modal
        title="新建 Workflow"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={create}
        okText="创建"
        okButtonProps={{ disabled: !validName || !displayName.trim() }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="显示名称" />
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="唯一标识，例如 order_fulfillment"
            status={name && !validName ? 'error' : undefined}
          />
          {name && !validName && (
            <Typography.Text type="danger">
              标识须以英文字母开头，且只能包含英文字母、数字、下划线和连字符（最多 100 位）。
            </Typography.Text>
          )}
        </Space>
      </Modal>
    </Card>
  )
}
