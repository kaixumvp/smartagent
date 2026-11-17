import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowUpRight, Bot, ChevronDown, ChevronLeft, ChevronRight, Globe2, MessageCircle, Plus, RefreshCw, Search, Send, Server, Sparkles, Wrench, X } from 'lucide-react';
import { MD_MODES } from '../../constants.js';
import MarkdownText, { isMdOverridden, resolveMdMode } from '../../components/MarkdownText.jsx';
import RunResultPanel from '../../components/RunResultPanel.jsx';
import Status from '../../components/RunStatus.jsx';
import { getAgentPlugins } from './agentPlugins.js';

function pluginLabel(plugin, tools, providers, providerTools, apiTools) {
  const kind = plugin.type || 'tool';
  const ref = plugin.ref || '';
  if (kind === 'capability_provider') {
    const provider = providers.find((item) => item.id === ref);
    const count = providerTools[ref]?.length;
    return { icon: <Server size={15} />, title: provider?.name || `MCP Provider ${ref}`, detail: `${count ?? '全部'} 个 Provider Tools` };
  }
  if (kind === 'capability_tool') {
    const [providerId, toolId] = ref.split('/');
    const provider = providers.find((item) => item.id === providerId);
    const tool = providerTools[providerId]?.find((item) => item.id === toolId);
    return { icon: <Server size={15} />, title: tool?.display_name || tool?.name || `MCP Tool ${toolId}`, detail: provider?.name || 'Capability MCP' };
  }
  if (kind === 'capability_api_tool') {
    const tool = apiTools.find((item) => item.id === ref);
    return { icon: <Globe2 size={15} />, title: tool?.display_name || tool?.name || `API Tool ${ref}`, detail: tool?.service_name || 'Capability API' };
  }
  if (kind === 'tool') {
    const name = ref.replace(/^tool:/, '');
    const tool = tools.find((item) => item.name === name || item.id === name);
    return { icon: <Wrench size={15} />, title: tool?.name || name, detail: tool?.type || 'Tool' };
  }
  return { icon: <Sparkles size={15} />, title: ref.replace(/^skill:/, ''), detail: 'Skill' };
}

const MCP_PROVIDER_PAGE_SIZE = 6;
const MCP_TOOL_PAGE_SIZE = 10;

// 只保留首尾页 + 当前页附近的页码，中间用省略号折叠，避免页码条过长。
function pagerWindow(page, pageCount) {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, index) => index + 1);
  const visible = [...new Set([1, pageCount, page, page - 1, page + 1])]
    .filter((item) => item >= 1 && item <= pageCount)
    .sort((a, b) => a - b);
  return visible.flatMap((item, index) => (index > 0 && item - visible[index - 1] > 1 ? ['…', item] : [item]));
}

function Pager({ page, pageCount, total, unit = '项', onChange }) {
  if (pageCount <= 1) return null;
  return <nav className="picker-pager" aria-label="分页">
    <button type="button" className="pager-step" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="上一页"><ChevronLeft size={13} /></button>
    {pagerWindow(page, pageCount).map((item, index) => item === '…'
      ? <span className="pager-gap" key={`gap-${index}`}>…</span>
      : <button
        type="button"
        key={item}
        className={`pager-page ${item === page ? 'active' : ''}`}
        aria-current={item === page ? 'page' : undefined}
        onClick={() => onChange(item)}
      >{item}</button>)}
    <button type="button" className="pager-step" disabled={page >= pageCount} onClick={() => onChange(page + 1)} aria-label="下一页"><ChevronRight size={13} /></button>
    <span className="pager-total">共 {total} {unit} · 第 {page}/{pageCount} 页</span>
  </nav>;
}

export default function AgentDetailDialog({
  agent, tools, providers, providerTools, apiTools, runs, messages, chatInput, chatBusy,
  saving, deleting, deletingRunId, selectedRun, setChatInput, mdMode, onClose, onUnbind,
  onDelete, onDeleteRun, onSend, onSelectRun, onAddPlugins, onLoadProviderTools,
  onSetMdMode, onSetMessageMdView,
}) {
  const chatMessagesRef = useRef(null);
  const [showCapabilityPicker, setShowCapabilityPicker] = useState(false);
  const [capabilityTab, setCapabilityTab] = useState('tools');
  const [capabilitySearch, setCapabilitySearch] = useState('');
  const [expandedMcpProviders, setExpandedMcpProviders] = useState({});
  const [mcpPage, setMcpPage] = useState(1);
  const [mcpToolPages, setMcpToolPages] = useState({});
  const [pendingPlugins, setPendingPlugins] = useState([]);
  const [loadingCapabilityTools, setLoadingCapabilityTools] = useState(false);
  const [capabilityLoadError, setCapabilityLoadError] = useState('');
  const plugins = getAgentPlugins(agent.config);
  useEffect(() => {
    const messagesElement = chatMessagesRef.current;
    if (messagesElement) messagesElement.scrollTop = messagesElement.scrollHeight;
  }, [messages, chatBusy]);
  // 搜索词或 Tab 变化后结果集会变，回到第一页避免停留在越界页码。
  useEffect(() => {
    setMcpPage(1);
    setMcpToolPages({});
  }, [capabilitySearch, capabilityTab]);

  const openCapabilityPicker = async () => {
    setPendingPlugins([]);
    setCapabilitySearch('');
    setCapabilityLoadError('');
    setMcpPage(1);
    setMcpToolPages({});
    setShowCapabilityPicker(true);
    if (providers.length === 0) return;
    setLoadingCapabilityTools(true);
    const results = await Promise.allSettled(providers.map((provider) => onLoadProviderTools(provider.id)));
    const failedCount = results.filter((result) => result.status === 'rejected').length;
    if (failedCount > 0) setCapabilityLoadError(`${failedCount} 个 MCP Provider 工具列表加载失败，可关闭窗口后重试。`);
    setLoadingCapabilityTools(false);
  };
  const isPending = (type, ref) => pendingPlugins.some((plugin) => plugin.type === type && plugin.ref === ref);
  const togglePlugin = (plugin, checked) => {
    setPendingPlugins((current) => {
      if (checked) {
        if (plugin.type === 'capability_provider') {
          const prefix = `${plugin.ref}/`;
          return [
            ...current.filter((item) => item.type !== 'capability_tool' || !item.ref.startsWith(prefix)),
            plugin,
          ];
        }
        if (plugin.type === 'capability_tool' && current.some((item) => (
          item.type === 'capability_provider' && plugin.ref.startsWith(`${item.ref}/`)
        ))) return current;
        return current.some((item) => item.type === plugin.type && item.ref === plugin.ref)
          ? current
          : [...current, plugin];
      }
      return current.filter((item) => !(item.type === plugin.type && item.ref === plugin.ref));
    });
  };
  const normalizedSearch = capabilitySearch.trim().toLocaleLowerCase();
  const filteredTools = tools.filter((tool) => (
    !normalizedSearch
    || tool.name?.toLocaleLowerCase().includes(normalizedSearch)
    || tool.description?.toLocaleLowerCase().includes(normalizedSearch)
    || tool.type?.toLocaleLowerCase().includes(normalizedSearch)
  ));
  const mcpProviders = providers.map((provider) => {
    const providerToolList = providerTools[provider.id] || [];
    const matchesProvider = !normalizedSearch
      || provider.name?.toLocaleLowerCase().includes(normalizedSearch)
      || provider.status?.toLocaleLowerCase().includes(normalizedSearch);
    const matchingTools = providerToolList.filter((tool) => (
      !normalizedSearch
      || matchesProvider
      || tool.name?.toLocaleLowerCase().includes(normalizedSearch)
      || tool.display_name?.toLocaleLowerCase().includes(normalizedSearch)
      || tool.description?.toLocaleLowerCase().includes(normalizedSearch)
    ));
    return { ...provider, providerToolList, matchingTools, matchesProvider };
  }).filter((provider) => provider.matchesProvider || provider.matchingTools.length > 0);
  const mcpPageCount = Math.max(1, Math.ceil(mcpProviders.length / MCP_PROVIDER_PAGE_SIZE));
  const safeMcpPage = Math.min(mcpPage, mcpPageCount);
  const pagedMcpProviders = mcpProviders.slice((safeMcpPage - 1) * MCP_PROVIDER_PAGE_SIZE, safeMcpPage * MCP_PROVIDER_PAGE_SIZE);
  const filteredApiTools = apiTools.filter((tool) => (
    !normalizedSearch
    || tool.name?.toLocaleLowerCase().includes(normalizedSearch)
    || tool.display_name?.toLocaleLowerCase().includes(normalizedSearch)
    || tool.description?.toLocaleLowerCase().includes(normalizedSearch)
    || tool.service_name?.toLocaleLowerCase().includes(normalizedSearch)
  ));

  return <>
    <div className="modal-backdrop agent-detail-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="agent-detail modal-card" role="dialog" aria-modal="true" aria-label={`${agent.name} 管理`}>
      <div className="agent-detail-header">
        <div><span className="section-kicker">AGENT WORKSPACE · {agent.version}</span><h2>{agent.name}</h2><p>模型：{agent.config?.model || '使用平台默认模型'}</p></div>
        <button className="icon-btn" onClick={onClose} aria-label="关闭"><X size={18} /></button>
      </div>
      <div className="agent-detail-columns">
        <div className="agent-detail-left">
          <section className="agent-detail-section">
            <div className="agent-detail-section-heading">
              <div><span className="section-kicker">BOUND CAPABILITIES</span><h3>绑定的 Tools 与 MCP</h3></div>
              <div className="capability-heading-actions">
                <span className="agent-count">{plugins.length}</span>
                <button type="button" className="add-capability-btn" onClick={openCapabilityPicker} disabled={saving}><Plus size={13} />添加</button>
              </div>
            </div>
            {plugins.length === 0
              ? <p className="agent-detail-empty">尚未绑定 Tool、MCP 或 Skill。</p>
              : <div className="bound-plugin-list">{plugins.map((plugin, index) => {
                const item = pluginLabel(plugin, tools, providers, providerTools, apiTools);
                return <div className="bound-plugin" key={`${plugin.type}-${plugin.ref}-${index}`}>
                  <span className="bound-plugin-icon">{item.icon}</span><span className="bound-plugin-copy"><strong>{item.title}</strong><small>{item.detail}</small></span>
                  <button className="text-btn danger-text" onClick={() => onUnbind(index)} disabled={saving} title={`解绑 ${item.title}`}><X size={14} />解绑</button>
                </div>;
              })}</div>}
          </section>
          <section className="agent-detail-section">
            <div className="agent-detail-section-heading"><div><span className="section-kicker">RECENT RUNS</span><h3>运行记录</h3></div><span className="agent-count">{runs.length}</span></div>
            {runs.length === 0
              ? <p className="agent-detail-empty">还没有运行记录，发送一条消息试运行。</p>
              : <div className="agent-run-list">{runs.map((run) => <div key={run.run_id} className={`agent-run-item ${selectedRun?.run_id === run.run_id ? 'selected' : ''}`}>
                <button type="button" className="agent-run-select" onClick={() => onSelectRun(run)}>
                  <span><strong>{run.input}</strong><small>{run.run_id}</small></span><Status status={run.status} />
                </button>
                <button
                  type="button"
                  className="agent-run-delete"
                  aria-label={`删除运行记录 ${run.run_id}`}
                  title={run.status === 'running' || run.status === 'awaiting_human' ? '运行中或待审批的记录不能删除' : '删除运行记录'}
                  disabled={deletingRunId === run.run_id || run.status === 'running' || run.status === 'awaiting_human'}
                  onClick={() => onDeleteRun(run)}
                >
                  {deletingRunId === run.run_id ? <RefreshCw className="spin" size={13} /> : <Trash2 size={13} />}
                </button>
              </div>)}</div>}
          </section>
          <button className="agent-delete-btn" onClick={onDelete} disabled={deleting}>{deleting ? <RefreshCw className="spin" size={15} /> : <Trash2 size={15} />}删除 Agent（保留历史记录）</button>
        </div>
        <div className="agent-detail-right">
          <div className="agent-chat-heading"><div><span className="section-kicker">PLAYGROUND</span><h3><MessageCircle size={17} />试运行与对话</h3></div><div className="agent-chat-heading-actions"><div className="md-mode-switch" role="group" aria-label="Markdown 显示方式"><button type="button" aria-pressed={mdMode === MD_MODES.formatted} className={mdMode === MD_MODES.formatted ? 'active' : ''} onClick={() => onSetMdMode(MD_MODES.formatted)}>格式化</button><button type="button" aria-pressed={mdMode === MD_MODES.raw} className={mdMode === MD_MODES.raw ? 'active' : ''} onClick={() => onSetMdMode(MD_MODES.raw)}>原文</button></div><span className="live-badge"><span />SESSION</span></div></div>
          <div className="agent-chat-messages" ref={chatMessagesRef}>
            {messages.length === 0 && <div className="agent-chat-empty"><div className="empty-orbit"><Bot size={24} /></div><strong>开始与 {agent.name} 对话</strong><span>试运行会使用当前绑定的 Tools、MCP 和模型配置。</span></div>}
            {messages.map((message) => {
              // 用户输入与错误信息不解析 Markdown：里面的 *、_ 不应被当成语法，
              // 因此既不渲染格式化视图，也不提供逐条切换。
              const isAssistant = message.role === 'assistant';
              const mode = resolveMdMode(message, mdMode);
              const overridden = isMdOverridden(message, mdMode);
              return <div className={`agent-chat-message ${message.role} ${isAssistant && mode === MD_MODES.formatted ? 'is-md' : ''}`} key={message.id}>
                <div className="agent-message-head">
                  <span className="agent-message-role">{message.role === 'user' ? '你' : message.role === 'error' ? '运行错误' : agent.name}</span>
                  {isAssistant && <button
                    type="button"
                    className={`md-toggle-mini ${overridden ? 'is-overridden' : ''}`}
                    title={overridden ? '本条已单独设置，点击恢复跟随全局' : '仅切换本条消息的显示方式'}
                    onClick={() => onSetMessageMdView(
                      message.id,
                      overridden ? undefined : (mode === MD_MODES.formatted ? MD_MODES.raw : MD_MODES.formatted),
                    )}
                  >{overridden ? '↺ 跟随全局' : (mode === MD_MODES.formatted ? '原文' : '格式化')}</button>}
                </div>
                <div><MarkdownText content={message.content} mode={mode} /></div>
                {message.run && <button className="run-result-link" onClick={() => onSelectRun(message.run)}><Activity size={13} />查看步骤 · {message.run.status}</button>}
              </div>;
            })}
            {chatBusy && <div className="agent-chat-pending"><RefreshCw className="spin" size={15} />Agent 正在运行…</div>}
          </div>
          {selectedRun && <RunResultPanel run={selectedRun} mdMode={mdMode} onClose={() => onSelectRun(null)} />}
          <form className="agent-chat-form" onSubmit={onSend}>
            <textarea value={chatInput} onChange={(event) => setChatInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); onSend(event); } }} placeholder="输入消息，试运行或继续对话…" rows={3} disabled={chatBusy} />
            <div><span>Enter 发送 · Shift+Enter 换行</span><button className="primary-btn" type="submit" disabled={chatBusy || !chatInput.trim()}><Send size={15} />发送</button></div>
          </form>
        </div>
      </div>
      </div>
    </div>
    {showCapabilityPicker && <div className="modal-backdrop capability-picker-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowCapabilityPicker(false); }}>
      <section className="capability-modal modal-card" role="dialog" aria-modal="true" aria-label="添加 Agent 能力">
        <header className="capability-modal-header">
          <div><span className="section-kicker">ADD CAPABILITIES</span><h2>为 {agent.name} 添加能力</h2><p>选择平台 Tool、整个 MCP 服务或单个 MCP Tool。</p></div>
          <button type="button" className="icon-btn" aria-label="关闭" onClick={() => setShowCapabilityPicker(false)}><X size={18} /></button>
        </header>
        <div className="capability-modal-controls">
          <div className="capability-tabs" role="tablist" aria-label="能力类型">
            <button type="button" role="tab" aria-selected={capabilityTab === 'tools'} className={capabilityTab === 'tools' ? 'active' : ''} onClick={() => setCapabilityTab('tools')}>平台 Tools <span>{tools.length}</span></button>
            <button type="button" role="tab" aria-selected={capabilityTab === 'mcp'} className={capabilityTab === 'mcp' ? 'active' : ''} onClick={() => setCapabilityTab('mcp')}>MCP 服务 <span>{providers.length}</span></button>
            <button type="button" role="tab" aria-selected={capabilityTab === 'api'} className={capabilityTab === 'api' ? 'active' : ''} onClick={() => setCapabilityTab('api')}>API Tools <span>{apiTools.length}</span></button>
          </div>
          <label className="capability-search"><Search size={16} /><input value={capabilitySearch} onChange={(event) => setCapabilitySearch(event.target.value)} placeholder={capabilityTab === 'tools' ? '搜索 Tool 名称、类型或描述' : capabilityTab === 'api' ? '搜索 API Tool 或服务' : '搜索 MCP 服务或工具'} /><kbd>/</kbd></label>
        </div>
        {capabilityLoadError && <div className="capability-load-error" role="status">{capabilityLoadError}</div>}
        <div className="capability-modal-list">
          {capabilityTab === 'tools' && (filteredTools.length === 0
            ? <p className="agent-detail-empty">{tools.length === 0 ? '当前没有可用的 Tool。' : '没有匹配的 Tool。'}</p>
            : filteredTools.map((tool) => {
              const ref = `tool:${tool.name}`;
              const alreadyBound = plugins.some((plugin) => plugin.type === 'tool' && [tool.name, tool.id, `tool:${tool.name}`].includes(plugin.ref));
              const checked = alreadyBound || isPending('tool', ref);
              return <label className={`capability-option ${alreadyBound ? 'is-bound' : ''}`} key={tool.id}>
                <input type="checkbox" checked={checked} disabled={alreadyBound || saving} onChange={(event) => togglePlugin({ type: 'tool', ref }, event.target.checked)} />
                <span className="capability-option-copy"><strong>{tool.name}</strong><small>{tool.description || '无描述'}</small></span>
                <span className="capability-option-tag">{alreadyBound ? '已绑定' : tool.type || 'Tool'}</span>
              </label>;
            }))}
          {capabilityTab === 'mcp' && (loadingCapabilityTools
            ? <div className="capability-picker-loading"><RefreshCw className="spin" size={17} />正在加载 MCP 工具…</div>
            : mcpProviders.length === 0
              ? <p className="agent-detail-empty">{providers.length === 0 ? '暂无可用 MCP Provider，请先在 Capability Registry 配置并同步服务。' : '没有匹配的 MCP 服务或工具。'}</p>
              : <>
                {pagedMcpProviders.map((provider) => {
                const providerBound = plugins.some((plugin) => plugin.type === 'capability_provider' && plugin.ref === provider.id);
                const providerChecked = providerBound || isPending('capability_provider', provider.id);
                const matchingToolCount = provider.matchesProvider ? provider.providerToolList.length : provider.matchingTools.length;
                const expanded = expandedMcpProviders[provider.id] ?? Boolean(normalizedSearch && !provider.matchesProvider);
                const toolsListId = `mcp-tools-${provider.id}`;
                const toolPageCount = Math.max(1, Math.ceil(provider.matchingTools.length / MCP_TOOL_PAGE_SIZE));
                const toolPage = Math.min(mcpToolPages[provider.id] || 1, toolPageCount);
                const pagedTools = provider.matchingTools.slice((toolPage - 1) * MCP_TOOL_PAGE_SIZE, toolPage * MCP_TOOL_PAGE_SIZE);
                return <section className="mcp-picker-group" key={provider.id}>
                  <header className={`mcp-picker-provider ${expanded ? 'expanded' : ''}`}>
                    <button
                      type="button"
                      className="mcp-picker-toggle"
                      aria-expanded={expanded}
                      aria-controls={expanded ? toolsListId : undefined}
                      onClick={() => setExpandedMcpProviders((current) => ({ ...current, [provider.id]: !expanded }))}
                    >
                      <ChevronDown className={`mcp-picker-chevron ${expanded ? 'expanded' : ''}`} size={15} />
                      <span><strong>{provider.name}</strong><small>{provider.auth_type || 'MCP'} · {provider.status} · {provider.providerToolList.length} 个工具</small></span>
                    </button>
                    <label className="mcp-provider-select">
                      <input type="checkbox" checked={providerChecked} disabled={providerBound || saving} onChange={(event) => togglePlugin({ type: 'capability_provider', ref: provider.id }, event.target.checked)} />
                      <span>{providerBound ? '已绑定全部' : '绑定全部'}</span>
                    </label>
                  </header>
                  {expanded && (provider.providerToolList.length === 0
                    ? <p className="mcp-picker-empty" id={toolsListId}>此 Provider 暂无可用工具。</p>
                    : <div className="mcp-picker-tools" id={toolsListId}>
                      <div className="mcp-picker-tool-scroll">
                        {pagedTools.map((tool) => {
                          const ref = `${provider.id}/${tool.id}`;
                          const coveredByProvider = providerBound || isPending('capability_provider', provider.id);
                          const alreadyBound = plugins.some((plugin) => plugin.type === 'capability_tool' && plugin.ref === ref);
                          const checked = coveredByProvider || alreadyBound || isPending('capability_tool', ref);
                          return <label className={`capability-option ${checked && !isPending('capability_tool', ref) ? 'is-bound' : ''}`} key={tool.id}>
                            <input type="checkbox" checked={checked} disabled={coveredByProvider || alreadyBound || saving} onChange={(event) => togglePlugin({ type: 'capability_tool', ref }, event.target.checked)} />
                            <span className="capability-option-copy"><strong>{tool.display_name || tool.name}</strong><small>{tool.description || tool.name}</small></span>
                            {alreadyBound && !providerBound && <span className="capability-option-tag">已绑定</span>}
                          </label>;
                        })}
                        {matchingToolCount === 0 && <p className="mcp-picker-empty">此服务下没有匹配的工具。</p>}
                      </div>
                      <Pager
                        page={toolPage}
                        pageCount={toolPageCount}
                        total={provider.matchingTools.length}
                        unit="个工具"
                        onChange={(next) => setMcpToolPages((current) => ({ ...current, [provider.id]: next }))}
                      />
                    </div>)}
                </section>;
              })}
                <Pager page={safeMcpPage} pageCount={mcpPageCount} total={mcpProviders.length} unit="个 MCP 服务" onChange={setMcpPage} />
              </>)}
          {capabilityTab === 'api' && (filteredApiTools.length === 0
            ? <p className="agent-detail-empty">{apiTools.length === 0 ? '暂无启用的 API Tool，请先在 Capability Registry 创建并启用。' : '没有匹配的 API Tool。'}</p>
            : filteredApiTools.map((tool) => {
              const ref = tool.id;
              const alreadyBound = plugins.some((plugin) => plugin.type === 'capability_api_tool' && plugin.ref === ref);
              const checked = alreadyBound || isPending('capability_api_tool', ref);
              return <label className={`capability-option ${alreadyBound ? 'is-bound' : ''}`} key={tool.id}>
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={alreadyBound || saving}
                  onChange={(event) => togglePlugin({ type: 'capability_api_tool', ref }, event.target.checked)}
                />
                <span className="capability-option-copy"><strong>{tool.display_name || tool.name}</strong><small>{tool.description || '无描述'}</small></span>
                <span className="capability-option-tag">{tool.service_name}</span>
              </label>;
            }))}
        </div>
        <footer className="capability-modal-footer">
          <span>已选择 {pendingPlugins.length} 项</span>
          <div><button type="button" className="secondary-btn" onClick={() => setShowCapabilityPicker(false)}>取消</button><button type="button" className="primary-btn" disabled={saving || pendingPlugins.length === 0} onClick={async () => { if (await onAddPlugins(pendingPlugins)) setShowCapabilityPicker(false); }}>{saving ? '保存中…' : `添加所选 (${pendingPlugins.length})`}</button></div>
        </footer>
      </section>
    </div>}
  </>;
}
