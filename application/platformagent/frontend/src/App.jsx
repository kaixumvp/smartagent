import React, { useEffect, useState } from 'react';
import {
  Activity, Bot, Check, ChevronDown, Command, Database, Gauge, LayoutDashboard,
  LogOut, RefreshCw, Search, ShieldCheck, Sparkles, Terminal, X,
} from 'lucide-react';
import { MD_MODES } from './constants.js';
import AgentCreationDialog from './features/agents/AgentCreationDialog.jsx';
import AgentDetailDialog from './features/agents/AgentDetailDialog.jsx';
import useAgentWorkspace from './features/agents/useAgentWorkspace.js';
import OverviewPage from './features/dashboard/OverviewPage.jsx';
import EvaluationLab from './features/evaluation/EvaluationLab.jsx';
import IamPage from './features/iam/IamPage.jsx';
import RunHistoryPage from './features/runs/RunHistoryPage.jsx';
import ToolsPage from './features/tools/ToolsPage.jsx';
import Login from './components/Login.jsx';
import { AgentPage, EmptyState, NavItem } from './components/ConsoleWidgets.jsx';

const API_BASE = import.meta.env.VITE_API_BASE || '/v1';
const MD_VIEW_KEY = 'smartagent_md_view';
// 原文模式即改造前的表现（CSS white-space: pre-wrap 原样回显），格式化模式交给 react-markdown。

function tokenClaims(token) {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(payload));
  } catch {
    return {};
  }
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
  const [runAgentFilter, setRunAgentFilter] = useState('all');
  const [selectedAgent, setSelectedAgent] = useState(demoAgents[0]);
  const [task, setTask] = useState('');
  const [overviewRun, setOverviewRun] = useState(null);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const [toolsList, setToolsList] = useState([]);
  const [skillsList, setSkillsList] = useState([]);
  const [capabilityProviders, setCapabilityProviders] = useState([]);
  const [capabilityTools, setCapabilityTools] = useState({});
  const [capabilityApiTools, setCapabilityApiTools] = useState([]);
  const [mdMode, setMdMode] = useState(() => (
    localStorage.getItem(MD_VIEW_KEY) === MD_MODES.raw ? MD_MODES.raw : MD_MODES.formatted
  ));
  const agentWorkspace = useAgentWorkspace({
    api,
    agents,
    setAgents,
    selectedAgent,
    setSelectedAgent,
    setRuns,
    loadCapabilityTools,
    setNotice,
  });
  const {
    agent: agentDetail,
    runs: agentRuns,
    messages: agentChatMessages,
    chatInput: agentChatInput,
    chatBusy: agentChatBusy,
    saving: agentSaving,
    deleting: agentDeleting,
    deletingRunId,
    selectedRun,
    setChatInput: setAgentChatInput,
    setSelectedRun,
    setMessageMdView,
    openAgent: openAgentDetails,
    unbindPlugin: unbindAgentPlugin,
    addPlugins: addAgentPlugins,
    deleteAgent,
    deleteRun: deleteAgentRun,
    sendMessage: sendAgentMessage,
  } = agentWorkspace;
  const runAgentOptions = [
    { value: 'all', label: '所有 Agent' },
    ...Array.from(new Map([
      ...agents.map((agent) => [agent.id, { value: agent.id, label: agent.name }]),
      ...runs
        .filter((run) => run.agent_id)
        .map((run) => [run.agent_id, { value: run.agent_id, label: run.agent || run.agent_id }]),
    ]).values()),
  ];

  useEffect(() => { localStorage.setItem(MD_VIEW_KEY, mdMode); }, [mdMode]);

  useEffect(() => {
    if (!notice) return undefined;
    const timeoutId = window.setTimeout(() => setNotice(''), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [notice]);

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
    const optimistic = { id: `run_demo_${Date.now()}`, agent_id: selectedAgent.id, agent: selectedAgent.name, task, status: 'running', time: '刚刚', cost: '计算中' };
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
  const principal = tokenClaims(token);

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
        {active === 'overview' && (
          <OverviewPage
            agents={agents}
            selectedAgent={selectedAgent}
            onSelectAgent={(agentId) => {
              setSelectedAgent(agents.find((agent) => agent.id === agentId) || selectedAgent);
              setOverviewRun(null);
            }}
            task={task}
            onTaskChange={setTask}
            onExecute={executeTask}
            loading={loading}
            run={overviewRun}
            mdMode={mdMode}
            onCloseRun={() => setOverviewRun(null)}
          />
        )}
        {active === 'agents' && <AgentPage agents={agents} onSelect={openAgentDetails} onCreate={() => setShowCreateAgent(true)} />}
        <AgentCreationDialog
          open={showCreateAgent}
          api={api}
          tools={toolsList}
          skills={skillsList}
          providers={capabilityProviders}
          providerTools={capabilityTools}
          apiTools={capabilityApiTools}
          onLoadProviderTools={loadCapabilityTools}
          onCreated={(result) => {
            const created = { ...result, model: result.config?.model || 'auto', runs: 0, success: 0, accent: 'coral' };
            setAgents((current) => [created, ...current]);
            setSelectedAgent(created);
            setNotice('Agent 已创建');
            setShowCreateAgent(false);
          }}
          onClose={() => setShowCreateAgent(false)}
          onNotice={setNotice}
        />
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
            onClose={() => agentWorkspace.setAgent(null)}
            onUnbind={unbindAgentPlugin}
            onAddPlugins={addAgentPlugins}
            onDelete={deleteAgent}
            onDeleteRun={deleteAgentRun}
            onSend={sendAgentMessage}
            onSelectRun={setSelectedRun}
          />
        )}
        {active === 'runs' && (
          <RunHistoryPage
            runs={runs}
            agentOptions={runAgentOptions}
            filter={runAgentFilter}
            onFilterChange={setRunAgentFilter}
            onRefresh={() => loadRuns()}
            loading={runsLoading}
            onApprove={approve}
            selectedRun={selectedRun}
            onSelectRun={setSelectedRun}
            mdMode={mdMode}
          />
        )}
        {active === 'tools' && (
          <ToolsPage
            api={api}
            tools={toolsList}
            skills={skillsList}
            onToolCreated={(tool) => {
              setToolsList((current) => [tool, ...current]);
              setNotice('Tool 已创建');
            }}
            onSkillCreated={(skill) => {
              setSkillsList((current) => [skill, ...current]);
              setNotice('Skill 已创建');
            }}
            onNotice={setNotice}
          />
        )}
        {active === 'evals' && <EvaluationLab api={api} agents={agents} onNotice={setNotice} />}
        {active === 'memory' && <EmptyState active={active} />}
        {active === 'iam' && (
          <IamPage api={api} token={token} tenantId={principal.tenant_id || ''} onNotice={setNotice} />
        )}

      </div>
    </main>
  </div>;
}
