import React, { useState } from 'react';

export default function AgentCreationDialog({
  open,
  api,
  tools,
  skills,
  providers,
  providerTools,
  onLoadProviderTools,
  onCreated,
  onClose,
  onNotice,
}) {
  const [name, setName] = useState('');
  const [version, setVersion] = useState('1');
  const [selectedTools, setSelectedTools] = useState([]);
  const [selectedSkills, setSelectedSkills] = useState([]);
  const [selectedApiTools, setSelectedApiTools] = useState([]);
  const [providerSelections, setProviderSelections] = useState({});
  const [creating, setCreating] = useState(false);

  async function toggleProvider(provider, enabled) {
    setProviderSelections((current) => ({
      ...current,
      [provider.id]: { ...current[provider.id], all: enabled },
    }));
    if (enabled && !providerTools[provider.id]) {
      try {
        await onLoadProviderTools(provider.id);
      } catch (error) {
        onNotice(`MCP Tools 加载失败：${error.message}`);
      }
    }
  }

  async function toggleProviderTool(provider, tool, checked) {
    try {
      if (!providerTools[provider.id]) await onLoadProviderTools(provider.id);
      setProviderSelections((current) => {
        const previous = current[provider.id] || { all: false, toolIds: [] };
        const toolIds = new Set(previous.toolIds || []);
        if (checked) toolIds.add(tool.id);
        else toolIds.delete(tool.id);
        return {
          ...current,
          [provider.id]: { ...previous, all: false, toolIds: [...toolIds] },
        };
      });
    } catch (error) {
      onNotice(`MCP Tools 加载失败：${error.message}`);
    }
  }

  async function createAgent() {
    if (!name.trim()) {
      onNotice('请输入 Agent 名称');
      return;
    }
    setCreating(true);
    try {
      const plugins = selectedTools.map((tool) => ({ type: 'tool', ref: `tool:${tool}` }));
      for (const [providerId, selection] of Object.entries(providerSelections)) {
        if (selection.all) {
          plugins.push({ type: 'capability_provider', ref: providerId });
        } else {
          for (const toolId of selection.toolIds || []) {
            plugins.push({ type: 'capability_tool', ref: `${providerId}/${toolId}` });
          }
        }
      }
      for (const toolId of selectedApiTools) {
        plugins.push({ type: 'capability_api_tool', ref: toolId });
      }
      for (const skill of selectedSkills) {
        const [skillName, skillVersion] = skill.split('@');
        plugins.push({ type: 'skill', ref: `skill:${skillName}@${skillVersion}` });
      }
      const result = await api('/agents', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          version: version || '1',
          config: { plugins },
        }),
      });
      onCreated(result);
      setName('');
      setVersion('1');
      setSelectedTools([]);
      setSelectedSkills([]);
      setSelectedApiTools([]);
      setProviderSelections({});
    } catch (error) {
      onNotice(error.message || '创建 Agent 失败');
    } finally {
      setCreating(false);
    }
  }

  if (!open) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <h3>新建 Agent</h3>
        <label>名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Agent 名称" /></label>
        <label>版本<input value={version} onChange={(event) => setVersion(event.target.value)} placeholder="1" /></label>
        <label>绑定工具（多选）
          <select multiple value={selectedTools} onChange={(event) => setSelectedTools(Array.from(event.target.selectedOptions, (option) => option.value))}>
            {tools.map((tool) => <option key={tool.id} value={tool.name}>{tool.name} ({tool.type})</option>)}
          </select>
        </label>
        <div className="capability-picker">
          <strong>Capability MCP</strong>
          <small>可绑定一个 Provider 的全部工具，或只选择该服务中的特定工具。</small>
          {providers.length === 0 && <small>没有可用 Provider；请先在 Capability Registry 同步 MCP Tools。</small>}
          {providers.map((provider) => {
            const selection = providerSelections[provider.id] || { all: false, toolIds: [] };
            const availableTools = providerTools[provider.id] || [];
            return (
              <div className="capability-provider" key={provider.id}>
                <div className="capability-provider-heading">
                  <span><b>{provider.name}</b><small>{provider.auth_type} · {provider.status}</small></span>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={!!selection.all}
                      onChange={(event) => toggleProvider(provider, event.target.checked)}
                    />
                    绑定整个 Provider
                  </label>
                </div>
                <div className="capability-tool-list">
                  {availableTools.length === 0
                    ? <small>暂无已同步且启用的 Tool</small>
                    : availableTools.map((tool) => (
                      <label className="checkbox" key={tool.id}>
                        <input
                          type="checkbox"
                          checked={!!selection.all || selection.toolIds?.includes(tool.id)}
                          disabled={!!selection.all}
                          onChange={(event) => toggleProviderTool(provider, tool, event.target.checked)}
                        />
                        <span>{tool.display_name || tool.name}</span>
                        <small>{tool.name}</small>
                      </label>
                    ))}
                </div>
                {availableTools.length === 0 && (
                  <button
                    type="button"
                    className="text-btn"
                    onClick={async () => {
                      try {
                        await onLoadProviderTools(provider.id);
                      } catch (error) {
                        onNotice(`MCP Tools 加载失败：${error.message}`);
                      }
                    }}
                  >
                    加载该 Provider 的 Tools
                  </button>
                )}
              </div>
            );
          })}
        </div>
        <div className="capability-picker">
          <strong>Capability API Tools</strong>
          <small>仅选择已启用的 API Tool；Agent 通过标准 Tool Schema 调用，不会收到 API 凭据或 HTTP 配置。</small>
          {apiTools.length === 0
            ? <small>暂无可用 API Tool，请先在 Capability Registry 创建并启用。</small>
            : <div className="capability-tool-list">
              {apiTools.map((tool) => (
                <label className="checkbox" key={tool.id}>
                  <input
                    type="checkbox"
                    checked={selectedApiTools.includes(tool.id)}
                    onChange={(event) => setSelectedApiTools((current) => (
                      event.target.checked
                        ? [...new Set([...current, tool.id])]
                        : current.filter((id) => id !== tool.id)
                    ))}
                  />
                  <span>{tool.display_name || tool.name}</span>
                  <small>{tool.service_name} · {tool.description}</small>
                </label>
              ))}
            </div>}
        </div>
        <label>绑定技能（多选，选择后会以 skill:name@version 引用）
          <select multiple value={selectedSkills} onChange={(event) => setSelectedSkills(Array.from(event.target.selectedOptions, (option) => option.value))}>
            {skills.map((skill) => <option key={skill.id} value={`${skill.name}@${skill.version}`}>{skill.name}@{skill.version} ({skill.type})</option>)}
          </select>
        </label>
        <div className="modal-actions">
          <button className="secondary-btn" onClick={onClose} disabled={creating}>取消</button>
          <button className="primary-btn" onClick={createAgent} disabled={creating}>
            {creating ? '创建中...' : '创建'}
          </button>
        </div>
      </div>
    </div>
  );
}
