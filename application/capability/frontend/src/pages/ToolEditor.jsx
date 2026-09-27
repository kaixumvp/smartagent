import { useEffect, useState } from 'react'
import { Button, Form, Input, Radio, Select, Space, Tabs, message } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import { createTool, getTool, updateTool } from '../api'

const { TextArea } = Input

function buildManifest(values) {
  return {
    identity: {
      name: values.display_name,
      display_name: values.display_name,
      version: values.version || '1.0.0',
    },
    provider: null,
    metadata: {
      description: values.description || '',
      owner: null,
      tags: values.tags || [],
      keywords: values.keywords || [],
    },
    discovery: { enabled: false, intents: [] },
    permission: null,
    contract: {
      input_schema: safeParse(values.input_schema),
      output_schema: safeParse(values.output_schema),
    },
  }
}

function safeParse(text) {
  try {
    return text ? JSON.parse(text) : {}
  } catch {
    return {}
  }
}

export default function ToolEditor() {
  const { id } = useParams()
  const isEdit = !!id
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [manifest, setManifest] = useState({})

  const recompute = () => setManifest(buildManifest(form.getFieldsValue()))

  useEffect(() => {
    if (!isEdit) return
    ;(async () => {
      setLoading(true)
      try {
        const t = await getTool(id)
        const m = t.manifest || {}
        form.setFieldsValue({
          display_name: t.display_name,
          description: t.description,
          lifecycle_state: t.lifecycle_state,
          version: m.identity?.version || '1.0.0',
          tags: m.metadata?.tags || [],
          keywords: m.metadata?.keywords || [],
          input_schema: JSON.stringify(m.contract?.input_schema || {}, null, 2),
          output_schema: JSON.stringify(m.contract?.output_schema || {}, null, 2),
        })
        recompute()
      } catch {
        message.error('加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [id])

  const onFinish = async (values) => {
    let input_schema = {}
    let output_schema = {}
    if (values.input_schema) {
      try {
        input_schema = JSON.parse(values.input_schema)
      } catch {
        message.error('input_schema 不是合法 JSON')
        return
      }
    }
    if (values.output_schema) {
      try {
        output_schema = JSON.parse(values.output_schema)
      } catch {
        message.error('output_schema 不是合法 JSON')
        return
      }
    }

    const payload = {
      display_name: values.display_name,
      description: values.description || '',
      lifecycle_state: values.lifecycle_state || 'draft',
      version: values.version || '1.0.0',
      tags: values.tags || [],
      keywords: values.keywords || [],
      input_schema,
      output_schema,
    }

    try {
      if (isEdit) await updateTool(id, payload)
      else await createTool(payload)
      message.success(isEdit ? '已保存' : '已创建')
      navigate('/')
    } catch {
      message.error('保存失败')
    }
  }

  const items = [
    {
      key: 'basic',
      label: 'Basic',
      children: (
        <>
          <Form.Item
            name="display_name"
            label="Display Name"
            rules={[{ required: true, message: '必填' }]}
          >
            <Input placeholder="展示名称" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <TextArea rows={3} placeholder="描述" />
          </Form.Item>
          <Form.Item name="lifecycle_state" label="状态" initialValue="draft">
            <Radio.Group>
              <Radio.Button value="draft">draft</Radio.Button>
              <Radio.Button value="active">active</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="version" label="Version" initialValue="1.0.0">
            <Input />
          </Form.Item>
          <Form.Item name="tags" label="Tags">
            <Select mode="tags" placeholder="回车添加标签" />
          </Form.Item>
          <Form.Item name="keywords" label="Keywords">
            <Select mode="tags" placeholder="回车添加关键词" />
          </Form.Item>
        </>
      ),
    },
    {
      key: 'contract',
      label: 'Contract',
      children: (
        <>
          <Form.Item name="input_schema" label="input_schema" extra="JSON Schema，输入参数定义">
            <TextArea rows={8} style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="output_schema" label="output_schema" extra="JSON Schema，输出定义">
            <TextArea rows={8} style={{ fontFamily: 'monospace' }} />
          </Form.Item>
        </>
      ),
    },
    {
      key: 'manifest',
      label: 'Manifest',
      children: (
        <pre
          style={{
            background: '#0f172a',
            color: '#e2e8f0',
            padding: 16,
            borderRadius: 8,
            overflow: 'auto',
            maxHeight: 480,
          }}
        >
          {JSON.stringify(manifest, null, 2)}
        </pre>
      ),
    },
  ]

  return (
    <div>
      <h2>{isEdit ? '编辑 Tool' : '新建 Tool'}</h2>
      <Form form={form} layout="vertical" onFinish={onFinish} onValuesChange={recompute}>
        <Tabs items={items} />
        <Space style={{ marginTop: 16 }}>
          <Button onClick={() => navigate('/')}>取消</Button>
          <Button type="primary" htmlType="submit" loading={loading}>
            {isEdit ? '保存' : '创建'}
          </Button>
        </Space>
      </Form>
    </div>
  )
}
