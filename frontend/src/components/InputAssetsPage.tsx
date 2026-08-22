import {
  INPUT_ASSET_DEFINITION_BY_PANEL,
  inputAssetPreview,
  inputAssetUpdatedLabel,
  isTrendCsvInputAsset,
  type InputAssetPanel,
} from '../inputAssets'
import type { InputAsset, TextInputAsset, TrendCsvInputAsset } from '../types'
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
  onSetInputAssetBatchFile: (panel: TextInputAssetPanel, file: File | null) => void
  onUploadTextInputAssetsCsv: (panel: TextInputAssetPanel) => void
  xhsImportFiles: Record<XhsImportPanel, File | null>
  onSetXhsImportFile: (panel: XhsImportPanel, file: File | null) => void
  onUploadXhsImport: (panel: XhsImportPanel) => void
}

const SAVE_STATE_BY_TEXT_INPUT_PANEL = {
  account_profiles: 'accountProfilesSaveState',
  historical_posts: 'historicalSaveState',
  comments: 'commentsSaveState',
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

  const renderTextBatchImport = (
    panel: TextInputAssetPanel,
    label: string,
    hint: string,
  ) => (
    <div className="source-editor-card">
      <label htmlFor={`${panel}-batch-file`}>{label}批量导入（CSV / TSV）</label>
      <input
        id={`${panel}-batch-file`}
        type="file"
        accept=".csv,.tsv"
        onChange={(event) =>
          props.onSetInputAssetBatchFile(panel, event.target.files?.[0] || null)
        }
      />
      <p className="subline">{hint}</p>
      <div className="save-row">
        <button
          className="save-button"
          onClick={() => props.onUploadTextInputAssetsCsv(panel)}
        >
          上传并保存{label}
        </button>
        <SaveIndicator state={props[SAVE_STATE_BY_TEXT_INPUT_PANEL[panel]]} />
      </div>
    </div>
  )

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
        <SaveIndicator state={props[SAVE_STATE_BY_TEXT_INPUT_PANEL[panel]]} />
      </div>
    </div>
  )

  const renderInputAssetDetail = () => {
    if (inputAssetPanel === 'xhs_creator_profiles') {
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
          {renderTextBatchImport(
            'xhs_creator_profiles',
            '小红书主页',
            '表头支持 name/content、xhs_creator_profile、xhs_profile、小红书主页。',
          )}
          {renderXhsOfflineImport('xhs_creator_profiles')}
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
          {renderTextBatchImport(
            'account_profiles',
            '账号概况',
            '表头支持 name/profile、profile_name/account_profile、账号/定位。',
          )}
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
          {renderTextBatchImport(
            'comments',
            '评论样本',
            '表头支持 name/content、comments、comment_samples、评论、评论样本。',
          )}
        </>
      )
    }

    if (inputAssetPanel === 'trend_csv') {
      return (
        <>
          <div className="detail-head">
            <div>
              <h2>{trendMaterial ? trendMaterial.name : '上传新趋势 CSV'}</h2>
            </div>
          </div>
          <div className="source-editor-card">
            <label htmlFor="trend-csv-draft-name">趋势 CSV 名称</label>
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
                  : '新建视频创作者样本'}
              </h2>
            </div>
          </div>
          <div className="source-editor-card">
            <label htmlFor="video-creator-samples-draft-name">
              视频创作者样本名称
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
              视频创作者样本（创作者背景、视频样本、互动数据、运营备注）
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
                  ? '保存当前视频创作者样本'
                  : '保存为视频创作者样本'}
              </button>
              <button
                className="save-button"
                onClick={props.onSaveVideoCreatorSamplesAsNew}
              >
                另存为新视频创作者样本
              </button>
              <SaveIndicator state={props.videoSaveState} />
            </div>
          </div>
          {renderTextBatchImport(
            'video_creator_samples',
            '视频创作者样本',
            '表头支持 name/content、video_creator_samples、video_samples、创作者样本。',
          )}
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
        {renderTextBatchImport(
          'historical_posts',
          '历史笔记',
          '表头支持 name/content、historical_posts、posts、历史笔记、笔记。',
        )}
        {renderXhsOfflineImport('historical_posts')}
      </>
    )
  }

  return (
    <div className="workspace-page asset-page">
      <section className="history-list">
        <div className="panel-title">
          {definition.icon} {definition.label}
        </div>
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
