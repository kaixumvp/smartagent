import React from 'react';
import { RefreshCw } from 'lucide-react';
import { Select } from 'antd';
import RunResultPanel from '../../components/RunResultPanel.jsx';
import { RunTable } from '../../components/ConsoleWidgets.jsx';

export default function RunHistoryPage({
  runs,
  agentOptions,
  filter,
  onFilterChange,
  onRefresh,
  loading,
  onApprove,
  selectedRun,
  onSelectRun,
  mdMode,
}) {
  const filteredRuns = filter === 'all' ? runs : runs.filter((run) => run.agent_id === filter);
  return (
    <section className="panel full-panel">
      <div className="panel-header">
        <div><span className="section-kicker">RUN HISTORY</span><h2>运行记录</h2></div>
        <div className="run-history-actions">
          <label htmlFor="run-agent-filter">所属 Agent</label>
          <Select
            id="run-agent-filter"
            aria-label="按所属 Agent 筛选运行记录"
            value={filter}
            options={agentOptions}
            showSearch
            optionFilterProp="label"
            onChange={onFilterChange}
          />
          <button className="secondary-btn" onClick={onRefresh} disabled={loading}>
            {loading ? <RefreshCw className="spin" size={15} /> : <RefreshCw size={15} />}
            {loading ? '加载中' : '刷新'}
          </button>
        </div>
      </div>
      <RunTable
        runs={filteredRuns}
        onApprove={onApprove}
        onSelect={onSelectRun}
        detailed
        loading={loading}
        emptyMessage={filter === 'all' ? undefined : '该 Agent 暂无运行记录。'}
      />
      {selectedRun && <RunResultPanel run={selectedRun} mdMode={mdMode} onClose={() => onSelectRun(null)} />}
    </section>
  );
}
