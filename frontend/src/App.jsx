import React, { useEffect, useRef, useState } from 'react';
import strings from '../../backend/ui_strings.json';
import * as api from './api';
const codes = Object.keys(strings.LANGS),
  targets = ['Chinese', 'English', 'Japanese', 'Korean', 'French', 'Portuguese'],
  recoveryOptions = [['quick_return', 'quickReturn'], ['next_step', 'nextStep'], ['translation', 'translationPractice']];
const clock = n => `${String(Math.floor(Math.max(0, n) / 60)).padStart(2, '0')}:${String(Math.max(0, n) % 60).padStart(2, '0')}`;
export default function App() {
  const [view, setView] = useState('focus'),
    [data, setData] = useState(null),
    [draft, setDraft] = useState(null),
    [connected, setConnected] = useState(false),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [task, setTask] = useState(''),
    [duration, setDuration] = useState(25),
    [item, setItem] = useState(null),
    [label, setLabel] = useState('on_task'),
    [reason, setReason] = useState(''),
    [caseTask, setCaseTask] = useState(''),
    [message, setMessage] = useState('');
  const dialog = useRef(),
    dirty = useRef(false),
    alive = useRef(true),
    requestId = useRef(0);
  const settings = data?.settings.settings,
    status = data?.status,
    ui = settings?.ui_language || 'en',
    active = status?.active;
  const t = k => strings.copy[k]?.[codes.indexOf(ui)] || k;
  async function refresh() {
    const id = ++requestId.current;
    const value = await api.mvpRequest('/overview');
    if (!alive.current || id !== requestId.current) return;
    setData(value);
    setConnected(true);
    if (!dirty.current) setDraft(value.settings.settings);
  }
  useEffect(() => {
    alive.current = true;
    let timer,
      stop = false;
    async function poll() {
      try {
        await refresh();
      } catch {
        if (!stop) setConnected(false);
      }
      if (!stop) timer = setTimeout(poll, 2000);
    }
    poll();
    const pending = () => setView('recent');
    window.addEventListener('aimonitor-pending-capture', pending);
    return () => {
      stop = true;
      alive.current = false;
      clearTimeout(timer);
      window.removeEventListener('aimonitor-pending-capture', pending);
    };
  }, []);
  useEffect(() => {
    document.documentElement.lang = ui;
  }, [ui]);
  useEffect(() => {
    if (item && !dialog.current.open) dialog.current.showModal();
  }, [item]);
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(''), 5000);
    return () => clearTimeout(timer);
  }, [message]);
  async function act(fn) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function open(x) {
    setItem(x);
    setLabel(x.ai_label === 'off_task' ? 'off_task' : 'on_task');
    setReason('');
    setCaseTask(x.task || '');
  }
  function close() {
    dialog.current.close();
    setItem(null);
  }
  function edit(k, v) {
    dirty.current = true;
    setDraft(s => ({
      ...s,
      [k]: v
    }));
  }
  const select = (value, onChange) => <select aria-label={t('uiLanguage')} value={value} disabled={busy} onChange={e => onChange(e.target.value)}>{codes.map(c => <option key={c} value={c}>{strings.LANGS[c]}</option>)}</select>;
  const j = active ? status.latest_judgement : null,
    failed = j?.judgement_status === 'api_error' || status?.monitor_error,
    remaining = active ? status.remaining_seconds : duration * 60,
    total = active ? (status.duration_minutes || duration) * 60 : duration * 60;
  return <div className="shell"><aside className="sidebar"><a className="brand" href="#focus" onClick={e => {
        e.preventDefault();
        setView('focus');
      }}><span className="brand-mark">f<span>g</span></span>FocusGuard<span className="brand-dot" /></a><div className="workspace-label">{t('workspace')}</div><nav>{['focus', 'recent', 'cases', 'settings'].map((key, i) => <button key={key} className={`nav-item ${view === key ? 'active' : ''}`} onClick={() => setView(key)} aria-current={view === key ? 'page' : undefined}><span className="nav-icon">{['◉', '≡', '▧', '⚙'][i]}</span>{t(key)}{key === 'cases' && <span className="count">{data?.samples.length || 0}</span>}</button>)}</nav><div className="sidebar-bottom"><div className="quiet-symbol">◎</div><p>{t('sidebarNote')}</p><div className="version">FocusGuard <span>MVP</span></div></div></aside>
 <div className="main-shell"><header className="topbar"><div className="breadcrumb">FocusGuard <span>/</span><span>{t(view)}</span></div><div className="locale-control">◎ {select(ui, v => act(async () => {
            await api.saveSettings({
              ui_language: v
            });
            if (dirty.current) setDraft(s => ({
              ...s,
              ui_language: v
            }));
          }))}</div></header><main>
 {!connected && <div className="app-error" role="alert">{t('connectionError')}</div>}{error && <div className="app-error" role="alert">{error}<button className="text-button" onClick={() => setError('')}>×</button></div>}
 {view === 'focus' && <section id="focusView" className="view"><div className="page-heading"><div><h1>{t('headline')}</h1><p>{t('intro')}</p></div><span className="pill neutral">{t('sessionOnly')}</span></div><div className="focus-grid"><section className="focus-card"><div className="card-top"><span className="card-label">{t('currentSession')}</span><span className="pill">{t(active ? 'running' : 'ready')}</span></div><label className="field-label" htmlFor="task">{t('taskLabel')}</label><input id="task" className="task-input" value={active ? status.task : task} disabled={active || busy} maxLength={500} onChange={e => setTask(e.target.value)} placeholder={t('sampleTask')} /><div className="timer-wrap"><svg className="timer-ring" viewBox="0 0 260 260" aria-hidden="true"><circle className="ring-track" cx="130" cy="130" r="112" /><circle className="ring-progress" cx="130" cy="130" r="112" style={{
                    strokeDashoffset: 703.72 * (1 - remaining / total)
                  }} /></svg><div className="timer-content"><span className="timer-caption">{t(active ? 'remaining' : 'planned')}</span><div id="timer" role="timer">{clock(remaining)}</div><span className="timer-foot">{t(status?.should_block ? 'blocked' : 'timerHint')}</span></div></div><div className="duration-picker">{[25, 45, 60].map(n => <button key={n} disabled={active || busy} className={duration === n ? 'selected' : ''} onClick={() => setDuration(n)}>{n} {t('min')}</button>)}</div><button className="primary wide" disabled={busy || !connected || !active && !task.trim()} onClick={() => act(() => active ? api.mvpRequest('/stop', {
                session_id: status.session_id
              }) : api.startSession(task.trim(), duration, settings.default_check_interval_seconds, [], true, settings.trigger_threshold))}>{t(active ? 'stop' : 'start')}</button><p className="micro-copy">{t('screenNotice')}</p></section>
 <section className="status-card"><div className="card-top"><span className="card-label">{t('liveStatus')}</span><span className={`live-dot ${!connected || failed ? 'offline' : ''}`} /></div><div className="status-icon">{failed ? '!' : j?.on_task ? '✓' : '◎'}</div><h2>{t(!connected ? 'connectionError' : failed ? 'errorTitle' : status?.should_block ? 'blocked' : !active ? 'readyTitle' : !j ? 'waiting' : j.on_task ? 'focusedTitle' : 'offTask')}</h2><p className="status-description">{failed ? status.monitor_error || j?.error_message || j?.reason : j?.reason || t('readyDescription')}</p><div className="status-meta"><span>{t('nextCheck')}</span><strong>{active && !status.should_block ? clock(status.next_check_seconds || 0) : '—'}</strong></div><div className="status-meta"><span>{t('reference')}</span><strong>{j?.personal_reference_count ?? '—'}</strong></div><div className="status-tip"><span>✧</span><p>{t('referenceHint')}</p></div></section></div></section>}
 {view === 'recent' && <section className="view"><div className="page-heading"><h1>{t('recent')}</h1><button className="text-button" disabled={busy} onClick={() => act(async () => {})}>{t('refresh')}</button></div>{data?.pending && <div className="case-info"><h2>{t('pending')}</h2><button className="text-button" onClick={() => open({
              pending: true,
              task: data.pending.context?.task || '',
              ai_label: data.pending.verdict === '错' ? 'off_task' : 'on_task',
              captured_at: data.pending.captured_at
            })}>{t('correct')}</button><button className="text-button" disabled={busy} onClick={() => act(() => api.discardPersonalBenchPendingCapture())}>{t('discard')}</button></div>}{!data?.recent.length && <p className="empty">{t('noRecords')}</p>}{data?.recent.map(x => <article className="record" key={x.id}><span className="record-symbol">▤</span><div className="record-content"><div className="record-title">{x.task}</div><div className="record-detail">{x.ai_activity} · {x.ai_reason}</div></div><time>{new Date(x.captured_at).toLocaleString(ui)}</time><span className={`pill ${x.ai_label === 'off_task' ? 'warning' : ''}`}>{t(x.judgement_status === 'api_error' ? 'errorTitle' : x.ai_label === 'on_task' ? 'onTask' : 'offTask')}</span><button className="text-button" onClick={() => open(x)}>{t('review')} ↗</button></article>)}</section>}
 {view === 'cases' && <section className="view"><div className="page-heading"><div><h1>{t('cases')}</h1><p>{t('casesIntro')}</p></div><span className="pill neutral">{data?.samples.length || 0}</span></div><div className="case-info"><span>✧</span><p>{t('caseInfo')}</p></div><div className="case-grid">{!data?.samples.length && <p className="empty">{t('empty')}</p>}{data?.samples.map(x => <article className="case-card" key={x.id}><img className="case-image" src={api.getPersonalBenchSampleImageUrl(x)} alt={x.task} loading="lazy" onError={e => {
                e.currentTarget.hidden = true;
              }} /><div className="case-card-body"><span className={`pill ${x.human_label === 'off_task' ? 'warning' : ''}`}>{t(x.human_label === 'on_task' ? 'onTask' : 'offTask')}</span><h2>{x.task}</h2><p>{x.human_reason}</p><div className="case-footer"><time>{new Date(x.added_at || x.captured_at).toLocaleDateString(ui)}</time><button className="text-button delete-case" disabled={busy} onClick={() => {
                    if (window.confirm(t('confirmation'))) act(() => api.deletePersonalBenchSample(x.id));
                  }}>{t('delete')}</button></div></div></article>)}</div></section>}
 {view === 'settings' && draft && <section className="view"><div className="page-heading"><div><h1>{t('settings')}</h1><p>{t('settingsIntro')}</p></div></div><form className="settings-card" onSubmit={e => {
            e.preventDefault();
            act(async () => {
              await api.saveSettings({
                ui_language: draft.ui_language,
                recovery_mode: draft.recovery_mode,
                practice_target_language: draft.practice_target_language,
                model: draft.model,
                default_check_interval_seconds: Number(draft.default_check_interval_seconds),
                trigger_threshold: Number(draft.trigger_threshold)
              });
              dirty.current = false;
              setMessage(t('savedSettings'));
            });
          }}><h2>{t('recoveryMethod')}</h2><div className="setting-row"><div><label htmlFor="recovery">{t('recoveryMethod')}</label><p>{t('recoveryHint')}</p></div><select id="recovery" value={draft.recovery_mode || 'quick_return'} onChange={e => edit('recovery_mode', e.target.value)}>{recoveryOptions.map(([value, key]) => <option key={value} value={value}>{t(key)}</option>)}</select></div>{(draft.recovery_mode || 'quick_return') === 'translation' && <div className="setting-row"><div><label htmlFor="target">{t('answerLanguage')}</label><p>{t('answerHint')}</p></div><select id="target" value={draft.practice_target_language} onChange={e => edit('practice_target_language', e.target.value)}>{targets.map((v, i) => <option key={v} value={v}>{strings.LANGS[codes[i]]}</option>)}</select></div>}<h2>{t('languages')}</h2><div className="setting-row"><div><label>{t('uiLanguage')}</label><p>{t('uiHint')}</p></div>{select(draft.ui_language, v => edit('ui_language', v))}</div><details><summary>{t('advanced')}</summary><div className="setting-row"><label htmlFor="model">{t('model')}</label><select id="model" value={draft.model} onChange={e => edit('model', e.target.value)}>{data.settings.model_options?.map(m => <option key={m.id} value={m.id}>{m.id}</option>)}</select></div><div className="setting-row"><label htmlFor="interval">{t('interval')}</label><input id="interval" type="number" min="5" max="3600" required value={draft.default_check_interval_seconds} onChange={e => edit('default_check_interval_seconds', e.target.value)} /></div><div className="setting-row"><label htmlFor="threshold">{t('threshold')}</label><input id="threshold" type="number" min="1" max="20" required value={draft.trigger_threshold} onChange={e => edit('trigger_threshold', e.target.value)} /></div></details><button className="primary" disabled={busy || !connected}>{t('save')}</button></form></section>}
 </main><footer><span>FocusGuard</span><span>{t('footer')}</span></footer></div>
 <dialog ref={dialog} className="correction-dialog" onCancel={close} onClose={() => setItem(null)}><form onSubmit={e => {
        e.preventDefault();
        act(async () => {
          if (item.pending) await api.mvpRequest('/pending-feedback', {
            label,
            reason: reason.trim(),
            task: caseTask.trim(),
            captured_at: item.captured_at
          });else await api.mvpRequest('/feedback', {
            record_id: item.id,
            label,
            reason: reason.trim()
          });
          close();
          setMessage(t('saved'));
        });
      }}><div className="card-top"><h2>{t('correctTitle')}</h2><button type="button" className="icon-button" disabled={busy} onClick={close}>×</button></div>{item && <><p>{item.task}</p>{item.screenshot_path || item.pending ? <img className="feedback-image" src={item.pending ? api.getPersonalBenchPendingImageUrl(item) : api.getPersonalBenchRecentImageUrl(item)} alt={t('review')} onError={e => {
            e.currentTarget.hidden = true;
          }} /> : <p>{t('noImage')}</p>}<p>{item.ai_reason}</p>{item.pending && <label className="field-label">{t('taskLabel')}<input value={caseTask} onChange={e => setCaseTask(e.target.value)} required maxLength={500} /></label>}<fieldset><legend>{t('actualLabel')}</legend>{['on_task', 'off_task'].map(v => <label key={v} className="radio-choice"><input type="radio" name="label" checked={label === v} onChange={() => setLabel(v)} />{t(v === 'on_task' ? 'onTask' : 'offTask')}</label>)}</fieldset><label className="field-label" htmlFor="reason">{t('reasonLabel')}</label><textarea id="reason" rows="3" required maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /><p className="subtle">{t('saveHint')}</p>{error && <p role="alert" className="app-error">{error}</p>}<button className="primary wide" disabled={busy || !reason.trim() || !item.pending && !item.screenshot_path}>{t('saveCase')}</button></>}</form></dialog>{message && <div className="toast" role="status">{message}</div>}
 </div>;
}
