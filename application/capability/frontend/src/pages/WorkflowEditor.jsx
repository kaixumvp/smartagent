import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Alert, Button, Dropdown, Input, Modal, Select, Tag, Typography, message,
} from 'antd'
import {
  ApartmentOutlined, ApiOutlined, CheckCircleOutlined, CloseOutlined, CloudUploadOutlined,
  DeleteOutlined, EyeOutlined, MoreOutlined, PlayCircleOutlined, PlusOutlined, SettingOutlined,
  ThunderboltOutlined, UserOutlined,
} from '@ant-design/icons'
import {
  getWorkflow, listTools, listWorkflowRuns, publishWorkflow, runWorkflow,
  saveWorkflowDraft, validateWorkflow,
} from '../api'
import './WorkflowEditor.css'

const { TextArea } = Input
const STARTER_DEFINITION = {
  schema_version: 1,
  input_schema: { type: 'object', properties: {}, additionalProperties: false },
  output_schema: { type: 'object', properties: {}, additionalProperties: true },
  nodes: [
    { id: 'start', type: 'start' },
    { id: 'end', type: 'end', output_mapping: {} },
  ],
  edges: [{ from: 'start', to: 'end' }],
}
const NODE_LABELS = {
  start: '开始', tool: 'MCP Tool', api: 'API Tool', condition: '条件',
  transform: '转换', human_input: '人工输入', approval: '人工审批', end: '结束',
}
const NODE_COLORS = {
  start: '#8b42df', tool: '#f52270', api: '#1677ff', condition: '#fa8c16',
  transform: '#16a34a', human_input: '#0ea5e9', approval: '#f59e0b', end: '#f04438',
}
const NODE_ICONS = {
  start: <ApartmentOutlined />, tool: <ThunderboltOutlined />, api: <ApiOutlined />,
  condition: <ApartmentOutlined />, transform: <ThunderboltOutlined />,
  human_input: <UserOutlined />, approval: <CheckCircleOutlined />, end: <CheckCircleOutlined />,
}

function arrangeNodes(nodes, edges) {
  const nodeIds = new Set(nodes.map((node) => node.id))
  const depth = new Map()
  const start = nodes.find((node) => node.type === 'start')
  if (start) depth.set(start.id, 0)

  for (let pass = 0; pass < nodes.length; pass += 1) {
    let changed = false
    for (const edge of edges) {
      if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to) || !depth.has(edge.from)) continue
      const nextDepth = depth.get(edge.from) + 1
      if (!depth.has(edge.to) || depth.get(edge.to) < nextDepth) {
        depth.set(edge.to, nextDepth)
        changed = true
      }
    }
    if (!changed) break
  }

  let nextDepth = Math.max(-1, ...depth.values()) + 1
  for (const node of nodes) {
    if (!depth.has(node.id)) {
      depth.set(node.id, nextDepth)
      nextDepth += 1
    }
  }

  const levels = new Map()
  for (const node of nodes) {
    const level = depth.get(node.id)
    if (!levels.has(level)) levels.set(level, [])
    levels.get(level).push(node)
  }
  return [...levels.entries()].sort(([left], [right]) => left - right).map(([level, items]) => ({
    level,
    nodes: items,
    edges: edges.filter((edge) => depth.get(edge.from) === level && depth.get(edge.to) > level),
  }))
}

function nodeDefaults(type, id) {
  if (type === 'condition') {
    return { id, type, branches: [{ id: 'yes', when: { op: 'equals', left: '$.input.value', right: true } }, { id: 'no', default: true }] }
  }
  if (type === 'human_input') {
    return { id, type, title: '补充信息', input_schema: { type: 'object', properties: {}, additionalProperties: false } }
  }
  if (type === 'approval') {
    return { id, type, title: '待审批', on_expire: 'fail' }
  }
  if (type === 'end') return { id, type, output_mapping: {} }
  if (type === 'transform') return { id, type, output_mapping: {} }
  if (type === 'tool' || type === 'api') return { id, type, tool_id: '', input_mapping: {} }
  return { id, type }
}

export default function WorkflowEditor() {
  const { id } = useParams()
  const [workflow, setWorkflow] = useState(null)
  const [definition, setDefinition] = useState(() => structuredClone(STARTER_DEFINITION))
  const [revision, setRevision] = useState(1)
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [nodeText, setNodeText] = useState('')
  const [argumentsText, setArgumentsText] = useState('{}')
  const [result, setResult] = useState(null)
  const [tools, setTools] = useState([])
  const [fromId, setFromId] = useState()
  const [toId, setToId] = useState()
  const [edgeBranch, setEdgeBranch] = useState('')
  const [jsonOpen, setJsonOpen] = useState(false)
  const [wholeJson, setWholeJson] = useState('')
  const [previewOpen, setPreviewOpen] = useState(false)
  const [controlsOpen, setControlsOpen] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [renameText, setRenameText] = useState('')
  const selectedNode = useMemo(
    () => definition?.nodes?.find((node) => node.id === selectedId),
    [definition, selectedId],
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [item, availableTools] = await Promise.all([getWorkflow(id), listTools()])
      setWorkflow(item)
      setDefinition(item.draft?.definition || item.active_version?.definition || structuredClone(STARTER_DEFINITION))
      setRevision(item.draft?.revision || 1)
      setTools(availableTools.filter((tool) => tool.enabled && tool.lifecycle_state === 'active' && ['mcp', 'api'].includes(tool.source)))
    } catch (error) {
      message.error(error?.response?.data?.detail || '加载 Workflow 失败')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])
  useEffect(() => { setNodeText(selectedNode ? JSON.stringify(selectedNode, null, 2) : '') }, [selectedNode])

  const refreshWorkflow = async (item) => {
    setWorkflow(item)
    if (item.draft) {
      setDefinition(item.draft.definition)
      setRevision(item.draft.revision)
    } else if (item.active_version) {
      setDefinition(item.active_version.definition)
      setRevision(1)
    }
  }

  const changeDefinition = (fn) => setDefinition((current) => fn(structuredClone(current)))

  const updateSelectedNode = (patch) => {
    if (!selectedNode) return
    const updated = { ...selectedNode, ...patch }
    setNodeText(JSON.stringify(updated, null, 2))
    changeDefinition((next) => {
      next.nodes = next.nodes.map((node) => node.id === selectedId ? updated : node)
      return next
    })
  }

  const beginRenameNode = (node) => {
    setSelectedId(node.id)
    setRenameText(node.title || node.display_name || NODE_LABELS[node.type] || node.id)
    setRenameOpen(true)
  }

  const renameSelectedNode = () => {
    const title = renameText.trim()
    if (!title || !selectedId) {
      message.warning('节点名称不能为空')
      return
    }
    changeDefinition((next) => {
      next.nodes = next.nodes.map((node) => node.id === selectedId ? { ...node, title } : node)
      return next
    })
    setNodeText((current) => {
      try {
        return JSON.stringify({ ...JSON.parse(current), title }, null, 2)
      } catch {
        return current
      }
    })
    setRenameOpen(false)
  }

  const addNode = (type, edgeToInsert = null) => {
    if (type === 'start' && definition.nodes.some((node) => node.type === 'start')) {
      message.warning('Workflow 只能有一个开始节点')
      return
    }
    const base = type.replace('_', '')
    let index = 1
    while (definition.nodes.some((node) => node.id === `${base}_${index}`)) index += 1
    const node = nodeDefaults(type, `${base}_${index}`)
    let insertionEdge = edgeToInsert
    if (!insertionEdge && selectedId) {
      const outgoing = definition.edges.filter((edge) => edge.from === selectedId)
      if (outgoing.length === 1) insertionEdge = outgoing[0]
    }
    if (!insertionEdge) {
      const endNode = definition.nodes.find((item) => item.type === 'end')
      const incoming = endNode ? definition.edges.filter((edge) => edge.to === endNode.id) : []
      if (incoming.length === 1) insertionEdge = incoming[0]
    }
    changeDefinition((next) => {
      next.nodes.push(node)
      if (insertionEdge) {
        next.edges = next.edges.filter((edge) => !(
          edge.from === insertionEdge.from
          && edge.to === insertionEdge.to
          && edge.branch === insertionEdge.branch
        ))
        next.edges.push(
          { from: insertionEdge.from, to: node.id, ...(insertionEdge.branch ? { branch: insertionEdge.branch } : {}) },
          { from: node.id, to: insertionEdge.to },
        )
      }
      return next
    })
    setSelectedId(node.id)
  }

  const addEdge = () => {
    if (!fromId || !toId || fromId === toId) return
    const source = definition.nodes.find((node) => node.id === fromId)
    const edge = { from: fromId, to: toId }
    if (['condition', 'approval'].includes(source?.type) || (source?.type === 'human_input' && edgeBranch)) {
      if (!edgeBranch) {
        message.warning('该节点连线需要填写结果分支 ID')
        return
      }
      edge.branch = edgeBranch
    }
    changeDefinition((next) => {
      if (next.edges.some((item) => item.from === edge.from && item.to === edge.to && item.branch === edge.branch)) {
        message.warning('该连线已存在')
        return next
      }
      next.edges.push(edge)
      return next
    })
    setEdgeBranch('')
  }

  const saveSelectedNode = () => {
    let parsed
    try {
      parsed = JSON.parse(nodeText)
    } catch {
      message.error('节点配置必须是合法 JSON')
      return
    }
    if (parsed.id !== selectedId) {
      message.error('不能通过节点配置修改节点 ID')
      return
    }
    changeDefinition((next) => {
      next.nodes = next.nodes.map((node) => node.id === selectedId ? parsed : node)
      return next
    })
    message.success('节点配置已应用到草稿')
  }

  const save = async () => {
    try {
      const item = await saveWorkflowDraft(id, { definition, revision })
      await refreshWorkflow(item)
      message.success('草稿已保存')
      return true
    } catch (error) {
      message.error(error?.response?.data?.detail || '保存失败')
      return false
    }
  }

  const validate = async () => {
    if (await save()) {
      const response = await validateWorkflow(id)
      if (response.valid) message.success('Workflow 校验通过')
      else Modal.error({ title: 'Workflow 校验失败', content: response.errors.join('\n') })
    }
  }

  const publish = async () => {
    try {
      if (!(await save())) return
      const item = await publishWorkflow(id)
      await refreshWorkflow(item)
      message.success('Workflow 已发布并启用')
    } catch (error) {
      message.error(error?.response?.data?.detail || '发布失败')
    }
  }

  const testRun = async () => {
    let arguments_
    try {
      arguments_ = JSON.parse(argumentsText)
      if (!arguments_ || Array.isArray(arguments_) || typeof arguments_ !== 'object') throw new Error('object required')
    } catch {
      message.error('输入参数必须是 JSON 对象')
      return
    }
    try {
      if (!(await save())) return
      setResult(await runWorkflow(id, { arguments: arguments_ }))
    } catch (error) {
      message.error(error?.response?.data?.detail || '运行失败')
    }
  }

  const removeNode = (nodeId) => {
    changeDefinition((next) => {
      next.nodes = next.nodes.filter((node) => node.id !== nodeId)
      next.edges = next.edges.filter((edge) => edge.from !== nodeId && edge.to !== nodeId)
      return next
    })
    if (selectedId === nodeId) setSelectedId(null)
  }

  const edges = definition?.edges || []
  const nodes = definition?.nodes || []
  const flowLevels = useMemo(() => arrangeNodes(nodes, edges), [nodes, edges])
  const availableTools = tools.filter((tool) => selectedNode?.type === 'tool' ? tool.source === 'mcp' : tool.source === 'api')
  const menuItems = [
    { key: 'runs', label: '执行记录' },
    { key: 'json', label: '编辑完整 JSON' },
  ]

  const handleMenuClick = ({ key }) => {
    if (key === 'runs') {
      listWorkflowRuns(id).then((runs) => Modal.info({
        title: '最近执行',
        width: 760,
        content: <pre style={{ maxHeight: 500, overflow: 'auto' }}>{JSON.stringify(runs, null, 2)}</pre>,
      })).catch((error) => message.error(error?.response?.data?.detail || '加载执行记录失败'))
    } else {
      setWholeJson(JSON.stringify(definition, null, 2))
      setJsonOpen(true)
    }
  }

  const addableTypes = ['tool', 'api', 'condition', 'transform', 'human_input', 'approval', 'end']
  const renderNodeButton = (node, compact = false) => (
    <button
      key={node.id}
      type="button"
      className={`workflow-node${selectedId === node.id ? ' is-selected' : ''}${compact ? ' workflow-node-compact' : ''}`}
      onClick={(event) => {
        event.stopPropagation()
        setSelectedId(node.id)
      }}
      onDoubleClick={(event) => {
        event.stopPropagation()
        beginRenameNode(node)
      }}
      onContextMenu={(event) => {
        event.preventDefault()
        if (node.type !== 'start') removeNode(node.id)
      }}
      style={{ '--node-color': NODE_COLORS[node.type] || '#64748b' }}
    >
      <span className="workflow-node-icon">{NODE_ICONS[node.type] || <ThunderboltOutlined />}</span>
      <span className="workflow-node-copy">
        <strong>{node.title || node.display_name || NODE_LABELS[node.type] || node.type}</strong>
        <small>{node.id}{node.tool_id ? ` · ${tools.find((tool) => tool.id === node.tool_id)?.display_name || '已配置 Tool'}` : ''}</small>
      </span>
      <span className="workflow-node-actions">
        {node.type !== 'start' && (
          <span
            role="button"
            tabIndex={0}
            aria-label={`删除 ${node.id}`}
            onClick={(event) => { event.stopPropagation(); removeNode(node.id) }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.stopPropagation()
                removeNode(node.id)
              }
            }}
          ><DeleteOutlined /></span>
        )}
      </span>
    </button>
  )

  return (
    <div className="workflow-editor" aria-busy={loading}>
      <header className="workflow-toolbar">
        <div className="workflow-toolbar-title">
          <Input
            bordered={false}
            value={workflow?.display_name || ''}
            readOnly
            className="workflow-name-input"
            aria-label="Workflow 名称"
            placeholder={loading ? '正在加载 Workflow…' : 'Workflow'}
          />
          <Tag color={workflow?.enabled ? 'green' : 'default'}>
            {workflow?.enabled ? '已发布' : workflow?.draft ? `草稿 v${workflow.draft.version_no}` : '未发布'}
          </Tag>
        </div>
        <div className="workflow-toolbar-actions">
          <Dropdown menu={{ items: menuItems, onClick: handleMenuClick }} trigger={['click']}>
            <Button icon={<MoreOutlined />}>更多</Button>
          </Dropdown>
          <Button icon={<SettingOutlined />} onClick={() => { setWholeJson(JSON.stringify(definition, null, 2)); setJsonOpen(true) }}>设置</Button>
          <Button className="workflow-mobile-controls" icon={<ApartmentOutlined />} onClick={() => setControlsOpen((open) => !open)}>控件</Button>
          <Button icon={<EyeOutlined />} onClick={() => setPreviewOpen(true)}>预览</Button>
          <Button type="primary" icon={<CloudUploadOutlined />} onClick={publish}>发布</Button>
        </div>
      </header>
      <div className="workflow-workspace">
        <aside className="workflow-steps-panel">
          <div className="workflow-panel-heading"><span>步骤</span><ApartmentOutlined /></div>
          <div className="workflow-steps-list">
            {nodes.map((node) => (
              <button
                type="button"
                key={node.id}
                className={`workflow-step-item${selectedId === node.id ? ' is-active' : ''}`}
                onClick={() => setSelectedId(node.id)}
              >
                <span className="workflow-step-dot" style={{ background: NODE_COLORS[node.type] }} />
                <span
                  title="双击修改名称"
                  onDoubleClick={(event) => { event.stopPropagation(); beginRenameNode(node) }}
                >{node.title || node.display_name || NODE_LABELS[node.type]} <small>{node.id}</small></span>
                {node.type !== 'start' && (
                  <span className="workflow-step-remove" onClick={(event) => { event.stopPropagation(); removeNode(node.id) }}><CloseOutlined /></span>
                )}
              </button>
            ))}
          </div>
          <Button type="primary" icon={<PlusOutlined />} block onClick={() => addNode('tool')}>添加步骤</Button>
          <div className="workflow-panel-footer">
            <Button block onClick={validate}>校验流程</Button>
            <Button block onClick={save}>保存草稿</Button>
          </div>
        </aside>

        <main className="workflow-canvas-panel">
          <div className="workflow-canvas-tools">
            <div className="workflow-mode-switch"><span>Form</span><span className="workflow-switch-dot" /><strong>Workflow</strong></div>
            <Typography.Text type="secondary">{nodes.length} 个步骤 · {edges.length} 条连线</Typography.Text>
          </div>
          <div
            className="workflow-canvas-scroll"
            onClick={(event) => {
              if (!event.target.closest('.workflow-node, .workflow-add-between, .workflow-edge-labels, .workflow-canvas-add')) {
                setSelectedId(null)
              }
            }}
          >
            <div className="workflow-canvas-grid">
              <div className="workflow-flow">
                {flowLevels.map((group, groupIndex) => (
                  <div className="workflow-flow-level" key={group.level}>
                    <div className="workflow-flow-row">
                      {group.nodes.map((node) => renderNodeButton(node, true))}
                    </div>
                    {groupIndex < flowLevels.length - 1 && (
                      <div className={`workflow-flow-connector${group.edges.length > 1 ? ' has-branches' : ''}`}>
                        <span className="workflow-connector-line" />
                        {group.edges.length > 0 && (
                          <div className="workflow-edge-labels">
                            {group.edges.map((edge, index) => (
                              <Tag
                                key={`${edge.from}-${edge.to}-${edge.branch || index}`}
                                closable
                                onClose={(event) => {
                                  event.preventDefault()
                                  changeDefinition((next) => {
                                    next.edges = next.edges.filter((item) => (
                                      item.from !== edge.from || item.to !== edge.to || item.branch !== edge.branch
                                    ))
                                    return next
                                  })
                                }}
                              >
                                {edge.branch || '下一步'} → {nodes.find((node) => node.id === edge.to)?.title || edge.to}
                              </Tag>
                            ))}
                          </div>
                        )}
                        <button
                          type="button"
                          className="workflow-add-between"
                          aria-label="添加步骤"
                          onClick={() => addNode('tool', group.edges.length === 1 ? group.edges[0] : null)}
                        >
                          <PlusOutlined />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                <div className="workflow-canvas-add">
                  <Button shape="circle" icon={<PlusOutlined />} onClick={() => addNode('tool')} aria-label="添加步骤" />
                </div>
              </div>
            </div>
          </div>
          <div className="workflow-canvas-footer">
            <Button size="small" onClick={() => { setWholeJson(JSON.stringify(definition, null, 2)); setJsonOpen(true) }}>编辑 JSON</Button>
            <Button size="small" icon={<CheckCircleOutlined />} onClick={validate}>校验</Button>
          </div>
        </main>

        <aside className={`workflow-controls-panel${controlsOpen ? ' is-open' : ''}`}>
          <div className="workflow-panel-heading">
            {selectedNode ? (
              <span>
                配置 ·{' '}
                <button
                  type="button"
                  className="workflow-rename-trigger"
                  title="双击修改节点名称"
                  onDoubleClick={() => beginRenameNode(selectedNode)}
                >{selectedNode.title || selectedNode.display_name || selectedNode.id}</button>
              </span>
            ) : '控件库'}
            <MoreOutlined />
          </div>
          {selectedNode ? (
            <div className="workflow-node-config">
              <label className="workflow-field">
                <span>画布显示名称</span>
                <Input
                  value={selectedNode.title || ''}
                  maxLength={100}
                  placeholder={NODE_LABELS[selectedNode.type] || selectedNode.type}
                  onChange={(event) => updateSelectedNode({ title: event.target.value })}
                />
              </label>
              {['tool', 'api'].includes(selectedNode.type) && (
                <>
                  <label className="workflow-field">
                    <span>工具类型</span>
                    <Select
                      value={selectedNode.type}
                      options={[
                        { value: 'tool', label: 'MCP Tool' },
                        { value: 'api', label: 'API Tool' },
                      ]}
                      onChange={(type) => {
                        updateSelectedNode({ type, tool_id: '' })
                      }}
                    />
                  </label>
                  <label className="workflow-field">
                    <span>选择 {selectedNode.type === 'tool' ? 'MCP Tool' : 'API Tool'}</span>
                    <Select
                      showSearch
                      optionFilterProp="label"
                      placeholder={`选择已启用的${selectedNode.type === 'tool' ? 'MCP' : 'API'} Tool`}
                      value={selectedNode.tool_id || undefined}
                      options={availableTools.map((tool) => ({
                        value: tool.id,
                        label: tool.remote_tool_name && tool.remote_tool_name !== tool.display_name
                          ? `${tool.display_name} · ${tool.remote_tool_name}`
                          : tool.display_name,
                      }))}
                      notFoundContent={`没有可用的${selectedNode.type === 'tool' ? 'MCP' : 'API'} Tool；请先在工具目录中启用`}
                      onChange={(toolId) => updateSelectedNode({ tool_id: toolId })}
                    />
                  </label>
                  <div className="workflow-mapping-preview">
                    <span>画布映射预览</span>
                    <strong>{selectedNode.title || NODE_LABELS[selectedNode.type]}</strong>
                    <small>
                      {selectedNode.type === 'tool' ? 'MCP Tool' : 'API Tool'} ·{' '}
                      {tools.find((tool) => tool.id === selectedNode.tool_id)?.display_name || '尚未绑定工具'}
                    </small>
                  </div>
                </>
              )}
              <Typography.Text type="secondary">节点配置（JSON）</Typography.Text>
              <Input.TextArea rows={16} value={nodeText} onChange={(event) => setNodeText(event.target.value)} className="workflow-json-input" />
              <Button type="primary" block onClick={saveSelectedNode}>应用节点配置</Button>
              <div className="workflow-config-divider" />
              <Typography.Text type="secondary">连线与判断</Typography.Text>
              <Select
                placeholder="起始步骤"
                value={fromId}
                onChange={setFromId}
                options={nodes.map((node) => ({ value: node.id, label: `${NODE_LABELS[node.type]} · ${node.id}` }))}
              />
              <Select
                placeholder="目标步骤"
                value={toId}
                onChange={setToId}
                options={nodes.map((node) => ({ value: node.id, label: `${NODE_LABELS[node.type]} · ${node.id}` }))}
              />
              <Input placeholder="分支 ID（可选）" value={edgeBranch} onChange={(event) => setEdgeBranch(event.target.value)} />
              <Button block onClick={addEdge}>添加连线</Button>
            </div>
          ) : (
            <div className="workflow-control-library">
              <Typography.Text type="secondary">流程节点</Typography.Text>
              {addableTypes.map((type) => (
                <Button
                  key={type}
                  block
                  disabled={type === 'end' && nodes.some((node) => node.type === 'end')}
                  icon={<span className="workflow-control-icon" style={{ color: NODE_COLORS[type] }}>{NODE_ICONS[type]}</span>}
                  onClick={() => addNode(type)}
                >{NODE_LABELS[type]}</Button>
              ))}
              <div className="workflow-config-divider" />
              <Typography.Text type="secondary">人工交互</Typography.Text>
              <Button block icon={<UserOutlined />} onClick={() => addNode('human_input')}>输入表单</Button>
              <Button block icon={<CheckCircleOutlined />} onClick={() => addNode('approval')}>审批节点</Button>
              <Alert
                type="info"
                showIcon
                message="选择画布节点以编辑参数、分支和输入 Schema。"
              />
            </div>
          )}
        </aside>
      </div>
      <Modal
        title="编辑 Workflow 定义 JSON"
        open={jsonOpen}
        width={900}
        onCancel={() => setJsonOpen(false)}
        onOk={() => {
          try {
            const parsed = JSON.parse(wholeJson)
            if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) throw new Error('nodes/edges must be arrays')
            setDefinition(parsed)
            setJsonOpen(false)
          } catch (error) {
            message.error(`Workflow JSON 无效：${error.message}`)
          }
        }}
      >
        <TextArea rows={28} value={wholeJson} onChange={(event) => setWholeJson(event.target.value)} style={{ fontFamily: 'monospace' }} />
      </Modal>
      <Modal
        title="预览并试运行"
        open={previewOpen}
        width={720}
        onCancel={() => setPreviewOpen(false)}
        footer={[
          <Button key="close" onClick={() => setPreviewOpen(false)}>关闭</Button>,
          <Button key="run" type="primary" icon={<PlayCircleOutlined />} onClick={testRun}>运行草稿</Button>,
        ]}
      >
        <Alert
          type="warning"
          showIcon
          message="试运行会真实调用已配置的 MCP/API Tool"
          description="下游写操作可能产生副作用，请使用安全的样例参数。"
          style={{ marginBottom: 12 }}
        />
        <Input.TextArea rows={8} value={argumentsText} onChange={(event) => setArgumentsText(event.target.value)} />
        {result && <pre className="workflow-run-result">{JSON.stringify(result, null, 2)}</pre>}
      </Modal>
      <Modal
        title="修改节点名称"
        open={renameOpen}
        onCancel={() => setRenameOpen(false)}
        onOk={renameSelectedNode}
        okText="确定"
        cancelText="取消"
      >
        <Input
          autoFocus
          maxLength={100}
          value={renameText}
          placeholder="输入节点显示名称"
          onChange={(event) => setRenameText(event.target.value)}
          onPressEnter={renameSelectedNode}
        />
        <Typography.Text type="secondary">只修改显示名称，节点 ID 和流程连线保持不变。</Typography.Text>
      </Modal>
    </div>
  )
}
