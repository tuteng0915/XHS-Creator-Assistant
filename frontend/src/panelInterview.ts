export type InterviewMessage = {id: string; role: 'author'|'reader'; personaId: string|null; senderName: string; recipientName: string; recipientPersonaId: string|null; content: string; createdAt: string}
export type PanelInterview = {id: string; status: string; question: string; messages: InterviewMessage[]; completedReplies: number; totalReplies: number; currentParticipantName: string; error: string; elapsedSeconds: number}
async function request<T>(url: string, payload?: unknown): Promise<T> {
  const response = await fetch(url, payload === undefined ? undefined : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
  const body = await response.json()
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : '访谈暂时无法完成，请重试。')
  return body as T
}
const path = (workspaceId:string, runId:string) => `/api/workspaces/${workspaceId}/simulation-runs/${runId}/interviews`
export const panelInterviewApi = {
  list: (workspaceId:string, runId:string) => request<PanelInterview[]>(path(workspaceId,runId)),
  create: (workspaceId:string, runId:string, payload:{requestKey:string; question:string; recipientPersonaId:string|null}) => request<PanelInterview>(path(workspaceId,runId),payload),
  cancel: (workspaceId:string, runId:string, id:string) => request<PanelInterview>(`${path(workspaceId,runId)}/${id}/cancel`,{}),
}
