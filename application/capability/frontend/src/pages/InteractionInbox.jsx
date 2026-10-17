import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Input, InputNumber, List, Radio, Space, Tag, Typography, message } from 'antd'
import { decideInteraction, listInteractions, submitInteraction } from '../api'

const { TextArea } = Input

export default function InteractionInbox() {
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(null)
  const [values, setValues] = useState({})
  const [comment, setComment] = useState('')
  const [decision, setDecision] = useState('approve')
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await listInteractions({ status: 'open' })
      setItems(data)
      setSelected((current) => current ? data.find((item) => item.id === current.id) || null : (data[0] || null))
    } catch (error) {
      message.error(error?.response?.data?.detail || '待办加载失败')
    }
  }, [])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [load])

  useEffect(() => {
    setValues({})
    setComment('')
    setDecision('approve')
  }, [selected?.id])

  const submit = async () => {
    if (!selected) return
    setLoading(true)
    try {
      const responseValues = { ...values }
      for (const [key, schema] of Object.entries(properties)) {
        if ((schema.type === 'object' || schema.type === 'array') && typeof responseValues[key] === 'string') {
          try {
            responseValues[key] = JSON.parse(responseValues[key])
          } catch {
            message.error(`${key} 必须是合法 JSON`)
            setLoading(false)
            return
          }
        }
      }
      const response = selected.kind === 'input'
        ? await submitInteraction(selected.id, { response: responseValues, comment, revision: selected.revision })
        : await decideInteraction(selected.id, { decision, comment, revision: selected.revision })
      message.success(response.status === 'succeeded' ? '流程已完成' : `已提交，流程状态：${response.status}`)
      setSelected(null)
      await load()
    } catch (error) {
      message.error(error?.response?.data?.detail || '提交待办失败')
      await load()
    } finally {
      setLoading(false)
    }
  }

  const properties = selected?.form_schema?.properties || {}

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 360px) minmax(0, 1fr)', gap: 16 }}>
      <Card title={`待办中心 (${items.length})`} extra={<Button onClick={load}>刷新</Button>}>
        <List
          dataSource={items}
          locale={{ emptyText: '没有待处理事项' }}
          renderItem={(item) => (
            <List.Item
              onClick={() => setSelected(item)}
              style={{ cursor: 'pointer', background: selected?.id === item.id ? '#e6f4ff' : undefined, padding: 12 }}
            >
              <List.Item.Meta
                title={<Space>{item.title}<Tag color={item.kind === 'approval' ? 'orange' : 'blue'}>{item.kind === 'approval' ? '审批' : '补充信息'}</Tag></Space>}
                description={`运行 ${item.workflow_run_id.slice(0, 8)} · 节点 ${item.node_id}${item.due_at ? ` · 截止 ${new Date(item.due_at).toLocaleString()}` : ''}`}
              />
            </List.Item>
          )}
        />
      </Card>
      <Card title={selected?.title || '选择待办'}>
        {selected ? (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Typography.Paragraph>{selected.prompt || '请根据流程信息处理此待办。'}</Typography.Paragraph>
            {Object.keys(selected.display_data || {}).length > 0 && (
              <Alert
                type="info"
                showIcon
                message="流程上下文"
                description={<pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(selected.display_data, null, 2)}</pre>}
              />
            )}
            {selected.kind === 'input' ? (
              Object.entries(properties).map(([key, schema]) => (
                <label key={key} style={{ display: 'block' }}>
                  <div style={{ marginBottom: 6 }}>{key}{selected.form_schema.required?.includes(key) ? ' *' : ''}{schema.description ? ` · ${schema.description}` : ''}</div>
                  {schema.enum ? (
                    <Radio.Group
                      value={values[key]}
                      options={schema.enum.map((value) => ({ label: String(value), value }))}
                      onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}
                    />
                  ) : schema.type === 'number' || schema.type === 'integer' ? (
                    <InputNumber
                      style={{ width: '100%' }}
                      precision={schema.type === 'integer' ? 0 : undefined}
                      value={values[key]}
                      min={schema.minimum}
                      max={schema.maximum}
                      onChange={(value) => setValues((current) => ({ ...current, [key]: value }))}
                    />
                  ) : schema.type === 'boolean' ? (
                    <Radio.Group
                      value={values[key]}
                      options={[{ label: '是', value: true }, { label: '否', value: false }]}
                      onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}
                    />
                  ) : schema.type === 'object' || schema.type === 'array' ? (
                    <TextArea
                      rows={4}
                      placeholder="输入合法 JSON"
                      value={typeof values[key] === 'string' ? values[key] : JSON.stringify(values[key] ?? (schema.type === 'array' ? [] : {}))}
                      onChange={(event) => {
                        const text = event.target.value
                        try {
                          setValues((current) => ({ ...current, [key]: JSON.parse(text) }))
                        } catch {
                          setValues((current) => ({ ...current, [key]: text }))
                        }
                      }}
                    />
                  ) : (
                    <Input
                      value={values[key]}
                      maxLength={schema.maxLength}
                      onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}
                    />
                  )}
                </label>
              ))
            ) : (
              <Radio.Group value={decision} onChange={(event) => setDecision(event.target.value)}>
                <Space direction="vertical">
                  <Radio value="approve">批准</Radio>
                  <Radio value="reject">拒绝</Radio>
                  <Radio value="return">退回补充</Radio>
                </Space>
              </Radio.Group>
            )}
            <div>
              <div style={{ marginBottom: 6 }}>说明（可选）</div>
              <TextArea rows={3} maxLength={4000} value={comment} onChange={(event) => setComment(event.target.value)} />
            </div>
            <Button type="primary" loading={loading} onClick={submit}>
              {selected.kind === 'approval' ? '提交审批决定' : '提交信息'}
            </Button>
          </Space>
        ) : <Typography.Text type="secondary">选择左侧待办以查看详情。</Typography.Text>}
      </Card>
    </div>
  )
}
