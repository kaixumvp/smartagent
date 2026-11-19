import React from 'react';
import { ArrowUpRight, Bot, Check, Plus, Sparkles, Wrench } from 'lucide-react';
import Status from './RunStatus.jsx';

export function NavItem({ icon, label, active, onClick, badge, href }) {
  if (href) {
    return (
      <a className={`nav-item ${active ? 'active' : ''}`} href={href}>
        {icon}<span>{label}</span>{badge && <b>{badge}</b>}
      </a>
    );
  }

  return (
    <button className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}>
      {icon}<span>{label}</span>{badge && <b>{badge}</b>}
    </button>
  );
}

export function Metric({ icon, label, value, delta, tone }) {
  return (
    <div className="metric">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div className="metric-copy">
        <span>{label}</span><strong>{value}</strong>
        <small className={delta.startsWith('-') ? 'positive' : ''}>{delta}</small>
      </div>
      <div className="metric-spark">▰▂▅▃▇▆▂</div>
    </div>
  );
}

export function RunTable({ runs, onApprove, onSelect, detailed, loading, emptyMessage }) {
  if (runs.length === 0) {
    return <div className="run-history-empty">{loading ? '正在加载运行记录…' : emptyMessage || '还没有运行记录。运行 Agent 后，记录会显示在这里。'}</div>;
  }
  return (
    <div className="run-table">
      <div className="table-head"><span>任务 / Agent</span><span>状态</span><span>时间</span><span>成本</span>{detailed && <span />}</div>
      {runs.map((run) => (
        <div className="run-row" key={run.id}>
          <div className="run-name"><div className="mini-agent"><Bot size={16} /></div><div><strong>{run.task}</strong><span>{run.agent} · {run.id}</span></div></div>
          <div><Status status={run.status} />{run.status === 'awaiting_human' && <button className="approve-btn" onClick={() => onApprove(run)}><Check size={13} />审批</button>}</div>
          <span className="muted">{run.time}</span><span className="cost">{run.cost}</span>
          {detailed && <button className="row-arrow" onClick={() => onSelect(run)} aria-label={`查看运行记录 ${run.id}`}><ArrowUpRight size={16} /></button>}
        </div>
      ))}
    </div>
  );
}

export function AgentPage({ agents, onSelect, onCreate }) {
  return (
    <section>
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
    </section>
  );
}

export function EmptyState({ active }) {
  const names = {
    evals: ['EVALUATION LAB', '评测与实验', '在这里比较 Agent 版本，追踪质量和成本。'],
    tools: ['PLUGIN REGISTRY', '工具与技能', '连接工具、技能和外部服务。'],
    memory: ['LONG-TERM MEMORY', '记忆库', '查看和检索 Agent 的长期语义记忆。'],
    iam: ['ACCESS CONTROL', '权限管理', '管理角色、授权和高风险操作审批。'],
  };
  const [kicker, title, description] = names[active];
  return (
    <section className="empty-state">
      <div className="empty-orbit"><Sparkles size={28} /></div>
      <span className="section-kicker">{kicker}</span><h1>{title}</h1><p>{description}</p>
      <button className="primary-btn"><Plus size={16} />开始配置</button>
    </section>
  );
}
