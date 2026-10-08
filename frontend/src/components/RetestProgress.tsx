import {useEffect, useRef, useState} from 'react'
import {simulationRunApi} from '../api'
import type {SimulationRun} from '../types'

export function RetestProgress({run, onObserved}: {run: SimulationRun; onObserved: (run: SimulationRun) => void}) {
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const observed = useRef(onObserved)
  useEffect(() => {observed.current = onObserved}, [onObserved])
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const latest = await simulationRunApi.get(run.id)
        if (!active) return
        if (latest.id !== run.id || latest.workspaceId !== run.workspaceId || latest.parentSimulationId !== run.parentSimulationId) {
          throw new Error('返回的复测记录不匹配。')
        }
        observed.current(latest)
        if (['pending', 'running'].includes(latest.status)) timer = setTimeout(() => void poll(), 1500)
      } catch (e) {if (active) setError(e instanceof Error ? e.message : String(e))}
    }
    timer = setTimeout(() => void poll(), 500)
    return () => {active = false; clearTimeout(timer)}
  }, [run.id, run.workspaceId, run.parentSimulationId, attempt])
  return error ? <div><p role="alert">读取进度暂时失败：{error} 复测可能仍在后台继续，无需再次创建。</p>
    <button onClick={() => {setError(''); setAttempt(n => n + 1)}}>重新读取进度</button></div>
    : <p role="status">同组读者正在试读，结果会自动更新。可以离开页面，稍后从历史继续查看。</p>
}
