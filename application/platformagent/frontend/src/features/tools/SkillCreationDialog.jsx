import React, { useState } from 'react';

export default function SkillCreationDialog({ open, api, onCreated, onClose, onNotice }) {
  const [name, setName] = useState('');
  const [version, setVersion] = useState('1');
  const [type, setType] = useState('prompt');
  const [prompt, setPrompt] = useState('');
  const [functionModule, setFunctionModule] = useState('');
  const [functionName, setFunctionName] = useState('');
  const [definition, setDefinition] = useState('');
  const [creating, setCreating] = useState(false);

  async function createSkill() {
    if (!name.trim()) {
      onNotice('请输入 Skill 名称');
      return;
    }
    let body;
    if (type === 'prompt') {
      if (!prompt.trim()) {
        onNotice('Prompt 不能为空');
        return;
      }
      body = { prompt };
    } else if (type === 'function') {
      if (!functionModule.trim() || !functionName.trim()) {
        onNotice('请填写模块与函数名');
        return;
      }
      body = { module: functionModule.trim(), function: functionName.trim() };
    } else {
      body = { definition: definition || '' };
    }

    setCreating(true);
    try {
      const result = await api('/skills', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          version: version || '1',
          type,
          description: '',
          body,
          parameters: {},
        }),
      });
      onCreated(result);
      setName('');
      setVersion('1');
      setType('prompt');
      setPrompt('');
      setFunctionModule('');
      setFunctionName('');
      setDefinition('');
    } catch (error) {
      onNotice(error.message || '创建 Skill 失败');
    } finally {
      setCreating(false);
    }
  }

  if (!open) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <h3>新建 Skill</h3>
        <label>名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="skill_name" /></label>
        <label>版本<input value={version} onChange={(event) => setVersion(event.target.value)} placeholder="1" /></label>
        <label>类型
          <select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="prompt">prompt</option><option value="function">function</option>
            <option value="flow">flow</option><option value="agent">agent</option>
          </select>
        </label>
        <label>Body
          {type === 'prompt' && (
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={6} placeholder="Prompt 模板: 使用 {{input}} 引用输入" />
          )}
          {type === 'function' && (
            <div className="kv-list">
              <label>模块<input value={functionModule} onChange={(event) => setFunctionModule(event.target.value)} placeholder="module.path" /></label>
              <label>函数<input value={functionName} onChange={(event) => setFunctionName(event.target.value)} placeholder="function_name" /></label>
              <small>函数类型 Skill 会被注册并在运行时被调用。</small>
            </div>
          )}
          {['flow', 'agent'].includes(type) && (
            <textarea value={definition} onChange={(event) => setDefinition(event.target.value)} rows={6} placeholder="技能定义或说明（自由文本）" />
          )}
        </label>
        <div className="modal-actions">
          <button className="secondary-btn" onClick={onClose} disabled={creating}>取消</button>
          <button className="primary-btn" onClick={createSkill} disabled={creating}>{creating ? '创建中...' : '创建'}</button>
        </div>
      </div>
    </div>
  );
}
