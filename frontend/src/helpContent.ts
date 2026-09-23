import type { ActivePage } from './components/WorkspaceShell'
import {
  INPUT_ASSET_DEFINITION_BY_PANEL,
  type InputAssetPanel,
} from './inputAssets'
import type { WorkflowTab } from './workflows'

export type HelpContent = {
  title: string
  description: string
  bullets: string[]
}

export function getWorkspaceHelpContent({
  activePage,
  inputAssetPanel,
  workflowTab,
  publicMode = false,
}: {
  activePage: ActivePage
  inputAssetPanel: InputAssetPanel
  workflowTab: WorkflowTab
  publicMode?: boolean
}): HelpContent {
  if (publicMode && activePage !== 'creator-start') {
    return {
      title: activePage === 'source-materials' ? '浏览笔记' : '使用帮助',
      description: '所有材料、分析和创作结果都保存在当前账号下。',
      bullets: [
        '从账号概览查看已读取的内容；点击笔记封面可查看正文和对应评论。',
        '默认分析最近 10 条已导入笔记，也可以调整为最近 7、30、90 天或全部。缺少发布时间的旧笔记不纳入日期筛选。',
        '诊断生成的推荐会自动保存到选题库；选择选题后可以编辑、用 AI 细化或进行受众模拟。',
        '受众模拟是方向性参考，不代表真实用户的评论或实际流量。',
        '保存修改后再进入下一步；原始生成内容会保留以供对照。',
      ],
    }
  }
  if (activePage === 'creator-start') {
    return {
      title: '导入小红书账号',
      description:
        '粘贴小红书用户主页链接后，系统会在本机启动低并发导入任务，并把结果保存到当前账号档案。',
      bullets: [
        '支持完整的小红书用户主页 URL，也支持用户主页短链。',
        '首次运行可能打开浏览器窗口；请使用小红书扫码登录，不要关闭该窗口。',
        '默认读取最近 10 条笔记及一级评论；调整范围可以读取更多或全部可见笔记。',
        '导入完成后会保存笔记正文、互动数据、评论和可用封面。',
        '如果主平台和抓取程序不在同一台机器，扫码窗口会出现在抓取程序所在机器。',
      ],
    }
  }

  if (activePage === 'source-materials') {
    const definition = INPUT_ASSET_DEFINITION_BY_PANEL[inputAssetPanel]
    return {
      title: `${definition.label} 帮助`,
      description:
        '输入素材是 workflow 可复用的内容资产实例。每一种资产类型都有固定 contract，不是通用文件夹。',
      bullets: [
        definition.description,
        `当前类型：${definition.type}，内容形态：${definition.contentKind}。`,
        `Workflow role：${definition.workflowRoles.join(', ')}。`,
        `Context selector：${definition.contextSelectors.join(', ')}。`,
        '左侧列表选择已有实例；点击新建或上传可以创建新的输入实例。',
        '保存是显式动作；运行 workflow 前，当前编辑内容也会自动保存为对应输入素材。',
      ],
    }
  }

  if (activePage === 'image-assets' || activePage === 'video-assets') {
    const isImage = activePage === 'image-assets'
    return {
      title: `${isImage ? '图文素材' : '视频素材'}帮助`,
      description:
        '媒体素材是内容资产的一部分，用于保存创作者图文/视频材料和后续可复用的派生信息。',
      bullets: [
        '媒体页支持上传、metadata、derived JSON、用户备注、Qwen 图片/视频理解和 Qwen 图片/视频生成。',
        '演示模式不会调用 Qwen，会返回 demo 结果；实时生成模式会使用后端已配置的 Qwen API。',
        '图片/视频理解结果先作为草稿展示，用户点击保存后才写入 derived，避免静默覆盖素材。',
        '原始文件由后端受控保存，前端通过 /api/media-assets/{id}/file 预览。',
        '本地视频理解会先抽取少量预览帧，不会把完整视频文件直接发送给模型。',
        '后续视频博主质量诊断可以读取媒体资产的 compact snapshot，而不是直接读取完整二进制。',
      ],
    }
  }

  if (
    activePage === 'account-diagnosis' ||
    activePage === 'trend-analysis' ||
    activePage === 'video-quality'
  ) {
    return {
      account: {
        title: '账号诊断帮助',
        description:
          '账号诊断会读取账号概况、历史笔记和评论样本，生成账号画像、痛点分析和候选选题。',
        bullets: [
          '账号概况、历史笔记和评论样本都以已保存实例形式传入 workflow。',
          '历史笔记和评论样本会绑定为本次 run 的 immutable input snapshot。',
          'Demo 模式会在缺少输入时填入示例数据；Live 模式使用真实模型配置。',
          '每次运行只处理当前选择的一组输入资产，便于检查和复盘。',
        ],
      },
      trend: {
        title: '热点分析帮助',
        description:
          '热点分析会读取账号概况和趋势数据，先确定性解析排名，再生成趋势洞察和候选选题。',
        bullets: [
          '趋势数据上传后保存为输入素材；原始 CSV/TSV 文件由后端托管，前端只展示 preview。',
          'Workflow 会保留 top-50 engagement ranking 行为。',
          '运行时保存的是 compact input snapshot，不把完整 CSV 放进 graph state。',
          '适合用来把热点内容转成适配当前账号定位的选题。',
        ],
      },
      video: {
        title: '视频博主质量诊断帮助',
        description:
          '视频博主质量诊断会读取账号概况和视频创作样本，判断创作者画像、视频质量和激励计划适配度。',
        bullets: [
          '样本应包含创作者背景、视频标题/数据、内容观察和运营备注。',
          '适合创作者运营逐个评估 AIGC 视频创作者。',
          '输出会区分剧本驱动、商单驱动、技术探索等不同激励适配路径。',
          '后续应优先优化单个创作者的证据检查和诊断质量。',
        ],
      },
    }[workflowTab]
  }

  if (activePage === 'history') {
    return {
      title: '分析结果帮助',
      description: '这里保存每次账号诊断、热点分析、视频博主质量诊断的运行历史。',
      bullets: [
        '每条 run 都包含 workflow type、status、input snapshot、stage results 和 errors。',
        '重新打开历史结果不会重新执行 workflow。',
        'Input snapshot 和 stage results 是不可变执行历史，用于复盘和后续生成选题/结构。',
        '人工复盘状态和备注可以编辑，用来标记结果是否有用、是否需要弃用。',
        '失败或部分完成的 run 也会保留可用 stage result。',
      ],
    }
  }

  if (activePage === 'topics') {
    return {
      title: '选题库帮助',
      description: '选题库保存来自诊断、热点分析或手动录入的选题资产。',
      bullets: [
        '选题可以先生成创作 Brief，再继续生成内容结构或发送到受众模拟。',
        'title 和 angle 可编辑；generated snapshot 作为来源记录保留。',
        'Archive 会把选题从候选工作流中移出，但不删除历史。',
        '从生成卡片“填入下一步”的快捷动作会尽量绑定到 Topic entity。',
      ],
    }
  }

  if (activePage === 'drafts') {
    return {
      title: '创作输出帮助',
      description: '这里保存由能力资产生成的创作 Brief、内容结构，以及用户后续编辑内容。',
      bullets: [
        'generated snapshot 是模型生成快照，不应被用户编辑覆盖。',
        'editable content 保存用户修改版本。',
        '生成 Brief、生成结构、改写润色等动作属于能力资产；这里保存的是这些能力产生的内容资产。',
        '创作 Brief 用于对齐目标读者、内容承诺、核心观点和素材需求。',
        '内容结构可以从 Topic 直接生成，也可以从已确认的 Brief 继续生成。',
        'Brief 和结构都可以继续发送到受众模拟。',
      ],
    }
  }

  if (activePage === 'simulations') {
    return {
      title: '受众模拟帮助',
      description: '这里保存围绕某个 Topic、创作 Brief 或内容结构运行的受众模拟结果。',
      bullets: [
        '模拟会生成产品特定 personas，不是通用可配置 agents。',
        '每个 persona 的反应是独立结果，失败时尽量保留部分反应。',
        '可以重新打开历史 simulation，不会重新执行。',
        '人工复盘状态和备注可以编辑；persona、reaction、debate、synthesis 和 model metadata 保持只读。',
        '适合验证选题角度、受众疑虑、反对意见和内容策略。',
      ],
    }
  }

  if (activePage === 'conversations') {
    return {
      title: '对话记录帮助',
      description:
        '这里保存和 Agent、Capability Maker、输入素材整理能力相关的对话历史，作为可复盘的内容资产。',
      bullets: [
        '每条对话会显示对应 Agent、执行状态、更新时间和完整消息。',
        '对话标题和归档状态可编辑，方便整理生成历史。',
        'Assistant 消息里的引用资产、model metadata 和 proposed actions 会一起保留。',
        '重新打开对话不会重新执行模型；它只是读取已保存的 conversation 记录。',
        '消息正文、context pack 和 model metadata 是执行历史，保持只读。',
        '如果需要继续和某个 Agent 对话，可以从右侧 Agents 页面进入对应 Agent。',
      ],
    }
  }

  if (activePage === 'skills') {
    return {
      title: 'Skills 帮助',
      description:
        'Skills 是产品内部可组合能力资产，描述输入 contract、输出 schema、side effects 和组合边界。',
      bullets: [
        '当前用户侧只读；我们可以在代码和 maker agent 中新增或调整。',
        'Capability Maker 会根据需求调用对应 skill，生成 Skill asset proposal。',
        'Skill 的输入应引用 InputAsset、AnalysisRun、Topic 等产品资产。',
        '旧 source.* skill id 暂时保留为兼容 ID，但 contract 已迁到 InputAsset 语义。',
      ],
    }
  }

  if (activePage === 'agents') {
    return {
      title: 'Agents 帮助',
      description:
        'Agents 是产品角色资产：system prompt + 多个 Skills + 默认 context policy。',
      bullets: [
        'Conversation 入口可以和 agent 对话，用于生成或修改资产提案。',
        'Agent 可以读取 broad workspace context pack，但不能直接访问数据库或任意文件。',
        'Capability Maker 可用于生成 Agent asset proposal。',
        '未来 agent 可逐步拥有确认后应用的资产修改能力。',
      ],
    }
  }

  if (activePage === 'workflows') {
    return {
      title: 'Workflows 帮助',
      description: 'Workflows 是多 agent、多 task 的产品执行计划，不是通用流程编辑器。',
      bullets: [
        'workflow 调用在右侧发起；这里查看 workflow asset 定义和 agent plan。',
        '当前 graph 执行仍由后端产品接口封装，前端不暴露 LangGraph 术语。',
        'Capability Maker 可用于生成 workflow asset proposal。',
        'Workflow 输入应绑定具体 InputAsset 实例或由运行前自动保存。',
      ],
    }
  }

  return {
    title: '账号诊断助手',
    description:
      '这里围绕一个小红书账号保存材料、诊断结果、选题、创作方案和受众模拟。',
    bullets: [
      '每个账号档案的数据彼此独立。',
      '推荐依次完成导入账号、账号诊断、选题、AI 创作和受众模拟。',
      '所有生成结果都会保存，刷新页面后仍可重新打开。',
    ],
  }
}
