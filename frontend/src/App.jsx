import { useState, useEffect, useRef } from 'react'
import {
  startSession, stopSession, getStatus,
  startGuardianEntertainment,
  startGuardianBreak,
  getSchedules, addSchedule, deleteSchedule,
  getDailyReport, testBlock,
  getSettings, saveSettings, getAiStatus,
  getPracticeStatus, uploadPracticeFile,
  saveDailyNotes,
  getGuardianImageUrl,
  getPersonalBenchRecent,
  getPersonalBenchRecentImageUrl,
  getPersonalBenchSamples,
  getPersonalBenchSampleImageUrl,
  getPersonalBenchCaptureContext,
  getPersonalBenchPendingCapture,
  getPersonalBenchPendingImageUrl,
  takePersonalBenchPendingCapture,
  updatePersonalBenchPendingVerdict,
  commitPersonalBenchPendingCapture,
  discardPersonalBenchPendingCapture,
  movePersonalBenchSample,
  deletePersonalBenchSample,
  addPersonalBenchFromRecent,
} from './api'

function todayString() {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const IDLE_STATUS_POLL_MS = 15000
const ACTIVE_STATUS_POLL_MS = 30000
const COUNTDOWN_TICK_MS = 10000

function App() {
  const [tab, setTab] = useState('session')
  const [task, setTask] = useState('')
  const [tags, setTags] = useState('')
  const [sessionStrict, setSessionStrict] = useState(true)
  const [duration, setDuration] = useState('30')
  const [interval, setInterval_] = useState('300')
  const [triggerThreshold, setTriggerThreshold] = useState('1')
  const [status, setStatus] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [remainingSeconds, setRemainingSeconds] = useState(0)
  const [flowRemainingSeconds, setFlowRemainingSeconds] = useState(0)
  const [formError, setFormError] = useState('')
  const [stopReason, setStopReason] = useState('')
  const [stopMinutes, setStopMinutes] = useState('10')
  const [stopTags, setStopTags] = useState('')
  const [showStopForm, setShowStopForm] = useState(false)
  const taskRef = useRef(null)
  const sessionEndsAtRef = useRef(0)
  const flowEndsAtRef = useRef(0)
  const completionCheckedRef = useRef(false)

  const [aiStatus, setAiStatus] = useState(null)
  const [schedules, setSchedules] = useState([])
  const [schedTask, setSchedTask] = useState('')
  const [schedTags, setSchedTags] = useState('')
  const [schedStrict, setSchedStrict] = useState(true)
  const [schedInterval, setSchedInterval] = useState('300')
  const [schedTriggerThreshold, setSchedTriggerThreshold] = useState('1')
  const [schedDate, setSchedDate] = useState(todayString())
  const [schedStart, setSchedStart] = useState('')
  const [schedEnd, setSchedEnd] = useState('')
  const [scheduleError, setScheduleError] = useState('')

  const [reportDate, setReportDate] = useState(todayString())
  const [dailyReport, setDailyReport] = useState(null)
  const [todaySummary, setTodaySummary] = useState('')
  const [tomorrowPlan, setTomorrowPlan] = useState('')
  const [notesStatus, setNotesStatus] = useState('')
  const [settings, setSettings] = useState(null)
  const [modelOptions, setModelOptions] = useState([])
  const [supervisionLevelOptions, setSupervisionLevelOptions] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [selectedSupervisionLevel, setSelectedSupervisionLevel] = useState('not_entertainment')
  const [nudgePrompt, setNudgePrompt] = useState('')
  const [defaultInterval, setDefaultInterval] = useState('300')
  const [postBlockCooldown, setPostBlockCooldown] = useState('300')
  const [defaultTriggerThreshold, setDefaultTriggerThreshold] = useState('1')
  const [whitelistText, setWhitelistText] = useState('')
  const [guardianEnabled, setGuardianEnabled] = useState(true)
  const [guardianInterval, setGuardianInterval] = useState('300')
  const [guardianEntertainmentMinutes, setGuardianEntertainmentMinutes] = useState('20')
  const [guardianRestMinutes, setGuardianRestMinutes] = useState('10')
  const [guardianDailyEntertainmentLimit, setGuardianDailyEntertainmentLimit] = useState('60')
  const [guardianRestQuota, setGuardianRestQuota] = useState('3')
  const [guardianDayStartTime, setGuardianDayStartTime] = useState('04:00')
  const [guardianActionStatus, setGuardianActionStatus] = useState('')
  const [practiceTargetLanguage, setPracticeTargetLanguage] = useState('Japanese')
  const [practiceStatus, setPracticeStatus] = useState(null)
  const [practiceUploadStatus, setPracticeUploadStatus] = useState('')
  const [datasetTagOptions, setDatasetTagOptions] = useState(['guardian mode'])
  const [datasetTagOptionsText, setDatasetTagOptionsText] = useState('guardian mode')
  const [personalBenchRoot, setPersonalBenchRoot] = useState('')
  const [personalBenchStatus, setPersonalBenchStatus] = useState(null)
  const [settingsStatus, setSettingsStatus] = useState('')
  const [captureContext, setCaptureContext] = useState({
    mode: 'guardian',
    task: '',
    supervision_level: '',
    activity: '',
    note: '',
    split: 'train',
  })
  const [benchSamples, setBenchSamples] = useState([])
  const [benchSampleId, setBenchSampleId] = useState(null)
  const [benchSplitFilter, setBenchSplitFilter] = useState('')
  const [pendingCapture, setPendingCapture] = useState(null)
  const [benchSaving, setBenchSaving] = useState(false)
  const [datasetStatus, setDatasetStatus] = useState('')
  const [recentJudgments, setRecentJudgments] = useState([])
  const [expandedJudgmentId, setExpandedJudgmentId] = useState(null)
  const [benchHumanLabel, setBenchHumanLabel] = useState('')
  const [benchHumanReason, setBenchHumanReason] = useState('')
  const [benchStatus, setBenchStatus] = useState('')

  const applySessionStatus = (s) => {
    setStatus(s)
    setSessionId(s.session_id || null)
    const active = Boolean(s.active)
    setIsRunning(active)
    if (active && typeof s.remaining_seconds === 'number') {
      sessionEndsAtRef.current = Date.now() + s.remaining_seconds * 1000
      setRemainingSeconds(s.remaining_seconds)
      completionCheckedRef.current = false
    }
    if (!active && s.flow_status?.active && typeof s.flow_status.remaining_seconds === 'number') {
      flowEndsAtRef.current = Date.now() + s.flow_status.remaining_seconds * 1000
      setFlowRemainingSeconds(s.flow_status.remaining_seconds)
    } else if (!s.flow_status?.active) {
      flowEndsAtRef.current = 0
      setFlowRemainingSeconds(0)
    }
  }

  useEffect(() => {
    const poll = async () => {
      try {
        applySessionStatus(await getStatus())
      } catch (e) {
        // Backend may still be starting.
      }
    }
    poll()
    const intervalMs = isRunning ? ACTIVE_STATUS_POLL_MS : IDLE_STATUS_POLL_MS
    const id = window.setInterval(poll, intervalMs)
    return () => window.clearInterval(id)
  }, [isRunning])

  useEffect(() => {
    if (!isRunning) {
      completionCheckedRef.current = false
      setRemainingSeconds(0)
      return
    }
    if (status?.should_block || status?.paused_for_rest) {
      return
    }

    const tick = () => {
      const left = Math.max(0, Math.ceil((sessionEndsAtRef.current - Date.now()) / 1000))
      setRemainingSeconds(left)
      if (left <= 0 && !completionCheckedRef.current) {
        completionCheckedRef.current = true
        getStatus()
          .then((s) => applySessionStatus(s))
          .catch(() => {})
      }
    }

    tick()
    const id = window.setInterval(tick, COUNTDOWN_TICK_MS)
    return () => window.clearInterval(id)
  }, [isRunning, status?.should_block, status?.paused_for_rest])

  useEffect(() => {
    if (isRunning || !status?.flow_status?.active) return

    const tick = () => {
      const left = Math.max(0, Math.ceil((flowEndsAtRef.current - Date.now()) / 1000))
      setFlowRemainingSeconds(left)
      if (left <= 0) {
        getStatus()
          .then((s) => applySessionStatus(s))
          .catch(() => {})
      }
    }

    tick()
    const id = window.setInterval(tick, COUNTDOWN_TICK_MS)
    return () => window.clearInterval(id)
  }, [isRunning, status?.flow_status?.active])

  useEffect(() => {
    const pollAi = async () => {
      try {
        setAiStatus(await getAiStatus())
      } catch (e) {
        setAiStatus({ state: 'error', message: '无法连接后端。' })
      }
    }
    pollAi()
    const id = window.setInterval(pollAi, 10000)
    return () => window.clearInterval(id)
  }, [])

  const refreshRecentJudgments = async () => {
    try {
      const data = await getPersonalBenchRecent(10)
      setRecentJudgments(data.items || [])
    } catch (e) {
      // Keep previous list if backend is still starting.
    }
  }

  useEffect(() => {
    if (tab !== 'session') return
    refreshRecentJudgments()
    const id = window.setInterval(refreshRecentJudgments, 30000)
    return () => window.clearInterval(id)
  }, [tab])

  useEffect(() => {
    if (tab === 'schedule') {
      refreshSchedules()
      const id = window.setInterval(refreshSchedules, 5000)
      return () => window.clearInterval(id)
    }
  }, [tab])

  useEffect(() => {
    if (tab === 'report') {
      refreshReport()
    }
  }, [tab, reportDate])

  useEffect(() => {
    if (tab === 'settings') {
      getSettings()
        .then((d) => {
          setSettings(d.settings)
          setModelOptions(d.model_options || [])
          setSupervisionLevelOptions(d.supervision_level_options || [])
          setSelectedModel(d.settings?.model || '')
          setSelectedSupervisionLevel(d.settings?.supervision_level || 'not_entertainment')
          setNudgePrompt(d.settings?.nudge_prompt || '')
          setDefaultInterval(String(d.settings?.default_check_interval_seconds || 300))
          setPostBlockCooldown(String(d.settings?.post_block_cooldown_seconds ?? 300))
          setDefaultTriggerThreshold(String(d.settings?.trigger_threshold || 1))
          setWhitelistText((d.settings?.whitelist_behaviors || []).join('\n'))
          setGuardianEnabled(Boolean(d.settings?.guardian_mode_enabled ?? true))
          setGuardianInterval(String(d.settings?.guardian_check_interval_seconds || 300))
          setGuardianDailyEntertainmentLimit(String(d.settings?.guardian_entertainment_daily_limit_minutes ?? 60))
          setGuardianRestQuota(String(
            d.settings?.guardian_rest_quota_pending ?? d.settings?.guardian_rest_quota_per_day ?? 3
          ))
          setGuardianDayStartTime(d.settings?.guardian_entertainment_day_start_time || '04:00')
          setPracticeTargetLanguage(d.settings?.practice_target_language || 'Japanese')
          setDatasetTagOptions(d.settings?.dataset_tag_options || ['guardian mode'])
          setDatasetTagOptionsText((d.settings?.dataset_tag_options || ['guardian mode']).join('\n'))
          setPersonalBenchRoot(d.settings?.personal_bench_root || '')
          setPersonalBenchStatus(d.personal_bench || null)
          setSettingsStatus('')
        })
        .catch(() => setSettingsStatus('设置读取失败'))
    }
  }, [tab])

  const captureContextLoadedRef = useRef(false)

  useEffect(() => {
    const onPending = () => {
      setTab('dataset')
      refreshPendingCapture()
    }
    window.addEventListener('aimonitor-pending-capture', onPending)
    return () => window.removeEventListener('aimonitor-pending-capture', onPending)
  }, [])

  useEffect(() => {
    if (tab !== 'dataset') return
    if (!captureContextLoadedRef.current) {
      captureContextLoadedRef.current = true
      getPersonalBenchCaptureContext()
        .then((d) => {
          const c = d.context || {}
          setCaptureContext({
            mode: c.mode || 'guardian',
            task: c.task || '',
            supervision_level: c.supervision_level || '',
            activity: c.activity || '',
            note: c.note || '',
            split: c.split || 'train',
          })
        })
        .catch(() => {})
    }
    refreshPendingCapture()
    refreshBenchSamples()
    const id = window.setInterval(() => {
      refreshPendingCapture()
      refreshBenchSamples()
    }, 4000)
    return () => window.clearInterval(id)
  }, [tab, benchSplitFilter])

  useEffect(() => {
    if (tab === 'settings') {
      getPracticeStatus()
        .then(setPracticeStatus)
        .catch(() => {})
    }
  }, [tab])

  const refreshSchedules = async () => {
    try {
      const d = await getSchedules()
      setSchedules(d.schedules || [])
    } catch (e) {
      // Keep the last loaded list.
    }
  }

  const refreshReport = async () => {
    try {
      const report = await getDailyReport(reportDate)
      setDailyReport(report)
      setTodaySummary(report.today_summary || '')
      setTomorrowPlan(report.tomorrow_plan || '')
      setNotesStatus('')
    } catch (e) {
      setDailyReport(null)
    }
  }

  const refreshBenchSamples = async () => {
    try {
      const data = await getPersonalBenchSamples(benchSplitFilter)
      const samples = data.samples || []
      setBenchSamples(samples)
      setBenchSampleId((id) => {
        if (id && samples.some((s) => s.id === id)) return id
        return samples[0]?.id || null
      })
    } catch (e) {
      setDatasetStatus(e.message || '样本读取失败')
    }
  }

  const refreshPendingCapture = async () => {
    try {
      const data = await getPersonalBenchPendingCapture()
      const next = data.pending || null
      setPendingCapture((prev) => {
        if (!next) return null
        if (prev && prev.captured_at === next.captured_at) {
          return { ...next, verdict: prev.verdict || next.verdict }
        }
        return next
      })
    } catch (e) {
      // Keep the last pending screenshot if the poll fails.
    }
  }

  const currentBenchSample = benchSamples.find((s) => s.id === benchSampleId) || null

  const updateCaptureField = (key, value) => {
    setCaptureContext((prev) => {
      const next = { ...prev, [key]: value }
      if (key === 'mode' && value === 'guardian') next.task = ''
      return next
    })
  }

  const capturePending = async (verdict) => {
    try {
      const result = await takePersonalBenchPendingCapture(verdict)
      setPendingCapture(result.pending || null)
      setDatasetStatus(result.pending?.replaced ? '已截图（覆盖了未保存的上一张）' : '已截图，请对着图填 context 后保存')
    } catch (e) {
      setDatasetStatus(e.message || '截图失败')
    }
  }

  const setPendingVerdict = async (verdict) => {
    if (!pendingCapture) {
      await capturePending(verdict)
      return
    }
    try {
      const result = await updatePersonalBenchPendingVerdict(verdict)
      setPendingCapture(result.pending || { ...pendingCapture, verdict })
      setDatasetStatus(`已标记：${verdict}`)
    } catch (e) {
      setDatasetStatus(e.message || '标记失败')
    }
  }

  const commitPending = async (verdict) => {
    const chosen = verdict || pendingCapture?.verdict
    if (!pendingCapture) {
      setDatasetStatus('请先截图，再填 context 保存')
      return
    }
    if (!chosen) {
      setDatasetStatus('请选择对或错')
      return
    }
    if (benchSaving) return
    setBenchSaving(true)
    try {
      const result = await commitPersonalBenchPendingCapture({
        verdict: chosen,
        mode: captureContext.mode,
        task: captureContext.mode === 'session' ? captureContext.task : '',
        supervision_level: captureContext.supervision_level || null,
        activity: captureContext.activity,
        note: captureContext.note,
        split: captureContext.split,
      })
      const sample = result.sample
      setPendingCapture(null)
      if (sample && (!benchSplitFilter || sample.split === benchSplitFilter)) {
        setBenchSamples((list) => [sample, ...list.filter((s) => s.id !== sample.id)])
        setBenchSampleId(sample.id)
      } else {
        await refreshBenchSamples()
      }
      setCaptureContext((prev) => ({ ...prev, activity: '', note: '' }))
      setDatasetStatus(`已入库：${sample?.verdict || chosen} → ${sample?.human_label || ''}`)
    } catch (e) {
      setDatasetStatus(e.message || '保存失败')
    } finally {
      setBenchSaving(false)
    }
  }

  const discardPending = async () => {
    try {
      await discardPersonalBenchPendingCapture()
      setPendingCapture(null)
      setDatasetStatus('已丢弃未保存截图')
    } catch (e) {
      setDatasetStatus(e.message || '丢弃失败')
    }
  }

  const moveBenchSample = async (split) => {
    if (!currentBenchSample) return
    try {
      await movePersonalBenchSample(currentBenchSample.id, split)
      await refreshBenchSamples()
      setDatasetStatus(`已移到 ${split}`)
    } catch (e) {
      setDatasetStatus(e.message || '移动失败')
    }
  }

  const deleteBenchSample = async () => {
    if (!currentBenchSample) return
    try {
      await deletePersonalBenchSample(currentBenchSample.id)
      const next = benchSamples.filter((s) => s.id !== currentBenchSample.id)
      setBenchSamples(next)
      setBenchSampleId(next[0]?.id || null)
      setDatasetStatus('样本已删除')
    } catch (e) {
      setDatasetStatus(e.message || '删除失败')
    }
  }

  const parsePositiveInt = (value, min) => {
    if (value === '') return null
    const n = Number(value)
    return Number.isInteger(n) && n >= min ? n : null
  }

  const parseTags = (value) => value
    .replace(/，/g, ',')
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)

  const parsePresetTags = (value) => {
    const tags = value
      .replace(/，/g, '\n')
      .replace(/,/g, '\n')
      .split('\n')
      .map((tag) => tag.trim())
      .filter(Boolean)
    const hasGuardian = tags.some((tag) => tag.toLowerCase() === 'guardian mode')
    return hasGuardian ? tags : ['guardian mode', ...tags]
  }

  const handleStart = async () => {
    setFormError('')
    const durationMinutes = parsePositiveInt(duration, 1)
    const checkIntervalSeconds = parsePositiveInt(interval, 5)
    const threshold = parsePositiveInt(triggerThreshold, 1)

    if (!task.trim()) {
      setFormError('请输入当前要完成的任务。')
      taskRef.current?.focus()
      return
    }
    if (durationMinutes === null) {
      setFormError('工作时长需要是 1 分钟以上的整数。')
      return
    }
    if (checkIntervalSeconds === null) {
      setFormError('检查间隔需要是 5 秒以上的整数。')
      return
    }
    if (threshold === null) {
      setFormError('触发答题命中次数需要是 1 以上的整数。')
      return
    }

    try {
      const res = await startSession(
        task.trim(),
        durationMinutes,
        checkIntervalSeconds,
        parseTags(tags),
        sessionStrict,
        threshold,
      )
      setSessionId(res.session_id)
      setIsRunning(true)
      sessionEndsAtRef.current = Date.now() + durationMinutes * 60 * 1000
      setRemainingSeconds(durationMinutes * 60)
      completionCheckedRef.current = false
    } catch (e) {
      setFormError(e.message || '无法启动监督。')
    }
  }

  const handleStop = async () => {
    setStopTags((status?.tags || []).join(', '))
    setShowStopForm(true)
  }

  const handleStartGuardianEntertainment = async () => {
    setGuardianActionStatus('')
    const minutes = parsePositiveInt(guardianEntertainmentMinutes, 1)
    if (minutes === null) {
      setGuardianActionStatus('请输入 1 分钟以上的娱乐时长。')
      return
    }
    try {
      await startGuardianEntertainment(minutes)
      setGuardianActionStatus('娱乐时间已开始。')
      applySessionStatus(await getStatus())
    } catch (e) {
      setGuardianActionStatus(e.message || '无法开始娱乐时间。')
    }
  }

  const handleStartGuardianRest = async () => {
    setGuardianActionStatus('')
    const minutes = parsePositiveInt(guardianRestMinutes, 1)
    if (minutes === null) {
      setGuardianActionStatus('请输入 1 分钟以上的休息时长。')
      return
    }
    try {
      await startGuardianBreak(minutes, '回到工作')
      setGuardianActionStatus('休息已开始。Session 和 Guardian 都会暂停，结束后答题再继续。')
      applySessionStatus(await getStatus())
    } catch (e) {
      setGuardianActionStatus(e.message || '无法开始休息。')
    }
  }

  const handlePracticeUpload = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setPracticeUploadStatus('上传中...')
    try {
      const content = await file.text()
      const res = await uploadPracticeFile(file.name, content)
      setPracticeStatus({
        source_path: res.path,
        source_name: res.name,
        item_count: res.item_count,
        target_language: res.settings?.practice_target_language || practiceTargetLanguage,
      })
      setSettings(res.settings)
      setPracticeUploadStatus(`已选择 ${res.name}，共 ${res.item_count} 条。`)
    } catch (e) {
      setPracticeUploadStatus(e.message || '上传失败')
    } finally {
      event.target.value = ''
    }
  }

  const handleConfirmStop = async () => {
    setFormError('')
    const minutes = parsePositiveInt(stopMinutes, 1)
    if (!stopReason.trim()) {
      setFormError('请输入停止原因。')
      return
    }
    if (minutes === null) {
      setFormError('停止多久需要是 1 分钟以上的整数。')
      return
    }

    await stopSession(sessionId, stopReason.trim(), minutes, parseTags(stopTags))
    setIsRunning(false)
    setRemainingSeconds(0)
    sessionEndsAtRef.current = 0
    setShowStopForm(false)
    setStopReason('')
    setStopTags('')
    await refreshReport()
  }

  const handleAddSchedule = async () => {
    setScheduleError('')
    const checkIntervalSeconds = parsePositiveInt(schedInterval, 5)
    const threshold = parsePositiveInt(schedTriggerThreshold, 1)
    if (!schedTask.trim() || !schedDate || !schedStart || !schedEnd) {
      setScheduleError('请填写任务、日期、开始时间和结束时间。')
      return
    }
    if (checkIntervalSeconds === null) {
      setScheduleError('检查间隔需要是 5 秒以上的整数。')
      return
    }
    if (threshold === null) {
      setScheduleError('触发答题命中次数需要是 1 以上的整数。')
      return
    }

    try {
      await addSchedule(
        schedTask.trim(),
        schedDate,
        schedStart,
        schedEnd,
        checkIntervalSeconds,
        parseTags(schedTags),
        schedStrict,
        threshold,
      )
      await refreshSchedules()
      setSchedTask('')
      setSchedTags('')
      setSchedStrict(true)
      setSchedInterval(defaultInterval || '300')
      setSchedTriggerThreshold(defaultTriggerThreshold || '1')
      setSchedStart('')
      setSchedEnd('')
    } catch (e) {
      setScheduleError(e.message || '无法添加日程。')
    }
  }

  const handleDeleteSchedule = async (id) => {
    await deleteSchedule(id)
    await refreshSchedules()
  }

  const formatTime = (seconds) => {
    if (!seconds && seconds !== 0) return '--:--'
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }

  const getStatusLabel = () => {
    if (!status || !status.active) return '待机中'
    if (status.paused_for_rest) {
      return guardianBreakStatus?.active ? '休息中（Session 已暂停）' : '等待恢复'
    }
    if (!status.latest_judgement) return '等待首次检查'
    if (status.latest_judgement.judgement_status === 'api_error') return 'AI 未连接'
    return status.latest_judgement.on_task ? '专注中' : '疑似分心'
  }

  const handleSaveSettings = async () => {
    if (!selectedModel) return
    const defaultIntervalSeconds = parsePositiveInt(defaultInterval, 5)
    const postBlockCooldownSeconds = parsePositiveInt(postBlockCooldown, 0)
    const defaultThreshold = parsePositiveInt(defaultTriggerThreshold, 1)
    const guardianIntervalSeconds = parsePositiveInt(guardianInterval, 30)
    const guardianDailyLimitMinutes = parsePositiveInt(guardianDailyEntertainmentLimit, 0)
    const restQuota = parsePositiveInt(guardianRestQuota, 0)
    if (!nudgePrompt.trim()) {
      setSettingsStatus('提示语不能为空。')
      return
    }
    if (defaultIntervalSeconds === null) {
      setSettingsStatus('默认检测间隔需要是 5 秒以上的整数。')
      return
    }
    if (postBlockCooldownSeconds === null || postBlockCooldownSeconds > 3600) {
      setSettingsStatus('答完题后的冷却时间需要是 0 到 3600 秒的整数。')
      return
    }
    if (defaultThreshold === null) {
      setSettingsStatus('默认触发答题命中次数需要是 1 以上的整数。')
      return
    }
    if (guardianIntervalSeconds === null) {
      setSettingsStatus('Guardian mode 检测间隔需要是 30 秒以上的整数。')
      return
    }
    if (guardianDailyLimitMinutes === null) {
      setSettingsStatus('Guardian 每日娱乐额度需要是 0 分钟以上的整数。')
      return
    }
    if (restQuota === null || restQuota > 20) {
      setSettingsStatus('每日休息次数需要是 0 到 20 的整数。')
      return
    }
    if (!/^\d{1,2}:\d{2}$/.test(guardianDayStartTime)) {
      setSettingsStatus('Guardian 新一天开始时间需要是 HH:MM。')
      return
    }
    if (!practiceTargetLanguage.trim()) {
      setSettingsStatus('Practice 目标语言不能为空。')
      return
    }
    setSettingsStatus('保存中...')
    try {
      const res = await saveSettings({
        model: selectedModel,
        supervision_level: selectedSupervisionLevel,
        nudge_prompt: nudgePrompt.trim(),
        default_check_interval_seconds: defaultIntervalSeconds,
        post_block_cooldown_seconds: postBlockCooldownSeconds,
        trigger_threshold: defaultThreshold,
        whitelist_behaviors: whitelistText
          .replace(/，/g, '\n')
          .replace(/,/g, '\n')
          .split('\n')
          .map((item) => item.trim())
          .filter(Boolean),
        guardian_mode_enabled: guardianEnabled,
        guardian_check_interval_seconds: guardianIntervalSeconds,
        guardian_entertainment_daily_limit_minutes: guardianDailyLimitMinutes,
        guardian_entertainment_day_start_time: guardianDayStartTime,
        guardian_rest_quota_per_day: restQuota,
        practice_target_language: practiceTargetLanguage.trim(),
        dataset_tag_options: parsePresetTags(datasetTagOptionsText),
        personal_bench_root: personalBenchRoot.trim(),
        strict_mode_enabled: true,
      })
      setSettings(res.settings)
      setDefaultInterval(String(res.settings?.default_check_interval_seconds || defaultIntervalSeconds))
      setPostBlockCooldown(String(res.settings?.post_block_cooldown_seconds ?? postBlockCooldownSeconds))
      setDefaultTriggerThreshold(String(res.settings?.trigger_threshold || defaultThreshold))
      setWhitelistText((res.settings?.whitelist_behaviors || []).join('\n'))
      setGuardianEnabled(Boolean(res.settings?.guardian_mode_enabled ?? guardianEnabled))
      setGuardianInterval(String(res.settings?.guardian_check_interval_seconds || guardianIntervalSeconds))
      setGuardianDailyEntertainmentLimit(String(res.settings?.guardian_entertainment_daily_limit_minutes ?? guardianDailyLimitMinutes))
      setGuardianRestQuota(String(
        res.settings?.guardian_rest_quota_pending ?? res.settings?.guardian_rest_quota_per_day ?? restQuota
      ))
      setGuardianDayStartTime(res.settings?.guardian_entertainment_day_start_time || guardianDayStartTime)
      setPracticeTargetLanguage(res.settings?.practice_target_language || practiceTargetLanguage.trim())
      setDatasetTagOptions(res.settings?.dataset_tag_options || ['guardian mode'])
      setDatasetTagOptionsText((res.settings?.dataset_tag_options || ['guardian mode']).join('\n'))
      setPersonalBenchRoot(res.settings?.personal_bench_root || '')
      setPersonalBenchStatus(res.personal_bench || null)
      setSettingsStatus('已保存，下一次 AI 判定生效。')
      setAiStatus(await getAiStatus())
    } catch (e) {
      setSettingsStatus(e.message || '保存失败')
    }
  }

  const handleSaveNotes = async () => {
    setNotesStatus('保存中...')
    try {
      setDailyReport(await saveDailyNotes(reportDate, todaySummary, tomorrowPlan))
      setNotesStatus('已保存')
    } catch (e) {
      setNotesStatus(e.message || '保存失败')
    }
  }

  const labelsForBenchMode = (mode) => (
    mode === 'guardian'
      ? ['allow', 'interrupt', 'ambiguous']
      : ['on_task', 'off_task', 'ambiguous']
  )

  const toggleJudgmentExpand = (item) => {
    if (expandedJudgmentId === item.id) {
      setExpandedJudgmentId(null)
      return
    }
    setExpandedJudgmentId(item.id)
    setBenchHumanLabel(item.suggested_human_label || (item.mode === 'guardian' ? 'allow' : 'on_task'))
    setBenchHumanReason('')
    setBenchStatus('')
  }

  const handleAddToPersonalBench = async (item) => {
    if (!item?.screenshot_available) {
      setBenchStatus('该条没有可用截图，无法加入校准集。')
      return
    }
    try {
      const result = await addPersonalBenchFromRecent({
        mode: item.mode,
        human_label: benchHumanLabel || item.suggested_human_label,
        screenshot_path: item.screenshot_path,
        split: 'train',
        task: item.task || '',
        supervision_level: item.supervision_level,
        human_reason: benchHumanReason,
        ai_activity: item.ai_activity,
        ai_reason: item.ai_reason,
        ai_label: item.ai_label,
        captured_at: item.captured_at,
        source: item.source,
      })
      setBenchStatus(`已加入 train：${result.sample?.human_label} · ${result.sample?.id?.slice(0, 8)}`)
    } catch (e) {
      setBenchStatus(e.message || '加入失败')
    }
  }

  const aiClass = aiStatus?.state === 'connected' ? 'ok' : aiStatus?.state === 'unknown' ? 'warn' : 'bad'
  const statusText = status?.latest_judgement?.judgement_status === 'api_error'
    ? status.latest_judgement.reason
    : status?.latest_judgement?.reason || '--'

  const statusName = {
    completed: '已完成',
    stopped: '手动停止',
    replaced: '被新任务替换',
    missed: '已错过',
    skipped_conflict: '冲突跳过',
    break: '休息',
    stopped_pending: '停止中',
    day_paused: '暂停今日',
  }

  const flowStatus = status?.flow_status
  const strictStatus = status?.strict_status
  const guardianStatus = status?.guardian_status
  const guardianJudgement = guardianStatus?.latest_judgement
  const guardianBreakStatus = guardianStatus?.break_status
  const guardianEntertainmentStatus = guardianStatus?.entertainment_status
  const guardianRestStatus = guardianStatus?.rest_status
  const guardianStateLabel = guardianBreakStatus?.active
    ? '休息中'
    : guardianStatus?.paused_by_session
    ? 'Session 中暂停'
    : guardianStatus?.effective_enabled
      ? '运行中'
      : '关闭'

  const guardianEffectiveStateLabel = guardianBreakStatus?.active
    ? '休息中'
    : guardianEntertainmentStatus?.active
      ? '娱乐时间中'
      : guardianStatus?.paused_by_session
        ? 'Session 中暂停'
        : guardianStatus?.effective_enabled
          ? '运行中'
          : '关闭'

  const blockStart = (b) => b.actual_start || b.planned_start
  const blockEnd = (b) => b.actual_end || b.planned_end

  const formatClock = (value) => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--'

  const buildTimeline = () => {
    const blocks = (dailyReport?.blocks || [])
      .filter((b) => blockStart(b))
      .map((b) => ({
        ...b,
        startDate: new Date(blockStart(b)),
        endDate: blockEnd(b) ? new Date(blockEnd(b)) : new Date(),
      }))
      .filter((b) => !Number.isNaN(b.startDate.getTime()))
      .sort((a, b) => a.startDate - b.startDate)

    if (blocks.length === 0) return { segments: [], start: null, end: null }

    const start = blocks[0].startDate
    const end = new Date()
    const totalMs = Math.max(1, end - start)
    const segments = []
    let cursor = start

    blocks.forEach((block) => {
      const blockStartDate = block.startDate < start ? start : block.startDate
      const blockEndDate = block.endDate > end ? end : block.endDate
      if (blockStartDate > cursor) {
        segments.push({ kind: 'idle', label: '无指令', width: ((blockStartDate - cursor) / totalMs) * 100 })
      }
      if (blockEndDate > blockStartDate) {
        const kind = block.status === 'break' ? 'break' : block.status === 'stopped_pending' ? 'stopped' : 'focus'
        segments.push({
          kind,
          label: block.task || statusName[block.status] || block.status,
          width: ((blockEndDate - blockStartDate) / totalMs) * 100,
        })
        cursor = blockEndDate > cursor ? blockEndDate : cursor
      }
    })

    if (cursor < end) {
      segments.push({ kind: 'idle', label: '无指令', width: ((end - cursor) / totalMs) * 100 })
    }

    return { segments, start, end }
  }

  return (
    <div className="container">
      <header>
        <h1>FocusGuard Agent</h1>
        <p className="subtitle">AI 工作监督助手</p>
      </header>

      <nav className="tabs">
        <button className={tab === 'session' ? 'tab active' : 'tab'} onClick={() => setTab('session')}>Session</button>
        <button className={tab === 'schedule' ? 'tab active' : 'tab'} onClick={() => setTab('schedule')}>Schedule</button>
        <button className={tab === 'report' ? 'tab active' : 'tab'} onClick={() => setTab('report')}>Report</button>
        <button className={tab === 'dataset' ? 'tab active' : 'tab'} onClick={() => setTab('dataset')}>Dataset</button>
        <button className={tab === 'settings' ? 'tab active' : 'tab'} onClick={() => setTab('settings')}>Settings</button>
      </nav>

      <div className={`ai-banner ${aiClass}`}>
        <span>AI 状态：{aiStatus?.message || '读取中...'}</span>
        {aiStatus?.model && <span className="ai-model">{aiStatus.model}</span>}
      </div>

      {tab === 'session' && (
        <>
          <section className={`status-panel guardian-panel ${guardianJudgement?.should_interrupt ? 'guardian-alert' : ''}`}>
            <div className="status-header">
              <div className="status-badge">Guardian mode：{guardianEffectiveStateLabel}</div>
              <div className="flow-timer">{guardianStatus?.check_interval_seconds || '--'}s</div>
            </div>
            <div className="status-info">
              <div className="info-item">
                <span className="label">最近检查</span>
                <span className="value">{guardianStatus?.last_checked_at ? new Date(guardianStatus.last_checked_at).toLocaleString() : '等待首次检查'}</span>
              </div>
              <div className="info-item">
                <span className="label">是否打断</span>
                <span className={`value ${guardianJudgement?.should_interrupt ? 'danger' : ''}`}>
                  {guardianJudgement ? (guardianJudgement.should_interrupt ? '是' : '否') : '--'}
                </span>
              </div>
              <div className="info-item"><span className="label">当前活动</span><span className="value">{guardianJudgement?.current_activity || '--'}</span></div>
              <div className="info-item"><span className="label">理由</span><span className="value">{guardianJudgement?.reason || '--'}</span></div>
              {guardianBreakStatus?.active && (
                <div className="info-item">
                  <span className="label">休息剩余</span>
                  <span className="value timer">{formatTime(guardianBreakStatus.remaining_seconds || 0)}</span>
                </div>
              )}
              <div className="info-item">
                <span className="label">娱乐额度</span>
                <span className="value">
                  今日剩余 {formatTime(guardianEntertainmentStatus?.remaining_seconds || 0)}
                  {guardianEntertainmentStatus?.active ? ` · 本次 ${formatTime(guardianEntertainmentStatus.active_remaining_seconds || 0)}` : ''}
                </span>
              </div>
              <div className="info-item">
                <span className="label">今日休息</span>
                <span className="value">
                  剩余 {guardianRestStatus?.remaining ?? '--'} / {guardianRestStatus?.quota ?? 3} 次
                </span>
              </div>
            </div>
            <div className="guardian-actions">
              <div className="input-group guardian-minutes">
                <label>本次休息（分钟）</label>
                <input
                  type="number"
                  value={guardianRestMinutes}
                  onChange={(e) => setGuardianRestMinutes(e.target.value)}
                  min="1"
                  step="1"
                />
              </div>
              <button
                type="button"
                className="btn-small"
                disabled={
                  guardianBreakStatus?.active ||
                  guardianEntertainmentStatus?.active ||
                  (guardianRestStatus?.remaining || 0) <= 0
                }
                onClick={handleStartGuardianRest}
              >
                开始休息
              </button>
              <div className="input-group guardian-minutes">
                <label>本次娱乐（分钟）</label>
                <input
                  type="number"
                  value={guardianEntertainmentMinutes}
                  onChange={(e) => setGuardianEntertainmentMinutes(e.target.value)}
                  min="1"
                  step="1"
                />
              </div>
              <button
                type="button"
                className="btn-small"
                disabled={
                  isRunning ||
                  guardianBreakStatus?.active ||
                  guardianEntertainmentStatus?.active ||
                  !guardianStatus?.enabled ||
                  (guardianEntertainmentStatus?.remaining_seconds || 0) <= 0
                }
                onClick={handleStartGuardianEntertainment}
              >
                开始娱乐
              </button>
            </div>
            {guardianActionStatus && <p className="settings-status">{guardianActionStatus}</p>}
          </section>

          {!isRunning && flowStatus?.active && (
            <section className={`status-panel flow-${flowStatus.kind}`}>
              <div className="status-header">
                <div className="status-badge">{flowStatus.kind === 'break' ? '休息中' : '停止中'}</div>
                <div className="flow-timer">{flowStatus.kind === 'break' ? '休息还差 ' : '还差 '}{formatTime(flowRemainingSeconds || flowStatus.remaining_seconds || 0)}</div>
              </div>
              <div className="status-info">
                <div className="info-item"><span className="label">状态</span><span className="value">{flowStatus.kind === 'break' ? flowStatus.activity : flowStatus.reason}</span></div>
                {flowStatus.minimum_next_step && <div className="info-item"><span className="label">最小下一步</span><span className="value">{flowStatus.minimum_next_step}</span></div>}
                <div className="info-item"><span className="label">结束后</span><span className="value">输入下一轮任务和时间</span></div>
              </div>
            </section>
          )}

          {!isRunning ? (
            <section className="controls">
              <div className="input-group">
                <label>当前任务</label>
                <input ref={taskRef} type="text" value={task} onChange={(e) => setTask(e.target.value)}
                  placeholder="例如：开发产品 / 写报告 / 准备面谈" />
              </div>
              <div className="input-group">
                <label>标签（逗号分隔）</label>
                <input type="text" value={tags} onChange={(e) => setTags(e.target.value)}
                  placeholder="例如：产品, 写作, 深度工作" />
              </div>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={sessionStrict}
                  onChange={(e) => setSessionStrict(e.target.checked)}
                />
                下一个 Session 触发后强制答题（英文到日语翻译）
              </label>
              <div className="input-row">
                <div className="input-group">
                  <label>工作时长（分钟）</label>
                  <input type="number" value={duration} onChange={(e) => setDuration(e.target.value)} min="1" step="1" />
                </div>
                <div className="input-group">
                  <label>检查间隔（秒，默认 300）</label>
                  <input type="number" value={interval} onChange={(e) => setInterval_(e.target.value)} min="5" step="1" />
                </div>
                <div className="input-group">
                  <label>命中几次后答题</label>
                  <input type="number" value={triggerThreshold} onChange={(e) => setTriggerThreshold(e.target.value)} min="1" step="1" />
                </div>
              </div>
              {formError && <p className="form-error">{formError}</p>}
              <button className="btn-start" onClick={handleStart}>开始监督</button>
              <button className="btn-test" onClick={() => testBlock()}>测试遮挡窗口</button>
            </section>
          ) : (
            <section className="status-panel">
              <div className="status-header">
                <div className="status-badge">{getStatusLabel()}</div>
                <button className="btn-stop" onClick={handleStop} disabled={strictStatus?.session_locked}>停止</button>
              </div>
              {strictStatus?.session_locked && <p className="form-error">当前 Session 触发后强制答题；分心后需要完成英文到日语翻译题，然后选择回到工作或定时休息。</p>}
              <div className="status-info">
                <div className="info-item"><span className="label">任务</span><span className="value">{status?.task || task}</span></div>
                <div className="info-item"><span className="label">来源</span><span className="value">{status?.source === 'schedule' ? 'Schedule' : '手动'}</span></div>
                <div className="info-item"><span className="label">标签</span><span className="value">{(status?.tags || []).join(', ') || '--'}</span></div>
                <div className="info-item"><span className="label">强制答题</span><span className="value">{status?.strict_mode ? '开启' : '关闭'}</span></div>
                <div className="info-item"><span className="label">Session 档位</span><span className="value">{supervisionLevelOptions.find((level) => level.id === status?.supervision_level)?.label || status?.supervision_level || '--'}</span></div>
                <div className="info-item"><span className="label">答题阈值</span><span className="value">{status?.trigger_threshold || 1} 次命中</span></div>
                <div className="info-item"><span className="label">剩余时间</span><span className="value timer">{formatTime(remainingSeconds)}</span></div>
                {status?.paused_for_rest && guardianBreakStatus?.active && (
                  <div className="info-item">
                    <span className="label">休息剩余</span>
                    <span className="value timer">{formatTime(guardianBreakStatus.remaining_seconds || 0)}</span>
                  </div>
                )}
                <div className="info-item"><span className="label">当前活动</span><span className="value">{status?.latest_judgement?.current_activity || '等待检查...'}</span></div>
                <div className="info-item"><span className="label">AI 理由</span><span className="value">{statusText}</span></div>
                <div className="info-item"><span className="label">连续分心</span><span className={`value ${status?.off_task_streak >= (status?.trigger_threshold || 1) ? 'danger' : ''}`}>{status?.off_task_streak ?? 0}</span></div>
              </div>
              {showStopForm && (
                <div className="stop-form">
                  <div className="input-group">
                    <label>停止原因</label>
                    <input type="text" value={stopReason} onChange={(e) => setStopReason(e.target.value)}
                      placeholder="例如：临时会议 / 处理家务 / 身体不适" />
                  </div>
                  <div className="input-group">
                    <label>停止多久（分钟）</label>
                    <input type="number" value={stopMinutes} onChange={(e) => setStopMinutes(e.target.value)} min="1" step="1" />
                  </div>
                  <div className="input-group">
                    <label>停止标签（逗号分隔）</label>
                    <input type="text" value={stopTags} onChange={(e) => setStopTags(e.target.value)}
                      placeholder="例如：中断, 会议, 家务" />
                  </div>
                  {formError && <p className="form-error">{formError}</p>}
                  <div className="button-row">
                    <button className="btn-secondary" onClick={() => setShowStopForm(false)}>取消</button>
                    <button className="btn-stop" onClick={handleConfirmStop}>确认停止</button>
                  </div>
                </div>
              )}
            </section>
          )}

          <section className="logs recent-judgments">
            <div className="status-header">
              <h2>最近判定</h2>
              <button type="button" className="btn-secondary" onClick={refreshRecentJudgments}>刷新</button>
            </div>
            <p className="recent-judgments-hint">点击条目展开查看截图与 context；若 AI 判错，可纠正后加入 train 校准集。</p>
            {recentJudgments.length === 0 ? (
              <p className="empty-msg">暂无判定记录。Guardian / Session 检查后会出现在这里。</p>
            ) : (
              <div className="log-list recent-judgment-list">
                {recentJudgments.map((item) => {
                  const expanded = expandedJudgmentId === item.id
                  const tone = item.judgement_status === 'api_error'
                    ? 'api-error'
                    : (item.ai_label === 'interrupt' || item.ai_label === 'off_task')
                      ? 'off-task'
                      : 'on-task'
                  return (
                    <div key={item.id} className={`log-item recent-judgment-item ${tone} ${expanded ? 'expanded' : ''}`}>
                      <button type="button" className="recent-judgment-summary" onClick={() => toggleJudgmentExpand(item)}>
                        <div className="log-time">{item.captured_at ? new Date(item.captured_at).toLocaleTimeString() : '--'}</div>
                        <div className="log-details">
                          <span className="log-activity">
                            <span className="pill">{item.mode}</span>
                            <span className="pill">{item.ai_label || '—'}</span>
                            {item.ai_activity || '(no activity)'}
                          </span>
                          <span className="log-reason">{item.ai_reason || '--'}</span>
                          <span className="log-model">{item.judgement_status || 'ok'}{item.task ? ` · ${item.task}` : ''}{item.screenshot_available ? '' : ' · 无图'}</span>
                        </div>
                        <div className="log-confidence">{expanded ? '收起' : '展开'}</div>
                      </button>
                      {expanded && (
                        <div className="recent-judgment-detail">
                          <div className="recent-judgment-grid">
                            <div className="recent-judgment-shot">
                              {item.screenshot_available ? (
                                <img
                                  src={getPersonalBenchRecentImageUrl(item)}
                                  alt="Judgment screenshot"
                                  title="点击图片可在原尺寸/适应宽度间切换"
                                  onClick={(e) => e.currentTarget.classList.toggle('zoomed')}
                                />
                              ) : (
                                <p className="empty-msg">无可用截图</p>
                              )}
                            </div>
                            <div className="recent-judgment-context">
                              <div className="info-item"><span className="label">mode</span><span className="value">{item.mode}</span></div>
                              <div className="info-item"><span className="label">captured_at</span><span className="value">{item.captured_at || '--'}</span></div>
                              <div className="info-item"><span className="label">task</span><span className="value">{item.task || '(guardian 无任务)'}</span></div>
                              <div className="info-item"><span className="label">AI 标签</span><span className="value">{item.ai_label || '--'}</span></div>
                              <div className="info-item"><span className="label">AI activity</span><span className="value">{item.ai_activity || '--'}</span></div>
                              <div className="info-item"><span className="label">AI reason</span><span className="value">{item.ai_reason || '--'}</span></div>
                              <div className="info-item"><span className="label">confidence</span><span className="value">{item.ai_confidence ?? '--'}</span></div>
                            </div>
                          </div>
                          <div className="recent-judgment-correct">
                            <div className="input-group">
                              <label>人工标签（纠正 AI）</label>
                              <select value={benchHumanLabel} onChange={(e) => setBenchHumanLabel(e.target.value)}>
                                {labelsForBenchMode(item.mode).map((label) => (
                                  <option key={label} value={label}>{label}</option>
                                ))}
                              </select>
                            </div>
                            <div className="input-group">
                              <label>人工理由</label>
                              <input
                                type="text"
                                value={benchHumanReason}
                                onChange={(e) => setBenchHumanReason(e.target.value)}
                                placeholder="例如：主窗口是文档，不是娱乐"
                              />
                            </div>
                            <button type="button" className="btn-start" onClick={() => handleAddToPersonalBench(item)}>
                              纠正并加入 train
                            </button>
                          </div>
                          {benchStatus && <p className="settings-status">{benchStatus}</p>}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          {status?.logs && status.logs.length > 0 && (
            <section className="logs">
              <h2>当前 Session 检查</h2>
              <div className="log-list">
                {[...status.logs].reverse().map((log, i) => (
                  <div key={i} className={`log-item ${log.judgement_status === 'api_error' ? 'api-error' : log.on_task ? 'on-task' : 'off-task'}`}>
                    <div className="log-time">{new Date(log.timestamp).toLocaleTimeString()}</div>
                    <div className="log-details">
                      <span className="log-activity">{log.current_activity}</span>
                      <span className="log-reason">{log.reason}</span>
                      <span className="log-model">{log.judgement_status || 'ok'} · {log.model || '--'}</span>
                    </div>
                    <div className="log-confidence">{Math.round((log.confidence || 0) * 100)}%</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {tab === 'schedule' && (
        <section className="schedule-panel">
          <h2>自动日程</h2>
          <div className="schedule-form">
            <div className="input-group">
              <label>任务</label>
              <input type="text" value={schedTask} onChange={(e) => setSchedTask(e.target.value)}
                placeholder="例如：产品开发" />
            </div>
            <div className="input-group">
              <label>标签（逗号分隔）</label>
              <input type="text" value={schedTags} onChange={(e) => setSchedTags(e.target.value)}
                placeholder="例如：学习, 数学" />
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={schedStrict}
                onChange={(e) => setSchedStrict(e.target.checked)}
              />
              到点后开启强制答题任务
            </label>
            <div className="input-row">
              <div className="input-group">
                <label>日期</label>
                <input type="date" value={schedDate} onChange={(e) => setSchedDate(e.target.value)} />
              </div>
              <div className="input-group">
                <label>开始</label>
                <input type="time" value={schedStart} onChange={(e) => setSchedStart(e.target.value)} />
              </div>
              <div className="input-group">
                <label>结束</label>
                <input type="time" value={schedEnd} onChange={(e) => setSchedEnd(e.target.value)} />
              </div>
            </div>
            <div className="input-row">
              <div className="input-group">
                <label>检查间隔（秒）</label>
                <input type="number" value={schedInterval} onChange={(e) => setSchedInterval(e.target.value)} min="5" step="1" />
              </div>
              <div className="input-group">
                <label>命中几次后答题</label>
                <input type="number" value={schedTriggerThreshold} onChange={(e) => setSchedTriggerThreshold(e.target.value)} min="1" step="1" />
              </div>
            </div>
            {scheduleError && <p className="form-error">{scheduleError}</p>}
            <button className="btn-start" onClick={handleAddSchedule}>添加日程</button>
          </div>

          <div className="schedule-list">
            {schedules.length === 0 && <p className="empty-msg">暂无日程</p>}
            {schedules.map((s) => (
              <div key={s.id} className="schedule-item">
                <div className="schedule-info">
                  <span className="schedule-task">{s.task}</span>
                  <span className="schedule-time">
                    {s.date} {s.start_time} - {s.end_time} · {s.status === 'in_progress' ? '进行中' : '未开始'}{s.strict_mode ? ' · 监管' : ''} · {s.check_interval_seconds || 300}s / {s.trigger_threshold || 1} 次
                  </span>
                  {(s.tags || []).length > 0 && <span className="tag-row">{s.tags.join(', ')}</span>}
                </div>
                <div className="schedule-actions">
                  <button className="btn-small btn-red" onClick={() => handleDeleteSchedule(s.id)}>×</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === 'report' && (
        <section className="analytics-panel">
          <div className="section-title-row">
            <h2>每日报告</h2>
            <input type="date" value={reportDate} onChange={(e) => setReportDate(e.target.value)} />
          </div>

          {dailyReport ? (
            <>
              <div className="stats-grid">
                <div className="stat-card"><div className="stat-value">{dailyReport.total_blocks}</div><div className="stat-label">Block</div></div>
                <div className="stat-card good"><div className="stat-value">{dailyReport.total_focus_minutes}</div><div className="stat-label">专注分钟</div></div>
                <div className="stat-card rest"><div className="stat-value">{dailyReport.total_break_minutes || 0}</div><div className="stat-label">休息分钟</div></div>
                <div className="stat-card stopped"><div className="stat-value">{dailyReport.total_stopped_minutes || 0}</div><div className="stat-label">停止分钟</div></div>
              </div>

              {(() => {
                const timeline = buildTimeline()
                return (
                  <div className="timeline-panel">
                    <div className="timeline-head">
                      <span>{timeline.start ? formatClock(timeline.start) : '--'}</span>
                      <span>{timeline.end ? formatClock(timeline.end) : '--'}</span>
                    </div>
                    <div className="timeline-bar">
                      {timeline.segments.length === 0 && <div className="timeline-empty">无记录</div>}
                      {timeline.segments.map((segment, i) => (
                        <div
                          key={`${segment.kind}-${i}`}
                          className={`timeline-segment ${segment.kind}`}
                          title={segment.label}
                          style={{ width: `${Math.max(segment.width, 0.5)}%` }}
                        />
                      ))}
                    </div>
                    <div className="timeline-legend">
                      <span><b className="legend focus"></b>专注</span>
                      <span><b className="legend break"></b>休息</span>
                      <span><b className="legend stopped"></b>停止</span>
                      <span><b className="legend idle"></b>无指令</span>
                    </div>
                  </div>
                )
              })()}

              <div className="notes-panel">
                <div className="input-group">
                  <label>今天的总结</label>
                  <textarea value={todaySummary} onChange={(e) => setTodaySummary(e.target.value)}
                    placeholder="今天完成了什么？哪里被打断？明天要注意什么？" />
                </div>
                <div className="input-group">
                  <label>明天的规划</label>
                  <textarea value={tomorrowPlan} onChange={(e) => setTomorrowPlan(e.target.value)}
                    placeholder="明天准备做哪些任务？" />
                </div>
                <button className="btn-start" onClick={handleSaveNotes}>保存总结和规划</button>
                {notesStatus && <p className="settings-status">{notesStatus}</p>}
              </div>

              <div className="session-history">
                {(dailyReport.blocks || []).length === 0 && <p className="empty-msg">这一天还没有记录</p>}
                {(dailyReport.blocks || []).map((b) => (
                  <div key={b.session_id} className="history-item">
                    <div className="history-task">{b.task}</div>
                    <div className="history-meta">
                      <span>{b.source === 'schedule' ? 'Schedule' : '手动'} · {statusName[b.status] || b.status}</span>
                      <span>{b.focus_minutes} 分钟专注</span>
                    </div>
                    <div className="history-meta">
                      <span>{b.planned_start ? new Date(b.planned_start).toLocaleTimeString() : '--'} - {b.planned_end ? new Date(b.planned_end).toLocaleTimeString() : '--'}</span>
                      <span>分心 {b.distracted_checks || 0} · AI 错误 {b.api_error_checks || 0}</span>
                    </div>
                    {(b.tags || []).length > 0 && <div className="tag-row">{b.tags.join(', ')}</div>}
                    <div className="history-bar">
                      <div className="history-bar-fill" style={{ width: `${b.total_checks > 0 ? (b.focused_checks / b.total_checks * 100) : 0}%` }}></div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="empty-msg">报告读取失败</p>
          )}
        </section>
      )}

      {tab === 'dataset' && (
        <section className="dataset-panel">
          <div className="section-title-row">
            <h2>个人 Bench 截图</h2>
            <button className="btn-secondary" onClick={() => { refreshPendingCapture(); refreshBenchSamples() }}>刷新</button>
          </div>
          <p className="settings-current">
            Ctrl+Alt+1/2 先截当前屏。对着图填 context，再保存入库。
          </p>

          <div className="dataset-capture-row">
            <button className="btn-secondary" onClick={() => capturePending(pendingCapture?.verdict)}>截图</button>
            <button
              className={pendingCapture?.verdict === '对' ? 'btn-start' : 'btn-secondary'}
              onClick={() => setPendingVerdict('对')}
            >
              1 对 → {captureContext.mode === 'guardian' ? 'allow' : 'on_task'}
            </button>
            <button
              className={pendingCapture?.verdict === '错' ? 'btn-stop' : 'btn-secondary'}
              onClick={() => setPendingVerdict('错')}
            >
              2 错 → {captureContext.mode === 'guardian' ? 'interrupt' : 'off_task'}
            </button>
            <button className="btn-start" onClick={() => commitPending()} disabled={!pendingCapture || benchSaving}>保存入库</button>
            {pendingCapture && (
              <button className="btn-secondary" onClick={discardPending}>丢弃截图</button>
            )}
          </div>

          {pendingCapture && (
            <div className="dataset-layout">
              <div className="dataset-preview">
                <img src={getPersonalBenchPendingImageUrl(pendingCapture)} alt="Pending screenshot" />
              </div>
              <div className="dataset-editor">
                <div className="history-meta">
                  <span>待保存 · {pendingCapture.verdict || '未选对/错'}</span>
                  <span>{pendingCapture.captured_at ? new Date(pendingCapture.captured_at).toLocaleString() : ''}</span>
                </div>
                <div className="input-row">
                  <div className="input-group">
                    <label>mode</label>
                    <select value={captureContext.mode} onChange={(e) => updateCaptureField('mode', e.target.value)}>
                      <option value="guardian">guardian</option>
                      <option value="session">session</option>
                    </select>
                  </div>
                  <div className="input-group">
                    <label>split</label>
                    <select value={captureContext.split} onChange={(e) => updateCaptureField('split', e.target.value)}>
                      <option value="train">train</option>
                      <option value="test">test</option>
                    </select>
                  </div>
                </div>
                {captureContext.mode === 'session' && (
                  <div className="input-row">
                    <div className="input-group">
                      <label>task（session 必填）</label>
                      <input
                        value={captureContext.task}
                        onChange={(e) => updateCaptureField('task', e.target.value)}
                        placeholder="例如：写报告 / 写代码"
                      />
                    </div>
                    <div className="input-group">
                      <label>supervision_level（可选）</label>
                      <select
                        value={captureContext.supervision_level}
                        onChange={(e) => updateCaptureField('supervision_level', e.target.value)}
                      >
                        <option value="">（空）</option>
                        <option value="not_entertainment">not_entertainment</option>
                        <option value="task_related">task_related</option>
                      </select>
                    </div>
                  </div>
                )}
                <div className="input-group">
                  <label>activity（画面在干什么）</label>
                  <input
                    value={captureContext.activity}
                    onChange={(e) => updateCaptureField('activity', e.target.value)}
                    placeholder="例如：VS Code 编辑器 / 微博时间线"
                  />
                </div>
                <div className="input-group">
                  <label>note（可选备注）</label>
                  <textarea
                    value={captureContext.note}
                    onChange={(e) => updateCaptureField('note', e.target.value)}
                    placeholder="为何标对/错"
                  />
                </div>
              </div>
            </div>
          )}

          {!pendingCapture && (
            <>
              <div className="input-row">
                <div className="input-group">
                  <label>列表筛选</label>
                  <select value={benchSplitFilter} onChange={(e) => setBenchSplitFilter(e.target.value)}>
                    <option value="">全部</option>
                    <option value="train">train</option>
                    <option value="test">test</option>
                  </select>
                </div>
              </div>
              <p className="empty-msg">还没有待保存截图。按 Ctrl+Alt+1/2 或点「截图」。</p>
            </>
          )}

          {benchSamples.length > 0 && (
            <div className="dataset-list">
              {benchSamples.map((sample) => (
                <button
                  key={sample.id}
                  type="button"
                  className={sample.id === benchSampleId ? 'dataset-list-item selected' : 'dataset-list-item'}
                  onClick={() => setBenchSampleId(sample.id)}
                >
                  <span className="dataset-list-index">{sample.verdict || (sample.human_label === 'allow' || sample.human_label === 'on_task' ? '对' : '错')}</span>
                  <span className="dataset-list-main">
                    <span>{sample.mode} · {sample.human_label} · {sample.split}</span>
                    <span>{sample.task || sample.ai_activity || sample.human_reason || '—'}</span>
                  </span>
                  <span className="dataset-list-time">{sample.added_at ? new Date(sample.added_at).toLocaleTimeString() : ''}</span>
                </button>
              ))}
            </div>
          )}

          {!pendingCapture && currentBenchSample && (
            <div className="dataset-layout">
              <div className="dataset-preview">
                <img src={getPersonalBenchSampleImageUrl(currentBenchSample)} alt="Bench screenshot" />
              </div>
              <div className="dataset-editor">
                <div className="history-meta">
                  <span>{currentBenchSample.mode} / {currentBenchSample.split}</span>
                  <span>{currentBenchSample.added_at ? new Date(currentBenchSample.added_at).toLocaleString() : ''}</span>
                </div>
                <div className="info-item"><span className="label">判定</span><span className="value">{currentBenchSample.verdict || '—'} → {currentBenchSample.human_label}</span></div>
                <div className="info-item"><span className="label">task</span><span className="value">{currentBenchSample.task || '—'}</span></div>
                <div className="info-item"><span className="label">activity</span><span className="value">{currentBenchSample.ai_activity || '—'}</span></div>
                <div className="info-item"><span className="label">note</span><span className="value">{currentBenchSample.human_reason || '—'}</span></div>
                <div className="dataset-action-grid">
                  <button
                    className="btn-secondary"
                    onClick={() => moveBenchSample(currentBenchSample.split === 'train' ? 'test' : 'train')}
                  >
                    移到 {currentBenchSample.split === 'train' ? 'test' : 'train'}
                  </button>
                  <button className="btn-stop" onClick={deleteBenchSample}>删除样本</button>
                </div>
              </div>
            </div>
          )}

          {datasetStatus && <p className="settings-status">{datasetStatus}</p>}
        </section>
      )}

      {tab === 'settings' && (
        <section className="settings-panel">
          <h2>设置</h2>

          <div className={`ai-banner ${aiClass}`}>
            <span>{aiStatus?.message || 'AI 状态读取中...'}</span>
            {aiStatus?.last_error_at && <span className="ai-model">最近错误：{new Date(aiStatus.last_error_at).toLocaleString()}</span>}
          </div>

          <div className="input-group">
            <label>AI 模型</label>
            <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
              {modelOptions.map((model) => (
                <option key={model.id} value={model.id}>{model.label}</option>
              ))}
            </select>
          </div>

          <div className="model-list">
            {modelOptions.map((model) => (
              <button
                key={model.id}
                type="button"
                className={selectedModel === model.id ? 'model-option selected' : 'model-option'}
                onClick={() => setSelectedModel(model.id)}
              >
                <span className="model-name">{model.label}</span>
                <span className="model-id">{model.id}</span>
                <span className="model-description">{model.description}</span>
              </button>
            ))}
          </div>

          <div className="strict-box">
            <h3>Session 模式</h3>
            <div className="input-group">
              <label>Session 档位</label>
              <select value={selectedSupervisionLevel} onChange={(e) => setSelectedSupervisionLevel(e.target.value)}>
                {supervisionLevelOptions.map((level) => (
                  <option key={level.id} value={level.id}>{level.label}</option>
                ))}
              </select>
            </div>
            <div className="model-list">
              {supervisionLevelOptions.map((level) => (
                <button
                  key={level.id}
                  type="button"
                  className={selectedSupervisionLevel === level.id ? 'model-option selected' : 'model-option'}
                  onClick={() => setSelectedSupervisionLevel(level.id)}
                >
                  <span className="model-name">{level.label}</span>
                  <span className="model-description">{level.description}</span>
                </button>
              ))}
            </div>
            <div className="input-group">
              <label>触发时的心理距离提示语</label>
              <textarea value={nudgePrompt} onChange={(e) => setNudgePrompt(e.target.value)}
                placeholder="例如：先和冲动保持一点距离，然后选择一个最小下一步。" />
            </div>
            <div className="input-row">
              <div className="input-group">
                <label>默认检测间隔（秒）</label>
                <input type="number" value={defaultInterval} onChange={(e) => setDefaultInterval(e.target.value)} min="5" step="1" />
              </div>
              <div className="input-group">
                <label>答完题后再等几秒才截图</label>
                <input type="number" value={postBlockCooldown} onChange={(e) => setPostBlockCooldown(e.target.value)} min="0" step="1" />
              </div>
              <div className="input-group">
                <label>默认命中几次后答题</label>
                <input type="number" value={defaultTriggerThreshold} onChange={(e) => setDefaultTriggerThreshold(e.target.value)} min="1" step="1" />
              </div>
            </div>
            <div className="input-group">
              <label>白名单行为（每行一条）</label>
              <textarea value={whitelistText} onChange={(e) => setWhitelistText(e.target.value)}
                placeholder="例如：听音乐&#10;看计时器&#10;查字典" />
            </div>
            <p className="settings-current">
              Session 模式用于正在运行的任务；白名单行为优先于 Session 档位，但小说、漫画和色情内容仍会被硬拦截。
            </p>
            <div className="input-group">
              <label>Dataset 任务标签（每行一条）</label>
              <textarea
                value={datasetTagOptionsText}
                onChange={(e) => setDatasetTagOptionsText(e.target.value)}
                placeholder="guardian mode&#10;论文阅读&#10;日语学习&#10;产品开发"
              />
            </div>
            <p className="settings-current">
              Dataset 页会把这些标签显示成可点击按钮；新截图默认带 guardian mode。
            </p>
            <div className="input-group">
              <label>Calibration dataset 目录</label>
              <input
                type="text"
                value={personalBenchRoot}
                onChange={(e) => setPersonalBenchRoot(e.target.value)}
                placeholder="留空=本机个人数据。也可填 0906_lv_bench 或它的 data 目录"
              />
            </div>
            <p className="settings-current">
              AI 只检索该目录下的 train 作为 prior calibration，test 不参与判定。
              {personalBenchStatus?.ok
                ? ` 当前：${personalBenchStatus.resolved}（train ${personalBenchStatus.train} / test ${personalBenchStatus.test}）`
                : personalBenchStatus?.error
                  ? ` 无效：${personalBenchStatus.error}`
                  : ''}
            </p>
          </div>
          <div className="strict-box">
            <h3>Practice questions</h3>
            <div className="input-row">
              <div className="input-group">
                <label>目标语言</label>
                <input
                  type="text"
                  value={practiceTargetLanguage}
                  onChange={(e) => setPracticeTargetLanguage(e.target.value)}
                  placeholder="Japanese / Chinese / English"
                />
              </div>
              <div className="input-group">
                <label>上传 md/txt 题库</label>
                <input type="file" accept=".md,.txt,text/markdown,text/plain" onChange={handlePracticeUpload} />
              </div>
            </div>
            <p className="settings-current">
              当前题库：{practiceStatus?.source_name || '--'} · {practiceStatus?.item_count ?? 0} 条 · 下一题 #{(practiceStatus?.next_index ?? 0) + 1}
            </p>
            {practiceUploadStatus && <p className="settings-status">{practiceUploadStatus}</p>}
          </div>
          <div className="strict-box">
            <h3>Guardian mode</h3>
            <label className="check-row">
              <input
                type="checkbox"
                checked={guardianEnabled}
                onChange={(e) => setGuardianEnabled(e.target.checked)}
              />
              默认开启常驻 Guardian mode
            </label>
            <div className="input-group">
              <label>Guardian 检测间隔（秒）</label>
              <input type="number" value={guardianInterval} onChange={(e) => setGuardianInterval(e.target.value)} min="30" step="1" />
            </div>
            <div className="input-row">
              <div className="input-group">
                <label>每日娱乐额度（分钟）</label>
                <input
                  type="number"
                  value={guardianDailyEntertainmentLimit}
                  onChange={(e) => setGuardianDailyEntertainmentLimit(e.target.value)}
                  min="0"
                  step="1"
                />
              </div>
              <div className="input-group">
                <label>新一天开始时间</label>
                <input
                  type="time"
                  value={guardianDayStartTime}
                  onChange={(e) => setGuardianDayStartTime(e.target.value)}
                />
              </div>
              <div className="input-group">
                <label>每日可休息次数</label>
                <input
                  type="number"
                  value={guardianRestQuota}
                  onChange={(e) => setGuardianRestQuota(e.target.value)}
                  min="0"
                  max="20"
                  step="1"
                />
              </div>
            </div>
            <p className="settings-current">
              {settings?.guardian_rest_quota_pending != null
                ? `今日生效 ${settings.guardian_rest_quota_per_day} 次；将于 ${settings.guardian_rest_quota_pending_day} 起改为 ${settings.guardian_rest_quota_pending} 次。`
                : `今日生效 ${settings?.guardian_rest_quota_per_day ?? 3} 次。修改次数会在下一个 Guardian 日（按上面的「新一天开始时间」）才生效。`}
            </p>
            <p className="settings-current">
              Guardian mode 独立于 Session。休息次数用完后，打断仍可答题回到 Guardian，但不能再开新的休息。
            </p>
          </div>
          <button className="btn-start" onClick={handleSaveSettings}>保存设置</button>
          {settingsStatus && <p className="settings-status">{settingsStatus}</p>}
          {settings?.model && <p className="settings-current">当前模型：{settings.model}</p>}
        </section>
      )}
    </div>
  )
}

export default App
