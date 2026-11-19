import { X } from 'lucide-react';
import { MD_MODES } from '../constants.js';
import MarkdownText from './MarkdownText.jsx';
import Status from './RunStatus.jsx';

export default function RunResultPanel({ run, mdMode = MD_MODES.formatted, onClose, className = '' }) {
  return <section className={`run-result-panel ${className}`}>
    <div className="run-result-heading"><div><span className="section-kicker">RUN RESULT</span><strong>{run.run_id}</strong></div><button className="icon-btn" onClick={onClose} aria-label="关闭运行详情"><X size={15} /></button></div>
    <div className="run-result-meta"><Status status={run.status} /><span>{run.model || '默认模型'}</span><span>${Number(run.cost || 0).toFixed(4)}</span><span>{run.usage?.total_tokens || 0} tokens</span></div>
    {run.result && <div className={`run-result-answer ${mdMode === MD_MODES.formatted ? 'is-md' : ''}`}><MarkdownText content={run.result} mode={mdMode} /></div>}
    {run.error && <div className="agent-run-error">{run.error}</div>}
    <div className="run-result-steps"><strong>执行步骤 · {run.steps?.length || 0}</strong>
      {run.steps?.length ? run.steps.map((step) => <details key={`${run.run_id}-${step.seq}`}>
        <summary><span>#{step.seq} · {step.node}{step.action ? ` · ${step.action}` : ''}</span><span>{step.latency_ms ?? 0} ms</span></summary>
        {step.input && <pre>{JSON.stringify(step.input, null, 2)}</pre>}
        {step.output && <pre>{JSON.stringify(step.output, null, 2)}</pre>}
      </details>) : <small>没有可显示的执行步骤。</small>}
    </div>
  </section>;
}
