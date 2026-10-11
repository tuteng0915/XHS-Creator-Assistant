import type { CollaborationSession } from '../contentCollaboration'
import type { CreatorNote } from '../creatorNotes'
import type { Observations, Portrait } from '../components/AccountPortraitView'
import type { AnalysisRun, AudienceAnalysis, SimulationRun, TextInputAsset, Topic, Workspace } from '../types'

// Handwritten fictional material, never a copy of an account or a model response.
export const timestamp = '2026-10-08T02:00:00Z'
export const workspace: Workspace = {
  id: 'readme-fictional-workspace', name: '慢慢做事 · 演示', accountPositioning: '记录普通人把事情慢慢做成的过程',
  positioningVersion: 1, currentTopicId: 'readme-fictional-topic', createdAt: timestamp, updatedAt: timestamp,
}
export const notes: CreatorNote[] = [
  {
    noteId: 'readme-small-start', title: '开始一件事，不必先准备好一切',
    desc: '买了三本手账，我还是没开始记录。\n\n后来我把目标改成：每天只写一句。今天先记下窗边那杯凉掉的茶。写完就合上本子，不补昨天，也不规划明天。\n\n一周后回头看，原来我已经留下了七个小片段。开始不是把准备做完，而是让第一步小一点。',
    metrics: { liked: 128, collected: 76, comments: 12, shares: 5 }, comments: [], publishedAt: '2026-10-01T02:00:00Z',
  },
  {
    noteId: 'readme-ten-minutes', title: '只收拾十分钟，房间真的会变好吗？',
    desc: '周末想把整个房间收拾好，最后却一直坐着。\n\n我设了十分钟计时，只清掉桌面上的空杯子。时间到了就停。第二天再整理一小格抽屉。\n\n房间没有突然焕然一新，但我终于不再害怕开始。',
    metrics: { liked: 96, collected: 54, comments: 9, shares: 3 }, comments: [], publishedAt: '2026-10-04T02:00:00Z',
  },
]
export const profile: TextInputAsset = {
  id: 'readme-fictional-profile', workspaceId: workspace.id, type: 'xhs_creator_profile', name: '慢慢做事的虚构笔记',
  content: JSON.stringify({ nickname: '慢慢做事', noteCount: notes.length, notes }), createdAt: timestamp, updatedAt: timestamp,
}
const evidence = notes.map(note => ({ noteId: note.noteId, scope: 'note' as const }))
function fragment(source: 'title' | 'body', quote: string) {
  const text = source === 'title' ? notes[0].title : notes[0].desc
  const start = text.indexOf(quote)
  if (start < 0) throw new Error('README example must quote its fictional source exactly')
  return { source, quote, start, end: start + quote.length }
}
const portrait: Portrait = {
  summary: { statement: '你把“怎么开始”写成生活里的小事：先承认卡住，再给出一个今天就能做的动作。', evidence },
  keywords: ['低门槛行动', '日常记录', '温和陪伴'].map(statement => ({ statement, evidence })),
  strengths: [{
    statement: '写出小变化，也保留真实的限度：“房间没有突然焕然一新，但我终于不再害怕开始。”',
    evidence: [{ noteId: notes[1].noteId, quote: '房间没有突然焕然一新，但我终于不再害怕开始。' }],
  }],
  expressionPatterns: [
    {
      statement: '标题先说出熟悉的顾虑，再松开“必须准备好”的限制。', evidence: [evidence[0]],
      examples: [{ noteId: notes[0].noteId, title: notes[0].title,
        fragments: [fragment('title', notes[0].title)],
        interpretation: '“开始一件事”交代场景，“不必”回应迟迟不动手的压力；没有承诺结果，而是邀请读者先试一步。' }],
    },
    {
      statement: '正文用具体动作接住情绪，让建议有可以照着做的落点。', evidence: [evidence[0]],
      examples: [{ noteId: notes[0].noteId, title: notes[0].title,
        fragments: [fragment('body', '每天只写一句。'), fragment('body', '写完就合上本子，不补昨天，也不规划明天。')],
        interpretation: '一句话缩小任务，“合上本子”给出停止的位置；两个动作一起降低了持续记录的负担。' }],
    },
  ],
}
export const observations: Observations = {
  schemaVersion: 'xhs-account-observations/v1',
  coverage: { selectedCount: 2, availableCount: 2, missingDateCount: 0, capturedCommentCount: 0,
    missingMetricCounts: {}, snapshotAt: timestamp, dateRange: { earliest: '2026-10-01', latest: '2026-10-04' } },
  notes: notes.map(note => ({ noteId: note.noteId, title: note.title, publishedAt: String(note.publishedAt), metrics: note.metrics })),
}
export const accountResult = {
  observations,
  profile: {
    accountPortrait: portrait,
    viralStructure: {
      name: '从卡住到迈出第一步', kind: 'narrative', scope: 'whole',
      overview: '先交代生活中的阻力，再展示一次微小尝试，最后回到自己的发现。',
      steps: ['真实处境：买了手账，却没有开始。', '缩小动作：每天一句，写完就停。', '回看变化：一周后留下七个片段。'],
    },
  },
}
export const accountRun: AnalysisRun = {
  id: 'readme-fictional-account-analysis', workspaceId: workspace.id, workflowType: 'account_diagnosis', status: 'completed',
  userNotes: '', reviewStatus: 'unreviewed', createdAt: timestamp, updatedAt: timestamp, startedAt: timestamp, completedAt: timestamp,
  inputSnapshot: { xhsCreatorProfile: { notes, noteCount: notes.length }, analysisRange: { selectedNoteCount: notes.length } },
  stageResults: { profile: accountResult }, stageErrors: {}, modelMetadata: {},
}
export const audienceRun: AudienceAnalysis = {
  id: 'readme-fictional-audience-analysis', workspaceId: workspace.id, sourceMaterialId: profile.id, status: 'completed',
  inputSnapshot: { scope: { scope: 'all', selectedNoteCount: 2 } },
  result: {
    summary: '这份虚构材料展示三种阅读视角：愿意尝试、需要细节、担心坚持不下去。',
    groups: [
      { id: 'start', name: '想先试一步的人', profile: '有想法，但经常停在准备阶段。', coreConcern: '今天能做的第一步是什么？', evidence: [] },
      { id: 'detail', name: '关心具体方法的人', profile: '愿意行动，希望建议更具体。', coreConcern: '怎么做，做到哪里可以停？', evidence: [] },
      { id: 'pressure', name: '容易自我加压的人', profile: '担心错过一天就前功尽弃。', coreConcern: '中断以后还能继续吗？', evidence: [] },
    ],
  }, error: '', createdAt: timestamp,
}
export const topic: Topic = {
  id: 'readme-fictional-topic', workspaceId: workspace.id, title: '想做的事很多，先留十分钟给自己',
  body: '周日晚，我又列了一张很长的计划表。\n读书、运动、整理照片……每件都想做，结果一件也没开始。\n\n这次我没有重新排计划，只选了最想做的一件事，给它十分钟。\n\n我翻开那本搁了很久的书，只读两页。手机计时响了，就把书签放进去。没有追赶进度，也没有给明天加码。\n\n这十分钟并没有让生活焕然一新，但让我从“等有空再说”，走到了“今天已经做了一点”。\n\n如果你也卡在开始之前，今晚想把这十分钟留给什么？',
  angle: '把开始缩小到十分钟', associatedPainPoint: '', whyItFits: '', generatedSnapshot: {},
  sourceAnalysisRunId: null, sourceWorkflow: 'manual', status: 'candidate', createdAt: timestamp, updatedAt: timestamp,
}
export const session: CollaborationSession = {
  id: 'readme-fictional-session', workspaceId: workspace.id, title: topic.title, assistantMode: 'single_writer',
  status: 'active', executionStatus: 'waiting_creator', contextTarget: { assetType: 'topic', assetId: topic.id },
  failureCode: '', failureDetail: '', createdAt: timestamp, updatedAt: timestamp, contextRevision: 1,
  creatorContextSelection: { schemaVersion: 'creator-context-selection/v1', references: [
    { kind: 'imported_note', id: profile.id, noteId: notes[0].noteId },
    { kind: 'account_analysis', id: accountRun.id },
    { kind: 'audience_analysis', id: audienceRun.id },
  ] },
  messages: [
    { id: 'readme-creator-message', sessionId: 'readme-fictional-session', sequenceNo: 1, sender: 'creator', recipient: 'writing',
      content: '保留我平常聊天的语气。开头再具体一点，不要像在讲道理。', replyToMessageId: null, modelMetadata: {}, createdAt: timestamp },
    { id: 'readme-writing-message', sessionId: 'readme-fictional-session', sequenceNo: 2, sender: 'writing', recipient: 'creator',
      content: '你原来的“一句记录”写法很适合延续。先让人看见那个迟迟没动手的周日，再引出十分钟。',
      replyToMessageId: 'readme-creator-message', modelMetadata: { candidateSuggestions: [{ kind: 'copy_option', title: '从那个周日晚上写起',
        body: '周日晚，计划表列了很长：读书、运动、整理照片。每件都想做，却一件也没开始。这次我没再重排计划，只翻开那本搁了很久的书，先读两页。', confidence: 'inference' }] }, createdAt: timestamp },
  ], runs: [],
}
const feedbackQuote = '手机计时响了，就把书签放进去。'
const feedbackStart = Array.from((topic.body || '').split(feedbackQuote)[0]).length
const targetContentHash = 'readme-fictional-target-v1'
const timingConcern = {
  id: 'readme-concern-timing', messageId: 'initial:detail', personaId: 'detail', field: 'concerns',
  text: '十分钟的作用还可以解释清楚。',
}
export const simulation: SimulationRun = {
  id: 'readme-fictional-simulation', workspaceId: workspace.id, topicId: topic.id, draftId: null,
  status: 'completed', simulationCategory: 'creation', inputSnapshot: { topic: { title: topic.title, body: topic.body }, targetContentHash, panelTask: { discussionEnabled: true } },
  personaDefinitions: (audienceRun.result.groups || []).map(group => ({ id: group.id, name: group.name })),
  reactionResults: [
    { personaId: 'start', action: 'comment', quote: '“只读两页”让我觉得今晚就能试。不是又一份需要坚持一百天的计划。', understanding: '把想做的事缩小到今天的一小步。' },
    { personaId: 'detail', messageId: 'initial:detail', action: 'comment', quote: '十分钟到了就停，我反而有点不确定：如果正读得起劲呢？想知道这是上限，还是一个起点。', concerns: [timingConcern.text] },
    { personaId: 'pressure', action: 'comment', quote: '我最在意“没有给明天加码”。但如果第二天没做，是不是也没关系？希望你再说一句。', understanding: '不必一次做好所有事。' },
  ],
  debateResults: [{ personaId: 'start', replyToId: 'initial:pressure', response: '我也是！如果能写“漏一天也可以重新开始”，会更愿意试。' }],
  synthesis: {
    verdict: '保留具体的生活场景，补清“十分钟”的边界和中断后的选择。',
    editorFeedback: [{
      id: 'readme-feedback-timing', kind: 'add_material', sourceType: 'reader', priority: 'first',
      observation: '补清计时结束后的选择',
      reason: '读者已理解如何开始，但还不确定十分钟是上限还是起点，需要作者补充自己的做法。',
      materialRequests: ['如果十分钟到了还想继续读，你会停下来还是继续？补一句你自己的选择。'],
      sourceMessageIds: [timingConcern.messageId], readerConcernIds: [timingConcern.id], readerConcerns: [timingConcern],
      beneficiaries: ['detail'],
      target: { field: 'body', quote: feedbackQuote, occurrence: 1, start: feedbackStart,
        end: feedbackStart + Array.from(feedbackQuote).length, coordinateSystem: 'unicode_code_points', contentHash: targetContentHash },
    }],
    editorFeedbackValidation: { status: 'validated', rejected: [] },
  },
  stageErrors: {}, modelMetadata: {}, userNotes: '', reviewStatus: 'unreviewed',
  createdAt: timestamp, updatedAt: timestamp, startedAt: timestamp, completedAt: timestamp,
}
