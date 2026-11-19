import React, { useEffect, useState } from 'react';
import { ChevronDown, LogOut, Menu, ShieldCheck } from 'lucide-react';
import Login from '../../components/Login.jsx';
import IamPage, { IAM_NAV_ITEMS } from './IamPage.jsx';

const API_BASE = import.meta.env.VITE_API_BASE || '/v1';

function tokenClaims(token) {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(payload));
  } catch {
    return {};
  }
}

export default function IamConsoleRoute() {
  const [token, setToken] = useState(localStorage.getItem('smartagent_token') || '');
  const [notice, setNotice] = useState('');
  const [activeTab, setActiveTab] = useState('users');
  const [menuOpen, setMenuOpen] = useState(false);
  const principal = tokenClaims(token);
  const activePage = IAM_NAV_ITEMS.find((item) => item.id === activeTab) || IAM_NAV_ITEMS[0];
  const displayName = principal.name || principal.username || principal.sub || '当前用户';
  const avatar = displayName.slice(0, 1).toUpperCase();

  useEffect(() => {
    document.title = 'SmartAgent IAM Console';
  }, []);

  async function api(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const error = new Error(payload.error?.message || '请求失败');
      error.status = response.status;
      if (response.status === 401) {
        localStorage.removeItem('smartagent_token');
        setToken('');
      }
      throw error;
    }
    return response.status === 204 ? null : response.json();
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
        throw new Error(message === 'invalid credentials'
          ? '用户名或密码错误。引导账号是 admin，未改过密码则为 admin123。'
          : message);
      }
      throw new Error(message);
    }
    localStorage.setItem('smartagent_token', data.access_token);
    setToken(data.access_token);
  }

  function logout() {
    localStorage.removeItem('smartagent_token');
    setToken('');
  }

  if (!token) return <Login onLogin={login} />;

  return (
    <div className={`iam-console-shell ${menuOpen ? 'menu-open' : ''}`}>
      <aside className="iam-sidebar">
        <div className="iam-brand">
          <span className="iam-brand-mark">S</span>
          <span className="iam-brand-name">smartagent</span>
          <span className="iam-brand-tag">IDENTITY</span>
        </div>
        <div className="iam-tenant">
          <span className="iam-tenant-mark">{(principal.tenant_id || 'T').slice(0, 1).toUpperCase()}</span>
          <span className="iam-tenant-copy"><strong>{principal.tenant_name || '当前租户'}</strong><small>Tenant · {principal.tenant_id || 'default'}</small></span>
          <ChevronDown size={14} />
        </div>
        <p className="iam-sidebar-label">身份与权限</p>
        <nav className="iam-sidebar-nav" aria-label="身份管理导航">
          {IAM_NAV_ITEMS.map(({ id, label, icon: Icon }) => (
            <button key={id} className={`iam-sidebar-item ${activeTab === id ? 'active' : ''}`} onClick={() => {
              setActiveTab(id);
              setMenuOpen(false);
            }}>
              <Icon size={16} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="iam-sidebar-bottom">
          <div className="iam-security-note">
            <strong><ShieldCheck size={13} />身份安全状态</strong>
            <p>身份提供商与角色授权均按当前租户隔离。</p>
          </div>
          <div className="iam-profile">
            <span className="iam-profile-avatar">{avatar}</span>
            <span className="iam-profile-copy"><strong>{displayName} · {(principal.roles || []).includes('admin') ? '管理员' : '成员'}</strong><small>{principal.sub || principal.tenant_id || ''}</small></span>
            <button onClick={logout} title="退出登录" aria-label="退出登录"><LogOut size={14} /></button>
          </div>
        </div>
      </aside>
      {menuOpen && <button className="iam-sidebar-scrim" aria-label="关闭菜单" onClick={() => setMenuOpen(false)} />}
      <main className="iam-console-main">
        <header className="iam-topbar">
          <button className="iam-mobile-menu" aria-label="打开菜单" onClick={() => setMenuOpen((open) => !open)}><Menu size={18} /></button>
          <div className="iam-crumb"><span>IAM 控制台</span><span>/</span><strong>{activePage.label}</strong></div>
          <div className="iam-top-actions">
            <span className="iam-env-pill"><i />租户隔离</span>
            <span className="iam-help-icon" aria-label="帮助">ⓘ</span>
            <span className="iam-top-avatar">{avatar}</span>
          </div>
        </header>
        <div className="iam-console-content">
          {notice && <div className="iam-console-notice" role="status">{notice}</div>}
          <IamPage
            api={api}
            token={token}
            tenantId={principal.tenant_id || ''}
            onNotice={setNotice}
            tab={activeTab}
          />
        </div>
      </main>
    </div>
  );
}
