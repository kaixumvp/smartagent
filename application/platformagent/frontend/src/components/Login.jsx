import React, { useEffect, useState } from 'react';
import { ArrowUpRight, KeyRound, Sparkles } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '/v1';

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [tenant, setTenant] = useState('');
  const [providers, setProviders] = useState([]);
  const [providerLoading, setProviderLoading] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const tenantId = tenant.trim();
    if (!tenantId) {
      setProviders([]);
      return undefined;
    }
    let active = true;
    setProviderLoading(true);
    fetch(`${API_BASE}/auth/oidc/providers/${encodeURIComponent(tenantId)}`)
      .then(async (response) => {
        const data = await response.json().catch(() => []);
        if (!response.ok) throw new Error(data.error?.message || '无法加载第三方登录方式');
        if (active) setProviders(Array.isArray(data) ? data : []);
      })
      .catch((requestError) => {
        if (active) {
          setProviders([]);
          setError(requestError.message || '无法加载第三方登录方式');
        }
      })
      .finally(() => { if (active) setProviderLoading(false); });
    return () => { active = false; };
  }, [tenant]);

  useEffect(() => {
    function onMessage(event) {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === 'smartagent-oidc-login' && event.data.access_token) {
        localStorage.setItem('smartagent_token', event.data.access_token);
        window.location.reload();
      } else if (event.data?.type === 'smartagent-oidc-error') {
        setError(event.data.error || '第三方登录失败');
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError('请输入用户名和密码');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await onLogin({ username: username.trim(), password, tenant });
    } catch (loginError) {
      setError(loginError.message || '登录失败');
    } finally {
      setSubmitting(false);
    }
  }

  function startOidc(provider) {
    const popup = window.open('about:blank', 'smartagent-oidc-login', 'popup,width=560,height=720');
    if (!popup) {
      setError('浏览器拦截了弹窗，请允许此站点打开弹窗后重试');
      return;
    }
    setError('');
    popup.location.href = `${API_BASE}/auth/oidc/${encodeURIComponent(provider.id)}/authorize`;
  }

  return (
    <div className="login-page">
      <div className="login-art">
        <div className="art-orbit orbit-one" />
        <div className="art-orbit orbit-two" />
        <div className="art-copy">
          <span className="eyebrow">AGENT OPERATIONS, REFINED</span>
          <h1>让每一次<br /><em>智能运行</em><br />都清晰可见。</h1>
          <p>一个安静、可靠的控制中心，连接你的 Agent、工具与数据。</p>
        </div>
      </div>
      <form className="login-card" onSubmit={submit}>
        <div className="brand"><div className="brand-mark"><Sparkles size={17} /></div><span>smartagent</span></div>
        <div className="login-title">
          <span className="section-kicker">WELCOME BACK</span>
          <h2>进入控制台</h2>
          <p>使用账号密码或企业身份提供商登录你的工作区。</p>
        </div>
        <div className="login-fields">
          <label>用户名<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" placeholder="admin" /></label>
          <label>密码<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" placeholder="输入密码" /></label>
          <details className="login-advanced">
            <summary>高级选项</summary>
            <label>租户（可选）<input value={tenant} onChange={(event) => setTenant(event.target.value)} autoComplete="off" placeholder="单租户请留空" /></label>
          </details>
        </div>
        {error && <p className="login-error">{error}</p>}
        <button className="primary-btn login-btn" type="submit" disabled={submitting}>
          {submitting ? '登录中' : '进入工作台'} <ArrowUpRight size={17} />
        </button>
        <div className="login-oidc">
          <span>第三方登录</span>
          {!tenant.trim() && <small>展开“高级选项”并填写租户 ID 后显示企业登录方式</small>}
          {providerLoading && <small>正在加载登录方式…</small>}
          {providers.map((provider) => (
            <button type="button" className="secondary-btn" key={provider.id} onClick={() => startOidc(provider)}>
              <KeyRound size={14} />使用 {provider.display_name} 登录
            </button>
          ))}
          {tenant.trim() && !providerLoading && providers.length === 0 && (
            <small>此租户没有可用的第三方登录方式</small>
          )}
        </div>
        <div className="login-note"><KeyRound size={14} /> 会话凭证仅保存在当前浏览器</div>
      </form>
    </div>
  );
}
