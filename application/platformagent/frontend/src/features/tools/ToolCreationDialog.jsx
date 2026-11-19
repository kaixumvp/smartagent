import React, { useState } from 'react';

const EMPTY_PARAMETER = { name: '', type: 'string', description: '' };
const EMPTY_CONFIG = { key: '', value: '' };

export default function ToolCreationDialog({ open, api, onCreated, onClose, onNotice }) {
  const [name, setName] = useState('');
  const [type, setType] = useState('http');
  const [endpoint, setEndpoint] = useState('');
  const [description, setDescription] = useState('');
  const [permission, setPermission] = useState('read');
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [parameters, setParameters] = useState([EMPTY_PARAMETER]);
  const [config, setConfig] = useState([EMPTY_CONFIG]);
  const [creating, setCreating] = useState(false);

  function updateParameter(index, field, value) {
    setParameters((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, [field]: value } : item
    )));
  }

  function updateConfig(index, field, value) {
    setConfig((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, [field]: value } : item
    )));
  }

  async function createTool() {
    if (!name.trim()) {
      onNotice('请输入 Tool 名称');
      return;
    }
    const properties = {};
    const required = [];
    for (const parameter of parameters) {
      const key = parameter.name.trim();
      if (!key) continue;
      properties[key] = { type: parameter.type, description: parameter.description || '' };
      required.push(key);
    }
    const toolConfig = {};
    for (const item of config) {
      if (item.key.trim()) toolConfig[item.key.trim()] = item.value;
    }

    setCreating(true);
    try {
      const result = await api('/tools', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          type,
          endpoint: endpoint || undefined,
          parameters: { type: 'object', properties, required },
          description: description || '',
          permission,
          requires_approval: requiresApproval,
          config: toolConfig,
        }),
      });
      onCreated(result);
      setName('');
      setType('http');
      setEndpoint('');
      setDescription('');
      setPermission('read');
      setRequiresApproval(false);
    } catch (error) {
      onNotice(error.message || '创建 Tool 失败');
    } finally {
      setCreating(false);
    }
  }

  if (!open) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <h3>新建 Tool</h3>
        <label>名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="calculator" /></label>
        <label>类型
          <select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="builtin">builtin</option><option value="mcp">mcp</option><option value="http">http</option>
          </select>
        </label>
        <label>Endpoint (HTTP/MCP 可选)<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://..." /></label>
        <label>描述<input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="工具描述（可选）" /></label>
        <label>参数 Schema (JSON)
          <div className="kv-list">
            {parameters.map((parameter, index) => (
              <div className="kv-row" key={index}>
                <input placeholder="name" value={parameter.name} onChange={(event) => updateParameter(index, 'name', event.target.value)} />
                <select value={parameter.type} onChange={(event) => updateParameter(index, 'type', event.target.value)}>
                  <option value="string">string</option><option value="number">number</option>
                  <option value="boolean">boolean</option><option value="object">object</option>
                </select>
                <input placeholder="description" value={parameter.description} onChange={(event) => updateParameter(index, 'description', event.target.value)} />
                <button className="text-btn" type="button" onClick={() => setParameters((current) => current.filter((_, itemIndex) => itemIndex !== index))}>删除</button>
              </div>
            ))}
            <button className="text-btn" type="button" onClick={() => setParameters((current) => [...current, { ...EMPTY_PARAMETER }])}>添加参数</button>
          </div>
        </label>
        <label>Config (JSON，可用于 endpoint 的额外配置)
          <div className="kv-list">
            {config.map((item, index) => (
              <div className="kv-row" key={index}>
                <input placeholder="key" value={item.key} onChange={(event) => updateConfig(index, 'key', event.target.value)} />
                <input placeholder="value" value={item.value} onChange={(event) => updateConfig(index, 'value', event.target.value)} />
                <button className="text-btn" type="button" onClick={() => setConfig((current) => current.filter((_, itemIndex) => itemIndex !== index))}>删除</button>
              </div>
            ))}
            <button className="text-btn" type="button" onClick={() => setConfig((current) => [...current, { ...EMPTY_CONFIG }])}>添加配置项</button>
          </div>
        </label>
        <label>权限
          <select value={permission} onChange={(event) => setPermission(event.target.value)}>
            <option value="read">read</option><option value="write">write</option>
          </select>
        </label>
        <label className="checkbox"><input type="checkbox" checked={requiresApproval} onChange={(event) => setRequiresApproval(event.target.checked)} /> 需要审批</label>
        <div className="modal-actions">
          <button className="secondary-btn" onClick={onClose} disabled={creating}>取消</button>
          <button className="primary-btn" onClick={createTool} disabled={creating}>{creating ? '创建中...' : '创建'}</button>
        </div>
      </div>
    </div>
  );
}
