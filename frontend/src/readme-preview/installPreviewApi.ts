import * as api from '../api'
import { contentCollaborationApi } from '../contentCollaboration'
import { creatorDraftKey } from '../creatorDraftCache'
import { panelInterviewApi } from '../panelInterview'
import { accountRun, audienceRun, profile, session, simulation, topic, workspace } from './fixtures'

/** Isolated preview entry only. Unknown calls always fail; there is no backend fallback. */
export function installPreviewApi() {
  const blocked = async (): Promise<never> => { throw new Error('界面演示不连接后端，也不调用模型。') }
  window.fetch = blocked
  for (const group of [...Object.values(api), contentCollaborationApi, panelInterviewApi]) {
    if (!group || typeof group !== 'object') continue
    for (const key of Object.keys(group)) {
      if (typeof Reflect.get(group, key) === 'function') Reflect.set(group, key, blocked)
    }
  }
  // Clear only this fixture's cache so screenshots cannot pick up an edited demo draft.
  for (const kind of ['draft', 'message'] as const) window.sessionStorage.removeItem(creatorDraftKey(kind, workspace.id, topic.id))
  let savedTopic = structuredClone(topic)
  api.agentConversationApi.list = async () => []
  api.analysisRunApi.list = async () => [structuredClone(accountRun)]
  api.analysisRunApi.get = async () => structuredClone(accountRun)
  api.audienceAnalysisApi.list = async () => [structuredClone(audienceRun)]
  api.audienceAnalysisApi.get = async () => structuredClone(audienceRun)
  api.inputAssetApi.get = async () => structuredClone(profile)
  api.topicApi.get = async () => structuredClone(savedTopic)
  api.topicApi.update = async (_id, patch) => {
    savedTopic = { ...savedTopic, ...patch, updatedAt: new Date(Date.parse(savedTopic.updatedAt) + 1000).toISOString() }
    return structuredClone(savedTopic)
  }
  api.simulationRunApi.get = async () => structuredClone(simulation)
  api.panelEditApi.list = async () => []
  contentCollaborationApi.list = async () => [structuredClone(session)]
  contentCollaborationApi.get = async () => structuredClone(session)
  panelInterviewApi.list = async () => []
}
