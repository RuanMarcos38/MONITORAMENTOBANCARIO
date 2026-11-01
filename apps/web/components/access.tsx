'use client';
import { useEffect, useState } from 'react';
import { ShieldCheck, LockKeyhole } from 'lucide-react';
import { api, post, Row } from '../lib/api';

export function Access({ onLogin }: { onLogin: (user: Row) => void }) {
  const [mode, setMode] = useState('login');
  const [setup, setSetup] = useState(false);
  const [invite, setInvite] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api('auth/setup/status').then(s => setSetup(s.required && s.enabled)).catch(() => {});
    const params = new URLSearchParams(window.location.hash.slice(1));
    if (params.get('invite')) { setInvite(params.get('invite')!); setMode('invite'); }
  }, []);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(''); setMessage('');
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (mode === 'setup') {
        await post('auth/setup', fields);
        setSetup(false); setMode('login'); setMessage('Organização criada. Faça login para configurar seu autenticador.');
      } else if (mode === 'invite') {
        await post('users/invitations/accept', { token: invite, password: fields.password });
        window.history.replaceState(null, '', window.location.pathname);
        setMode('login'); setMessage('Convite aceito. Entre com seu e-mail e sua nova senha.');
      } else {
        await post('auth/login', fields);
        onLogin(await api('auth/me'));
      }
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <main className="login">
    <div className="login-brand"><ShieldCheck size={48}/><h1>BankGuard<span> AI</span></h1><p>Inteligência financeira.<br/>Evidências que orientam decisões.</p><small>Fontes oficiais · Rastreabilidade · Revisão humana</small></div>
    <form onSubmit={submit} className="login-card" key={mode}>
      <div className="eyebrow">ACESSO À PLATAFORMA</div>
      <h2>{mode === 'setup' ? 'Configurar sua organização' : mode === 'invite' ? 'Aceitar convite' : 'Bem-vindo de volta'}</h2>
      <p>{mode === 'setup' ? 'Use o código de instalação disponível no ambiente seguro do servidor.' : 'Acesso restrito aos usuários da sua organização.'}</p>
      {mode === 'setup' && <><label>Código de instalação<input type="password" name="token" minLength={24} autoComplete="off" required/></label><label>Nome da organização<input name="organization" minLength={3} maxLength={120} required/></label></>}
      {mode !== 'invite' && <label>E-mail<input type="email" name="email" autoComplete="username" required/></label>}
      <label>{mode === 'login' ? 'Senha' : 'Crie sua senha'}<input type="password" name="password" minLength={mode === 'login' ? 12 : 14} maxLength={256} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required/></label>
      {mode === 'login' && <label>Código do autenticador<input name="otp" inputMode="numeric" autoComplete="one-time-code" maxLength={6}/></label>}
      {error && <div role="alert" className="error">{error}</div>}
      {message && <div role="status" className="notice">{message}</div>}
      <button disabled={busy}>{busy ? 'Verificando…' : mode === 'login' ? 'Acessar com segurança' : 'Concluir cadastro'}</button>
      {setup && <button type="button" className="secondary" onClick={() => setMode(mode === 'setup' ? 'login' : 'setup')}>{mode === 'setup' ? 'Voltar ao login' : 'Primeiro acesso · configurar organização'}</button>}
      <small><LockKeyhole size={13}/> Nunca informe senhas bancárias. Para recuperar o acesso, fale com o administrador da organização.</small>
    </form>
  </main>;
}

export function MFAEnrollment({ onComplete }: { onComplete: () => void }) {
  const [secret, setSecret] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function begin() {
    setBusy(true); setError('');
    try { const data = await post('auth/mfa/enroll'); setSecret(data.secret); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function confirm(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await post('auth/mfa/confirm', { code }); setSecret(''); onComplete(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <main className="splash"><section className="card case-form"><ShieldCheck size={32}/><h1>Proteja seu acesso</h1><p>Administradores e analistas usam um aplicativo autenticador. A chave é mostrada apenas durante este cadastro.</p>
    {!secret ? <button onClick={begin} disabled={busy}>Configurar autenticador</button> : <form onSubmit={confirm}><label>Chave para cadastro manual no seu autenticador<input value={secret} readOnly autoComplete="off"/></label><p>Adicione uma conta baseada em tempo (TOTP), de 6 dígitos. Este cadastro expira em 10 minutos.</p><label>Código de 6 dígitos<input value={code} onChange={e => setCode(e.target.value)} inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" required/></label><button disabled={busy}>Confirmar e voltar ao login</button></form>}
    {error && <div className="error" role="alert">{error}</div>}
  </section></main>;
}
