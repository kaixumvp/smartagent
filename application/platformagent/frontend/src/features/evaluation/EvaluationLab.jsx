import { useEffect, useState } from 'react';
import { Play, Plus, RefreshCw, X } from 'lucide-react';
import Status from '../../components/RunStatus.jsx';

export default function EvaluationLab({ api, agents, onNotice }) {
  const [tab, setTab] = useState('evaluations');
  const [goldenSets, setGoldenSets] = useState([]);
  const [evaluations, setEvaluations] = useState([]);
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showDatasetForm, setShowDatasetForm] = useState(false);
  const [showEvaluationForm, setShowEvaluationForm] = useState(null);
  const [showExperimentForm, setShowExperimentForm] = useState(false);
  const [selectedDataset, setSelectedDataset] = useState(null);
  const [selectedEvaluation, setSelectedEvaluation] = useState(null);
  const [selectedExperiment, setSelectedExperiment] = useState(null);
  const [experimentResults, setExperimentResults] = useState(null);
  const [datasetName, setDatasetName] = useState('');
  const [datasetDescription, setDatasetDescription] = useState('');
  const [datasetCases, setDatasetCases] = useState([{ task: '', reference: '' }]);
  const [evaluationAgent, setEvaluationAgent] = useState('');
  const [judgeType, setJudgeType] = useState('llm');
  const [experimentName, setExperimentName] = useState('');
  const [experimentDescription, setExperimentDescription] = useState('');
  const [entryAgent, setEntryAgent] = useState('');
  const [variants, setVariants] = useState([
    { label: 'A', agent_id: '', weight: 50 },
    { label: 'B', agent_id: '', weight: 50 },
  ]);
  const activeAgents = agents.filter((agent) => agent.status === 'active');
  const weightTotal = variants.reduce((total, item) => total + Number(item.weight || 0), 0);
  const agentName = (id) => agents.find((agent) => agent.id === id)?.name || id;

  async function refresh() {
    setLoading(true);
    try {
      const [sets, evals, exps] = await Promise.all([
        api('/golden-sets'),
        api('/evaluations'),
        api('/experiments'),
      ]);
      setGoldenSets(sets);
      setEvaluations(evals);
      setExperiments(exps);
    } catch (error) {
      onNotice(`评测数据加载失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    if (!evaluations.some((item) => ['queued', 'running'].includes(item.status))) return undefined;
    const timer = window.setInterval(async () => {
      try {
        setEvaluations(await api('/evaluations'));
      } catch (error) {
        onNotice(`刷新评测状态失败：${error.message}`);
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [evaluations]);

  useEffect(() => {
    if (!selectedEvaluation || !['queued', 'running'].includes(selectedEvaluation.status)) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const evaluation = await api(`/evaluations/${selectedEvaluation.id}`);
        const dataset = await api(`/golden-sets/${evaluation.golden_set_id}`);
        setSelectedEvaluation({ ...evaluation, cases: dataset.cases });
      } catch (error) {
        onNotice(`刷新评测详情失败：${error.message}`);
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [selectedEvaluation?.id, selectedEvaluation?.status]);

  async function openEvaluation(item) {
    try {
      const evaluation = await api(`/evaluations/${item.id}`);
      const dataset = await api(`/golden-sets/${evaluation.golden_set_id}`);
      setSelectedEvaluation({ ...evaluation, cases: dataset.cases });
    } catch (error) {
      onNotice(`加载评测详情失败：${error.message}`);
    }
  }

  async function openDataset(item) {
    try {
      setSelectedDataset(await api(`/golden-sets/${item.id}`));
    } catch (error) {
      onNotice(`加载数据集详情失败：${error.message}`);
    }
  }

  async function openExperiment(item) {
    setSelectedExperiment(item);
    setExperimentResults(null);
    try {
      setExperimentResults(await api(`/experiments/${item.id}/results`));
    } catch (error) {
      onNotice(`加载实验结果失败：${error.message}`);
    }
  }

  async function createDataset(event) {
    event.preventDefault();
    const cases = datasetCases.filter((item) => item.task.trim()).map((item) => ({
      task: item.task.trim(),
      ...(item.reference.trim() ? { reference: item.reference.trim() } : {}),
    }));
    if (!datasetName.trim() || cases.length === 0) {
      onNotice('请填写数据集名称和至少一个测试任务');
      return;
    }
    setSaving(true);
    try {
      await api('/golden-sets', {
        method: 'POST',
        body: JSON.stringify({ name: datasetName.trim(), description: datasetDescription.trim(), cases }),
      });
      setDatasetName('');
      setDatasetDescription('');
      setDatasetCases([{ task: '', reference: '' }]);
      setShowDatasetForm(false);
      await refresh();
      onNotice('测试数据集已创建');
    } catch (error) {
      onNotice(`创建数据集失败：${error.message}`);
    } finally {
      setSaving(false);
    }
  }

  async function startEvaluation(event) {
    event.preventDefault();
    if (!evaluationAgent || !showEvaluationForm) return;
    setSaving(true);
    try {
      await api('/evaluations', {
        method: 'POST',
        body: JSON.stringify({
          golden_set_id: showEvaluationForm.id,
          agent_id: evaluationAgent,
          judge_type: judgeType,
        }),
      });
      setShowEvaluationForm(null);
      await refresh();
      onNotice('评测已提交，后台运行完成后会自动更新');
    } catch (error) {
      onNotice(`启动评测失败：${error.message}`);
    } finally {
      setSaving(false);
    }
  }

  async function createExperiment(event) {
    event.preventDefault();
    if (new Set(variants.map((item) => item.agent_id)).size < 2 || variants.some((item) => !item.agent_id)) {
      onNotice('请选择两个不同的 Agent 作为实验版本');
      return;
    }
    if (Math.abs(weightTotal - 100) > 0.001) {
      onNotice('两个版本的流量权重总和必须为 100%');
      return;
    }
    setSaving(true);
    try {
      await api('/experiments', {
        method: 'POST',
        body: JSON.stringify({
          name: experimentName.trim(),
          description: experimentDescription.trim(),
          entry_agent_id: entryAgent,
          sticky_key: 'user',
          variants: variants.map((item) => ({ ...item, weight: Number(item.weight) })),
        }),
      });
      setShowExperimentForm(false);
      setExperimentName('');
      setExperimentDescription('');
      await refresh();
      onNotice('A/B 实验已创建');
    } catch (error) {
      onNotice(`创建实验失败：${error.message}`);
    } finally {
      setSaving(false);
    }
  }

  async function changeExperimentStatus(item, action) {
    try {
      await api(`/experiments/${item.id}/status`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      await refresh();
      onNotice(action === 'start' ? '实验已启动' : '实验已停止');
    } catch (error) {
      onNotice(`更新实验状态失败：${error.message}`);
    }
  }

  return <section className="evaluation-lab">
    <div className="panel eval-panel">
      <div className="panel-header">
        <div><span className="section-kicker">EVALUATION LAB</span><h2>评测与实验</h2><p className="eval-description">用固定测试集验证 Agent 质量，或通过 A/B 实验比较线上表现。</p></div>
        <button className="secondary-btn" onClick={refresh} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : ''} />刷新</button>
      </div>
      <div className="eval-tabs">
        {[['evaluations', '评测记录'], ['datasets', `测试数据集 · ${goldenSets.length}`], ['experiments', `A/B 实验 · ${experiments.length}`]].map(([key, label]) => (
          <button key={key} className={`text-btn ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}>{label}</button>
        ))}
        <span className="eval-tabs-spacer" />
        {tab === 'datasets' && <button className="primary-btn" onClick={() => setShowDatasetForm(true)}><Plus size={14} />新建数据集</button>}
        {tab === 'experiments' && <button className="primary-btn" onClick={() => { setEntryAgent(activeAgents[0]?.id || ''); setVariants([{ label: 'A', agent_id: activeAgents[0]?.id || '', weight: 50 }, { label: 'B', agent_id: activeAgents[1]?.id || '', weight: 50 }]); setShowExperimentForm(true); }} disabled={activeAgents.length < 2}><Plus size={14} />新建实验</button>}
      </div>
      {tab === 'evaluations' && <div className="eval-list">
        {evaluations.map((item) => <button className="eval-row" key={item.id} onClick={() => openEvaluation(item)}>
          <div className="eval-row-main"><strong>{agentName(item.agent_id)}</strong><span>数据集 {goldenSets.find((set) => set.id === item.golden_set_id)?.name || item.golden_set_id} · {new Date(item.created_at).toLocaleString()}</span></div>
          <span className={`eval-status ${item.status}`}>{item.status}</span>
          <span>{item.total ? `${item.passed}/${item.total} 通过` : '等待结果'}</span>
          <strong>{item.total ? `${Math.round(item.avg_score * 100)}%` : '—'}</strong>
        </button>)}
        {!evaluations.length && <div className="eval-empty">{loading ? '正在加载评测记录…' : '暂无评测记录。先创建测试数据集，再启动一次评测。'}</div>}
      </div>}
      {tab === 'datasets' && <div className="eval-card-grid">
        {goldenSets.map((item) => <article className="eval-card" key={item.id}>
          <div><span className="section-kicker">TEST DATASET</span><h3>{item.name}</h3><p>{item.description || '未填写说明'}</p><small>{item.status} · {new Date(item.created_at).toLocaleDateString()}</small></div>
          <div className="eval-card-actions"><button className="text-btn" onClick={() => openDataset(item)}>查看用例</button><button className="primary-btn" onClick={() => { setEvaluationAgent(activeAgents[0]?.id || ''); setShowEvaluationForm(item); }} disabled={!activeAgents.length}><Play size={13} />启动评测</button></div>
        </article>)}
        {!goldenSets.length && <div className="eval-empty">{loading ? '正在加载测试数据集…' : '还没有测试数据集。创建包含任务和参考答案的数据集后即可运行评测。'}</div>}
      </div>}
      {tab === 'experiments' && <div className="eval-card-grid">
        {experiments.map((item) => <article className="eval-card" key={item.id}>
          <div><span className={`eval-status ${item.status}`}>{item.status}</span><h3>{item.name}</h3><p>{item.description || '未填写说明'}</p><div className="experiment-variants">{item.variants.map((variant) => <span key={variant.label}>{variant.label}: {agentName(variant.agent_id)} · {variant.weight}%</span>)}</div></div>
          <div className="eval-card-actions"><button className="text-btn" onClick={() => openExperiment(item)}>查看结果</button>{item.status === 'running' ? <button className="secondary-btn" onClick={() => changeExperimentStatus(item, 'stop')}>停止</button> : item.status === 'draft' ? <button className="primary-btn" onClick={() => changeExperimentStatus(item, 'start')}>启动实验</button> : <span className="muted">已停止</span>}</div>
        </article>)}
        {!experiments.length && <div className="eval-empty">{loading ? '正在加载实验…' : activeAgents.length < 2 ? '至少需要两个已启用的 Agent 才能创建 A/B 实验。' : '暂无 A/B 实验。创建实验后，流量会按版本权重分配。'}</div>}
      </div>}
    </div>

    {selectedEvaluation && <div className="panel eval-detail">
      <div className="panel-header"><div><span className="section-kicker">EVALUATION RESULT</span><h2>{agentName(selectedEvaluation.agent_id)} · {selectedEvaluation.status}</h2></div><button className="icon-btn" onClick={() => setSelectedEvaluation(null)} aria-label="关闭评测详情"><X size={16} /></button></div>
      <div className="eval-summary"><span>通过 {selectedEvaluation.passed}/{selectedEvaluation.total}</span><span>平均分 {Math.round(selectedEvaluation.avg_score * 100)}%</span><span>成本 ${Number(selectedEvaluation.cost || 0).toFixed(4)}</span><span>Judge {selectedEvaluation.judge_type}</span></div>
      {selectedEvaluation.error && <p className="agent-run-error">{selectedEvaluation.error}</p>}
      <div className="eval-results">      {selectedEvaluation.results.map((result) => { const testCase = selectedEvaluation.cases?.find((item) => item.id === result.case_id); return <article key={result.case_id}><div><strong>{result.passed ? '通过' : '未通过'} · {Math.round(result.score * 100)}%</strong><span>{result.latency_ms ?? '—'} ms · ${Number(result.cost || 0).toFixed(4)}</span></div>{testCase?.task && <p><b>任务：</b>{testCase.task}</p>}{testCase?.reference && <p><b>参考答案：</b>{testCase.reference}</p>}{result.reason && <p><b>评分说明：</b>{result.reason}</p>}{result.error && <p className="agent-run-error">{result.error}</p>}{result.output && <pre>{result.output}</pre>}</article>; })}{!selectedEvaluation.results.length && <small>结果尚未生成，请稍后刷新。</small>}</div>
    </div>}

    {selectedDataset && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedDataset(null); }}>
      <div className="modal-card"><h3>{selectedDataset.name} · 测试用例</h3><p>{selectedDataset.description}</p><div className="eval-results">{selectedDataset.cases.map((item, index) => <article key={item.id}><strong>用例 {index + 1}</strong><p><b>任务：</b>{item.task}</p>{item.reference && <p><b>参考答案：</b>{item.reference}</p>}</article>)}</div><div className="modal-actions"><button className="secondary-btn" onClick={() => setSelectedDataset(null)}>关闭</button></div></div>
    </div>}

    {selectedExperiment && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedExperiment(null); }}>
      <div className="modal-card"><h3>{selectedExperiment.name} · 实验结果</h3><p>状态：{experimentResults?.status || selectedExperiment.status}</p><div className="eval-results">{experimentResults?.variants?.map((item) => <article key={item.variant}><strong>{item.variant} · {agentName(item.agent_id)}</strong><div className="eval-summary"><span>运行 {item.runs}</span><span>完成 {item.completed}</span><span>失败 {item.failed}</span><span>平均成本 ${Number(item.avg_cost || 0).toFixed(4)}</span><span>平均耗时 {Math.round(item.avg_latency_ms || 0)} ms</span><span>反馈评分 {item.avg_rating ?? '暂无'}</span></div></article>) || <small>正在加载结果…</small>}</div><div className="modal-actions"><button className="secondary-btn" onClick={() => setSelectedExperiment(null)}>关闭</button></div></div>
    </div>}

    {showDatasetForm && <div className="modal-backdrop"><form className="modal-card" onSubmit={createDataset}><h3>新建测试数据集</h3><label>数据集名称<input required value={datasetName} onChange={(event) => setDatasetName(event.target.value)} /></label><label>说明<input value={datasetDescription} onChange={(event) => setDatasetDescription(event.target.value)} /></label>{datasetCases.map((item, index) => <div className="eval-case-form" key={index}><strong>用例 {index + 1}</strong><label>测试任务<textarea required rows={2} value={item.task} onChange={(event) => setDatasetCases((items) => items.map((row, i) => i === index ? { ...row, task: event.target.value } : row))} /></label><label>参考答案（可选）<textarea rows={2} value={item.reference} onChange={(event) => setDatasetCases((items) => items.map((row, i) => i === index ? { ...row, reference: event.target.value } : row))} /></label>{datasetCases.length > 1 && <button type="button" className="text-btn" onClick={() => setDatasetCases((items) => items.filter((_, i) => i !== index))}>删除用例</button>}</div>)}<button type="button" className="text-btn" onClick={() => setDatasetCases((items) => [...items, { task: '', reference: '' }])}><Plus size={13} />添加用例</button><div className="modal-actions"><button type="button" className="secondary-btn" onClick={() => setShowDatasetForm(false)}>取消</button><button className="primary-btn" disabled={saving}>{saving ? '创建中…' : '创建数据集'}</button></div></form></div>}

    {showEvaluationForm && <div className="modal-backdrop"><form className="modal-card" onSubmit={startEvaluation}><h3>运行评测 · {showEvaluationForm.name}</h3><label>Agent<select required value={evaluationAgent} onChange={(event) => setEvaluationAgent(event.target.value)}><option value="">选择 Agent</option>{activeAgents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label><label>评分方式<select value={judgeType} onChange={(event) => setJudgeType(event.target.value)}><option value="llm">LLM Judge（语义评分）</option><option value="heuristic">Heuristic（规则评分）</option></select></label><div className="modal-actions"><button type="button" className="secondary-btn" onClick={() => setShowEvaluationForm(null)}>取消</button><button className="primary-btn" disabled={saving || !evaluationAgent}>{saving ? '提交中…' : '启动评测'}</button></div></form></div>}

    {showExperimentForm && <div className="modal-backdrop"><form className="modal-card" onSubmit={createExperiment}><h3>创建 A/B 实验</h3><label>实验名称<input required value={experimentName} onChange={(event) => setExperimentName(event.target.value)} /></label><label>说明<input value={experimentDescription} onChange={(event) => setExperimentDescription(event.target.value)} /></label><label>入口 Agent<select required value={entryAgent} onChange={(event) => setEntryAgent(event.target.value)}>{activeAgents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label>{variants.map((variant, index) => <div className="eval-variant-form" key={variant.label}><strong>版本 {variant.label}</strong><label>Agent<select required value={variant.agent_id} onChange={(event) => setVariants((items) => items.map((item, i) => i === index ? { ...item, agent_id: event.target.value } : item))}>{activeAgents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label><label>流量权重 (%)<input type="number" min="0" max="100" required value={variant.weight} onChange={(event) => setVariants((items) => items.map((item, i) => i === index ? { ...item, weight: event.target.value } : item))} /></label></div>)}<p className={`eval-weight-total ${Math.abs(weightTotal - 100) < 0.001 ? 'valid' : ''}`}>权重合计：{weightTotal}%（需为 100%）</p><div className="modal-actions"><button type="button" className="secondary-btn" onClick={() => setShowExperimentForm(false)}>取消</button><button className="primary-btn" disabled={saving || activeAgents.length < 2 || Math.abs(weightTotal - 100) > 0.001}>{saving ? '创建中…' : '创建实验'}</button></div></form></div>}
  </section>;
}

