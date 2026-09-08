import { useCallback, useState } from 'react'

import { idleState, type SaveKey } from '../appUtils'
import type { SaveState } from '../components/StageResultViews'

export function initialSaveStates(): Record<SaveKey, SaveState> {
  return {
    workspace: idleState,
    accountProfiles: idleState,
    historical: idleState,
    comments: idleState,
    trend: idleState,
    video: idleState,
    xhs: idleState,
    manualTopic: idleState,
    topic: idleState,
    draft: idleState,
    analysisReview: idleState,
    simulationReview: idleState,
  }
}

export function useSaveStates() {
  const [saveStates, setSaveStates] =
    useState<Record<SaveKey, SaveState>>(initialSaveStates)

  const setSaveState = useCallback((key: SaveKey, state: SaveState) => {
    setSaveStates((current) => ({ ...current, [key]: state }))
  }, [])

  const resetSaveStates = useCallback(() => {
    setSaveStates(initialSaveStates())
  }, [])

  return { saveStates, setSaveState, resetSaveStates, setSaveStates }
}
