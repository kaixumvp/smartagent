import { useEffect, useState } from 'react'
import { Alert, Button, Input, Modal, Popconfirm, Space, Table, Tag, message } from 'antd'
import { ExperimentOutlined, PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { deleteTool, listTools, testApiTool, testTool } from '../api'

const { TextArea } = Input

export default function ToolCatalog() {
  const navigate = useNavigate()
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [q, setQ] = useState('')
  const [testingTool, setTestingTool] = useState(null)
  const [testArguments, setTestArguments] = useState('{}')
  const [testLoading, setTestLoading] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [testError, setTestError] = useState('')

  const openTest = (tool) => {
    setTestingTool(tool)
    setTestArguments('{}')
    setTestResult(null)
    setTestError('')
  }

  const runTest = async () => {
    let arguments_
    try {
      arguments_ = JSON.parse(testArguments)
    } catch {
      setTestError('参数必须是合法 JSON')
      return
    }
    if (!arguments_ || Array.isArray(arguments_) || typeof arguments_ !== 'object') {
      setTestError('参数必须是 JSON 对象')
      return
    }

    setTestLoading(true)
    setTestError('')
    setTestResult(null)
    try {
      setTestResult(await (testingTool.source === 'api'
        ? testApiTool(testingTool.id, arguments_)
        : testTool(testingTool.id, arguments_)))
    } catch (e) {
      const detail = e?.response?.data?.detail
      const status = e?.response?.status
      setTestError(detail ? `${detail}（HTTP ${status}）` : 'Tool 调用失败')
    } finally {
      setTestLoading(false)
    }
  }

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
    {
      title: '名称',
      dataIndex: 'display_name',
      key: 'display_name',
      width: 180,
      ellipsis: true,
    },
    {
      title: 'MCP 名称',
      key: 'mcp_name',
      width: 160,
      ellipsis: true,
      render: (_, tool) => tool.source === 'mcp'
        ? tool.manifest?.provider?.provider_name || '—'
        : '—',
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 90,
      render: (v) => (v === 'mcp'
        ? <Tag color="blue">MCP</Tag>
        : v === 'api' ? <Tag color="purple">API</Tag> : <Tag>本地</Tag>),
    },
    { title: '描述', dataIndex: 'description', key: 'description', width: 240, ellipsis: true },
    {
      title: '状态',
      dataIndex: 'lifecycle_state',
      key: 'lifecycle_state',
      width: 120,
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
      width: 190,
      ellipsis: true,
      render: (v) => new Date(v).toLocaleString(),
    },
    {
      title: '操作',
      key: 'action',
      width: 190,
      render: (_, r) => (
        <Space size={[4, 0]} wrap>
          {['mcp', 'api'].includes(r.source) && (
            <Button
              type="link"
              icon={<ExperimentOutlined />}
              disabled={r.lifecycle_state === 'remote_missing' || (r.source === 'api' && r.lifecycle_state !== 'active')}
              onClick={() => openTest(r)}
            >
              测试
            </Button>
          )}
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
        <Input.Search
          placeholder="搜索名称 / 描述"
          allowClear
          style={{ width: '100%', maxWidth: 320, minWidth: 180 }}
          onSearch={setQ}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate('/new')}
          style={{ flexShrink: 0 }}
        >
          新建 Tool
        </Button>
        <Button type="primary" ghost onClick={() => navigate('/new?source=api')} style={{ flexShrink: 0 }}>
          新建自定义接口工具
        </Button>
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        tableLayout="fixed"
        scroll={{ x: 1170 }}
      />

      <Modal
        title={`测试 Tool：${testingTool?.display_name || ''}`}
        open={!!testingTool}
        onCancel={() => setTestingTool(null)}
        onOk={runTest}
        okText="执行测试"
        cancelText="关闭"
        confirmLoading={testLoading}
        closable={!testLoading}
        maskClosable={!testLoading}
      >
        <Alert
          type="warning"
          showIcon
          message={`将真实调用远端 ${testingTool?.source === 'api' ? 'HTTP API' : 'MCP Tool'}`}
          description="远端操作可能产生实际副作用，请确认参数及目标环境后再执行。"
          style={{ marginBottom: 16 }}
        />
        <details style={{ marginBottom: 16 }}>
          <summary>查看输入 Schema</summary>
          <pre
            style={{
              background: '#f5f5f5',
              padding: 12,
              borderRadius: 6,
              overflow: 'auto',
              maxHeight: 240,
            }}
          >
            {JSON.stringify(testingTool?.manifest?.contract?.input_schema || {}, null, 2)}
          </pre>
        </details>
        <div style={{ marginBottom: 8 }}>调用参数（JSON Object）</div>
        <TextArea
          value={testArguments}
          onChange={(e) => setTestArguments(e.target.value)}
          rows={8}
          disabled={testLoading}
          style={{ fontFamily: 'monospace' }}
        />
        {testError && <Alert type="error" showIcon message={testError} style={{ marginTop: 16 }} />}
        {testResult && (
          <>
            <Alert
              type={testResult.isError ? 'error' : 'success'}
              showIcon
              message={testResult.isError
                ? (testingTool?.source === 'api' ? 'API 返回执行错误' : 'MCP Tool 返回执行错误')
                : '调用完成'}
              style={{ marginTop: 16 }}
            />
            <pre
              style={{
                background: '#0f172a',
                color: '#e2e8f0',
                padding: 12,
                borderRadius: 6,
                marginTop: 8,
                overflow: 'auto',
                maxHeight: 320,
              }}
            >
              {JSON.stringify(testResult, null, 2)}
            </pre>
          </>
        )}
      </Modal>
    </div>
  )
}
