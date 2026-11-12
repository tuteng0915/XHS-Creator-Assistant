import {cleanup, render, screen} from '@testing-library/react'
import {afterEach, expect, it} from 'vitest'
import {MessageSkeleton, ReportSkeleton, SkeletonStatus} from './Skeleton'

afterEach(cleanup)

it('announces the wait once and keeps the placeholder shapes out of the accessibility tree',()=>{
  const {container}=render(<SkeletonStatus label="正在读取分析记录…"><ReportSkeleton sections={2}/><MessageSkeleton/></SkeletonStatus>)
  expect(screen.getByRole('status')).toHaveTextContent('正在读取分析记录…')
  expect(container.querySelectorAll('.skeleton-report-section')).toHaveLength(2)
  container.querySelectorAll('.skeleton').forEach(shape=>expect(shape.closest('[aria-hidden="true"]')).not.toBeNull())
})

it('holds queued sections still',()=>{
  const {container}=render(<ReportSkeleton sections={1} still/>)
  expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(0)
  container.querySelectorAll('.skeleton').forEach(shape=>expect(shape.matches('.is-still, .is-still > .skeleton')).toBe(true))
})
