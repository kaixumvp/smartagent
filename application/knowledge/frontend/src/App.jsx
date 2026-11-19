import React, { useEffect, useState } from 'react'
import {
  Button,
  Card,
  Collapse,
  Empty,
  Input,
  InputNumber,
  Layout,
  List,
  message,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd'
import { DeleteOutlined, InboxOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import {
  createKnowledgeBase,
  deleteDocument,
  listDocuments,
  listKnowledgeBases,
  processJobs,
  reingestDocument,
  search,
  uploadDocument,
} from './api.js'

const { Header, Content } = Layout

const STATUS_COLOR = {
  pending: 'default',
  processing: 'processing',
  ready: 'success',
  failed: 'error',
}

function KnowledgeTab() {
  const [kbs, setKbs] = useState([])
  const [kbId, setKbId] = useState(null)
  const [docs, setDocs] = useState([])
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)

  const refreshKBs = async () => setKbs(await listKnowledgeBases())
  const refreshDocs = async (id) => {
    if (!id) return
    setLoading(true)
    try {
      setDocs(await listDocuments(id))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshKBs()
  }, [])

  useEffect(() => {
    refreshDocs(kbId)
  }, [kbId])

  const onCreate = async () => {
    if (!name.trim()) return
    try {
      const kb = await createKnowledgeBase(name.trim())
      setName('')
      await refreshKBs()
      setKbId(kb.id)
      message.success('知识库已创建')
    } catch (e) {
      console.error('createKnowledgeBase failed', e)
      message.error(e?.response?.data?.detail || e?.message || '创建知识库失败')
    }
  }

  const onUpload = async ({ file, onSuccess, onError }) => {
    try {
      const doc = await uploadDocument(kbId, file)
      onSuccess(doc)
      message.success('已上传，等待处理')
      refreshDocs(kbId)
    } catch (e) {
      onError(e)
      message.error(e?.response?.data?.detail || '上传失败')
    }
  }

  const columns = [
    { title: '文件名', dataIndex: 'filename', key: 'filename' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (s) => <Tag color={STATUS_COLOR[s]}>{s}</Tag> },
    { title: '解析器', dataIndex: 'parser_name', key: 'parser_name' },
    { title: 'OCR', dataIndex: 'ocr_used', key: 'ocr_used', render: (v) => (v ? '是' : '否') },
    { title: '大小', dataIndex: 'size_bytes', key: 'size_bytes', render: (v) => `${(v / 1024).toFixed(1)} KB` },
    {
      title: '操作',
      key: 'actions',
      render: (_, doc) => (
        <Space>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => reingestDocument(doc.id).then(() => refreshDocs(kbId))}>
            重建索引
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteDocument(doc.id).then(() => refreshDocs(kbId))}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ display: 'flex', gap: 24 }}>
      <Card title="知识库" style={{ width: 280 }} size="small">
        <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
          <Input placeholder="新建知识库" value={name} onChange={(e) => setName(e.target.value)} onPressEnter={onCreate} />
          <Button type="primary" onClick={onCreate}>
            创建
          </Button>
        </Space.Compact>
        <List
          size="small"
          dataSource={kbs}
          renderItem={(kb) => (
            <List.Item
              onClick={() => setKbId(kb.id)}
              style={{ cursor: 'pointer', background: kb.id === kbId ? '#e6f4ff' : undefined, padding: '8px 12px' }}
            >
              {kb.name}
            </List.Item>
          )}
        />
      </Card>

      <Card
        title={kbId ? '文档' : '请选择知识库'}
        size="small"
        style={{ flex: 1 }}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => refreshDocs(kbId)}>
              刷新
            </Button>
            <Button onClick={async () => message.info(`已处理 ${(await processJobs()).processed} 个作业`)}>处理队列</Button>
            {kbId && (
              <Upload customRequest={onUpload} showUploadList={false}>
                <Button type="primary" icon={<InboxOutlined />}>
                  上传文档
                </Button>
              </Upload>
            )}
          </Space>
        }
      >
        <Table rowKey="id" columns={columns} dataSource={docs} loading={loading} pagination={false} size="small" />
      </Card>
    </div>
  )
}

function SearchTab() {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('hybrid')
  const [rerank, setRerank] = useState(true)
  const [topK, setTopK] = useState(8)
  const [kbIds, setKbIds] = useState([])
  const [result, setResult] = useState(null)
  const [kbs, setKbs] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    listKnowledgeBases().then(setKbs)
  }, [])

  const onSearch = async () => {
    setLoading(true)
    try {
      setResult(await search({ query, kb_ids: kbIds, top_k: topK, rerank, mode }))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Space wrap>
        <Input.Search
          placeholder="输入查询，例如：Q3 营收"
          allowClear
          enterButton={<SearchOutlined />}
          style={{ width: 360 }}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onSearch={onSearch}
        />
        <Select
          mode="multiple"
          allowClear
          placeholder="限定知识库"
          style={{ minWidth: 200 }}
          value={kbIds}
          onChange={setKbIds}
          options={kbs.map((kb) => ({ label: kb.name, value: kb.id }))}
        />
        <Select
          value={mode}
          onChange={setMode}
          style={{ width: 140 }}
          options={[
            { label: 'Hybrid 融合', value: 'hybrid' },
            { label: '纯向量', value: 'vector' },
            { label: '纯关键词', value: 'keyword' },
          ]}
        />
        <span>
          重排 <Switch checked={rerank} onChange={setRerank} />
        </span>
        <span>
          Top-K <InputNumber min={1} max={50} value={topK} onChange={setTopK} />
        </span>
      </Space>

      {result && (
        <>
          <Typography.Text type="secondary">
            模式：{result.mode} · 意图：{result.analysis.strategy} · 重排：{result.rerank_applied ? '是' : '否'} · 命中：{result.chunks.length}
          </Typography.Text>
          {result.chunks.length === 0 ? (
            <Empty description="无结果" />
          ) : (
            <List
              dataSource={result.chunks}
              renderItem={(h) => (
                <List.Item>
                  <Card
                    size="small"
                    style={{ width: '100%' }}
                    title={`${h.filename}${h.heading_path ? ' · ' + h.heading_path : ''}`}
                    extra={<Typography.Text type="secondary">chars {h.start_offset}–{h.end_offset}</Typography.Text>}
                  >
                    <Typography.Paragraph style={{ marginBottom: 8 }}>{h.text}</Typography.Paragraph>
                    <Space size="large">
                      <Typography.Text type="secondary">dense {h.dense_score.toFixed(4)}</Typography.Text>
                      <Typography.Text type="secondary">sparse {h.sparse_score.toFixed(4)}</Typography.Text>
                      <Typography.Text type="secondary">fused {h.fused_score.toFixed(4)}</Typography.Text>
                      <Typography.Text type="secondary">rerank {h.rerank_score.toFixed(4)}</Typography.Text>
                    </Space>
                  </Card>
                </List.Item>
              )}
            />
          )}
          {result.context && (
            <Collapse
              items={[
                {
                  key: 'context',
                  label: '拼接上下文 (Context Builder)',
                  children: <pre style={{ whiteSpace: 'pre-wrap' }}>{result.context}</pre>,
                },
              ]}
            />
          )}
        </>
      )}
    </Space>
  )
}

export default function App() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center' }}>
        <Typography.Title level={4} style={{ color: '#fff', margin: 0 }}>
          Knowledge Hub
        </Typography.Title>
      </Header>
      <Content style={{ padding: 24 }}>
        <Tabs
          items={[
            { key: 'kb', label: '知识库 / 文档', children: <KnowledgeTab /> },
            { key: 'search', label: '检索', children: <SearchTab /> },
          ]}
        />
      </Content>
    </Layout>
  )
}
