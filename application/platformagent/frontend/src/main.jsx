import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity, ArrowUpRight, Bot, Check, ChevronDown, CircleDollarSign,
  Clock3, Command, Database, Gauge, KeyRound, LayoutDashboard,
  LogOut, Play, Plus, RefreshCw, Search, ShieldCheck, Sparkles,
  Terminal, UserRound, X, Zap,
} from 'lucide-react';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || '/v1';

const demoAgents = [
  { id: 'agent_support', name: '客服协作员', version: 'v1.4', status: 'active', model: 'deepseek-chat', runs: 1284, success: 96, accent: 'coral' },
  { id: 'agent_ops', name: '运营分析师', version: 'v2.1', status: 'active', model: 'gpt-4o-mini', runs: 876, success: 92, accent: 'teal' },
  { id: 'agent_research', name: '研究助理', version: 'v0.9', status: 'active', model: 'deepseek-chat', runs: 438, success: 89, accent: 'gold' },
];

const demoRuns = [
  { id: 'run_8f2a', agent: '客服协作员', task: '整理本周退款政策的变化，并给出客服话术', status: 'completed', time: '刚刚', cost: '$0.0048' },
  { id: 'run_7c11', agent: '运营分析师', task: '分析近 30 天的转化漏斗', status: 'awaiting_human', time: '8 分钟前', cost: '$0.0121' },
  { id: 'run_6aa4', agent: '研究助理', task: '对比三份竞品报告中的定价策略', status: 'completed', time: '昨天', cost: '$0.0086' },
];

function App() {
  const [token, setToken] = useState(localStorage.getItem('smartagent_token') || '');
  const [active, setActive] = useState('overview');
  const [agents, setAgents] = useState(demoAgents);
  const [runs, setRuns] = useState(demoRuns);
  const [selectedAgent, setSelectedAgent] = useState(demoAgents[0]);
  const [task, setTask] = useState('');
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

  useEffect(() => {
    if (!token) return;
    api('/agents').then((data) => {
      if (Array.isArray(data)) {
        setAgents(data.map((agent, index) => ({ ...agent, model: agent.config?.model || 'auto', runs: 0, success: 0, accent: ['coral', 'teal', 'gold'][index % 3] })));
      }
    }).catch((error) => {
      if (error.status === 401) {
        localStorage.removeItem('smartagent_token');
        setToken('');
        return;
      }
      setNotice('后端暂不可用，当前显示演示数据');
    });
    // fetch tools and skills for plugin configuration
    api('/tools').then((data) => { if (Array.isArray(data)) setToolsList(data); }).catch(() => {});
    api('/skills').then((data) => { if (Array.isArray(data)) setSkillsList(data); }).catch(() => {});
  }, [token]);

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

  async function executeTask() {
    if (!task.trim()) return;
    setLoading(true);
    const optimistic = { id: `run_demo_${Date.now()}`, agent: selectedAgent.name, task, status: 'running', time: '刚刚', cost: '计算中' };
    setRuns((items) => [optimistic, ...items]);
    try {
      const result = await api(`/agents/${selectedAgent.id}/runs`, { method: 'POST', body: JSON.stringify({ input: task, stream: false }) });
      setRuns((items) => items.map((item) => item.id === optimistic.id ? { ...optimistic, id: result.run_id, status: result.status, cost: `$${Number(result.cost || 0).toFixed(4)}`, result: result.result, steps: result.steps } : item));
      setNotice(result.status === 'awaiting_human' ? '任务需要人工审批，请在运行列表中处理' : '任务已完成');
    } catch (error) {
      setRuns((items) => items.map((item) => item.id === optimistic.id ? { ...item, status: 'failed' } : item));
      setNotice(error.message);
    } finally { setLoading(false); setTask(''); }
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
      <header className="topbar"><div className="crumb"><span>工作台</span><span>/</span><strong>{active === 'overview' ? '总览' : active === 'agents' ? 'Agents' : '运行记录'}</strong></div><div className="top-actions"><button className="icon-btn" title="搜索"><Search size={18} /></button><button className="icon-btn" title="快捷键"><Command size={17} /></button><div className="notification"><span /></div><div className="top-avatar">AD</div></div></header>
      {notice && <div className="notice"><Check size={15} />{notice}<button onClick={() => setNotice('')}><X size={15} /></button></div>}
      <div className="content-wrap">
        <section className="page-heading"><div><div className="eyebrow">THURSDAY, AUGUST 27, 2026</div><h1>早上好，Admin <span>。</span></h1><p>这里是你的 Agent 运行控制中心。</p></div><button className="secondary-btn" onClick={() => setNotice('数据已刷新')}><RefreshCw size={16} />刷新数据</button></section>
        {active === 'overview' && <><section className="metrics"><Metric icon={<Zap />} label="今日运行" value="184" delta="+18.6%" tone="coral" /><Metric icon={<CircleDollarSign />} label="本月成本" value="$42.68" delta="-8.2%" tone="teal" /><Metric icon={<Gauge />} label="平均成功率" value="94.2%" delta="+2.4%" tone="gold" /><Metric icon={<Clock3 />} label="平均响应" value="2.8s" delta="-0.6s" tone="lavender" /></section><section className="workspace-grid"><div className="panel run-panel"><div className="panel-header"><div><span className="section-kicker">QUICK ACTION</span><h2>运行一个 Agent</h2></div><span className="live-badge"><span />LIVE</span></div><div className="agent-picker"><div className={`agent-icon ${selectedAgent.accent}`}><Bot size={20} /></div><div className="agent-choice"><span>选择 Agent</span><strong>{selectedAgent.name}</strong></div><select value={selectedAgent.id} onChange={(e) => setSelectedAgent(agents.find((a) => a.id === e.target.value) || selectedAgent)}>{agents.map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}</select><ChevronDown size={16} /></div><textarea value={task} onChange={(e) => setTask(e.target.value)} placeholder="输入你想让 Agent 完成的任务..." /><div className="run-footer"><span><Sparkles size={15} />支持工具调用与长期记忆</span><button className="primary-btn" onClick={executeTask} disabled={loading}>{loading ? <RefreshCw className="spin" size={16} /> : <Play size={16} fill="currentColor" />} {loading ? '执行中' : '开始运行'}</button></div></div><div className="panel activity-panel"><div className="panel-header"><div><span className="section-kicker">SYSTEM PULSE</span><h2>实时状态</h2></div><button className="more-btn">•••</button></div><div className="pulse-chart"><div className="chart-grid" /><svg viewBox="0 0 500 170" preserveAspectRatio="none"><path d="M0 140 C35 126 38 78 70 95 S105 138 135 105 S175 32 205 67 S230 130 258 107 S282 85 310 95 S335 142 360 110 S385 55 410 76 S435 112 456 84 S480 32 500 47" fill="none" stroke="#e45c4b" strokeWidth="3" /></svg><div className="chart-labels"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>现在</span></div></div><div className="pulse-footer"><span><i className="legend-dot coral-dot" />请求量</span><strong>1,284 <small>requests</small></strong></div></div></section><section className="panel recent-panel"><div className="panel-header"><div><span className="section-kicker">LATEST ACTIVITY</span><h2>最近运行</h2></div><button className="text-btn" onClick={() => setActive('runs')}>查看全部 <ArrowUpRight size={15} /></button></div><RunTable runs={runs.slice(0, 3)} onApprove={approve} /></section></>}
        {active === 'agents' && <AgentPage agents={agents} onSelect={(agent) => { setSelectedAgent(agent); setActive('overview'); }} onCreate={() => setShowCreateAgent(true)} />}
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
                    for (const s of newAgentSkills) {
                      const [name, ver] = s.split('@');
                      plugins.push({ type: 'skill', ref: `skill:${name}@${ver}` });
                    }
                    const body = { name: newAgentName.trim(), version: newAgentVersion || '1', config: { plugins } };
                    const result = await api('/agents', { method: 'POST', body: JSON.stringify(body) });
                    setAgents((prev) => [{ ...result, model: result.config?.model || 'auto', runs: 0, success: 0, accent: 'coral' }, ...prev]);
                    setNotice('Agent 已创建');
                    setShowCreateAgent(false);
                    setNewAgentName('');
                    setNewAgentVersion('1');
                    setNewAgentTools([]);
                    setNewAgentSkills([]);
                  } catch (err) {
                    setNotice(err.message || '创建 Agent 失败');
                  } finally { setCreatingAgent(false); }
                }} disabled={creatingAgent}>{creatingAgent ? '创建中...' : '创建'}</button>
              </div>
            </div>
          </div>
        )}
        {active === 'runs' && <section className="panel full-panel"><div className="panel-header"><div><span className="section-kicker">RUN HISTORY</span><h2>运行记录</h2></div><button className="secondary-btn" onClick={() => setNotice('运行列表已刷新')}><RefreshCw size={15} />刷新</button></div><RunTable runs={runs} onApprove={approve} detailed /></section>}
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
        {['evals', 'memory', 'iam'].includes(active) && <EmptyState active={active} />}

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
                  // build parameters object from list
                  const params = {};
                  for (const p of newToolParametersList) { if (p.name.trim()) params[p.name.trim()] = { type: p.type, description: p.description || '' }; }
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
function RunTable({ runs, onApprove, detailed }) { return <div className="run-table"><div className="table-head"><span>任务 / Agent</span><span>状态</span><span>时间</span><span>成本</span>{detailed && <span />}</div>{runs.map((run) => <div className="run-row" key={run.id}><div className="run-name"><div className="mini-agent"><Bot size={16} /></div><div><strong>{run.task}</strong><span>{run.agent} · {run.id}</span></div></div><div><Status status={run.status} />{run.status === 'awaiting_human' && <button className="approve-btn" onClick={() => onApprove(run)}><Check size={13} />审批</button>}</div><span className="muted">{run.time}</span><span className="cost">{run.cost}</span>{detailed && <button className="row-arrow"><ArrowUpRight size={16} /></button>}</div>)}</div> }
function Status({ status }) { const labels = { completed: '已完成', running: '运行中', awaiting_human: '待审批', failed: '失败' }; return <span className={`status ${status}`}><i />{labels[status] || status}</span> }
function AgentPage({ agents, onSelect, onCreate }) { return <section><div className="page-heading compact"><div><div className="eyebrow">AGENT CATALOG</div><h1>你的 Agents</h1><p>管理版本、模型与执行入口。</p></div><button className="primary-btn" onClick={onCreate}><Plus size={16} />新建 Agent</button></div><div className="agent-grid">{agents.map((agent) => <button className="agent-card" key={agent.id} onClick={() => onSelect(agent)}><div className={`large-agent-icon ${agent.accent}`}><Bot size={25} /></div><div className="card-top"><span className="active-pill"><i /> ACTIVE</span><span>{agent.version}</span></div><h3>{agent.name}</h3><p>{agent.model}</p><div className="agent-stats"><span><strong>{agent.runs || '--'}</strong> runs</span><span><strong>{agent.success || '--'}%</strong> success</span></div><div className="card-link">运行这个 Agent <ArrowUpRight size={15} /></div></button>)}</div></section> }
function EmptyState({ active }) { const names = { evals: ['EVALUATION LAB', '评测与实验', '在这里比较 Agent 版本，追踪质量和成本。'], tools: ['PLUGIN REGISTRY', '工具与技能', '连接工具、技能和外部服务。'], memory: ['LONG-TERM MEMORY', '记忆库', '查看和检索 Agent 的长期语义记忆。'], iam: ['ACCESS CONTROL', '权限管理', '管理角色、授权和高风险操作审批。'] }; const [kicker, title, desc] = names[active]; return <section className="empty-state"><div className="empty-orbit"><Sparkles size={28} /></div><span className="section-kicker">{kicker}</span><h1>{title}</h1><p>{desc}</p><button className="primary-btn"><Plus size={16} />开始配置</button></section> }

createRoot(document.getElementById('root')).render(<App />);
