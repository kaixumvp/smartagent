import React, { useEffect, useState } from 'react';
import {
  Activity, ArrowUpRight, Bot, Check, ChevronDown, CircleDollarSign,
  Clock3, Command, Database, Gauge, KeyRound, LayoutDashboard,
  LogOut, Play, Plus, RefreshCw, Search, ShieldCheck, Sparkles, Terminal,
  Trash2, Wrench, X, Zap,
} from 'lucide-react';
import { MD_MODES } from './constants.js';
import { getAgentPlugins } from './features/agents/agentPlugins.js';
import AgentDetailDialog from './features/agents/AgentDetailDialog.jsx';
import EvaluationLab from './features/evaluation/EvaluationLab.jsx';
import RunResultPanel from './components/RunResultPanel.jsx';
import Status from './components/RunStatus.jsx';

const API_BASE = import.meta.env.VITE_API_BASE || '/v1';
const MD_VIEW_KEY = 'smartagent_md_view';
// 原文模式即改造前的表现（CSS white-space: pre-wrap 原样回显），格式化模式交给 react-markdown。

function createClientId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const random = Math.floor(Math.random() * 16);
    return (char === 'x' ? random : (random & 0x3) | 0x8).toString(16);
  });
}

const demoAgents = [
  { id: 'agent_support', name: '客服协作员', version: 'v1.4', status: 'active', model: 'deepseek-chat', runs: 1284, success: 96, accent: 'coral' },
  { id: 'agent_ops', name: '运营分析师', version: 'v2.1', status: 'active', model: 'gpt-4o-mini', runs: 876, success: 92, accent: 'teal' },
  { id: 'agent_research', name: '研究助理', version: 'v0.9', status: 'active', model: 'deepseek-chat', runs: 438, success: 89, accent: 'gold' },
];

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('smartagent_token') || '');
  const [active, setActive] = useState('overview');
  const [agents, setAgents] = useState(demoAgents);
  const [runs, setRuns] = useState([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState(demoAgents[0]);
  const [task, setTask] = useState('');
  const [overviewRun, setOverviewRun] = useState(null);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentVersion, setNewAgentVersion] = useState('1');
  const [creatingAgent, setCreatingAgent] = useState(false);
  const [toolsList, setToolsList] = useState([]);
  const [skillsList, setSkillsList] = useState([]);
  const [showCreateTool, setShowCreateTool] = useState(false);
  const [creatingTool, setCreatingTool] = useState(false);
  const [newToolName, setNewToolName] = useState('');
  const [newToolType, setNewToolType] = useState('http');
  const [newToolEndpoint, setNewToolEndpoint] = useState('');
  const [newToolDescription, setNewToolDescription] = useState('');
  const [newToolParameters, setNewToolParameters] = useState('{}');
  const [newToolPermission, setNewToolPermission] = useState('read');
  const [newToolRequiresApproval, setNewToolRequiresApproval] = useState(false);
  const [newToolConfig, setNewToolConfig] = useState('{}');
  const [newToolParametersList, setNewToolParametersList] = useState([{ name: '', type: 'string', description: '' }]);
  const [newToolConfigList, setNewToolConfigList] = useState([{ key: '', value: '' }]);
  const [showCreateSkill, setShowCreateSkill] = useState(false);
  const [creatingSkill, setCreatingSkill] = useState(false);
  const [newSkillName, setNewSkillName] = useState('');
  const [newSkillVersion, setNewSkillVersion] = useState('1');
  const [newSkillType, setNewSkillType] = useState('prompt');
  const [newSkillBody, setNewSkillBody] = useState('{}');
  const [newSkillPrompt, setNewSkillPrompt] = useState('');
  const [newSkillFunctionModule, setNewSkillFunctionModule] = useState('');
  const [newSkillFunctionName, setNewSkillFunctionName] = useState('');
  const [newSkillDefinition, setNewSkillDefinition] = useState('');
  const [toolsTab, setToolsTab] = useState('tools');
  // selections for agent plugins
  const [newAgentTools, setNewAgentTools] = useState([]);
  const [newAgentSkills, setNewAgentSkills] = useState([]);
  const [capabilityProviders, setCapabilityProviders] = useState([]);
  const [capabilityTools, setCapabilityTools] = useState({});
  const [capabilityApiTools, setCapabilityApiTools] = useState([]);
  const [capabilitySelections, setCapabilitySelections] = useState({});
  const [newAgentApiTools, setNewAgentApiTools] = useState([]);
  const [agentDetail, setAgentDetail] = useState(null);
  const [agentRuns, setAgentRuns] = useState([]);
  const [agentConversationId, setAgentConversationId] = useState('');
  const [agentChatInput, setAgentChatInput] = useState('');
  const [agentChatMessages, setAgentChatMessages] = useState([]);
  const [agentChatBusy, setAgentChatBusy] = useState(false);
  const [mdMode, setMdMode] = useState(() => (
    localStorage.getItem(MD_VIEW_KEY) === MD_MODES.raw ? MD_MODES.raw : MD_MODES.formatted
  ));
  const [agentSaving, setAgentSaving] = useState(false);
  const [agentDeleting, setAgentDeleting] = useState(false);
  const [deletingRunId, setDeletingRunId] = useState('');
  const [selectedRun, setSelectedRun] = useState(null);

  useEffect(() => { localStorage.setItem(MD_VIEW_KEY, mdMode); }, [mdMode]);

  useEffect(() => {
    if (!notice) return undefined;
    const timeoutId = window.setTimeout(() => setNotice(''), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [notice]);

  // 逐条覆盖只存本会话状态：message.mdView 为空表示跟随全局 mdMode。
  function setMessageMdView(messageId, mdView) {
    setAgentChatMessages((messages) => messages.map((message) => (
      message.id === messageId ? { ...message, mdView } : message
    )));
  }

  useEffect(() => {
    if (!token) return;
    api('/agents').then((data) => {
      if (Array.isArray(data)) {
        const loadedAgents = data.map((agent, index) => ({ ...agent, model: agent.config?.model || 'auto', runs: 0, success: 0, accent: ['coral', 'teal', 'gold'][index % 3] }));
        setAgents(loadedAgents);
        setSelectedAgent((current) => loadedAgents.find((agent) => agent.id === current?.id) || loadedAgents[0] || { id: '', name: '暂无 Agent', accent: 'coral' });
        loadRuns(loadedAgents);
      }
    }).catch((error) => {
      if (error.status === 401) {
        localStorage.removeItem('smartagent_token');
        setToken('');
        return;
      }
      setNotice(`Agent 列表加载失败：${error.message}`);
    });
    // fetch tools and skills for plugin configuration
    api('/tools').then((data) => { if (Array.isArray(data)) setToolsList(data); }).catch(() => {});
    api('/skills').then((data) => { if (Array.isArray(data)) setSkillsList(data); }).catch(() => {});
    api('/capability/providers').then((data) => {
      if (Array.isArray(data)) setCapabilityProviders(data);
    }).catch((error) => {
      setNotice(`MCP Provider 列表加载失败：${error.message}`);
    });
    api('/capability/tools').then((data) => {
      if (Array.isArray(data)) setCapabilityApiTools(data.filter((item) => item.source === 'api'));
    }).catch((error) => {
      setNotice(`Capability API Tools 列表加载失败：${error.message}`);
    });
  }, [token]);

  async function loadCapabilityTools(providerId) {
    if (capabilityTools[providerId]) return capabilityTools[providerId];
    const items = await api(`/capability/providers/${providerId}/tools`);
    setCapabilityTools((current) => ({ ...current, [providerId]: items }));
    return items;
  }

  async function openAgentDetails(agent) {
    setAgentDetail(agent);
    setSelectedAgent(agent);
    setAgentRuns([]);
    const conversationKey = `smartagent_conversation_${agent.id}`;
    const conversationId = localStorage.getItem(conversationKey) || createClientId();
    localStorage.setItem(conversationKey, conversationId);
    setAgentConversationId(conversationId);
    setAgentChatInput('');
    setAgentChatMessages([]);
    setSelectedRun(null);
    try {
      const history = await api(`/agents/${agent.id}/runs`);
      const agentHistory = Array.isArray(history) ? history : [];
      setAgentRuns(agentHistory);
      setAgentChatMessages(agentHistory
        .filter((run) => run.conversation_id === conversationId)
        .reverse()
        .flatMap((run) => [
          { id: createClientId(), role: 'user', content: run.input },
          ...(run.result ? [{ id: createClientId(), role: 'assistant', content: run.result, run }] : []),
        ]));
    } catch (error) {
      setNotice(`加载 Agent 运行记录失败：${error.message}`);
    }
    const plugins = getAgentPlugins(agent.config);
    const providerIds = [...new Set(plugins
      .filter((plugin) => ['capability_provider', 'capability_tool'].includes(plugin.type))
      .map((plugin) => plugin.type === 'capability_provider' ? plugin.ref : plugin.ref?.split('/')[0])
      .filter(Boolean))];
    await Promise.allSettled(providerIds.map(loadCapabilityTools));
  }

  async function unbindAgentPlugin(index) {
    if (!agentDetail) return;
    const plugins = getAgentPlugins(agentDetail.config).filter((_, itemIndex) => itemIndex !== index);
    const config = { ...agentDetail.config, plugins };
    delete config.tools;
    setAgentSaving(true);
    try {
      const updated = await api(`/agents/${agentDetail.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ config }),
      });
      const next = { ...agentDetail, ...updated, model: updated.config?.model || 'auto' };
      setAgentDetail(next);
      setAgents((items) => items.map((agent) => agent.id === updated.id ? { ...agent, ...updated, model: updated.config?.model || 'auto' } : agent));
      setNotice('已解绑并保存 Agent 工具配置');
    } catch (error) {
      setNotice(`解绑失败：${error.message}`);
    } finally {
      setAgentSaving(false);
    }
  }

  async function addAgentPlugins(pluginsToAdd) {
    if (!agentDetail || pluginsToAdd.length === 0) return;
    const plugins = [...getAgentPlugins(agentDetail.config)];
    for (const plugin of pluginsToAdd) {
      if (plugin.type === 'capability_provider') {
        const providerPrefix = `${plugin.ref}/`;
        for (let index = plugins.length - 1; index >= 0; index -= 1) {
          if (plugins[index].type === 'capability_tool' && plugins[index].ref.startsWith(providerPrefix)) {
            plugins.splice(index, 1);
          }
        }
      } else if (plugin.type === 'capability_tool' && plugins.some((item) => (
        item.type === 'capability_provider' && plugin.ref.startsWith(`${item.ref}/`)
      ))) {
        continue;
      }
      if (!plugins.some((item) => item.type === plugin.type && item.ref === plugin.ref)) {
        plugins.push(plugin);
      }
    }
    const config = { ...(agentDetail.config || {}), plugins };
    delete config.tools;
    setAgentSaving(true);
    try {
      const updated = await api(`/agents/${agentDetail.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ config }),
      });
      const next = { ...agentDetail, ...updated, model: updated.config?.model || 'auto' };
      setAgentDetail(next);
      setAgents((items) => items.map((agent) => agent.id === updated.id
        ? { ...agent, ...updated, model: updated.config?.model || 'auto' }
        : agent));
      setNotice('已添加并保存 Agent 能力');
      return true;
    } catch (error) {
      setNotice(`添加能力失败：${error.message}`);
      return false;
    } finally {
      setAgentSaving(false);
    }
  }

  async function deleteAgent() {
    if (!agentDetail || !window.confirm(`确定删除 Agent「${agentDetail.name}」吗？运行记录会保留。`)) return;
    setAgentDeleting(true);
    try {
      await api(`/agents/${agentDetail.id}`, { method: 'DELETE' });
      const remaining = agents.filter((agent) => agent.id !== agentDetail.id);
      setAgents(remaining);
      localStorage.removeItem(`smartagent_conversation_${agentDetail.id}`);
      if (selectedAgent.id === agentDetail.id && remaining.length) setSelectedAgent(remaining[0]);
      if (selectedAgent.id === agentDetail.id && !remaining.length) setSelectedAgent({ id: '', name: '暂无 Agent', accent: 'coral' });
      setAgentDetail(null);
      setNotice('Agent 已删除，历史运行记录已保留');
    } catch (error) {
      setNotice(`删除 Agent 失败：${error.message}`);
    } finally {
      setAgentDeleting(false);
    }
  }

  async function deleteAgentRun(run) {
    if (!agentDetail || !window.confirm(`确定删除这条运行记录吗？\n${run.input}`)) return;
    setDeletingRunId(run.run_id);
    try {
      await api(`/runs/${run.run_id}`, { method: 'DELETE' });
      setAgentRuns((items) => items.filter((item) => item.run_id !== run.run_id));
      setRuns((items) => items.filter((item) => item.id !== run.run_id));
      setSelectedRun((current) => current?.run_id === run.run_id ? null : current);
      setAgentChatMessages((items) => {
        const assistantIndex = items.findIndex((item) => item.run?.run_id === run.run_id);
        if (assistantIndex < 0) return items;
        const userIndex = items[assistantIndex - 1]?.role === 'user' ? assistantIndex - 1 : -1;
        return items.filter((_, index) => index !== assistantIndex && index !== userIndex);
      });
      setNotice('运行记录已删除');
    } catch (error) {
      setNotice(`删除运行记录失败：${error.message}`);
    } finally {
      setDeletingRunId('');
    }
  }

  async function sendAgentMessage(event) {
    event?.preventDefault();
    const input = agentChatInput.trim();
    if (!input || !agentDetail || agentChatBusy) return;
    setAgentChatMessages((messages) => [...messages, { id: createClientId(), role: 'user', content: input }]);
    setAgentChatInput('');
    setAgentChatBusy(true);
    try {
      const result = await api(`/agents/${agentDetail.id}/runs`, {
        method: 'POST',
        body: JSON.stringify({ input, stream: false, conversation_id: agentConversationId }),
      });
      setAgentChatMessages((messages) => [...messages, {
        id: createClientId(),
        role: 'assistant',
        content: result.result || (result.status === 'awaiting_human' ? '运行正在等待人工审批。' : 'Agent 没有返回文本结果。'),
        run: result,
      }]);
      setAgentRuns((items) => [result, ...items.filter((run) => run.run_id !== result.run_id)].slice(0, 20));
      setRuns((items) => [{
        id: result.run_id,
        agent: agentDetail.name,
        task: input,
        status: result.status,
        time: '刚刚',
        cost: `$${Number(result.cost || 0).toFixed(4)}`,
        result: result.result,
        steps: result.steps,
      }, ...items.filter((run) => run.id !== result.run_id)]);
      setSelectedRun(result);
      setNotice(result.status === 'awaiting_human' ? '运行需要人工审批，详情已显示在对话中' : '试运行已完成');
    } catch (error) {
      setAgentChatMessages((messages) => [...messages, { id: createClientId(), role: 'error', content: error.message }]);
      setNotice(`试运行失败：${error.message}`);
    } finally {
      setAgentChatBusy(false);
    }
  }

  async function api(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const error = new Error(payload.error?.message || '请求失败');
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }

  async function loadRuns(agentList = agents) {
    setRunsLoading(true);
    try {
      const data = await api('/runs?limit=100');
      const agentNames = new Map(agentList.map((agent) => [agent.id, agent.name]));
      setRuns(data.map((run) => ({
        ...run,
        id: run.run_id,
        task: run.input,
        agent: agentNames.get(run.agent_id) || run.agent_id,
        time: run.created_at ? new Date(run.created_at).toLocaleString() : '—',
        cost: `$${Number(run.cost || 0).toFixed(4)}`,
      })));
    } catch (error) {
      setNotice(`加载运行记录失败：${error.message}`);
    } finally {
      setRunsLoading(false);
    }
  }

  async function executeTask() {
    if (!task.trim()) return;
    if (!selectedAgent?.id) { setNotice('请先创建 Agent'); return; }
    setLoading(true);
    setOverviewRun(null);
    const optimistic = { id: `run_demo_${Date.now()}`, agent: selectedAgent.name, task, status: 'running', time: '刚刚', cost: '计算中' };
    setRuns((items) => [optimistic, ...items]);
    try {
      const result = await api(`/agents/${selectedAgent.id}/runs`, { method: 'POST', body: JSON.stringify({ input: task, stream: false }) });
      setRuns((items) => items.map((item) => item.id === optimistic.id ? { ...optimistic, id: result.run_id, status: result.status, cost: `$${Number(result.cost || 0).toFixed(4)}`, result: result.result, steps: result.steps } : item));
      setOverviewRun(result);
      setNotice(result.status === 'awaiting_human' ? '任务需要人工审批，请在运行列表中处理' : '任务已完成');
    } catch (error) {
      setRuns((items) => items.map((item) => item.id === optimistic.id ? { ...item, status: 'failed' } : item));
      setOverviewRun({ run_id: optimistic.id, status: 'failed', error: error.message, steps: [] });
      setNotice(error.message);
    } finally { setLoading(false); }
  }

  async function approve(run) {
    try {
      await api(`/runs/${run.id}/actions`, { method: 'POST', body: JSON.stringify({ action: 'approve' }) });
      setRuns((items) => items.map((item) => item.id === run.id ? { ...item, status: 'completed' } : item));
      setNotice('审批已通过，运行继续执行');
    } catch (error) { setNotice(error.message); }
  }

  async function login({ username, password, tenant }) {
    const body = { username, password };
    if (tenant.trim()) body.tenant = tenant.trim();
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data.error?.message || '登录失败';
      if (response.status === 401) {
        throw new Error(message === 'invalid credentials' ? '用户名或密码错误。引导账号是 admin，未改过密码则为 admin123。' : message);
      }
      throw new Error(message);
    }
    localStorage.setItem('smartagent_token', data.access_token);
    setToken(data.access_token);
  }

  if (!token) return <Login onLogin={login} />;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Sparkles size={17} /></div><span>smartagent</span><small>CONSOLE</small></div>
      <div className="workspace"><div className="workspace-avatar">S</div><div><strong>SmartAgent Lab</strong><span>Default workspace</span></div><ChevronDown size={15} /></div>
      <nav>
        <p className="nav-label">工作台</p>
        <NavItem icon={<LayoutDashboard />} label="总览" active={active === 'overview'} onClick={() => setActive('overview')} />
        <NavItem icon={<Bot />} label="Agents" active={active === 'agents'} onClick={() => setActive('agents')} />
        <NavItem icon={<Activity />} label="运行记录" active={active === 'runs'} onClick={() => setActive('runs')} badge="3" />
        <NavItem icon={<Gauge />} label="评测与实验" active={active === 'evals'} onClick={() => setActive('evals')} />
        <p className="nav-label">资源</p>
        <NavItem icon={<Terminal />} label="工具与技能" active={active === 'tools'} onClick={() => setActive('tools')} />
        <NavItem icon={<Database />} label="记忆库" active={active === 'memory'} onClick={() => setActive('memory')} />
        <NavItem icon={<ShieldCheck />} label="权限管理" active={active === 'iam'} onClick={() => setActive('iam')} />
      </nav>
      <div className="sidebar-bottom"><div className="status-line"><span className="status-dot" />API 在线 <span className="latency">42ms</span></div><button className="user-menu" onClick={() => { localStorage.removeItem('smartagent_token'); setToken(''); }}><div className="user-avatar">AD</div><span><strong>Admin</strong><small>管理员</small></span><LogOut size={15} /></button></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div className="crumb"><span>工作台</span><span>/</span><strong>{{ overview: '总览', agents: 'Agents', runs: '运行记录', evals: '评测与实验', tools: '工具与技能', memory: '记忆库', iam: '权限管理' }[active] || '总览'}</strong></div><div className="top-actions"><button className="icon-btn" title="搜索"><Search size={18} /></button><button className="icon-btn" title="快捷键"><Command size={17} /></button><div className="notification"><span /></div><div className="top-avatar">AD</div></div></header>
      {notice && <div className="notice"><Check size={15} />{notice}<button onClick={() => setNotice('')}><X size={15} /></button></div>}
      <div className="content-wrap">
        <section className="page-heading"><div><div className="eyebrow">THURSDAY, AUGUST 27, 2026</div><h1>早上好，Admin <span>。</span></h1><p>这里是你的 Agent 运行控制中心。</p></div><button className="secondary-btn" onClick={() => setNotice('数据已刷新')}><RefreshCw size={16} />刷新数据</button></section>
        {active === 'overview' && <>
          <section className="metrics">
            <Metric icon={<Zap />} label="今日运行" value="184" delta="+18.6%" tone="coral" />
            <Metric icon={<CircleDollarSign />} label="本月成本" value="$42.68" delta="-8.2%" tone="teal" />
            <Metric icon={<Gauge />} label="平均成功率" value="94.2%" delta="+2.4%" tone="gold" />
            <Metric icon={<Clock3 />} label="平均响应" value="2.8s" delta="-0.6s" tone="lavender" />
          </section>
          <section className="workspace-grid">
            <div className="panel activity-panel">
              <div className="panel-header">
                <div><span className="section-kicker">SYSTEM PULSE</span><h2>实时状态</h2></div>
                <button className="more-btn">•••</button>
              </div>
              <div className="pulse-chart">
                <div className="chart-grid" />
                <svg viewBox="0 0 500 170" preserveAspectRatio="none">
                  <path d="M0 140 C35 126 38 78 70 95 S105 138 135 105 S175 32 205 67 S230 130 258 107 S282 85 310 95 S335 142 360 110 S385 55 410 76 S435 112 456 84 S480 32 500 47" fill="none" stroke="#e45c4b" strokeWidth="3" />
                </svg>
                <div className="chart-labels"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>现在</span></div>
              </div>
              <div className="pulse-footer"><span><i className="legend-dot coral-dot" />请求量</span><strong>1,284 <small>requests</small></strong></div>
            </div>
            <div className="panel run-panel">
              <div className="panel-header">
                <div><span className="section-kicker">QUICK ACTION</span><h2>试运行 Agent</h2></div>
                <span className="live-badge"><span />LIVE</span>
              </div>
              <div className="agent-picker">
                <div className={`agent-icon ${selectedAgent.accent}`}><Bot size={20} /></div>
                <div className="agent-choice"><span>选择 Agent</span><strong>{selectedAgent.name}</strong></div>
                <select
                  value={selectedAgent.id}
                  onChange={(event) => {
                    setSelectedAgent(agents.find((agent) => agent.id === event.target.value) || selectedAgent);
                    setOverviewRun(null);
                  }}
                >
                  {agents.map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}
                </select>
                <ChevronDown size={16} />
              </div>
              <textarea value={task} onChange={(event) => setTask(event.target.value)} placeholder="输入任务，试运行 Agent 并查看执行结果…" />
              <div className="run-footer">
                <span><Sparkles size={15} />支持工具调用与长期记忆</span>
                <button className="primary-btn" onClick={executeTask} disabled={loading || !task.trim() || !selectedAgent?.id}>
                  {loading ? <RefreshCw className="spin" size={16} /> : <Play size={16} fill="currentColor" />}
                  {loading ? '执行中' : '开始测试'}
                </button>
              </div>
              {overviewRun && <RunResultPanel run={overviewRun} mdMode={mdMode} onClose={() => setOverviewRun(null)} className="overview-run-result" />}
            </div>
          </section>
        </>}
        {active === 'agents' && <AgentPage agents={agents} onSelect={openAgentDetails} onCreate={() => { setCapabilitySelections({}); setNewAgentTools([]); setNewAgentApiTools([]); setNewAgentSkills([]); setShowCreateAgent(true); }} />}
        {showCreateAgent && (
          <div className="modal-backdrop">
            <div className="modal-card">
              <h3>新建 Agent</h3>
              <label>名称<input value={newAgentName} onChange={(e) => setNewAgentName(e.target.value)} placeholder="Agent 名称" /></label>
              <label>版本<input value={newAgentVersion} onChange={(e) => setNewAgentVersion(e.target.value)} placeholder="1" /></label>
              <label>绑定工具（多选）
                <select multiple value={newAgentTools} onChange={(e) => setNewAgentTools(Array.from(e.target.selectedOptions, (o) => o.value))}>
                  {toolsList.map((t) => <option key={t.id} value={t.name}>{t.name} ({t.type})</option>)}
                </select>
              </label>
              <div className="capability-picker">
                <strong>Capability MCP</strong>
                <small>可绑定一个 Provider 的全部工具，或只选择该服务中的特定工具。</small>
                {capabilityProviders.length === 0 && <small>没有可用 Provider；请先在 Capability Registry 同步 MCP Tools。</small>}
                {capabilityProviders.map((provider) => {
                  const selection = capabilitySelections[provider.id] || { all: false, toolIds: [] };
                  const providerTools = capabilityTools[provider.id] || [];
                  return <div className="capability-provider" key={provider.id}>
                    <div className="capability-provider-heading">
                      <span><b>{provider.name}</b><small>{provider.auth_type} · {provider.status}</small></span>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={!!selection.all}
                          onChange={async (event) => {
                            const enabled = event.target.checked;
                            setCapabilitySelections((current) => ({
                              ...current,
                              [provider.id]: { ...current[provider.id], all: enabled },
                            }));
                            if (enabled && !capabilityTools[provider.id]) {
                              try { await loadCapabilityTools(provider.id); }
                              catch (error) { setNotice(`MCP Tools 加载失败：${error.message}`); }
                            }
                          }}
                        />
                        绑定整个 Provider
                      </label>
                    </div>
                    <div className="capability-tool-list">
                      {providerTools.length === 0
                        ? <small>暂无已同步且启用的 Tool</small>
                        : providerTools.map((tool) => (
                          <label className="checkbox" key={tool.id}>
                            <input
                              type="checkbox"
                              checked={!!selection.all || selection.toolIds?.includes(tool.id)}
                              disabled={!!selection.all}
                              onChange={async (event) => {
                                const checked = event.target.checked;
                                try {
                                  if (!capabilityTools[provider.id]) await loadCapabilityTools(provider.id);
                                  setCapabilitySelections((current) => {
                                    const previous = current[provider.id] || { all: false, toolIds: [] };
                                    const toolIds = new Set(previous.toolIds || []);
                                    if (checked) toolIds.add(tool.id);
                                    else toolIds.delete(tool.id);
                                    return { ...current, [provider.id]: { ...previous, all: false, toolIds: [...toolIds] } };
                                  });
                                } catch (error) {
                                  setNotice(`MCP Tools 加载失败：${error.message}`);
                                }
                              }}
                            />
                            <span>{tool.display_name || tool.name}</span>
                            <small>{tool.name}</small>
                          </label>
                        ))}
                    </div>
                    {providerTools.length === 0 && (
                      <button
                        type="button"
                        className="text-btn"
                        onClick={async () => {
                          try { await loadCapabilityTools(provider.id); }
                          catch (error) { setNotice(`MCP Tools 加载失败：${error.message}`); }
                        }}
                      >
                        加载该 Provider 的 Tools
                      </button>
                    )}
                  </div>;
                })}
              </div>
              <div className="capability-picker">
                <strong>Capability API Tools</strong>
                <small>仅选择已启用的 API Tool；Agent 通过标准 Tool Schema 调用，不会收到 API 凭据或 HTTP 配置。</small>
                {capabilityApiTools.length === 0
                  ? <small>暂无可用 API Tool，请先在 Capability Registry 创建并启用。</small>
                  : <div className="capability-tool-list">
                    {capabilityApiTools.map((tool) => (
                      <label className="checkbox" key={tool.id}>
                        <input
                          type="checkbox"
                          checked={newAgentApiTools.includes(tool.id)}
                          onChange={(event) => setNewAgentApiTools((current) => (
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
                <select multiple value={newAgentSkills} onChange={(e) => setNewAgentSkills(Array.from(e.target.selectedOptions, (o) => o.value))}>
                  {skillsList.map((s) => <option key={s.id} value={`${s.name}@${s.version}`}>{s.name}@{s.version} ({s.type})</option>)}
                </select>
              </label>
              <div className="modal-actions">
                <button className="secondary-btn" onClick={() => setShowCreateAgent(false)} disabled={creatingAgent}>取消</button>
                <button className="primary-btn" onClick={async () => {
                  if (!newAgentName.trim()) { setNotice('请输入 Agent 名称'); return; }
                  setCreatingAgent(true);
                  try {
                    const plugins = [];
                    for (const t of newAgentTools) plugins.push({ type: 'tool', ref: `tool:${t}` });
                    for (const [providerId, selection] of Object.entries(capabilitySelections)) {
                      if (selection.all) {
                        plugins.push({ type: 'capability_provider', ref: providerId });
                      } else {
                        for (const toolId of selection.toolIds || []) {
                          plugins.push({ type: 'capability_tool', ref: `${providerId}/${toolId}` });
                        }
                      }
                    }
                    for (const toolId of newAgentApiTools) {
                      plugins.push({ type: 'capability_api_tool', ref: toolId });
                    }
                    for (const s of newAgentSkills) {
                      const [name, ver] = s.split('@');
                      plugins.push({ type: 'skill', ref: `skill:${name}@${ver}` });
                    }
                    const body = { name: newAgentName.trim(), version: newAgentVersion || '1', config: { plugins } };
                    const result = await api('/agents', { method: 'POST', body: JSON.stringify(body) });
                    const created = { ...result, model: result.config?.model || 'auto', runs: 0, success: 0, accent: 'coral' };
                    setAgents((prev) => [created, ...prev]);
                    setSelectedAgent(created);
                    setNotice('Agent 已创建');
                    setShowCreateAgent(false);
                    setNewAgentName('');
                    setNewAgentVersion('1');
                    setNewAgentTools([]);
                    setNewAgentApiTools([]);
                    setNewAgentSkills([]);
                    setCapabilitySelections({});
                  } catch (err) {
                    setNotice(err.message || '创建 Agent 失败');
                  } finally { setCreatingAgent(false); }
                }} disabled={creatingAgent}>{creatingAgent ? '创建中...' : '创建'}</button>
              </div>
            </div>
          </div>
        )}
        {agentDetail && (
          <AgentDetailDialog
            agent={agentDetail}
            tools={toolsList}
            providers={capabilityProviders}
            providerTools={capabilityTools}
            apiTools={capabilityApiTools}
            runs={agentRuns}
            messages={agentChatMessages}
            chatInput={agentChatInput}
            chatBusy={agentChatBusy}
            saving={agentSaving}
            deleting={agentDeleting}
            deletingRunId={deletingRunId}
            selectedRun={selectedRun}
            setChatInput={setAgentChatInput}
            mdMode={mdMode}
            onSetMdMode={setMdMode}
            onSetMessageMdView={setMessageMdView}
            onLoadProviderTools={loadCapabilityTools}
            onClose={() => setAgentDetail(null)}
            onUnbind={unbindAgentPlugin}
            onAddPlugins={addAgentPlugins}
            onDelete={deleteAgent}
            onDeleteRun={deleteAgentRun}
            onSend={sendAgentMessage}
            onSelectRun={setSelectedRun}
          />
        )}
        {active === 'runs' && <section className="panel full-panel"><div className="panel-header"><div><span className="section-kicker">RUN HISTORY</span><h2>运行记录</h2></div><button className="secondary-btn" onClick={() => loadRuns()} disabled={runsLoading}>{runsLoading ? <RefreshCw className="spin" size={15} /> : <RefreshCw size={15} />}{runsLoading ? '加载中' : '刷新'}</button></div><RunTable runs={runs} onApprove={approve} onSelect={setSelectedRun} detailed loading={runsLoading} />{selectedRun && <RunResultPanel run={selectedRun} mdMode={mdMode} onClose={() => setSelectedRun(null)} />}</section>}
        {active === 'tools' && (
          <section className="panel full-panel">
            <div className="panel-header">
              <div><span className="section-kicker">PLUGIN REGISTRY</span><h2>工具与技能</h2></div>
              <div>
                <button type="button" aria-pressed={toolsTab === 'tools'} className={`text-btn ${toolsTab === 'tools' ? 'active' : ''}`} onClick={() => setToolsTab('tools')}>Tools</button>
                <button type="button" aria-pressed={toolsTab === 'skills'} className={`text-btn ${toolsTab === 'skills' ? 'active' : ''}`} onClick={() => setToolsTab('skills')}>Skills</button>
                <button type="button" className="secondary-btn" onClick={() => setNotice('已刷新工具与技能') }><RefreshCw size={15} /> 刷新</button>
              </div>
            </div>
            {toolsTab === 'tools' && (
              <div className="tools-list">
                <div className="tools-actions"><button className="primary-btn" onClick={() => setShowCreateTool(true)}><Plus size={14} /> 新建 Tool</button></div>
                <div className="grid">
                  {toolsList.map((t) => <div className="card" key={t.id}><h3>{t.name}</h3><p>{t.type} · {t.permission}</p><small>{t.description}</small></div>)}
                </div>
              </div>
            )}
            {toolsTab === 'skills' && (
              <div className="skills-list">
                <div className="tools-actions"><button className="primary-btn" onClick={() => setShowCreateSkill(true)}><Plus size={14} /> 新建 Skill</button></div>
                <div className="grid">
                  {skillsList.map((s) => <div className="card" key={s.id}><h3>{s.name}@{s.version}</h3><p>{s.type}</p><small>{s.description}</small></div>)}
                </div>
              </div>
            )}
          </section>
        )}
        {active === 'evals' && <EvaluationLab api={api} agents={agents} onNotice={setNotice} />}
        {['memory', 'iam'].includes(active) && <EmptyState active={active} />}

        {showCreateTool && (
          <div className="modal-backdrop">
            <div className="modal-card">
              <h3>新建 Tool</h3>
              <label>名称<input value={newToolName} onChange={(e) => setNewToolName(e.target.value)} placeholder="calculator" /></label>
              <label>类型<select value={newToolType} onChange={(e) => setNewToolType(e.target.value)}><option value="builtin">builtin</option><option value="mcp">mcp</option><option value="http">http</option></select></label>
              <label>Endpoint (HTTP/MCP 可选)<input value={newToolEndpoint} onChange={(e) => setNewToolEndpoint(e.target.value)} placeholder="https://..." /></label>
              <label>描述<input value={newToolDescription} onChange={(e) => setNewToolDescription(e.target.value)} placeholder="工具描述（可选）" /></label>
              <label>参数 Schema (JSON)
                <div className="kv-list">
                  {newToolParametersList.map((p, idx) => (
                    <div className="kv-row" key={idx}>
                      <input placeholder="name" value={p.name} onChange={(e) => setNewToolParametersList((prev) => { const copy = [...prev]; copy[idx].name = e.target.value; return copy; })} />
                      <select value={p.type} onChange={(e) => setNewToolParametersList((prev) => { const copy = [...prev]; copy[idx].type = e.target.value; return copy; })}>
                        <option value="string">string</option>
                        <option value="number">number</option>
                        <option value="boolean">boolean</option>
                        <option value="object">object</option>
                      </select>
                      <input placeholder="description" value={p.description} onChange={(e) => setNewToolParametersList((prev) => { const copy = [...prev]; copy[idx].description = e.target.value; return copy; })} />
                      <button className="text-btn" type="button" onClick={() => setNewToolParametersList((prev) => prev.filter((_, i) => i !== idx))}>删除</button>
                    </div>
                  ))}
                  <button className="text-btn" type="button" onClick={() => setNewToolParametersList((prev) => [...prev, { name: '', type: 'string', description: '' }])}>添加参数</button>
                </div>
              </label>
              <label>Config (JSON，可用于 endpoint 的额外配置)
                <div className="kv-list">
                  {newToolConfigList.map((c, idx) => (
                    <div className="kv-row" key={idx}>
                      <input placeholder="key" value={c.key} onChange={(e) => setNewToolConfigList((prev) => { const copy = [...prev]; copy[idx].key = e.target.value; return copy; })} />
                      <input placeholder="value" value={c.value} onChange={(e) => setNewToolConfigList((prev) => { const copy = [...prev]; copy[idx].value = e.target.value; return copy; })} />
                      <button className="text-btn" type="button" onClick={() => setNewToolConfigList((prev) => prev.filter((_, i) => i !== idx))}>删除</button>
                    </div>
                  ))}
                  <button className="text-btn" type="button" onClick={() => setNewToolConfigList((prev) => [...prev, { key: '', value: '' }])}>添加配置项</button>
                </div>
              </label>
              <label>权限
                <select value={newToolPermission} onChange={(e) => setNewToolPermission(e.target.value)}>
                  <option value="read">read</option>
                  <option value="write">write</option>
                </select>
              </label>
              <label className="checkbox"><input type="checkbox" checked={newToolRequiresApproval} onChange={(e) => setNewToolRequiresApproval(e.target.checked)} /> 需要审批</label>
              <div className="modal-actions">
                <button className="secondary-btn" onClick={() => setShowCreateTool(false)} disabled={creatingTool}>取消</button>
                <button className="primary-btn" onClick={async () => {
                  if (!newToolName.trim()) { setNotice('请输入 Tool 名称'); return; }
                  // Build an OpenAI-function-style JSON Schema: the backend forwards
                  // tool.parameters straight to the LLM as the callable signature, so a flat
                  // {name: {...}} map would produce a schema with no `properties` at all.
                  const properties = {};
                  const required = [];
                  for (const p of newToolParametersList) {
                    const key = p.name.trim();
                    if (!key) continue;
                    properties[key] = { type: p.type, description: p.description || '' };
                    required.push(key);
                  }
                  const params = { type: 'object', properties, required };
                  const cfg = {};
                  for (const c of newToolConfigList) { if (c.key.trim()) cfg[c.key.trim()] = c.value; }
                  setCreatingTool(true);
                  try {
                    const body = { name: newToolName.trim(), type: newToolType, endpoint: newToolEndpoint || undefined, parameters: params, description: newToolDescription || '', permission: newToolPermission, requires_approval: newToolRequiresApproval, config: cfg };
                    const result = await api('/tools', { method: 'POST', body: JSON.stringify(body) });
                    setToolsList((prev) => [result, ...prev]);
                    setNotice('Tool 已创建');
                    setShowCreateTool(false);
                    setNewToolName(''); setNewToolType('http'); setNewToolEndpoint(''); setNewToolDescription(''); setNewToolParameters('{}'); setNewToolPermission('read'); setNewToolRequiresApproval(false); setNewToolConfig('{}');
                  } catch (err) { setNotice(err.message || '创建 Tool 失败'); }
                  finally { setCreatingTool(false); }
                }} disabled={creatingTool}>{creatingTool ? '创建中...' : '创建'}</button>
              </div>
            </div>
          </div>
        )}

        {showCreateSkill && (
          <div className="modal-backdrop">
            <div className="modal-card">
              <h3>新建 Skill</h3>
              <label>名称<input value={newSkillName} onChange={(e) => setNewSkillName(e.target.value)} placeholder="skill_name" /></label>
              <label>版本<input value={newSkillVersion} onChange={(e) => setNewSkillVersion(e.target.value)} placeholder="1" /></label>
              <label>类型<select value={newSkillType} onChange={(e) => setNewSkillType(e.target.value)}><option value="prompt">prompt</option><option value="function">function</option><option value="flow">flow</option><option value="agent">agent</option></select></label>
              <label>Body
                {newSkillType === 'prompt' && (
                  <textarea value={newSkillPrompt} onChange={(e) => setNewSkillPrompt(e.target.value)} rows={6} placeholder="Prompt 模板: 使用 {{input}} 引用输入" />
                )}
                {newSkillType === 'function' && (
                  <div className="kv-list">
                    <label>模块<input value={newSkillFunctionModule} onChange={(e) => setNewSkillFunctionModule(e.target.value)} placeholder="module.path" /></label>
                    <label>函数<input value={newSkillFunctionName} onChange={(e) => setNewSkillFunctionName(e.target.value)} placeholder="function_name" /></label>
                    <small>函数类型 Skill 会被注册并在运行时被调用。</small>
                  </div>
                )}
                {['flow', 'agent'].includes(newSkillType) && (
                  <textarea value={newSkillDefinition} onChange={(e) => setNewSkillDefinition(e.target.value)} rows={6} placeholder="技能定义或说明（自由文本）" />
                )}
              </label>
              <div className="modal-actions">
                <button className="secondary-btn" onClick={() => setShowCreateSkill(false)} disabled={creatingSkill}>取消</button>
                <button className="primary-btn" onClick={async () => {
                  if (!newSkillName.trim()) { setNotice('请输入 Skill 名称'); return; }
                  // build body according to type
                  let bodyObj = {};
                  if (newSkillType === 'prompt') {
                    if (!newSkillPrompt.trim()) { setNotice('Prompt 不能为空'); return; }
                    bodyObj = { prompt: newSkillPrompt };
                  } else if (newSkillType === 'function') {
                    if (!newSkillFunctionModule.trim() || !newSkillFunctionName.trim()) { setNotice('请填写模块与函数名'); return; }
                    bodyObj = { module: newSkillFunctionModule.trim(), function: newSkillFunctionName.trim() };
                  } else {
                    bodyObj = { definition: newSkillDefinition || '' };
                  }
                  setCreatingSkill(true);
                  try {
                    const body = { name: newSkillName.trim(), version: newSkillVersion || '1', type: newSkillType, description: '', body: bodyObj, parameters: {} };
                    const result = await api('/skills', { method: 'POST', body: JSON.stringify(body) });
                    setSkillsList((prev) => [result, ...prev]);
                    setNotice('Skill 已创建');
                    setShowCreateSkill(false);
                    setNewSkillName(''); setNewSkillVersion('1'); setNewSkillBody('{}'); setNewSkillType('prompt'); setNewSkillPrompt(''); setNewSkillFunctionModule(''); setNewSkillFunctionName(''); setNewSkillDefinition('');
                  } catch (err) { setNotice(err.message || '创建 Skill 失败'); }
                  finally { setCreatingSkill(false); }
                }} disabled={creatingSkill}>{creatingSkill ? '创建中...' : '创建'}</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  </div>;
}

function Login({ onLogin }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [tenant, setTenant] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError('请输入用户名和密码');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await onLogin({ username: username.trim(), password, tenant });
    } catch (err) {
      setError(err.message || '登录失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-art">
        <div className="art-orbit orbit-one" />
        <div className="art-orbit orbit-two" />
        <div className="art-copy">
          <span className="eyebrow">AGENT OPERATIONS, REFINED</span>
          <h1>让每一次<br /><em>智能运行</em><br />都清晰可见。</h1>
          <p>一个安静、可靠的控制中心，连接你的 Agent、工具与数据。</p>
        </div>
      </div>
      <form className="login-card" onSubmit={submit}>
        <div className="brand"><div className="brand-mark"><Sparkles size={17} /></div><span>smartagent</span></div>
        <div className="login-title">
          <span className="section-kicker">WELCOME BACK</span>
          <h2>进入控制台</h2>
          <p>使用账号密码登录你的工作区。</p>
        </div>
        <div className="login-fields">
          <label>用户名<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder="admin" /></label>
          <label>密码<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" placeholder="输入密码" /></label>
          <details className="login-advanced">
            <summary>高级选项</summary>
            <label>租户（可选）<input value={tenant} onChange={(e) => setTenant(e.target.value)} autoComplete="off" placeholder="单租户请留空" /></label>
          </details>
        </div>
        {error && <p className="login-error">{error}</p>}
        <button className="primary-btn login-btn" type="submit" disabled={submitting}>
          {submitting ? '登录中' : '进入工作台'} <ArrowUpRight size={17} />
        </button>
        <div className="login-note"><KeyRound size={14} /> 会话凭证仅保存在当前浏览器</div>
      </form>
    </div>
  );
}
function NavItem({ icon, label, active, onClick, badge }) { return <button className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}>{icon}<span>{label}</span>{badge && <b>{badge}</b>}</button> }
function Metric({ icon, label, value, delta, tone }) { return <div className="metric"><div className={`metric-icon ${tone}`}>{icon}</div><div className="metric-copy"><span>{label}</span><strong>{value}</strong><small className={delta.startsWith('-') ? 'positive' : ''}>{delta}</small></div><div className="metric-spark">▰▂▅▃▇▆▂</div></div> }
function RunTable({ runs, onApprove, onSelect, detailed, loading }) {
  if (runs.length === 0) {
    return <div className="run-history-empty">{loading ? '正在加载运行记录…' : '还没有运行记录。运行 Agent 后，记录会显示在这里。'}</div>;
  }
  return <div className="run-table">
    <div className="table-head"><span>任务 / Agent</span><span>状态</span><span>时间</span><span>成本</span>{detailed && <span />}</div>
    {runs.map((run) => <div className="run-row" key={run.id}>
      <div className="run-name"><div className="mini-agent"><Bot size={16} /></div><div><strong>{run.task}</strong><span>{run.agent} · {run.id}</span></div></div>
      <div><Status status={run.status} />{run.status === 'awaiting_human' && <button className="approve-btn" onClick={() => onApprove(run)}><Check size={13} />审批</button>}</div>
      <span className="muted">{run.time}</span><span className="cost">{run.cost}</span>
      {detailed && <button className="row-arrow" onClick={() => onSelect(run)} aria-label={`查看运行记录 ${run.id}`}><ArrowUpRight size={16} /></button>}
    </div>)}
  </div>;
}
function AgentPage({ agents, onSelect, onCreate }) {
  return <section>
    <div className="page-heading compact">
      <div><div className="eyebrow">AGENT CATALOG</div><h1>你的 Agents</h1><p>管理版本、模型与执行入口。</p></div>
      <button className="primary-btn" onClick={onCreate}><Plus size={16} />新建 Agent</button>
    </div>
    {agents.length === 0
      ? <div className="panel agent-empty">还没有 Agent，创建一个开始配置工具和 MCP。</div>
      : <div className="agent-grid">{agents.map((agent) => (
        <article className="agent-card" key={agent.id}>
          <button className="agent-card-open" onClick={() => onSelect(agent)} aria-label={`管理 ${agent.name}`}>
            <div className={`large-agent-icon ${agent.accent}`}><Bot size={25} /></div>
            <div className="card-top"><span className="active-pill"><i /> ACTIVE</span><span>{agent.version}</span></div>
            <h3>{agent.name}</h3><p>{agent.model}</p>
            <div className="agent-stats"><span><strong>{agent.runs || '--'}</strong> runs</span><span><strong>{agent.success || '--'}%</strong> success</span></div>
            <div className="card-link">管理、试运行与对话 <ArrowUpRight size={15} /></div>
          </button>
          <button type="button" className="agent-manage-btn" onClick={() => onSelect(agent)}><Wrench size={14} />管理 Agent</button>
        </article>
      ))}</div>}
  </section>;
}

// 逐条覆盖与全局一致时等同于「跟随全局」，避免全局切换后残留无意义的覆盖标记。
function EmptyState({ active }) { const names = { evals: ['EVALUATION LAB', '评测与实验', '在这里比较 Agent 版本，追踪质量和成本。'], tools: ['PLUGIN REGISTRY', '工具与技能', '连接工具、技能和外部服务。'], memory: ['LONG-TERM MEMORY', '记忆库', '查看和检索 Agent 的长期语义记忆。'], iam: ['ACCESS CONTROL', '权限管理', '管理角色、授权和高风险操作审批。'] }; const [kicker, title, desc] = names[active]; return <section className="empty-state"><div className="empty-orbit"><Sparkles size={28} /></div><span className="section-kicker">{kicker}</span><h1>{title}</h1><p>{desc}</p><button className="primary-btn"><Plus size={16} />开始配置</button></section> }
