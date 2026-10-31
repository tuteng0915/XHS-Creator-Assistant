import type { ActivePage } from './WorkspaceShell'

export type GuideStep = { target: string; title: string; description: string }
const step = (target: string, title: string, description: string): GuideStep => ({ target, title, description })
const nav = (page: ActivePage, title: string, description: string) => step(`[data-guide-nav="${page}"]`, title, description)

export const workflowGuide: GuideStep[] = [
  step('.creator-switcher', '先选一个账号', '切换已有账号，或添加新账号。各账号的笔记、分析和稿件分开保存。'),
  nav('source-materials', '查看笔记素材', '查看已导入的图片、正文、互动和评论，确认有哪些素材可用。'),
  nav('account-diagnosis', '了解账号', '选择一组笔记，了解内容特点、历史表现和读者反馈。'),
  nav('audience-analysis', '找到不同的读者', '从选定笔记和评论中生成候选读者，再由你选择收录。'),
  nav('simulated-fans', '整理读者档案', '查看和修改已收录的模拟读者，准备好之后邀请他们试读。'),
  nav('simulations', '邀请读者讨论', '让读者讨论账号方向、复盘已发布笔记，或试读正在写的稿件。'),
  nav('drafts', '开始创作', '从一个想法开始，也可以从选题库接着写。分析和试读按需使用，随时可以直接创作。'),
]

const writingSteps = [
  step('.creator-references-heading', '按需添加参考', '可以直接聊，也可以添加笔记或分析记录。未添加时，助手使用当前稿件与这段对话；更换参考后，下一次发送会开启新的对话段。'),
  step('.collaboration-composer', '说出你的想法', '写下想法、真实经历或修改要求，再点击发送。已有稿件时，发送也会保存当前稿件。'),
  step('.canvas-pane-tabs', '切换对话与稿件', '窄屏下用这两个标签切换。稿件里的手动修改会保留。'),
  step('.canvas-candidate-preview.is-first-draft .canvas-candidate-preview-actions', '采用这份首稿', '先检查并修改候选稿，再点“采用并保存”。还不满意可以点“暂不采用”，回到对话继续调整。'),
  step('.canvas-candidate-preview:not(.is-first-draft) .canvas-candidate-preview-actions', '采用这次修改', '确认后，建议会放入当前稿件；选段改写只替换选中的段落。检查满意后，再点击稿件区的“保存”。'),
  step('[data-guide="draft-heading"]', '手动编辑稿件', '在下方直接修改标题和正文，也可以选中一段文字，请助手局部改写。'),
  step('.canvas-editor .save-row', '保存与复制', '修改后点击“保存”。“复制全部”复制当前标题和正文，包括尚未保存的修改；复制后仍可继续编辑。'),
  step('.creator-canvas-page .creator-page-actions', '继续其他选题', '从“选题库”找已有想法和稿件；下拉框也能切换已有创作。有未保存的修改时，先保存再切换。'),
]

export const pageGuides: Partial<Record<ActivePage, GuideStep[]>> = {
  'creator-start': [
    step('.creator-url-form', '导入账号笔记', '粘贴小红书用户主页链接。已记录主页的账号可以直接继续读取。'),
    step('.creator-start-page .creator-range-row', '确认读取范围', '选择要读取的笔记数量，再点击上方导入按钮。如需登录，按页面提示完成后继续。'),
    step('.creator-capture-status > div:first-child', '查看导入进度', '这里显示当前读取进度，完成后可到“我的笔记”查看素材。'),
  ],
  'creator-overview': [
    step('.creator-switcher', '当前账号', '在这里切换或添加账号。'),
    step('.creator-overview-metrics', '快速了解账号', '这里显示已导入的账号数据。笔记详情和数据截止时间可在“我的笔记”查看。'),
    step('.creator-overview-page .creator-page-head', '从账号开始', '已有笔记时，点“分析账号”进入诊断；还没有素材时，先点“导入账号”。'),
    step('.creator-overview-section .creator-page-head', '查看和补充笔记', '查看已抓取笔记，也可以抓取更多笔记补充素材。'),
  ],
  'source-materials': [
    step('.creator-materials-page .creator-page-head', '整理笔记素材', '这里可以抓取更多笔记，或进入账号分析。标题旁显示数据截止时间。'),
    step('.creator-note-card', '打开一篇笔记', '点卡片查看图片、正文和评论；在详情右上角关闭预览。'),
  ],
  'account-diagnosis': [
    step('[data-guide="diagnosis-import"]', '先导入笔记', '点击这里导入账号素材，笔记准备好后就可以开始诊断。'),
    step('[data-guide="diagnosis-range"]', '选择分析范围', '选择这次要分析的笔记，可以按时间、点赞或互动筛选，也可以逐篇勾选。'),
    step('[data-guide="diagnosis-start"]', '开始诊断', '确认范围后开始。已完成的部分会先展示；若某部分失败，可在结果中单独重试。'),
    step('[data-guide="diagnosis-history"]', '回看诊断历史', '按时间找到之前的报告，查看当时使用的笔记和分析结果。'),
  ],
  'audience-analysis': [
    step('.audience-results-page .creator-range-row', '选择读者分析的素材', '点“调整范围”，选择这次要分析的笔记。'),
    step('.audience-results-page .creator-page-head button.primary', '生成候选读者', '点“分析受众”，完成后逐个查看人物，选择你想收录的读者。'),
    step('.audience-card-action button', '收录想邀请的读者', '查看人物的关注点和依据，再点“收录为模拟读者”。已收录的人物会保存在“模拟粉丝”，之后可以修改。'),
    step('.audience-results-heading > button', '邀请读者试读', '进入受众模拟后，再选择试读内容和实际参与的读者。'),
  ],
  'simulated-fans': [
    step('.fan-profiles-page .history-list > button.primary', '先准备读者', '先分析受众，再收录想邀请的人物。收录后可以在这里管理。'),
    step('.fan-profiles-page .run-row', '选择读者档案', '打开一位读者，查看其关注点和判断习惯。'),
    step('.fan-profile-head > button', '调整人物设定', '编辑这位读者的长期设定，保存后用于之后的试读。'),
    step('.fan-editor-actions', '保存档案修改', '点击“保存修改”更新档案；取消会放弃这次编辑。'),
  ],
  simulations: [
    step('.simulation-category-tabs', '先选模拟类别', '账号级看内容方向，已发布笔记级复盘同类内容，创作级帮助修改当前稿。'),
    step('.simulation-account-range', '选择账号笔记', '选择希望读者讨论的多篇笔记，这次模拟围绕你确认的范围展开。'),
    step('.simulation-note-target', '选择已发布笔记', '选择一篇笔记，复盘读者的反应，为下一篇同类内容积累建议。'),
    step('.simulation-target', '选择创作内容', '选择正在写的选题或稿件。只有标题时，先讨论阅读期待；有正文后可以试读全文。'),
    step('.panel-task-modes', '设置讨论目标', '让读者自由试读，或给出你希望他们重点回答的问题。'),
    step('.simulation-readers-empty button', '先添加模拟读者', '去受众分析收录人物，再回来选择本次参与者。'),
    step('.simulation-reader-controls', '确认参与读者', '用下拉框手动选人，也可以先推荐、采用后再调整。这里选定的名单才会参与；调整“本次角色”只影响这场模拟。'),
    step('.simulation-start', '开始试读', '选好内容和至少一位读者后开始；定向试读还需填好问题。发言会分段出现，讨论完成后可以继续追问。'),
  ],
  drafts: writingSteps,
  topics: [
    step('.creator-topics-page .history-list > button.primary', '记下一个选题', '新建选题，写下标题和切入角度，保存到选题库。也可以直接去创作助手聊想法。'),
    step('.creator-topics-page .topic-row', '查看已有选题', '点一条选题查看内容。“已有稿件”的选题可以接着修改。'),
    step('.creator-topics-page .detail-actions', '接着写或整理选题', '在这里开始或继续创作，也可以编辑选题。置顶和归档放在“更多”中。'),
  ],
  history: [
    step('[aria-label="诊断历史"] .run-row', '选择一次诊断', '按时间和笔记数量找到要看的报告，点击查看当时的分析。'),
    step('.creator-subpage-actions', '返回账号诊断', '需要分析另一组笔记时，从这里返回并重新选择范围。'),
  ],
}
