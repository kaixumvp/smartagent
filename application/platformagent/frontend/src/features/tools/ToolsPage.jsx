import React, { useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import ToolCreationDialog from './ToolCreationDialog.jsx';
import SkillCreationDialog from './SkillCreationDialog.jsx';

export default function ToolsPage({ api, tools, skills, onToolCreated, onSkillCreated, onNotice }) {
  const [tab, setTab] = useState('tools');
  const [showCreateTool, setShowCreateTool] = useState(false);
  const [showCreateSkill, setShowCreateSkill] = useState(false);

  return (
    <>
      <section className="panel full-panel">
        <div className="panel-header">
          <div><span className="section-kicker">PLUGIN REGISTRY</span><h2>工具与技能</h2></div>
          <div>
            <button type="button" aria-pressed={tab === 'tools'} className={`text-btn ${tab === 'tools' ? 'active' : ''}`} onClick={() => setTab('tools')}>Tools</button>
            <button type="button" aria-pressed={tab === 'skills'} className={`text-btn ${tab === 'skills' ? 'active' : ''}`} onClick={() => setTab('skills')}>Skills</button>
            <button type="button" className="secondary-btn" onClick={() => onNotice('已刷新工具与技能')}><RefreshCw size={15} /> 刷新</button>
          </div>
        </div>
        {tab === 'tools' && (
          <div className="tools-list">
            <div className="tools-actions"><button className="primary-btn" onClick={() => setShowCreateTool(true)}><Plus size={14} /> 新建 Tool</button></div>
            <div className="grid">
              {tools.map((tool) => <div className="card" key={tool.id}><h3>{tool.name}</h3><p>{tool.type} · {tool.permission}</p><small>{tool.description}</small></div>)}
            </div>
          </div>
        )}
        {tab === 'skills' && (
          <div className="skills-list">
            <div className="tools-actions"><button className="primary-btn" onClick={() => setShowCreateSkill(true)}><Plus size={14} /> 新建 Skill</button></div>
            <div className="grid">
              {skills.map((skill) => <div className="card" key={skill.id}><h3>{skill.name}@{skill.version}</h3><p>{skill.type}</p><small>{skill.description}</small></div>)}
            </div>
          </div>
        )}
      </section>
      <ToolCreationDialog
        open={showCreateTool}
        api={api}
        onCreated={(tool) => { onToolCreated(tool); setShowCreateTool(false); }}
        onClose={() => setShowCreateTool(false)}
        onNotice={onNotice}
      />
      <SkillCreationDialog
        open={showCreateSkill}
        api={api}
        onCreated={(skill) => { onSkillCreated(skill); setShowCreateSkill(false); }}
        onClose={() => setShowCreateSkill(false)}
        onNotice={onNotice}
      />
    </>
  );
}
