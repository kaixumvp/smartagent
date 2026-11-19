import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity, FileText, KeyRound, Plus, RefreshCw, Search, ShieldCheck, Trash2, Users, Wrench, X,
} from 'lucide-react';

export const IAM_NAV_ITEMS = [
  { id: 'users', label: '用户与成员', icon: Users, kicker: 'IDENTITY DIRECTORY', description: '集中管理租户成员、登录方式和角色分配。' },
  { id: 'roles', label: '角色与权限', icon: ShieldCheck, kicker: 'ROLE-BASED ACCESS', description: '用角色组合平台能力，再将角色分配给租户成员。' },
  { id: 'grants', label: '资源授权', icon: Wrench, kicker: 'RESOURCE-LEVEL POLICY', description: '对指定用户或角色授予单个 Tool 的执行权限。' },
  { id: 'oidc', label: '身份提供商', icon: KeyRound, kicker: 'FEDERATED IDENTITY', description: '配置第三方登录，并将外部身份安全绑定到已有租户成员。' },
  { id: 'audit', label: '访问审计', icon: FileText, kicker: 'SECURITY TRAIL', description: '按操作者、动作和结果追踪身份及授权变更。' },
];

const EMPTY_PROVIDER = {
  provider_key: '',
  display_name: '',
  issuer: '',
  client_id: '',
  client_secret: '',
  scopes: 'openid email profile',
};

export default function IamPage({ api, token, tenantId, onNotice, tab = 'users' }) {
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [users, setUsers] = useState([]);
  const [grants, setGrants] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [providers, setProviders] = useState([]);
  const [canManageProviders, setCanManageProviders] = useState(false);
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [error, setError] = useState('');
  const [userSearch, setUserSearch] = useState('');
  const [userStatusFilter, setUserStatusFilter] = useState('all');
  const [userSourceFilter, setUserSourceFilter] = useState('all');
  const [auditSearch, setAuditSearch] = useState('');
  const [auditResultFilter, setAuditResultFilter] = useState('all');
  const [roleName, setRoleName] = useState('');
  const [selectedRoleId, setSelectedRoleId] = useState('');
  const [roleCodes, setRoleCodes] = useState([]);
  const [savingRole, setSavingRole] = useState(false);
  const [newUser, setNewUser] = useState({ username: '', name: '', password: '', roles: [] });
  const [grantForm, setGrantForm] = useState({
    principal_type: 'role',
    principal_id: '',
    resource_type: 'tool',
    resource_id: '',
    effect: 'allow',
  });
  const [providerForm, setProviderForm] = useState(EMPTY_PROVIDER);
  const [linkProviderId, setLinkProviderId] = useState('');
  const [linkPassword, setLinkPassword] = useState('');
  const [linking, setLinking] = useState(false);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [showCreateProvider, setShowCreateProvider] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [userRoleEdit, setUserRoleEdit] = useState([]);

  const selectedRole = roles.find((role) => role.id === selectedRoleId);
  const activeProviders = useMemo(() => providers.filter((provider) => provider.status === 'active'), [providers]);
  const currentUserId = useMemo(() => {
    try {
      const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      return JSON.parse(atob(payload)).sub || '';
    } catch {
      return '';
    }
  }, [token]);

  async function loadAll() {
    setLoading(true);
    setError('');
    const jobs = [
      ['roles', '/roles', (items) => {
        setRoles(items);
        setSelectedRoleId((current) => items.some((role) => role.id === current)
          ? current
          : items[0]?.id || '');
      }],
      ['permissions', '/roles/permissions', setPermissions],
      ['users', '/users', setUsers],
      ['grants', '/grants', setGrants],
      ['tools', '/tools', setTools],
    ];
    const results = await Promise.all(jobs.map(async ([key, path, setter]) => {
      try {
        const result = await api(path);
        setter(Array.isArray(result) ? result : []);
        return null;
      } catch (requestError) {
        if (requestError.status === 401) return 'session: 登录已过期，请重新登录';
        if (requestError.status === 403) return `${key}: 当前账号没有访问权限`;
        return `${key}: ${requestError.message}`;
      }
    }));
    try {
      const providerList = await api('/auth/oidc/providers');
      setProviders(Array.isArray(providerList) ? providerList : []);
      setCanManageProviders(true);
    } catch (requestError) {
      setCanManageProviders(false);
      if (requestError.status === 401) {
        setError(requestError.message);
      } else if (requestError.status === 403 && tenantId) {
        try {
          const providerList = await api(`/auth/oidc/providers/${encodeURIComponent(tenantId)}`);
          setProviders((providerList || []).map((provider) => ({ ...provider, status: 'active' })));
        } catch (fallbackError) {
          setProviders([]);
          setError(`无法加载可用身份提供商：${fallbackError.message}`);
        }
      } else {
        setProviders([]);
        setError(`无法加载身份提供商：${requestError.message}`);
      }
    }
    const failures = results.filter(Boolean);
    if (failures.length) setError(`部分数据加载失败：${failures.join('；')}`);
    setLoading(false);
  }

  useEffect(() => { loadAll(); }, [token]);

  async function loadAudit() {
    setAuditLoading(true);
    setError('');
    try {
      const result = await api('/audit?limit=200');
      setAuditLogs(Array.isArray(result) ? result : []);
    } catch (requestError) {
      setError(requestError.status === 403
        ? '访问审计仅对管理员开放。'
        : `访问审计加载失败：${requestError.message}`);
    } finally {
      setAuditLoading(false);
    }
  }

  useEffect(() => {
    if (tab === 'audit') loadAudit();
  }, [tab, token]);

  useEffect(() => {
    if (!selectedRole) {
      setRoleCodes([]);
      return;
    }
    setRoleCodes(selectedRole.permission_codes || []);
  }, [selectedRoleId, roles]);

  async function createRole(event) {
    event.preventDefault();
    if (!roleName.trim()) return;
    setSavingRole(true);
    try {
      const created = await api('/roles', {
        method: 'POST',
        body: JSON.stringify({ name: roleName.trim(), permission_codes: [] }),
      });
      setRoles((current) => [...current, created]);
      setSelectedRoleId(created.id);
      setRoleName('');
      onNotice('角色已创建');
    } catch (requestError) {
      onNotice(`创建角色失败：${requestError.message}`);
    } finally {
      setSavingRole(false);
    }
  }

  async function saveRolePermissions() {
    if (!selectedRole) return;
    setSavingRole(true);
    try {
      const updated = await api(`/roles/${selectedRole.id}/permissions`, {
        method: 'POST',
        body: JSON.stringify({ permission_codes: roleCodes }),
      });
      setRoles((current) => current.map((role) => role.id === updated.id
        ? { ...role, ...updated, permission_codes: [...roleCodes] }
        : role));
      onNotice('角色权限已保存');
    } catch (requestError) {
      onNotice(`保存角色权限失败：${requestError.message}`);
    } finally {
      setSavingRole(false);
    }
  }

  async function createUser(event) {
    event.preventDefault();
    try {
      const created = await api('/users', {
        method: 'POST',
        body: JSON.stringify({
          username: newUser.username.trim(),
          name: newUser.name.trim(),
          password: newUser.password,
          roles: newUser.roles,
        }),
      });
      setUsers((current) => [...current, created]);
      setNewUser({ username: '', name: '', password: '', roles: [] });
      setShowCreateUser(false);
      onNotice('用户已创建');
    } catch (requestError) {
      onNotice(`创建用户失败：${requestError.message}`);
    }
  }

  async function updateUser(user, patch) {
    try {
      const updated = await api(`/users/${user.id}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setSelectedUser((current) => current?.id === updated.id ? updated : current);
      onNotice('用户信息已更新');
      return true;
    } catch (requestError) {
      onNotice(`更新用户失败：${requestError.message}`);
      return false;
    }
  }

  async function createGrant(event) {
    event.preventDefault();
    if (!grantForm.principal_id || !grantForm.resource_id.trim()) {
      onNotice('请选择授权主体并填写资源 ID');
      return;
    }
    try {
      const created = await api('/grants', {
        method: 'POST',
        body: JSON.stringify({
          ...grantForm,
          resource_id: grantForm.resource_id.trim(),
          action: 'execute',
        }),
      });
      setGrants((current) => [created, ...current]);
      setGrantForm((current) => ({ ...current, resource_id: '' }));
      onNotice('Tool 执行授权已创建');
    } catch (requestError) {
      onNotice(`创建授权失败：${requestError.message}`);
    }
  }

  async function deleteGrant(grant) {
    try {
      await api(`/grants/${grant.id}`, { method: 'DELETE' });
      setGrants((current) => current.filter((item) => item.id !== grant.id));
      onNotice('授权已删除');
    } catch (requestError) {
      onNotice(`删除授权失败：${requestError.message}`);
    }
  }

  async function createProvider(event) {
    event.preventDefault();
    try {
      const created = await api('/auth/oidc/providers', {
        method: 'POST',
        body: JSON.stringify({
          provider_key: providerForm.provider_key.trim(),
          display_name: providerForm.display_name.trim(),
          issuer: providerForm.issuer.trim(),
          client_id: providerForm.client_id.trim(),
          client_secret: providerForm.client_secret,
          scopes: providerForm.scopes.split(/\s+/).filter(Boolean),
        }),
      });
      setProviders((current) => [...current, created]);
      setProviderForm(EMPTY_PROVIDER);
      setShowCreateProvider(false);
      onNotice('OIDC 身份提供商已添加');
    } catch (requestError) {
      onNotice(`添加身份提供商失败：${requestError.message}`);
    }
  }

  async function setProviderStatus(provider, status) {
    try {
      const updated = await api(`/auth/oidc/providers/${provider.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      });
      setProviders((current) => current.map((item) => item.id === updated.id
        ? { ...updated, linked_user_count: item.linked_user_count || 0 }
        : item));
      onNotice(status === 'active' ? '身份提供商已启用' : '身份提供商已停用');
    } catch (requestError) {
      onNotice(`更新身份提供商失败：${requestError.message}`);
    }
  }

  async function removeProvider(provider) {
    if (!window.confirm(`删除“${provider.display_name}”？已绑定的外部身份也会被删除。`)) return;
    try {
      await api(`/auth/oidc/providers/${provider.id}`, { method: 'DELETE' });
      setProviders((current) => current.filter((item) => item.id !== provider.id));
      onNotice('身份提供商已删除');
    } catch (requestError) {
      onNotice(`删除身份提供商失败：${requestError.message}`);
    }
  }

  async function beginLink(event) {
    event.preventDefault();
    if (!linkProviderId || !linkPassword) {
      onNotice('请选择身份提供商并输入当前密码');
      return;
    }
    const popup = window.open('about:blank', 'smartagent-oidc-link', 'popup,width=560,height=720');
    if (!popup) {
      onNotice('浏览器拦截了弹窗，请允许此站点打开弹窗后重试');
      return;
    }
    setLinking(true);
    try {
      const result = await api(`/auth/oidc/${linkProviderId}/link`, {
        method: 'POST',
        body: JSON.stringify({ current_password: linkPassword }),
      });
      popup.location.href = result.authorization_url;
      setLinkPassword('');
    } catch (requestError) {
      popup.close();
      onNotice(`开始绑定失败：${requestError.message}`);
    } finally {
      setLinking(false);
    }
  }

  useEffect(() => {
    function onMessage(event) {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === 'smartagent-oidc-linked') {
        onNotice('第三方身份已绑定到当前账号');
      }
      if (event.data?.type === 'smartagent-oidc-error') {
        onNotice(event.data.error || '第三方身份绑定失败');
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [onNotice]);

  const principalOptions = grantForm.principal_type === 'role' ? roles : users;
  const filteredUsers = useMemo(() => {
    const query = userSearch.trim().toLocaleLowerCase();
    return users.filter((user) => {
      const matchesSearch = !query
        || [user.name, user.username, user.id, ...(user.roles || [])]
          .some((value) => String(value || '').toLocaleLowerCase().includes(query));
      const matchesStatus = userStatusFilter === 'all' || user.status === userStatusFilter;
      const sourceNames = user.identity_providers?.length ? user.identity_providers : ['本地账号'];
      const matchesSource = userSourceFilter === 'all' || sourceNames.includes(userSourceFilter);
      return matchesSearch && matchesStatus && matchesSource;
    });
  }, [users, userSearch, userStatusFilter, userSourceFilter]);
  const filteredAuditLogs = useMemo(() => {
    const query = auditSearch.trim().toLocaleLowerCase();
    return auditLogs.filter((entry) => {
      const matchesSearch = !query
        || [entry.actor, entry.action, entry.resource_type, entry.resource_id, entry.trace_id]
          .some((value) => String(value || '').toLocaleLowerCase().includes(query));
      return matchesSearch && (auditResultFilter === 'all' || entry.result === auditResultFilter);
    });
  }, [auditLogs, auditSearch, auditResultFilter]);

  const page = IAM_NAV_ITEMS.find((item) => item.id === tab) || IAM_NAV_ITEMS[0];
  const externalBindings = users.reduce((total, user) => total + (user.identity_providers?.length || 0), 0);
  const todayAudit = auditLogs.filter((entry) => (
    entry.created_at && new Date(entry.created_at).toDateString() === new Date().toDateString()
  ));

  return (
    <section className="iam-page">
      <div className="page-heading compact">
        <div>
          <div className="eyebrow">{page.kicker}</div>
          <h1>{page.label}</h1>
          <p>{page.description}</p>
        </div>
        <div className="iam-page-actions">
          {tab === 'users' && <button className="primary-btn" onClick={() => setShowCreateUser(true)}><Plus size={14} />添加用户</button>}
          {tab === 'roles' && <button className="primary-btn" onClick={() => document.getElementById('iam-role-name')?.focus()}><Plus size={14} />新建角色</button>}
          {tab === 'grants' && <button className="primary-btn" onClick={() => document.getElementById('iam-grant-principal')?.focus()}><Plus size={14} />新增授权规则</button>}
          {tab === 'oidc' && canManageProviders && <button className="primary-btn" onClick={() => setShowCreateProvider(true)}><Plus size={14} />添加身份提供商</button>}
          <button className="secondary-btn" onClick={loadAll} disabled={loading}>
            <RefreshCw size={15} className={loading ? 'spin' : ''} />刷新
          </button>
        </div>
      </div>
      {error && <div className="iam-error" role="alert">{error}</div>}

      {tab === 'users' && <div className="iam-prototype-stats" aria-label="成员统计">
        <article><span className="stat-icon"><Users size={16} /></span><span><small>租户成员</small><strong>{users.length}</strong></span></article>
        <article><span className="stat-icon purple"><Activity size={16} /></span><span><small>活跃用户</small><strong>{users.filter((user) => user.status === 'active').length}</strong></span></article>
        <article><span className="stat-icon amber"><ShieldCheck size={16} /></span><span><small>已分配角色</small><strong>{roles.length}</strong></span></article>
        <article><span className="stat-icon red"><KeyRound size={16} /></span><span><small>外部身份绑定</small><strong>{externalBindings}</strong></span></article>
      </div>}
      {tab === 'audit' && <div className="iam-prototype-stats" aria-label="审计统计">
        <article><span className="stat-icon"><Activity size={16} /></span><span><small>今日事件</small><strong>{todayAudit.length}</strong></span></article>
        <article><span className="stat-icon purple"><ShieldCheck size={16} /></span><span><small>授权成功</small><strong>{todayAudit.filter((entry) => entry.result === 'allow').length}</strong></span></article>
        <article><span className="stat-icon red"><X size={16} /></span><span><small>拒绝访问</small><strong>{todayAudit.filter((entry) => entry.result === 'deny').length}</strong></span></article>
        <article><span className="stat-icon amber"><Users size={16} /></span><span><small>操作者</small><strong>{new Set(todayAudit.map((entry) => entry.actor).filter(Boolean)).size}</strong></span></article>
      </div>}

      {tab === 'roles' && (
        <div className="iam-columns">
          <section className="panel iam-panel">
            <div className="iam-panel-heading"><div><span className="section-kicker">RBAC</span><h2>角色</h2></div></div>
            <form className="iam-inline-form" onSubmit={createRole}>
              <input id="iam-role-name" value={roleName} onChange={(event) => setRoleName(event.target.value)} placeholder="新角色名称" maxLength={64} />
              <button className="primary-btn" disabled={savingRole || !roleName.trim()}><Plus size={14} />新建</button>
            </form>
            <div className="iam-list">
              {roles.map((role) => (
                <button key={role.id} className={`iam-list-item ${role.id === selectedRoleId ? 'selected' : ''}`} onClick={() => setSelectedRoleId(role.id)}>
                  <span><strong>{role.name}</strong><small>{role.is_builtin ? '内置角色' : '自定义角色'} · {(role.permission_codes || []).length} 项权限</small></span>
                  <span className="iam-status">{role.is_builtin ? 'BUILT-IN' : 'CUSTOM'}</span>
                </button>
              ))}
              {roles.length === 0 && <p className="iam-empty">暂无角色</p>}
            </div>
          </section>
          <section className="panel iam-panel">
            <div className="iam-panel-heading"><div><span className="section-kicker">PERMISSIONS</span><h2>{selectedRole ? `配置「${selectedRole.name}」` : '选择一个角色'}</h2></div></div>
            {selectedRole && (
              <>
                <p className="iam-help">功能权限控制 API 能力；单个 Tool 的执行权在“Tool 授权”中配置。</p>
                <div className="iam-permission-list">
                  {permissions.map((permission) => (
                    <label className="iam-check" key={permission.code}>
                      <input
                        type="checkbox"
                        disabled={selectedRole.is_builtin}
                        checked={roleCodes.includes(permission.code)}
                        onChange={(event) => setRoleCodes((current) => event.target.checked
                          ? [...current, permission.code]
                          : current.filter((code) => code !== permission.code))}
                      />
                      <span><strong>{permission.code}</strong><small>{permission.description || '功能权限'}</small></span>
                    </label>
                  ))}
                  {permissions.length === 0 && <p className="iam-empty">接口未返回可配置权限。</p>}
                </div>
                {selectedRole.is_builtin
                  ? <p className="iam-help">内置角色的权限定义不可在控制台修改。</p>
                  : <button className="primary-btn iam-save" onClick={saveRolePermissions} disabled={savingRole}>
                    保存角色权限
                  </button>}
              </>
            )}
          </section>
        </div>
      )}

      {tab === 'audit' && (
        <section className="panel iam-panel iam-audit-panel">
          <div className="iam-panel-heading">
            <div><span className="section-kicker">ACCESS AUDIT</span><h2>访问审计</h2><p className="iam-subtitle">查看当前租户最近 200 条身份、权限与资源访问事件；仅管理员可见。</p></div>
            <button className="secondary-btn" onClick={loadAudit} disabled={auditLoading}>
              <RefreshCw size={14} className={auditLoading ? 'spin' : ''} />刷新
            </button>
          </div>
          <div className="iam-audit-filters">
            <label className="iam-search">
              <Search size={15} />
              <input value={auditSearch} onChange={(event) => setAuditSearch(event.target.value)} placeholder="搜索操作、成员、资源或 Trace ID" aria-label="搜索审计记录" />
            </label>
            <select aria-label="按结果筛选审计记录" value={auditResultFilter} onChange={(event) => setAuditResultFilter(event.target.value)}>
              <option value="all">全部结果</option>
              <option value="allow">允许</option>
              <option value="deny">拒绝</option>
              <option value="approve">批准</option>
              <option value="reject">拒绝审批</option>
            </select>
          </div>
          <div className="iam-audit-table-wrap">
            <table className="iam-audit-table">
              <thead><tr><th>操作</th><th>执行者</th><th>资源</th><th>结果</th><th>时间</th><th>Trace ID</th></tr></thead>
              <tbody>
                {filteredAuditLogs.map((entry) => {
                  const actor = users.find((user) => user.id === entry.actor);
                  return (
                    <tr key={entry.id}>
                      <td><strong>{entry.action}</strong>{entry.detail?.required && <small>需要权限：{entry.detail.required}</small>}</td>
                      <td>{actor?.name || actor?.username || entry.actor || '系统'}</td>
                      <td>{entry.resource_type ? <code>{entry.resource_type}:{entry.resource_id || '—'}</code> : '—'}</td>
                      <td><span className={`iam-audit-result ${entry.result}`}>{entry.result}</span></td>
                      <td>{entry.created_at ? new Date(entry.created_at).toLocaleString() : '—'}</td>
                      <td><code>{entry.trace_id || '—'}</code></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!auditLoading && filteredAuditLogs.length === 0 && (
              <p className="iam-empty">{auditLogs.length ? '没有符合筛选条件的审计记录。' : '暂无审计记录。'}</p>
            )}
            {auditLoading && <p className="iam-empty"><Activity size={14} />正在加载审计记录…</p>}
          </div>
          <p className="iam-list-footer">当前显示 {filteredAuditLogs.length} 条 · 接口最多返回最近 200 条</p>
        </section>
      )}

      {tab === 'users' && (
        <section className="panel iam-prototype-panel">
            <div className="iam-prototype-panel-head">
              <div><strong>成员目录</strong><small>查看成员状态、登录来源与角色</small></div>
              <button className="iam-icon-action" onClick={loadAll} disabled={loading}><RefreshCw size={14} className={loading ? 'spin' : ''} />刷新</button>
            </div>
            <div className="iam-member-filters">
              <label className="iam-search">
                <Search size={15} />
                <input value={userSearch} onChange={(event) => setUserSearch(event.target.value)} placeholder="搜索姓名或用户名" aria-label="搜索成员" />
              </label>
              <select className="iam-table-control" aria-label="筛选状态" value={userStatusFilter} onChange={(event) => setUserStatusFilter(event.target.value)}>
                <option value="all">全部状态</option>
                <option value="active">活跃</option>
                <option value="disabled">已停用</option>
              </select>
              <select className="iam-table-control" aria-label="筛选来源" value={userSourceFilter} onChange={(event) => setUserSourceFilter(event.target.value)}>
                <option value="all">全部来源</option>
                <option value="本地账号">本地账号</option>
                {providers.map((provider) => <option key={provider.id} value={provider.display_name}>{provider.display_name}</option>)}
              </select>
            </div>
            <div className="iam-table-wrap">
              <table className="iam-data-table">
                <thead><tr><th>成员</th><th>状态</th><th>登录来源</th><th>角色</th><th>创建时间</th><th /></tr></thead>
                <tbody>
                  {filteredUsers.map((user) => (
                    <tr key={user.id}>
                      <td><div className="iam-member-cell"><span className="iam-member-avatar">{(user.name || user.username || '?').slice(0, 1)}</span><span><strong>{user.name || user.username}</strong><small>{user.username}</small></span></div></td>
                      <td><span className={`iam-status-pill ${user.status}`}>{user.status === 'active' ? '活跃' : '已停用'}</span></td>
                      <td><span className="iam-source-list">{user.identity_providers?.length ? user.identity_providers.join('、') : '本地账号'}</span></td>
                      <td><span className="iam-role-tags">{(user.roles || []).length
                        ? user.roles.map((role) => <span className="iam-role-tag" key={role}>{role}</span>)
                        : <span className="iam-muted">未分配</span>}</span></td>
                      <td>{user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}</td>
                      <td><button className="iam-row-action" onClick={() => { setSelectedUser(user); setUserRoleEdit(user.roles || []); }}>查看详情 <span>→</span></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filteredUsers.length === 0 && <p className="iam-empty">{users.length ? '没有符合筛选条件的成员。' : '暂无用户，或当前账号没有 user:manage 权限。'}</p>}
            </div>
            <div className="iam-table-foot"><span>当前显示 {filteredUsers.length} 位成员 · 共 {users.length} 位成员</span></div>
          </section>
      )}

      {tab === 'grants' && (
        <section className="panel iam-panel">
          <div className="iam-panel-heading"><div><span className="section-kicker">RESOURCE ACL</span><h2>单个 Tool 执行授权</h2></div></div>
          <p className="iam-help">授权动作当前固定为 execute。新规则按稳定 Tool ID 匹配；ALLOW/DENY 同时命中时 DENY 优先。</p>
          <form className="iam-grant-form" onSubmit={createGrant}>
            <label>主体类型<select value={grantForm.principal_type} onChange={(event) => setGrantForm({ ...grantForm, principal_type: event.target.value, principal_id: '' })}><option value="role">角色</option><option value="user">用户</option></select></label>
            <label>主体<select id="iam-grant-principal" required value={grantForm.principal_id} onChange={(event) => setGrantForm({ ...grantForm, principal_id: event.target.value })}><option value="">选择主体</option>{principalOptions.map((item) => <option key={item.id} value={item.id}>{item.name || item.username}</option>)}</select></label>
            <label>Tool 资源
              <select value={grantForm.resource_id} onChange={(event) => setGrantForm({ ...grantForm, resource_id: event.target.value })}>
                <option value="">手动填写 ID</option>
                {tools.map((tool) => <option key={tool.id} value={tool.id}>{tool.name} · {tool.id}</option>)}
              </select>
            </label>
            <label>资源 ID<input required value={grantForm.resource_id} onChange={(event) => setGrantForm({ ...grantForm, resource_id: event.target.value })} placeholder="稳定 Tool ID" /></label>
            <label>效果<select value={grantForm.effect} onChange={(event) => setGrantForm({ ...grantForm, effect: event.target.value })}><option value="allow">允许</option><option value="deny">拒绝</option></select></label>
            <button className="primary-btn"><Plus size={14} />添加授权</button>
          </form>
          <div className="iam-grant-list">
            {grants.map((grant) => {
              const principal = grant.principal_type === 'role'
                ? roles.find((role) => role.id === grant.principal_id)?.name
                : users.find((user) => user.id === grant.principal_id)?.username;
              return (
                <div className="iam-grant-row" key={grant.id}>
                  <span className={`grant-effect ${grant.effect}`}>{grant.effect === 'deny' ? '拒绝' : '允许'}</span>
                  <strong>{principal || grant.principal_id}</strong>
                  <code>{grant.resource_type}:{grant.resource_id}</code>
                  <span>{grant.action === '*' ? '旧版全部动作' : grant.action}</span>
                  <button className="icon-btn" title="删除授权" onClick={() => deleteGrant(grant)}><Trash2 size={15} /></button>
                </div>
              );
            })}
            {grants.length === 0 && <p className="iam-empty">暂无资源授权</p>}
          </div>
        </section>
      )}

      {tab === 'oidc' && (
        <>
          <div className="iam-prototype-notice"><KeyRound size={15} /><span><strong>安全默认值：</strong>不按邮箱自动合并或创建账号。用户需先有本地成员账号，再主动绑定外部身份。</span></div>
          <section className="panel iam-prototype-panel">
            <div className="iam-prototype-panel-head">
              <div><strong>已配置的身份源</strong><small>登录和身份绑定按租户隔离</small></div>
              <button className="iam-icon-action" onClick={loadAll} disabled={loading}><RefreshCw size={14} className={loading ? 'spin' : ''} />刷新</button>
            </div>
            <div className="iam-provider-grid">
              {canManageProviders && providers.map((provider) => (
                <article className="iam-provider-prototype-card" key={provider.id}>
                  <div className="iam-provider-prototype-head">
                    <span className="iam-provider-logo">{provider.display_name.slice(0, 1)}</span>
                    <span className="iam-provider-name"><strong>{provider.display_name}</strong><small>OIDC · {provider.provider_key}</small></span>
                    <span className={`iam-status-pill ${provider.status}`}>{provider.status === 'active' ? '运行中' : '已停用'}</span>
                  </div>
                  <div className="iam-provider-details">
                    <div><span>Issuer</span><strong>{provider.issuer}</strong></div>
                    <div><span>Client ID</span><strong>{provider.client_id}</strong></div>
                    <div><span>绑定成员</span><strong>{provider.linked_user_count || 0} 人</strong></div>
                    <div><span>Scopes</span><strong>{(provider.scopes || []).join(' · ') || '—'}</strong></div>
                  </div>
                  <label className="iam-callback">回调地址<input readOnly value={provider.callback_url} onFocus={(event) => event.target.select()} /></label>
                  <div className="iam-provider-prototype-actions">
                    <button className="iam-row-action" onClick={() => setProviderStatus(provider, provider.status === 'active' ? 'disabled' : 'active')}>{provider.status === 'active' ? '停用' : '启用'}</button>
                    <button className="iam-row-action danger" onClick={() => removeProvider(provider)}><Trash2 size={12} />删除</button>
                    <small>Client Secret 已加密保存</small>
                  </div>
                </article>
              ))}
              {canManageProviders && providers.length === 0 && <p className="iam-empty">暂无身份提供商，请添加标准 OIDC 身份源。</p>}
              {!canManageProviders && <p className="iam-empty">当前账号仅可绑定已配置的身份提供商；管理身份源需要管理员权限。</p>}
              {canManageProviders && <button className="iam-provider-add-card" onClick={() => setShowCreateProvider(true)}>
                <Plus size={20} /><strong>接入标准 OIDC 身份源</strong><small>兼容自建 IdP 与其他标准 OIDC 服务</small>
              </button>}
            </div>
            <div className="iam-link-box">
              <strong>绑定当前账号</strong>
              <p>先用本地账号登录；绑定时需再次验证当前密码。</p>
              <form className="iam-link-form" onSubmit={beginLink}>
                <select required value={linkProviderId} onChange={(event) => setLinkProviderId(event.target.value)}>
                  <option value="">选择身份提供商</option>
                  {activeProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.display_name}</option>)}
                </select>
                <input required type="password" autoComplete="current-password" placeholder="当前密码" value={linkPassword} onChange={(event) => setLinkPassword(event.target.value)} />
                <button className="secondary-btn" disabled={linking}>{linking ? '正在打开…' : '绑定账号'}</button>
              </form>
            </div>
          </section>
          <div className="iam-prototype-notice subtle"><Activity size={14} /><span>不同平台若不支持标准 OIDC，需由后续适配器实现对应 OAuth/登录协议；通讯录同步与角色映射属于独立的后续能力。</span></div>
        </>
      )}
      {showCreateUser && (
        <div className="iam-dialog-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setShowCreateUser(false);
        }}>
          <section className="iam-dialog" role="dialog" aria-modal="true" aria-labelledby="iam-create-user-title">
            <div className="iam-dialog-head"><div><span className="section-kicker">TENANT MEMBERS</span><h2 id="iam-create-user-title">添加用户</h2></div><button className="iam-dialog-close" onClick={() => setShowCreateUser(false)} aria-label="关闭"><X size={17} /></button></div>
            <form className="iam-form" onSubmit={createUser}>
              <label>用户名<input required value={newUser.username} onChange={(event) => setNewUser({ ...newUser, username: event.target.value })} /></label>
              <label>显示名称<input value={newUser.name} onChange={(event) => setNewUser({ ...newUser, name: event.target.value })} /></label>
              <label>初始密码<input required minLength={8} type="password" autoComplete="new-password" value={newUser.password} onChange={(event) => setNewUser({ ...newUser, password: event.target.value })} /></label>
              <fieldset className="iam-role-picker"><legend>分配角色</legend>
                {roles.map((role) => <label key={role.id}><input type="checkbox" checked={newUser.roles.includes(role.name)} onChange={(event) => setNewUser((current) => ({ ...current, roles: event.target.checked ? [...current.roles, role.name] : current.roles.filter((name) => name !== role.name) }))} />{role.name}</label>)}
                {!roles.length && <small>尚无可分配角色。</small>}
              </fieldset>
              <div className="iam-dialog-actions"><button type="button" className="secondary-btn" onClick={() => setShowCreateUser(false)}>取消</button><button className="primary-btn"><Plus size={14} />创建用户</button></div>
            </form>
          </section>
        </div>
      )}
      {showCreateProvider && (
        <div className="iam-dialog-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setShowCreateProvider(false);
        }}>
          <section className="iam-dialog" role="dialog" aria-modal="true" aria-labelledby="iam-create-provider-title">
            <div className="iam-dialog-head"><div><span className="section-kicker">OPENID CONNECT</span><h2 id="iam-create-provider-title">添加身份提供商</h2></div><button className="iam-dialog-close" onClick={() => setShowCreateProvider(false)} aria-label="关闭"><X size={17} /></button></div>
            <form className="iam-form" onSubmit={createProvider}>
              <label>唯一标识<input required pattern="[a-z0-9][a-z0-9_-]{0,62}" value={providerForm.provider_key} onChange={(event) => setProviderForm({ ...providerForm, provider_key: event.target.value })} placeholder="company-sso" /></label>
              <label>显示名称<input required value={providerForm.display_name} onChange={(event) => setProviderForm({ ...providerForm, display_name: event.target.value })} placeholder="公司单点登录" /></label>
              <label>Issuer URL<input required type="url" value={providerForm.issuer} onChange={(event) => setProviderForm({ ...providerForm, issuer: event.target.value })} placeholder="https://login.example.com" /></label>
              <label>Client ID<input required value={providerForm.client_id} onChange={(event) => setProviderForm({ ...providerForm, client_id: event.target.value })} /></label>
              <label>Client Secret<input required type="password" autoComplete="new-password" value={providerForm.client_secret} onChange={(event) => setProviderForm({ ...providerForm, client_secret: event.target.value })} /></label>
              <label>Scopes（空格分隔）<input value={providerForm.scopes} onChange={(event) => setProviderForm({ ...providerForm, scopes: event.target.value })} /></label>
              <p className="iam-help">需要后端配置 OIDC_ENCRYPTION_KEY、OIDC_ALLOWED_HOSTS、OIDC_PUBLIC_BASE_URL。</p>
              <div className="iam-dialog-actions"><button type="button" className="secondary-btn" onClick={() => setShowCreateProvider(false)}>取消</button><button className="primary-btn"><Plus size={14} />添加身份提供商</button></div>
            </form>
          </section>
        </div>
      )}
      {selectedUser && (
        <div className="iam-dialog-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setSelectedUser(null);
        }}>
          <section className="iam-dialog" role="dialog" aria-modal="true" aria-labelledby="iam-user-detail-title">
            <div className="iam-dialog-head"><div><span className="section-kicker">MEMBER DETAIL</span><h2 id="iam-user-detail-title">{selectedUser.name || selectedUser.username}</h2><p>{selectedUser.username}</p></div><button className="iam-dialog-close" onClick={() => setSelectedUser(null)} aria-label="关闭"><X size={17} /></button></div>
            <div className="iam-member-detail-meta"><span>账号状态</span><strong>{selectedUser.status === 'active' ? '活跃' : '已停用'}</strong><span>登录来源</span><strong>{selectedUser.identity_providers?.length ? selectedUser.identity_providers.join('、') : '本地账号'}</strong></div>
            <form className="iam-form" onSubmit={(event) => {
              event.preventDefault();
              updateUser(selectedUser, { roles: userRoleEdit }).then((updated) => {
                if (updated) setSelectedUser(null);
              });
            }}>
              <fieldset className="iam-role-picker"><legend>角色分配</legend>
                {roles.map((role) => <label key={role.id}><input type="checkbox" checked={userRoleEdit.includes(role.name)} onChange={(event) => setUserRoleEdit((current) => event.target.checked ? [...current, role.name] : current.filter((name) => name !== role.name))} />{role.name}</label>)}
                {!roles.length && <small>暂无可分配角色。</small>}
              </fieldset>
              <div className="iam-dialog-actions">
                {selectedUser.id !== currentUserId && <button type="button" className="iam-danger-button" onClick={() => {
                  updateUser(selectedUser, { status: selectedUser.status === 'active' ? 'disabled' : 'active' });
                  setSelectedUser(null);
                }}>{selectedUser.status === 'active' ? '停用账号' : '启用账号'}</button>}
                <button type="button" className="secondary-btn" onClick={() => setSelectedUser(null)}>取消</button>
                <button className="primary-btn">保存角色</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
