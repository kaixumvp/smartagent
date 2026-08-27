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

  useEffect(() => {
    if (!token) return;
    api('/agents').then((data) => {
      if (Array.isArray(data)) {
        setAgents(data.map((agent, index) => ({ ...agent, model: agent.config?.model || 'auto', runs: 0, success: 0, accent: ['coral', 'teal', 'gold'][index % 3] })));
      }
    }).catch(() => setNotice('后端暂不可用，当前显示演示数据'));
  }, [token]);

  async function api(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) },
    });
    if (!response.ok) throw new Error((await response.json()).error?.message || '请求失败');
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

  if (!token) return <Login onLogin={(value) => { localStorage.setItem('smartagent_token', value); setToken(value); }} />;

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
        {active === 'agents' && <AgentPage agents={agents} onSelect={(agent) => { setSelectedAgent(agent); setActive('overview'); }} />}
        {active === 'runs' && <section className="panel full-panel"><div className="panel-header"><div><span className="section-kicker">RUN HISTORY</span><h2>运行记录</h2></div><button className="secondary-btn" onClick={() => setNotice('运行列表已刷新')}><RefreshCw size={15} />刷新</button></div><RunTable runs={runs} onApprove={approve} detailed /></section>}
        {['evals', 'tools', 'memory', 'iam'].includes(active) && <EmptyState active={active} />}
      </div>
    </main>
  </div>;
}

function Login({ onLogin }) { const [value, setValue] = useState('demo-token'); return <div className="login-page"><div className="login-art"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-copy"><span className="eyebrow">AGENT OPERATIONS, REFINED</span><h1>让每一次<br /><em>智能运行</em><br />都清晰可见。</h1><p>一个安静、可靠的控制中心，连接你的 Agent、工具与数据。</p></div></div><div className="login-card"><div className="brand"><div className="brand-mark"><Sparkles size={17} /></div><span>smartagent</span></div><div className="login-title"><span className="section-kicker">WELCOME BACK</span><h2>进入控制台</h2><p>输入 API Token 以连接你的工作区。</p></div><label>API TOKEN<input value={value} onChange={(e) => setValue(e.target.value)} placeholder="粘贴你的 Bearer token" /></label><button className="primary-btn login-btn" onClick={() => onLogin(value || 'demo-token')}>进入工作台 <ArrowUpRight size={17} /></button><div className="login-note"><KeyRound size={14} /> Token 仅保存在当前浏览器</div></div></div> }
function NavItem({ icon, label, active, onClick, badge }) { return <button className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}>{icon}<span>{label}</span>{badge && <b>{badge}</b>}</button> }
function Metric({ icon, label, value, delta, tone }) { return <div className="metric"><div className={`metric-icon ${tone}`}>{icon}</div><div className="metric-copy"><span>{label}</span><strong>{value}</strong><small className={delta.startsWith('-') ? 'positive' : ''}>{delta}</small></div><div className="metric-spark">▰▂▅▃▇▆▂</div></div> }
function RunTable({ runs, onApprove, detailed }) { return <div className="run-table"><div className="table-head"><span>任务 / Agent</span><span>状态</span><span>时间</span><span>成本</span>{detailed && <span />}</div>{runs.map((run) => <div className="run-row" key={run.id}><div className="run-name"><div className="mini-agent"><Bot size={16} /></div><div><strong>{run.task}</strong><span>{run.agent} · {run.id}</span></div></div><div><Status status={run.status} />{run.status === 'awaiting_human' && <button className="approve-btn" onClick={() => onApprove(run)}><Check size={13} />审批</button>}</div><span className="muted">{run.time}</span><span className="cost">{run.cost}</span>{detailed && <button className="row-arrow"><ArrowUpRight size={16} /></button>}</div>)}</div> }
function Status({ status }) { const labels = { completed: '已完成', running: '运行中', awaiting_human: '待审批', failed: '失败' }; return <span className={`status ${status}`}><i />{labels[status] || status}</span> }
function AgentPage({ agents, onSelect }) { return <section><div className="page-heading compact"><div><div className="eyebrow">AGENT CATALOG</div><h1>你的 Agents</h1><p>管理版本、模型与执行入口。</p></div><button className="primary-btn"><Plus size={16} />新建 Agent</button></div><div className="agent-grid">{agents.map((agent) => <button className="agent-card" key={agent.id} onClick={() => onSelect(agent)}><div className={`large-agent-icon ${agent.accent}`}><Bot size={25} /></div><div className="card-top"><span className="active-pill"><i /> ACTIVE</span><span>{agent.version}</span></div><h3>{agent.name}</h3><p>{agent.model}</p><div className="agent-stats"><span><strong>{agent.runs || '--'}</strong> runs</span><span><strong>{agent.success || '--'}%</strong> success</span></div><div className="card-link">运行这个 Agent <ArrowUpRight size={15} /></div></button>)}</div></section> }
function EmptyState({ active }) { const names = { evals: ['EVALUATION LAB', '评测与实验', '在这里比较 Agent 版本，追踪质量和成本。'], tools: ['PLUGIN REGISTRY', '工具与技能', '连接工具、技能和外部服务。'], memory: ['LONG-TERM MEMORY', '记忆库', '查看和检索 Agent 的长期语义记忆。'], iam: ['ACCESS CONTROL', '权限管理', '管理角色、授权和高风险操作审批。'] }; const [kicker, title, desc] = names[active]; return <section className="empty-state"><div className="empty-orbit"><Sparkles size={28} /></div><span className="section-kicker">{kicker}</span><h1>{title}</h1><p>{desc}</p><button className="primary-btn"><Plus size={16} />开始配置</button></section> }

createRoot(document.getElementById('root')).render(<App />);
