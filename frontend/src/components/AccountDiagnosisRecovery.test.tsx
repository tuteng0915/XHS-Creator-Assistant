import {cleanup, fireEvent, render, screen} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import type {AnalysisRun} from '../types'
import {AccountDiagnosisRecovery} from './AccountDiagnosisRecovery'

afterEach(cleanup)
const run = {id:'r', workflowType:'account_diagnosis', status:'partially_completed', stageErrors:{profile:'超时'}, modelMetadata:{profile:{pipelineCheckpoint:{overview:{},readings:{n1:{}}}}}} as unknown as AnalysisRun
const props = {run, stage:'profile', busy:false, mediaAssets:[], onRetry:vi.fn(), onOpenSource:vi.fn()}
it('offers continuation of saved readings and disables duplicate submission', () => {
  const {rerender} = render(<AccountDiagnosisRecovery {...props} />)
  fireEvent.click(screen.getByRole('button', {name:'继续完成报告'}))
  expect(props.onRetry).toHaveBeenCalledWith('profile')
  rerender(<AccountDiagnosisRecovery {...props} busy />)
  expect(screen.getByRole('button', {name:'继续完成报告'})).toBeDisabled()
})
it('shows failed images without claiming the whole report failed', () => {
  render(<AccountDiagnosisRecovery {...props} run={{...run,status:'completed',stageErrors:{},modelMetadata:{profile:{imageReadings:[{assetId:'a',noteId:'n',page:1,status:'failed',error:'超时'}]}}}} />)
  expect(screen.getByText('部分图片未读到，报告已使用正文和成功读取的图片。')).toBeVisible()
  expect(screen.getByRole('button', {name:'重试图片并更新报告'})).toBeEnabled()
})
it('does not offer retry for successful sections or running tasks', () => {
  render(<AccountDiagnosisRecovery {...props} run={{...run,status:'running'}} />)
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})
