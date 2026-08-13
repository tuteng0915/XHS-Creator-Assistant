import { SaveIndicator, type SaveState } from './StageResultViews'

type AccountProfilePageProps = {
  workspaceName: string
  positioning: string
  positioningVersion: number
  workspaceSaveState: SaveState
  accountProfilesSaveState: SaveState
  onWorkspaceNameChange: (value: string) => void
  onPositioningChange: (value: string) => void
  onSave: () => void
}

export function AccountProfilePage({
  workspaceName,
  positioning,
  positioningVersion,
  workspaceSaveState,
  accountProfilesSaveState,
  onWorkspaceNameChange,
  onPositioningChange,
  onSave,
}: AccountProfilePageProps) {
  return (
    <div className="workspace-page asset-page">
      <section className="history-list">
        <div className="panel-title">◎ 账号概况</div>
        <p className="subline">
          账号定位现在作为可复用 context asset，被账号诊断、热点分析和受众模拟共同引用。
        </p>
        <div className="asset-card active">
          <b>{workspaceName || '未命名工作区'}</b>
          <span>{positioning.trim() ? '已填写账号定位' : '账号定位为空'}</span>
          <small>positioningVersion: {positioningVersion}</small>
        </div>
      </section>
      <section className="history-detail">
        <div className="detail-head">
          <div>
            <h2>账号概况资产</h2>
            <p>编辑后会更新当前 workspace 的账号定位资产。</p>
          </div>
        </div>
        <label htmlFor="workspace-name">工作区名称</label>
        <input
          id="workspace-name"
          value={workspaceName}
          onChange={(event) => onWorkspaceNameChange(event.target.value)}
        />
        <label htmlFor="positioning">账号定位</label>
        <textarea
          id="positioning"
          rows={10}
          value={positioning}
          onChange={(event) => onPositioningChange(event.target.value)}
        />
        <div className="save-row">
          <button className="save-button" onClick={onSave}>
            保存账号概况
          </button>
          <SaveIndicator state={workspaceSaveState} />
          <SaveIndicator state={accountProfilesSaveState} />
        </div>
      </section>
    </div>
  )
}
