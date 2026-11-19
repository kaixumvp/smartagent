import { useState } from 'react';
import { getAgentPlugins } from './agentPlugins.js';

function createClientId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const random = Math.floor(Math.random() * 16);
    return (char === 'x' ? random : (random & 0x3) | 0x8).toString(16);
  });
}

export default function useAgentWorkspace({
  api,
  agents,
  setAgents,
  selectedAgent,
  setSelectedAgent,
  setRuns: setConsoleRuns,
  loadCapabilityTools,
  setNotice,
}) {
  const [agent, setAgent] = useState(null);
  const [runs, setRuns] = useState([]);
  const [conversationId, setConversationId] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deletingRunId, setDeletingRunId] = useState('');
  const [selectedRun, setSelectedRun] = useState(null);

  // An undefined message-level mode keeps the global Markdown preference in effect.
  function setMessageMdView(messageId, mdView) {
    setMessages((current) => current.map((message) => (
      message.id === messageId ? { ...message, mdView } : message
    )));
  }

  async function openAgent(agentToOpen) {
    setAgent(agentToOpen);
    setSelectedAgent(agentToOpen);
    setRuns([]);
    const conversationKey = `smartagent_conversation_${agentToOpen.id}`;
    const nextConversationId = localStorage.getItem(conversationKey) || createClientId();
    localStorage.setItem(conversationKey, nextConversationId);
    setConversationId(nextConversationId);
    setChatInput('');
    setMessages([]);
    setSelectedRun(null);
    try {
      const history = await api(`/agents/${agentToOpen.id}/runs`);
      const agentHistory = Array.isArray(history) ? history : [];
      setRuns(agentHistory);
      setMessages(agentHistory
        .filter((run) => run.conversation_id === nextConversationId)
        .reverse()
        .flatMap((run) => [
          { id: createClientId(), role: 'user', content: run.input },
          ...(run.result ? [{ id: createClientId(), role: 'assistant', content: run.result, run }] : []),
        ]));
    } catch (error) {
      setNotice(`加载 Agent 运行记录失败：${error.message}`);
    }
    const plugins = getAgentPlugins(agentToOpen.config);
    const providerIds = [...new Set(plugins
      .filter((plugin) => ['capability_provider', 'capability_tool'].includes(plugin.type))
      .map((plugin) => plugin.type === 'capability_provider' ? plugin.ref : plugin.ref?.split('/')[0])
      .filter(Boolean))];
    await Promise.allSettled(providerIds.map(loadCapabilityTools));
  }

  function updateAgent(nextAgent, result) {
    const next = { ...nextAgent, ...result, model: result.config?.model || 'auto' };
    setAgent(next);
    setAgents((current) => current.map((item) => item.id === result.id
      ? { ...item, ...result, model: result.config?.model || 'auto' }
      : item));
  }

  async function unbindPlugin(index) {
    if (!agent) return;
    const plugins = getAgentPlugins(agent.config).filter((_, itemIndex) => itemIndex !== index);
    const config = { ...agent.config, plugins };
    delete config.tools;
    setSaving(true);
    try {
      const updated = await api(`/agents/${agent.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ config }),
      });
      updateAgent(agent, updated);
      setNotice('已解绑并保存 Agent 工具配置');
    } catch (error) {
      setNotice(`解绑失败：${error.message}`);
    } finally {
      setSaving(false);
    }
  }

  async function addPlugins(pluginsToAdd) {
    if (!agent || pluginsToAdd.length === 0) return;
    const plugins = [...getAgentPlugins(agent.config)];
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
    const config = { ...(agent.config || {}), plugins };
    delete config.tools;
    setSaving(true);
    try {
      const updated = await api(`/agents/${agent.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ config }),
      });
      updateAgent(agent, updated);
      setNotice('已添加并保存 Agent 能力');
      return true;
    } catch (error) {
      setNotice(`添加能力失败：${error.message}`);
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function deleteAgent() {
    if (!agent || !window.confirm(`确定删除 Agent「${agent.name}」吗？运行记录会保留。`)) return;
    setDeleting(true);
    try {
      await api(`/agents/${agent.id}`, { method: 'DELETE' });
      const remaining = agents.filter((item) => item.id !== agent.id);
      setAgents(remaining);
      localStorage.removeItem(`smartagent_conversation_${agent.id}`);
      if (selectedAgent.id === agent.id && remaining.length) setSelectedAgent(remaining[0]);
      if (selectedAgent.id === agent.id && !remaining.length) setSelectedAgent({ id: '', name: '暂无 Agent', accent: 'coral' });
      setAgent(null);
      setNotice('Agent 已删除，历史运行记录已保留');
    } catch (error) {
      setNotice(`删除 Agent 失败：${error.message}`);
    } finally {
      setDeleting(false);
    }
  }

  async function deleteRun(run) {
    if (!agent || !window.confirm(`确定删除这条运行记录吗？\n${run.input}`)) return;
    setDeletingRunId(run.run_id);
    try {
      await api(`/runs/${run.run_id}`, { method: 'DELETE' });
      setRuns((current) => current.filter((item) => item.run_id !== run.run_id));
      setConsoleRuns((current) => current.filter((item) => item.id !== run.run_id));
      setSelectedRun((current) => current?.run_id === run.run_id ? null : current);
      setMessages((current) => {
        const assistantIndex = current.findIndex((item) => item.run?.run_id === run.run_id);
        if (assistantIndex < 0) return current;
        const userIndex = current[assistantIndex - 1]?.role === 'user' ? assistantIndex - 1 : -1;
        return current.filter((_, index) => index !== assistantIndex && index !== userIndex);
      });
      setNotice('运行记录已删除');
    } catch (error) {
      setNotice(`删除运行记录失败：${error.message}`);
    } finally {
      setDeletingRunId('');
    }
  }

  async function sendMessage(event) {
    event?.preventDefault();
    const input = chatInput.trim();
    if (!input || !agent || chatBusy) return;
    setMessages((current) => [...current, { id: createClientId(), role: 'user', content: input }]);
    setChatInput('');
    setChatBusy(true);
    try {
      const result = await api(`/agents/${agent.id}/runs`, {
        method: 'POST',
        body: JSON.stringify({ input, stream: false, conversation_id: conversationId }),
      });
      setMessages((current) => [...current, {
        id: createClientId(),
        role: 'assistant',
        content: result.result || (result.status === 'awaiting_human' ? '运行正在等待人工审批。' : 'Agent 没有返回文本结果。'),
        run: result,
      }]);
      setRuns((current) => [result, ...current.filter((run) => run.run_id !== result.run_id)].slice(0, 20));
      setConsoleRuns((current) => [{
        id: result.run_id,
        agent_id: agent.id,
        agent: agent.name,
        task: input,
        status: result.status,
        time: '刚刚',
        cost: `$${Number(result.cost || 0).toFixed(4)}`,
        result: result.result,
        steps: result.steps,
      }, ...current.filter((run) => run.id !== result.run_id)]);
      setSelectedRun(result);
      setNotice(result.status === 'awaiting_human' ? '运行需要人工审批，详情已显示在对话中' : '试运行已完成');
    } catch (error) {
      setMessages((current) => [...current, { id: createClientId(), role: 'error', content: error.message }]);
      setNotice(`试运行失败：${error.message}`);
    } finally {
      setChatBusy(false);
    }
  }

  return {
    agent,
    runs,
    messages,
    chatInput,
    chatBusy,
    saving,
    deleting,
    deletingRunId,
    selectedRun,
    setAgent,
    setChatInput,
    setSelectedRun,
    setMessageMdView,
    openAgent,
    unbindPlugin,
    addPlugins,
    deleteAgent,
    deleteRun,
    sendMessage,
  };
}
