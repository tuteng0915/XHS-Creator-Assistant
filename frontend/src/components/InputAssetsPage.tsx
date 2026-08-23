import {
  CREATOR_INPUT_ASSET_PANELS,
  INPUT_ASSET_DEFINITION_BY_PANEL,
  inputAssetPreview,
  inputAssetUpdatedLabel,
  isCreatorInputAssetPanel,
  isTrendCsvInputAsset,
  type InputAssetPanel,
} from '../inputAssets'
import type { InputAsset, TextInputAsset, TrendCsvInputAsset } from '../types'
import {
  xhsCreatorProfileSummaryFromAsset,
  type XhsCreatorProfileSummary,
  type XhsImportPackagePreview,
} from '../xhsCreatorProfile'
import { SaveIndicator, type SaveState } from './StageResultViews'

type TextInputAssetPanel = Exclude<InputAssetPanel, 'trend_csv'>
type XhsImportPanel = Extract<
  TextInputAssetPanel,
  'historical_posts' | 'video_creator_samples' | 'xhs_creator_profiles'
>

type InputAssetsPageProps = {
  inputAssetPanel: InputAssetPanel
  accountProfileMaterials: TextInputAsset[]
  historicalMaterials: TextInputAsset[]
  commentsMaterials: TextInputAsset[]
  trendMaterials: TrendCsvInputAsset[]
  videoCreatorSamplesMaterials: TextInputAsset[]
  xhsCreatorProfileMaterials: TextInputAsset[]
  selectedProfileMaterial: TextInputAsset | null
  historicalMaterial?: TextInputAsset
  commentsMaterial?: TextInputAsset
  trendMaterial?: TrendCsvInputAsset
  videoCreatorSamplesMaterial?: TextInputAsset
  xhsCreatorProfileMaterial?: TextInputAsset
  workspaceName: string
  positioning: string
  accountProfileDraftName: string
  historicalPostsDraftName: string
  commentsDraftName: string
  trendCsvDraftName: string
  videoCreatorSamplesDraftName: string
  xhsCreatorProfileDraftName: string
  historicalPosts: string
  comments: string
  trendKeyword: string
  videoCreatorSamples: string
  xhsCreatorProfileContent: string
  inputAssetFormatterDraft: string
  inputAssetFormatterStatus: string
  workspaceSaveState: SaveState
  accountProfilesSaveState: SaveState
  historicalSaveState: SaveState
  commentsSaveState: SaveState
  trendSaveState: SaveState
  videoSaveState: SaveState
  xhsSaveState: SaveState
  onStartNewInputAsset: (panel: InputAssetPanel) => void
  onOpenInputAsset: (panel: InputAssetPanel) => void
  onChooseTextMaterial: (material: TextInputAsset) => void
  onChooseTrendMaterial: (material: TrendCsvInputAsset) => void
  onFormatterDraftChange: (value: string) => void
  onApplyInputAssetFormatter: () => void
  onAccountProfileDraftNameChange: (value: string) => void
  onWorkspaceNameChange: (value: string) => void
  onPositioningChange: (value: string) => void
  onSaveAccountProfile: () => void
  onSaveAccountProfileAsNew: () => void
  onHistoricalPostsDraftNameChange: (value: string) => void
  onHistoricalPostsChange: (value: string) => void
  onSaveHistoricalPosts: () => void
  onSaveHistoricalPostsAsNew: () => void
  onCommentsDraftNameChange: (value: string) => void
  onCommentsChange: (value: string) => void
  onSaveComments: () => void
  onSaveCommentsAsNew: () => void
  onTrendCsvDraftNameChange: (value: string) => void
  onTrendKeywordChange: (value: string) => void
  onTrendFileChange: (file: File | null) => void
  onUploadTrendCsv: () => void
  onVideoCreatorSamplesDraftNameChange: (value: string) => void
  onVideoCreatorSamplesChange: (value: string) => void
  onSaveVideoCreatorSamples: () => void
  onSaveVideoCreatorSamplesAsNew: () => void
  onXhsCreatorProfileDraftNameChange: (value: string) => void
  onXhsCreatorProfileContentChange: (value: string) => void
  onSaveXhsCreatorProfile: () => void
  onSaveXhsCreatorProfileAsNew: () => void
  xhsImportFiles: Record<XhsImportPanel, File | null>
  onSetXhsImportFile: (panel: XhsImportPanel, file: File | null) => void
  onUploadXhsImport: (panel: XhsImportPanel) => void
  xhsPackageFiles: File[]
  xhsPackagePreview: XhsImportPackagePreview | null
  xhsPackagePreviewError: string
  xhsImportWarnings: string[]
  matchingXhsPackageMaterial: TextInputAsset | null
  onSetXhsPackageFiles: (files: File[]) => void
  onUploadXhsImportPackage: (saveAsNew?: boolean) => void
}

const SAVE_STATE_BY_XHS_IMPORT_PANEL = {
  historical_posts: 'historicalSaveState',
  video_creator_samples: 'videoSaveState',
  xhs_creator_profiles: 'xhsSaveState',
} as const

export function InputAssetsPage(props: InputAssetsPageProps) {
  const {
    inputAssetPanel,
    accountProfileMaterials,
    historicalMaterials,
    commentsMaterials,
    trendMaterials,
  videoCreatorSamplesMaterials,
  xhsCreatorProfileMaterials,
    selectedProfileMaterial,
    historicalMaterial,
    commentsMaterial,
    trendMaterial,
  videoCreatorSamplesMaterial,
  xhsCreatorProfileMaterial,
  } = props
  const definition = INPUT_ASSET_DEFINITION_BY_PANEL[inputAssetPanel]
  const isCreatorPanel = isCreatorInputAssetPanel(inputAssetPanel)
  const panelMaterials: InputAsset[] =
    inputAssetPanel === 'account_profiles'
      ? accountProfileMaterials
      : inputAssetPanel === 'historical_posts'
        ? historicalMaterials
        : inputAssetPanel === 'comments'
          ? commentsMaterials
          : inputAssetPanel === 'trend_csv'
            ? trendMaterials
            : inputAssetPanel === 'xhs_creator_profiles'
              ? xhsCreatorProfileMaterials
            : videoCreatorSamplesMaterials
  const selectedPanelAsset: InputAsset | null =
    inputAssetPanel === 'account_profiles'
      ? selectedProfileMaterial
      : inputAssetPanel === 'historical_posts'
        ? historicalMaterial || null
        : inputAssetPanel === 'comments'
          ? commentsMaterial || null
          : inputAssetPanel === 'trend_csv'
            ? trendMaterial || null
            : inputAssetPanel === 'xhs_creator_profiles'
              ? xhsCreatorProfileMaterial || null
            : videoCreatorSamplesMaterial || null

  const selectInputAsset = (asset: InputAsset) => {
    if (isTrendCsvInputAsset(asset)) {
      props.onChooseTrendMaterial(asset)
      return
    }
    props.onChooseTextMaterial(asset)
  }

  const renderCreatorProfileTabs = () => {
    if (!isCreatorPanel) return null
    return (
      <div className="asset-child-tabs" aria-label="创作者档案子类">
        {CREATOR_INPUT_ASSET_PANELS.map((panel) => {
          const childDefinition = INPUT_ASSET_DEFINITION_BY_PANEL[panel]
          const counts = {
            xhs_creator_profiles: xhsCreatorProfileMaterials.length,
            account_profiles: accountProfileMaterials.length,
            historical_posts: historicalMaterials.length,
            comments: commentsMaterials.length,
            video_creator_samples: videoCreatorSamplesMaterials.length,
          } as const
          return (
            <button
              key={panel}
              type="button"
              className={inputAssetPanel === panel ? 'active' : ''}
              onClick={() => props.onOpenInputAsset(panel)}
            >
              <span>{childDefinition.label}</span>
              <b>{counts[panel]}</b>
            </button>
          )
        })}
      </div>
    )
  }

  const renderDossierAssetSummary = (
    label: string,
    material: TextInputAsset | null | undefined,
    empty: string,
  ) => (
    <div className={`dossier-summary-item ${material ? 'ready' : 'missing'}`}>
      <div>
        <b>{label}</b>
        <span>{material ? material.name : empty}</span>
        {material && <small>{inputAssetPreview(material)}</small>}
      </div>
      <em>{material ? 'ready' : 'missing'}</em>
    </div>
  )

  const renderCreatorDossierOverview = () => {
    if (!isCreatorPanel) return null
    const xhsSummary = xhsCreatorProfileSummaryFromAsset(xhsCreatorProfileMaterial)
    return (
      <div className="creator-dossier-card">
        <div className="creator-dossier-head">
          <div>
            <b>创作者档案概览</b>
            <span>
              组合当前选中的创作者相关资产；底层仍保留独立 input asset。
            </span>
          </div>
          <em>{xhsCreatorProfileMaterial ? 'structured' : 'loose'}</em>
        </div>
        {xhsSummary && (
          <div className="creator-dossier-metrics">
            <span>账号：{xhsSummary.displayName}</span>
            <span>笔记：{xhsSummary.noteCount}</span>
            <span>视频：{xhsSummary.videoNoteCount}</span>
            <span>评论：{xhsSummary.commentCount}</span>
          </div>
        )}
        <div className="creator-dossier-assets">
          {renderDossierAssetSummary(
            '小红书主页',
            xhsCreatorProfileMaterial,
            '未选择结构化主页',
          )}
          {renderDossierAssetSummary(
            '账号概况',
            selectedProfileMaterial,
            '未选择账号概况',
          )}
          {renderDossierAssetSummary(
            '历史笔记',
            historicalMaterial,
            '未选择历史笔记',
          )}
          {renderDossierAssetSummary(
            '评论样本',
            commentsMaterial,
            '未选择评论样本',
          )}
          {renderDossierAssetSummary(
            '视频创作样本',
            videoCreatorSamplesMaterial,
            '未选择视频创作样本',
          )}
        </div>
      </div>
    )
  }

  const renderXhsOfflineImport = (panel: XhsImportPanel) => (
    <div className="source-editor-card">
      <label htmlFor={`${panel}-xhs-import-file`}>小红书离线导入</label>
      <input
        id={`${panel}-xhs-import-file`}
        type="file"
        accept=".json,.md,.markdown,.txt"
        onChange={(event) =>
          props.onSetXhsImportFile(panel, event.target.files?.[0] || null)
        }
      />
      <p className="subline">
        使用独立 xhs local importer 导出的 JSON / Markdown；主平台不会访问小红书。
      </p>
      <div className="save-row">
        <button className="save-button" onClick={() => props.onUploadXhsImport(panel)}>
          上传并保存 XHS 导入
        </button>
        {props.xhsImportFiles[panel] && (
          <span className="save-state saved" role="status">
            {props.xhsImportFiles[panel]?.name}
          </span>
        )}
        <SaveIndicator state={props[SAVE_STATE_BY_XHS_IMPORT_PANEL[panel]]} />
      </div>
    </div>
  )

  const renderXhsPackageImport = () => (
    <div className="source-editor-card">
      <label htmlFor="xhs-package-directory">小红书离线文件夹导入</label>
      <input
        id="xhs-package-directory"
        type="file"
        multiple
        {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
        onChange={(event) =>
          props.onSetXhsPackageFiles(Array.from(event.target.files || []))
        }
      />
      <p className="subline">
        选择包含 xhs_creator_profile.json / profile.json 和 images/... 的导入包；封面会创建为图文资产。
      </p>
      <div className="save-row">
        <button
          className="save-button"
          onClick={() => props.onUploadXhsImportPackage(false)}
        >
          {props.matchingXhsPackageMaterial
            ? '更新已有 XHS 主页'
            : '上传文件夹并保存 XHS 主页'}
        </button>
        {props.matchingXhsPackageMaterial && (
          <button
            className="save-button"
            onClick={() => props.onUploadXhsImportPackage(true)}
          >
            另存为新主页
          </button>
        )}
        {props.xhsPackageFiles.length > 0 && (
          <span className="save-state saved" role="status">
            已选择 {props.xhsPackageFiles.length} 个文件
          </span>
        )}
        <SaveIndicator state={props.xhsSaveState} />
      </div>
      {props.xhsPackagePreview && (
        <div className="xhs-summary-card">
          <div className="xhs-summary-head">
            <b>导入前预览</b>
            <span>{props.xhsPackagePreview.profileFileName}</span>
          </div>
          <div className="xhs-summary-grid">
            <span>账号：{props.xhsPackagePreview.displayName}</span>
            <span>笔记：{props.xhsPackagePreview.noteCount}</span>
            <span>评论：{props.xhsPackagePreview.commentCount}</span>
            <span>图片文件：{props.xhsPackagePreview.imageFileCount}</span>
            <span>匹配封面：{props.xhsPackagePreview.matchedCoverFileCount}</span>
            <span>缺失封面：{props.xhsPackagePreview.missingCoverCount}</span>
          </div>
          {props.matchingXhsPackageMaterial && (
            <p className="xhs-existing-note">
              已存在：{props.matchingXhsPackageMaterial.name}。默认会更新已有资产。
            </p>
          )}
        </div>
      )}
      {props.xhsPackagePreviewError && (
        <p className="save-state error">{props.xhsPackagePreviewError}</p>
      )}
      {renderXhsWarnings(props.xhsImportWarnings)}
    </div>
  )

  const renderXhsSummary = (summary: XhsCreatorProfileSummary | null) => {
    if (!summary) return null
    return (
      <div className="source-editor-card">
        <div className="xhs-summary-head">
          <b>主页摘要</b>
          <span>{summary.displayName}</span>
        </div>
        <div className="xhs-summary-grid">
          <span>笔记：{summary.noteCount}</span>
          <span>评论：{summary.commentCount}</span>
          <span>封面引用：{summary.coverReferenceCount}</span>
        </div>
        {summary.topNotes.length > 0 && (
          <div className="xhs-top-notes">
            <label>高互动前 5 条</label>
            <ol>
              {summary.topNotes.map((note) => (
                <li key={note.noteId || note.title}>
                  <b>{note.title}</b>
                  <span>
                    赞 {note.liked ?? '-'} · 藏 {note.collected ?? '-'} · 评{' '}
                    {note.comments ?? '-'} · 分享 {note.shares ?? '-'}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {renderXhsWarnings(summary.warnings)}
      </div>
    )
  }

  const renderXhsWarnings = (warnings: string[]) => {
    if (warnings.length === 0) return null
    return (
      <div className="xhs-warning-list">
        <b>{warnings.length} 条导入提示</b>
        <ul>
          {warnings.map((warning, index) => (
            <li key={`${index}-${warning}`}>{warning}</li>
          ))}
        </ul>
      </div>
    )
  }

  const renderInputAssetDetail = () => {
    if (inputAssetPanel === 'xhs_creator_profiles') {
      const xhsSummary = xhsCreatorProfileSummaryFromAsset(xhsCreatorProfileMaterial)
      return (
        <>
          <div className="detail-head">
            <div>
              <h2>
                {xhsCreatorProfileMaterial
                  ? xhsCreatorProfileMaterial.name
                  : '新建小红书创作者主页'}
              </h2>
            </div>
          </div>
          {renderXhsSummary(xhsSummary)}
          <div className="source-editor-card">
            <label htmlFor="xhs-creator-profile-draft-name">
              小红书创作者主页名称
            </label>
            <input
              id="xhs-creator-profile-draft-name"
              value={props.xhsCreatorProfileDraftName}
              onChange={(event) =>
                props.onXhsCreatorProfileDraftNameChange(event.target.value)
              }
              placeholder="例：XHS QSheep 创作者主页"
            />
            <label htmlFor="xhs-creator-profile-content">
              结构化主页 JSON（建议由 xhs local importer 导入）
            </label>
            <textarea
              id="xhs-creator-profile-content"
              rows={16}
              value={props.xhsCreatorProfileContent}
              onChange={(event) =>
                props.onXhsCreatorProfileContentChange(event.target.value)
              }
              placeholder='{"schemaVersion":"xhs-creator-profile/v1","notes":[]}'
            />
            <div className="save-row">
              <button className="save-button" onClick={props.onSaveXhsCreatorProfile}>
                {xhsCreatorProfileMaterial
                  ? '保存当前小红书主页'
                  : '保存为小红书主页'}
              </button>
              <button
                className="save-button"
                onClick={props.onSaveXhsCreatorProfileAsNew}
              >
                另存为新小红书主页
              </button>
              <SaveIndicator state={props.xhsSaveState} />
            </div>
          </div>
          {renderXhsOfflineImport('xhs_creator_profiles')}
          {renderXhsPackageImport()}
        </>
      )
    }

    if (inputAssetPanel === 'account_profiles') {
      return (
        <>
          <div className="detail-head">
            <div>
              <h2>
                {selectedProfileMaterial
                  ? selectedProfileMaterial.name
                  : '新建账号概况'}
              </h2>
            </div>
          </div>
          <div className="source-editor-card">
            <label htmlFor="account-profile-draft-name">账号概况名称</label>
            <input
              id="account-profile-draft-name"
              value={props.accountProfileDraftName}
              onChange={(event) =>
                props.onAccountProfileDraftNameChange(event.target.value)
              }
              placeholder="例：Qsheep 留学账号"
            />
            <label htmlFor="workspace-name-inline">工作区名称</label>
            <input
              id="workspace-name-inline"
              value={props.workspaceName}
              onChange={(event) => props.onWorkspaceNameChange(event.target.value)}
            />
            <label htmlFor="positioning-inline">账号定位</label>
            <textarea
              id="positioning-inline"
              rows={7}
              value={props.positioning}
              onChange={(event) => props.onPositioningChange(event.target.value)}
            />
            <div className="save-row">
              <button className="save-button" onClick={props.onSaveAccountProfile}>
                {selectedProfileMaterial ? '保存当前账号概况' : '保存为账号概况'}
              </button>
              <button className="save-button" onClick={props.onSaveAccountProfileAsNew}>
                另存为新账号概况
              </button>
              <SaveIndicator state={props.workspaceSaveState} />
              <SaveIndicator state={props.accountProfilesSaveState} />
            </div>
            <p className="subline">
              当前实现会同步更新 workspace 默认定位；后续可拆成纯资产编辑。
            </p>
          </div>
        </>
      )
    }

    if (inputAssetPanel === 'comments') {
      return (
        <>
          <div className="detail-head">
            <div>
              <h2>{commentsMaterial ? commentsMaterial.name : '新建评论样本'}</h2>
            </div>
          </div>
          <div className="source-editor-card">
            <label htmlFor="comments-draft-name">评论样本名称</label>
            <input
              id="comments-draft-name"
              value={props.commentsDraftName}
              onChange={(event) => props.onCommentsDraftNameChange(event.target.value)}
              placeholder="例：留学评论区合集"
            />
            <label htmlFor="comments">评论区原文（一行一条）</label>
            <textarea
              id="comments"
              rows={12}
              value={props.comments}
              onChange={(event) => props.onCommentsChange(event.target.value)}
            />
            <div className="save-row">
              <button className="save-button" onClick={props.onSaveComments}>
                {commentsMaterial ? '保存当前评论样本' : '保存为评论样本'}
              </button>
              <button className="save-button" onClick={props.onSaveCommentsAsNew}>
                另存为新评论样本
              </button>
              <SaveIndicator state={props.commentsSaveState} />
            </div>
          </div>
        </>
      )
    }

    if (inputAssetPanel === 'trend_csv') {
      return (
        <>
          <div className="detail-head">
            <div>
              <h2>{trendMaterial ? trendMaterial.name : '上传新趋势数据'}</h2>
            </div>
          </div>
          <div className="source-editor-card">
            <label htmlFor="trend-csv-draft-name">趋势数据名称</label>
            <input
              id="trend-csv-draft-name"
              value={props.trendCsvDraftName}
              onChange={(event) => props.onTrendCsvDraftNameChange(event.target.value)}
              placeholder="例：数字游民趋势.csv"
            />
            <label htmlFor="trend-keyword">话题关键词</label>
            <input
              id="trend-keyword"
              value={props.trendKeyword}
              onChange={(event) => props.onTrendKeywordChange(event.target.value)}
              placeholder="例：数字游民、留学申请"
            />
            <label htmlFor="trend-file">热帖数据（CSV / TSV）</label>
            <input
              id="trend-file"
              type="file"
              accept=".csv,.tsv"
              onChange={(event) => props.onTrendFileChange(event.target.files?.[0] || null)}
            />
            <div className="save-row">
              <button className="save-button" onClick={props.onUploadTrendCsv}>
                上传并保存 CSV
              </button>
              <SaveIndicator state={props.trendSaveState} />
            </div>
            {trendMaterial && (
              <div className="csv-preview">
                <div className="csv-summary">
                  <strong>{trendMaterial.originalFilename}</strong>
                  <span>{trendMaterial.rowCount} 条</span>
                </div>
                {trendMaterial.preview.length > 0 && (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          {Object.keys(trendMaterial.preview[0]).map((header) => (
                            <th key={header}>{header}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {trendMaterial.preview.map((row, index) => (
                          <tr key={index}>
                            {Object.keys(trendMaterial.preview[0]).map((header) => (
                              <td key={header}>{row[header] || ''}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )
    }

    if (inputAssetPanel === 'video_creator_samples') {
      return (
        <>
          <div className="detail-head">
            <div>
              <h2>
                {videoCreatorSamplesMaterial
                  ? videoCreatorSamplesMaterial.name
                  : '新建视频创作样本'}
              </h2>
            </div>
          </div>
          <div className="source-editor-card">
            <label htmlFor="video-creator-samples-draft-name">
              视频创作样本名称
            </label>
            <input
              id="video-creator-samples-draft-name"
              value={props.videoCreatorSamplesDraftName}
              onChange={(event) =>
                props.onVideoCreatorSamplesDraftNameChange(event.target.value)
              }
              placeholder="例：AI短剧创作者样本"
            />
            <label htmlFor="video-creator-samples">
              视频创作样本（创作者背景、视频样本、互动数据、运营备注）
            </label>
            <textarea
              id="video-creator-samples"
              rows={12}
              value={props.videoCreatorSamples}
              onChange={(event) => props.onVideoCreatorSamplesChange(event.target.value)}
              placeholder="例：创作者 @xxx；样本视频标题、数据、画面/脚本/更新频率观察；是否商单驱动等"
            />
            <div className="save-row">
              <button
                className="save-button"
                onClick={props.onSaveVideoCreatorSamples}
              >
                {videoCreatorSamplesMaterial
                  ? '保存当前视频创作样本'
                  : '保存为视频创作样本'}
              </button>
              <button
                className="save-button"
                onClick={props.onSaveVideoCreatorSamplesAsNew}
              >
                另存为新视频创作样本
              </button>
              <SaveIndicator state={props.videoSaveState} />
            </div>
          </div>
          {renderXhsOfflineImport('video_creator_samples')}
        </>
      )
    }

    return (
      <>
        <div className="detail-head">
          <div>
            <h2>{historicalMaterial ? historicalMaterial.name : '新建历史笔记'}</h2>
          </div>
        </div>
        <div className="source-editor-card">
          <label htmlFor="historical-posts-draft-name">历史笔记名称</label>
          <input
            id="historical-posts-draft-name"
            value={props.historicalPostsDraftName}
            onChange={(event) =>
              props.onHistoricalPostsDraftNameChange(event.target.value)
            }
            placeholder="例：留学帖子数据合集"
          />
          <label htmlFor="historical-posts">
            主页 / 历史笔记 + 数据（格式：标题 ｜ 数据 ｜ 爆/平/差）
          </label>
          <textarea
            id="historical-posts"
            rows={12}
            value={props.historicalPosts}
            onChange={(event) => props.onHistoricalPostsChange(event.target.value)}
          />
          <div className="save-row">
            <button className="save-button" onClick={props.onSaveHistoricalPosts}>
              {historicalMaterial ? '保存当前历史笔记' : '保存为历史笔记'}
            </button>
            <button
              className="save-button"
              onClick={props.onSaveHistoricalPostsAsNew}
            >
              另存为新历史笔记
            </button>
            <SaveIndicator state={props.historicalSaveState} />
          </div>
        </div>
        {renderXhsOfflineImport('historical_posts')}
      </>
    )
  }

  return (
    <div className="workspace-page asset-page">
      <section className="history-list">
        <div className="panel-title">
          {isCreatorPanel ? '👤 创作者档案' : `${definition.icon} ${definition.label}`}
        </div>
        {isCreatorPanel && (
          <p className="subline">
            小红书主页是上层结构化档案；账号概况、历史笔记、评论样本和视频创作样本是其子视图或兼容输入。
          </p>
        )}
        {renderCreatorDossierOverview()}
        {renderCreatorProfileTabs()}
        <button
          className={`run-row ${selectedPanelAsset ? '' : 'active'}`}
          type="button"
          onClick={() => props.onStartNewInputAsset(inputAssetPanel)}
        >
          <span>{definition.newLabel}</span>
          <b>{definition.contentKind === 'file' ? 'upload' : 'new'}</b>
          <small>创建一个新的 {definition.singularLabel} 实例</small>
        </button>
        {panelMaterials.length === 0 ? (
          <div className="empty-card">{definition.emptyLabel}</div>
        ) : (
          panelMaterials.map((material) => (
            <button
              key={material.id}
              className={`run-row ${
                selectedPanelAsset?.id === material.id ? 'active' : ''
              }`}
              type="button"
              onClick={() => selectInputAsset(material)}
            >
              <span>{material.name}</span>
              <b>{material.type}</b>
              <small>{inputAssetPreview(material)}</small>
              <small>更新于 {inputAssetUpdatedLabel(material)}</small>
            </button>
          ))
        )}
        <div className="asset-type-contract">
          <label>资产类型 contract</label>
          <span>type: {definition.type}</span>
          <span>kind: {definition.contentKind}</span>
          <span>workflow roles: {definition.workflowRoles.join(', ')}</span>
          <span>context: {definition.contextSelectors.join(', ')}</span>
        </div>
      </section>
      <section className="history-detail source-editor-stack">
        <div className="asset-agent-card">
          <div>
            <b>输入素材整理 agent</b>
            <span>
              粘贴原始材料，让 agent 先整理成当前资产类型的草稿；确认后再保存。
            </span>
          </div>
          <textarea
            rows={4}
            value={props.inputAssetFormatterDraft}
            onChange={(event) => props.onFormatterDraftChange(event.target.value)}
            placeholder="粘贴账号定位、历史帖子、评论、创作者样本或趋势说明..."
          />
          <div className="save-row">
            <button className="save-button" onClick={props.onApplyInputAssetFormatter}>
              让 Agent 整理并填入
            </button>
            {props.inputAssetFormatterStatus && (
              <span className="save-state saved" role="status">
                {props.inputAssetFormatterStatus}
              </span>
            )}
          </div>
        </div>
        {renderInputAssetDetail()}
      </section>
    </div>
  )
}
