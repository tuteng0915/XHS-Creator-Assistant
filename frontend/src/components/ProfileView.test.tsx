import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { ProfileView } from './StageResultViews'
import type { Observations } from './AccountPortraitView'

afterEach(cleanup)

const data = {
  pillars: ['生活记录'],
  contrast: {
    winners: [{ title: '模型指定的冠军', metric: '收藏999；分享None' }],
    losers: [{ title: '模型指定的低表现', metric: '赞-1' }],
    winFactors: ['收藏率超过30%所以推荐更多'],
    loseFactors: ['分享率低于15%所以内容差'],
    takeaways: ['参考日常记录的开头，下次先讲一个具体场景。'],
  },
}
const observations: Observations = {
  schemaVersion: 'xhs-account-observations/v1',
  coverage: { selectedCount: 2, missingDateCount: 2, capturedCommentCount: 0, missingMetricCounts: { shares: 1 } },
  notes: [
    { noteId: 'first', title: '同名笔记', metrics: { liked: 10, collected: 3, shares: null } },
    { noteId: 'second', title: '同名笔记', metrics: { liked: 20, collected: 5, shares: 0 } },
  ],
}

it('preserves saved comparison prose beside frozen counts without reusing model metric strings', () => {
  const original = JSON.stringify({ data, observations })
  render(<ProfileView data={data} observations={observations} />)
  expect(screen.queryByText('更多内容归纳')).not.toBeInTheDocument()
  expect(screen.getByText(data.contrast.takeaways[0]).closest('details')).toBeNull()
  expect(screen.getByRole('status')).toHaveTextContent('点赞数据 2 / 2 条 · 中位数 15')
  const performance = screen.getByRole('heading', { name: '历史笔记表现', level: 4 }).closest('section')!
  const higher = screen.getByRole('heading', { name: '较高表现' }).parentElement!
  const lower = screen.getByRole('heading', { name: '较低表现' }).parentElement!
  expect(performance).toContainElement(higher)
  expect(performance).toContainElement(lower)
  expect(performance).toContainElement(screen.getByRole('combobox', { name: '比较指标' }))
  expect(within(performance).getAllByRole('heading', { level: 4 })).toHaveLength(1)
  expect(higher).toContainElement(screen.getByText(data.contrast.winners[0].title))
  expect(higher).toContainElement(screen.getByText(data.contrast.winFactors[0]))
  expect(lower).toContainElement(screen.getByText(data.contrast.losers[0].title))
  expect(lower).toContainElement(screen.getByText(data.contrast.loseFactors[0]))
  for (const item of [...data.contrast.winners, ...data.contrast.losers]) {
    expect(screen.queryByText(item.metric, { exact: false })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: item.title })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: item.title })).not.toBeInTheDocument()
  }
  expect(screen.queryByText(/高表现 vs 低表现/)).not.toBeInTheDocument()
  expect(screen.getByText('生活记录')).toBeInTheDocument()
  expect(screen.getByText(data.contrast.takeaways[0])).toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: '比较指标' }), { target: { value: 'shares' } })
  expect(screen.getByRole('status')).toHaveTextContent('分享数据 1 / 2 条 · 中位数 0 · 1 条未获取')
  expect(higher).toContainElement(screen.getByText(data.contrast.winFactors[0]))
  expect(lower).toContainElement(screen.getByText(data.contrast.loseFactors[0]))
  expect(JSON.stringify({ data, observations })).toBe(original)
})

it('opens duplicate titles by frozen note ID without inferring a link from the model title', () => {
  const report = { ...data, contrast: { ...data.contrast, winners: [{ title: '同名笔记', metric: '收藏999；分享None' }] } }
  render(<ProfileView data={report} observations={observations} notes={[
    { noteId: 'first', title: '同名笔记', desc: '第一份冻结正文', metrics: { liked: 10 }, comments: [] },
    { noteId: 'second', title: '同名笔记', desc: '第二份冻结正文', metrics: { liked: 20 }, comments: [] },
  ]} />)
  const savedHigher = screen.getByRole('heading', { name: '较高表现' }).parentElement!
  expect(within(savedHigher).getByText('同名笔记')).toBeInTheDocument()
  expect(within(savedHigher).queryByRole('button', { name: '同名笔记' })).not.toBeInTheDocument()
  expect(within(savedHigher).queryByRole('link', { name: '同名笔记' })).not.toBeInTheDocument()
  const buttons = screen.getAllByRole('button', { name: '同名笔记' })
  expect(buttons).toHaveLength(2)
  fireEvent.click(buttons[0])
  fireEvent.click(screen.getByRole('button', { name: /同名笔记 赞 20/ }))
  expect(screen.getByText('第二份冻结正文')).toBeInTheDocument()
  expect(screen.queryByText('第一份冻结正文')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '关闭' }))
  fireEvent.click(buttons[1])
  fireEvent.click(screen.getByRole('button', { name: /同名笔记 赞 10/ }))
  expect(screen.getByText('第一份冻结正文')).toBeInTheDocument()
  expect(screen.queryByText('第二份冻结正文')).not.toBeInTheDocument()
})

it('keeps saved comparison prose when the structured snapshot is empty without inventing counts', () => {
  render(<ProfileView data={data} observations={{ ...observations, notes: [] }} />)
  expect(screen.getByRole('status')).toHaveTextContent('本次未获取点赞数据')
  for (const text of [data.contrast.winners[0].title, data.contrast.losers[0].title,
    ...data.contrast.winFactors, ...data.contrast.loseFactors]) {
    expect(screen.getByText(text)).toBeInTheDocument()
  }
  expect(screen.queryByText(/None|999|赞-1|本次点赞第/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: data.contrast.winners[0].title })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: data.contrast.losers[0].title })).not.toBeInTheDocument()
})

it('keeps original report groups fixed when a different metric changes the frozen ranking', () => {
  const snapshot: Observations = { ...observations, notes: [
    { noteId: 'a', title: '笔记甲', metrics: { liked: 100, shares: 0 } },
    { noteId: 'b', title: '笔记乙', metrics: { liked: 80, shares: 1 } },
    { noteId: 'c', title: '笔记丙', metrics: { liked: 20, shares: 100 } },
    { noteId: 'd', title: '笔记丁', metrics: { liked: 0, shares: 30 } },
  ] }
  const original = JSON.stringify({ data, snapshot })
  render(<ProfileView data={data} observations={snapshot} notes={snapshot.notes.map(note => ({
    noteId: note.noteId, title: note.title, desc: '冻结正文', metrics: {}, comments: [],
  }))} />)
  const higher = screen.getByRole('heading', { name: '较高表现' }).parentElement!
  const lower = screen.getByRole('heading', { name: '较低表现' }).parentElement!
  const savedText = [higher.textContent, lower.textContent]
  const rankedTitles = () => screen.getAllByRole('button', { name: /^笔记[甲乙丙丁]$/ }).map(button => button.textContent)
  expect(rankedTitles()).toEqual(['笔记甲', '笔记乙', '笔记丁', '笔记丙'])
  fireEvent.change(screen.getByRole('combobox', { name: '比较指标' }), { target: { value: 'shares' } })
  expect(rankedTitles()).toEqual(['笔记丙', '笔记丁', '笔记甲', '笔记乙'])
  expect([higher.textContent, lower.textContent]).toEqual(savedText)
  expect(screen.getByRole('status')).toHaveTextContent('分享数据 4 / 4 条 · 中位数 15.5')
  expect(JSON.stringify({ data, snapshot })).toBe(original)
})

it('keeps reports without observations readable without rewriting their saved content', () => {
  const original = JSON.stringify(data)
  render(<ProfileView data={data} />)
  expect(screen.getByText('模型指定的冠军')).toBeInTheDocument()
  expect(screen.getByText(data.contrast.winFactors[0])).toBeInTheDocument()
  expect(screen.getByText(data.contrast.takeaways[0])).toBeInTheDocument()
  expect(screen.queryByRole('combobox', { name: '比较指标' })).not.toBeInTheDocument()
  expect(JSON.stringify(data)).toBe(original)
})

it('does not leave an empty advice heading when contrast is absent', () => {
  render(<ProfileView data={{ pillars: ['生活记录'] }} observations={observations} />)
  expect(screen.queryByText('可尝试的写法：')).not.toBeInTheDocument()
  expect(screen.getByText('生活记录')).toBeInTheDocument()
})

it('omits empty legacy disclosures and headings while preserving genuine legacy fields', () => {
  const {rerender} = render(<ProfileView data={{pillars:[],titleFormulas:[],hookStyles:[],viralStructure:{},contrast:{winners:[{title:'不使用的模型对比'}]}}} observations={observations} />)
  expect(screen.queryByText('更多内容归纳')).not.toBeInTheDocument()
  rerender(<ProfileView data={{pillars:['生活记录']}} />)
  expect(screen.getByRole('heading',{name:'内容方向与读者价值'})).toBeInTheDocument()
  expect(screen.queryByRole('heading',{name:'标题写法'})).not.toBeInTheDocument()
  expect(screen.queryByRole('heading',{name:'开头写法'})).not.toBeInTheDocument()
  expect(screen.queryByRole('heading',{name:/表达结构/})).not.toBeInTheDocument()
  rerender(<ProfileView data={{titleFormulas:[{formula:'先说场景',examples:['下班以后']}],hookStyles:['用具体动作开头'],viralStructure:{name:'日常叙事',steps:['场景','感受']}}} />)
  expect(screen.getByText('先说场景')).toBeInTheDocument()
  expect(screen.getByText('例：下班以后')).toBeInTheDocument()
  expect(screen.getByText('用具体动作开头')).toBeInTheDocument()
  expect(screen.getByRole('heading',{name:'开头写法'})).toBeInTheDocument()
  expect(screen.queryByRole('heading',{name:'开头习惯'})).not.toBeInTheDocument()
  expect(screen.getByRole('heading',{name:'表达结构 · 日常叙事'})).toBeInTheDocument()
  expect(screen.getByText('感受')).toBeInTheDocument()
  rerender(<ProfileView data={{viralStructure:{steps:[]}}} />)
  expect(screen.queryByText('0')).not.toBeInTheDocument()
  expect(screen.queryByRole('heading')).not.toBeInTheDocument()
})

it.each([observations, undefined])('shows voice-only reports and preserves full legacy wording', snapshot => {
  const voice = '先用口语短句提出疑问，再用长句解释自己的取舍。'.repeat(15)
  render(<ProfileView data={{voiceFingerprint:[voice,{statement:'常用“我觉得”区分个人判断与事实'}]}} observations={snapshot} />)
  expect(screen.getByRole('heading', {name:'你的表达方式'})).toBeInTheDocument()
  expect(screen.getByText(voice).closest('details')).toBeNull()
  expect(screen.getByText('常用“我觉得”区分个人判断与事实')).toBeInTheDocument()
  expect(screen.queryByText(/本次暂无可展示/)).not.toBeInTheDocument()
})

it('combines report parts in reading order without repeating findings or hiding examples', () => {
  const statement = '短句开场，随后展开具体场景'
  const report = {
    accountPortrait:{summary:{statement:'用亲身记录解释选择',evidence:[{noteId:'first',quote:'真实场景'}]},
      strengths:[{statement,evidence:[{noteId:'first',quote:'具体做法'}]}],
      readerValue:[{statement:'帮助读者看清取舍',evidence:[{noteId:'second',quote:'取舍原文'}]}]},
    pillars:['生活记录'], voiceFingerprint:[statement,'常用“但”转入自己的判断'],
    titleFormulas:[{formula:'先说实际场景，再写反差',examples:['下班很晚，但我不想直接回家']}],
    hookStyles:['从一个现场动作切入'],viralStructure:{name:'经历推进',steps:['还原场景','解释选择']},
    contrast:{takeaways:['下次借鉴“下班很晚”的动作开头，保留一处具体细节。']},
  }
  const original = JSON.stringify(report)
  render(<ProfileView data={report} observations={observations} />)
  const headings = screen.getAllByRole('heading', {level:4}).map(heading => heading.textContent?.trim())
  expect(headings).toEqual(['这个账号给人的印象','历史笔记表现','值得继续放大的优势','内容方向与读者价值','你的表达方式','接下来值得试什么'])
  expect(screen.getAllByText(statement)).toHaveLength(1)
  for (const text of ['常用“但”转入自己的判断','先说实际场景，再写反差','例：下班很晚，但我不想直接回家','从一个现场动作切入','解释选择',report.contrast.takeaways[0]]) {
    expect(screen.getByText(text).closest('details')).toBeNull()
  }
  expect(JSON.stringify(report)).toBe(original)
})

it('preserves repeated steps in their saved order and does not merge different English word boundaries', () => {
  render(<ProfileView data={{voiceFingerprint:['now here','nowhere','值得继续？','值得继续。'],viralStructure:{steps:['回到现场','补充解释','回到现场']}}} />)
  expect(screen.getByText('now here')).toBeInTheDocument()
  expect(screen.getByText('nowhere')).toBeInTheDocument()
  expect(screen.getByText('值得继续？')).toBeInTheDocument()
  expect(screen.getByText('值得继续。')).toBeInTheDocument()
  const ordered = screen.getByRole('heading',{name:'表达结构'}).parentElement!.querySelectorAll('li')
  expect([...ordered].map(item => item.textContent)).toEqual(['回到现场','补充解释','回到现场'])
  expect(ordered[0].parentElement?.tagName).toBe('OL')
})

it.each([
  ['narrative', '行文推进', 'OL'],
  ['comparison', '并列比较', 'UL'],
  ['repeated_blocks', '重复模块', 'UL'],
])('renders %s without giving parallel units a chronological list', (kind, label, tagName) => {
  const report = {viralStructure:{name:'准备出发的三种选择',kind,scope:'section',scopeLabel:'比较交通方案',
    overview:'这一段分别交代各方案的用时与取舍。',steps:['步行：交代沿路体验。','乘车：说明时间成本。','骑行：补充天气限制。']}}
  const original = JSON.stringify(report)
  render(<ProfileView data={report} observations={observations} />)
  const section = screen.getByRole('heading',{name:'表达结构 · 准备出发的三种选择'}).parentElement!
  expect(section).toHaveTextContent(`${label} · 局部：比较交通方案。这一段分别交代各方案的用时与取舍。`)
  const items = section.querySelectorAll('li')
  expect(items[0].parentElement?.tagName).toBe(tagName)
  expect([...items].map(item => item.textContent)).toEqual(report.viralStructure.steps)
  expect(section.querySelector('details')).toBeNull()
  expect(section).not.toHaveTextContent(kind)
  expect(JSON.stringify(report)).toBe(original)
})

it.each([
  {scope:'whole_note',scopeLabel:'不应作为局部显示'},
  {scope:'section',scopeLabel:'   '},
  {},
])('omits absent or inapplicable structure scope without hiding the overview', scope => {
  const overview = '分别写清各项目的定位，再说明该项目的取舍。'.repeat(12)
  render(<ProfileView data={{viralStructure:{kind:'repeated_blocks',...scope,overview,steps:['项目一','项目二']}}} />)
  expect(screen.getByText(`重复模块。${overview}`)).toBeInTheDocument()
  expect(screen.queryByText(/不应作为局部显示|重复模块 ·|undefined|null/)).not.toBeInTheDocument()
})

it('preserves full legacy structure prose without adding inferred structure labels', () => {
  const step = '回到文首提出的问题，但这一次说清楚自己的选择。'.repeat(15)
  const {container} = render(<ProfileView data={{viralStructure:{name:'旧版正文拆解',steps:[step,'补充原来的结尾',step]}}} />)
  expect(screen.getAllByText(step)).toHaveLength(2)
  expect([...container.querySelectorAll('ol li')].map(item => item.textContent)).toEqual([step,'补充原来的结尾',step])
  expect(screen.queryByText(/行文推进|并列比较|重复模块/)).not.toBeInTheDocument()
})

it('retains unique title examples when formulas repeat findings or earlier formula groups', () => {
  const statement = '从具体场景写起'
  const report = {accountPortrait:{strengths:[{statement,evidence:[{noteId:'first',quote:'具体现场'}]}]},titleFormulas:[
    {formula:statement,examples:['夜跑以后']},
    {formula:'直接提出疑问',examples:['为什么想继续写？']},
    {formula:statement,examples:['夜跑以后','下班以前']},
  ]}
  const original = JSON.stringify(report)
  render(<ProfileView data={report} observations={observations} />)
  expect(screen.getAllByText(statement)).toHaveLength(1)
  const sceneExamples = screen.getByText('例：夜跑以后').closest('.account-profile-formula')!
  expect(sceneExamples).toContainElement(screen.getByText('例：下班以前'))
  expect(sceneExamples).not.toContainElement(screen.getByText('例：为什么想继续写？'))
  expect(screen.getAllByText('例：夜跑以后')).toHaveLength(1)
  expect(JSON.stringify(report)).toBe(original)
})

it.each([observations, undefined])('renders exact frozen note annotations as titles across writing advice without changing stored text', snapshot => {
  const notes = [{noteId:'n1',title:'准备之前的两件小事',desc:'冻结正文',metrics:{},comments:[]}]
  const report = {
    voiceFingerprint:['短句有停顿（noteId: n1）'],
    titleFormulas:[{formula:'先说场景（noteId：n1）',examples:['准备开始之前 (noteId: n1)']}],
    hookStyles:['先从现场动作开始（noteId: n1）'],
    viralStructure:{name:'场景推进（noteId: n1）',steps:['先写环境（noteId: n1）']},
    contrast:{takeaways:['下一次保留具体动作（noteId: n1）']},
  }
  const original = JSON.stringify({report,notes})
  const {container} = render(<ProfileView data={report} observations={snapshot} notes={notes} />)
  for (const prefix of ['短句有停顿','先说场景','先从现场动作开始','先写环境','下一次保留具体动作']) {
    expect(screen.getByText(`${prefix}（《准备之前的两件小事》）`)).toBeInTheDocument()
  }
  expect(screen.getByText('例：准备开始之前 （《准备之前的两件小事》）')).toBeInTheDocument()
  expect(screen.getByRole('heading',{name:'表达结构 · 场景推进（《准备之前的两件小事》）'})).toBeInTheDocument()
  expect(container).not.toHaveTextContent('noteId')
  expect(JSON.stringify({report,notes})).toBe(original)
})

it('preserves unknown, duplicate and untitled note IDs rather than guessing by matching titles', () => {
  const makeNote = (noteId: string, title: string) => ({noteId,title,desc:'冻结正文',metrics:{},comments:[]})
  const notes = [makeNote('duplicate','同一个标题'),makeNote('duplicate','另一个标题'),makeNote('empty',' '),
    makeNote('known','同一个标题'),makeNote('also-known','同一个标题')]
  render(<ProfileView notes={notes} data={{hookStyles:[
    '重复身份（noteId: duplicate）','未知身份（noteId: unknown）','空标题 (noteId: empty)',
    '有明确身份（noteId: known）','标题不是身份（noteId: 同一个标题）','正文中的 noteId: known 不处理',
  ]}} />)
  for (const text of ['重复身份（noteId: duplicate）','未知身份（noteId: unknown）','空标题 (noteId: empty)',
    '标题不是身份（noteId: 同一个标题）','正文中的 noteId: known 不处理']) expect(screen.getByText(text)).toBeInTheDocument()
  expect(screen.getByText('有明确身份（《同一个标题》）')).toBeInTheDocument()
})
