import {useRef} from 'react'
import {cleanup, fireEvent, render, screen} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {ReportToc} from './ReportToc'

afterEach(cleanup)

function Report({stages}:{stages:number}) {
  const ref=useRef<HTMLElement>(null)
  return <section ref={ref}>
    <ReportToc containerRef={ref} watch="run"/>
    <div className="stage"><div className="stage-h"><h3>账号画像</h3></div>
      <div className="account-portrait-view"><h4>这个账号给人的印象</h4><h4>历史笔记表现</h4></div></div>
    {stages>1&&<div className="stage"><div className="stage-h"><h3>读者反馈</h3></div></div>}
  </section>
}

it('lists the portrait sections and later stages, and scrolls to the chosen one',()=>{
  const scroll=vi.fn()
  HTMLElement.prototype.scrollIntoView=scroll
  render(<Report stages={2}/>)
  const toc=screen.getByRole('navigation',{name:'报告目录'})
  expect(Array.from(toc.querySelectorAll('button'),button=>button.textContent)).toEqual(['印象','笔记表现','读者反馈'])
  fireEvent.click(screen.getByRole('button',{name:'读者反馈'}))
  expect(scroll.mock.contexts[0]).toBe(screen.getByRole('heading',{name:'读者反馈'}))
})

it('stays hidden for a short report',()=>{
  render(<Report stages={1}/>)
  expect(screen.queryByRole('navigation',{name:'报告目录'})).not.toBeInTheDocument()
})
