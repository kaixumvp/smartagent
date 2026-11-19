import React from 'react';
import {
  Bot, ChevronDown, CircleDollarSign, Clock3, Gauge, Play, RefreshCw, Sparkles, Zap,
} from 'lucide-react';
import RunResultPanel from '../../components/RunResultPanel.jsx';
import { Metric } from '../../components/ConsoleWidgets.jsx';

export default function OverviewPage({
  agents,
  selectedAgent,
  onSelectAgent,
  task,
  onTaskChange,
  onExecute,
  loading,
  run,
  mdMode,
  onCloseRun,
}) {
  return (
    <>
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
            <select value={selectedAgent.id} onChange={(event) => onSelectAgent(event.target.value)}>
              {agents.map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}
            </select>
            <ChevronDown size={16} />
          </div>
          <textarea value={task} onChange={(event) => onTaskChange(event.target.value)} placeholder="输入任务，试运行 Agent 并查看执行结果…" />
          <div className="run-footer">
            <span><Sparkles size={15} />支持工具调用与长期记忆</span>
            <button className="primary-btn" onClick={onExecute} disabled={loading || !task.trim() || !selectedAgent?.id}>
              {loading ? <RefreshCw className="spin" size={16} /> : <Play size={16} fill="currentColor" />}
              {loading ? '执行中' : '开始测试'}
            </button>
          </div>
          {run && <RunResultPanel run={run} mdMode={mdMode} onClose={onCloseRun} className="overview-run-result" />}
        </div>
      </section>
    </>
  );
}
