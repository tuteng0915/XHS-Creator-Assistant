import { useMemo } from 'react'

import { NEW_INPUT_ASSET_ID } from '../appUtils'
import type {
  InputAsset,
  MediaAsset,
  TextInputAsset,
  TrendCsvInputAsset,
} from '../types'
import type { XhsImportPackagePreview } from '../xhsCreatorProfile'

type Args = {
  materials: InputAsset[]
  mediaAssets: MediaAsset[]
  selectedProfileInputAssetId: string
  selectedHistoricalInputAssetId: string
  selectedCommentsInputAssetId: string
  selectedTrendInputAssetId: string
  selectedVideoInputAssetId: string
  selectedXhsCreatorProfileInputAssetId: string
  selectedVideoWorkflowMediaAssetIds: string[]
  xhsPackagePreview: XhsImportPackagePreview | null
}

export function useWorkspaceAssetSelections({
  materials,
  mediaAssets,
  selectedProfileInputAssetId,
  selectedHistoricalInputAssetId,
  selectedCommentsInputAssetId,
  selectedTrendInputAssetId,
  selectedVideoInputAssetId,
  selectedXhsCreatorProfileInputAssetId,
  selectedVideoWorkflowMediaAssetIds,
  xhsPackagePreview,
}: Args) {
  const accountProfileMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset =>
          material.type === 'account_profile',
      ),
    [materials],
  )
  const selectedProfileMaterial = useMemo(() => {
    if (selectedProfileInputAssetId === NEW_INPUT_ASSET_ID) return null
    return (
      accountProfileMaterials.find(
        (material) => material.id === selectedProfileInputAssetId,
      ) ||
      accountProfileMaterials[0] ||
      null
    )
  }, [accountProfileMaterials, selectedProfileInputAssetId])
  const historicalMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset =>
          material.type === 'historical_posts',
      ),
    [materials],
  )
  const commentsMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset => material.type === 'comments',
      ),
    [materials],
  )
  const trendMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TrendCsvInputAsset =>
          material.type === 'trend_csv',
      ),
    [materials],
  )
  const videoCreatorSamplesMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset =>
          material.type === 'video_creator_samples',
      ),
    [materials],
  )
  const xhsCreatorProfileMaterials = useMemo(
    () =>
      materials.filter(
        (material): material is TextInputAsset =>
          material.type === 'xhs_creator_profile',
      ),
    [materials],
  )
  const historicalMaterial = useMemo(() => {
    if (selectedHistoricalInputAssetId === NEW_INPUT_ASSET_ID) return undefined
    return (
      historicalMaterials.find(
        (material) => material.id === selectedHistoricalInputAssetId,
      ) ||
      historicalMaterials[0] ||
      undefined
    )
  }, [historicalMaterials, selectedHistoricalInputAssetId])
  const commentsMaterial = useMemo(() => {
    if (selectedCommentsInputAssetId === NEW_INPUT_ASSET_ID) return undefined
    return (
      commentsMaterials.find(
        (material) => material.id === selectedCommentsInputAssetId,
      ) ||
      commentsMaterials[0] ||
      undefined
    )
  }, [commentsMaterials, selectedCommentsInputAssetId])
  const videoCreatorSamplesMaterial = useMemo(() => {
    if (selectedVideoInputAssetId === NEW_INPUT_ASSET_ID) return undefined
    return (
      videoCreatorSamplesMaterials.find(
        (material) => material.id === selectedVideoInputAssetId,
      ) ||
      videoCreatorSamplesMaterials[0] ||
      undefined
    )
  }, [videoCreatorSamplesMaterials, selectedVideoInputAssetId])
  const xhsCreatorProfileMaterial = useMemo(() => {
    if (selectedXhsCreatorProfileInputAssetId === NEW_INPUT_ASSET_ID) {
      return undefined
    }
    return (
      xhsCreatorProfileMaterials.find(
        (material) => material.id === selectedXhsCreatorProfileInputAssetId,
      ) || undefined
    )
  }, [xhsCreatorProfileMaterials, selectedXhsCreatorProfileInputAssetId])
  const matchingXhsPackageMaterial = useMemo(() => {
    if (!xhsPackagePreview) return null
    const expectedName = `XHS ${xhsPackagePreview.displayName} 创作者主页`
    return (
      xhsCreatorProfileMaterials.find((material) => material.name === expectedName) ||
      null
    )
  }, [xhsCreatorProfileMaterials, xhsPackagePreview])
  const trendMaterial = useMemo(() => {
    if (selectedTrendInputAssetId === NEW_INPUT_ASSET_ID) return undefined
    return (
      trendMaterials.find((material) => material.id === selectedTrendInputAssetId) ||
      trendMaterials[0] ||
      undefined
    )
  }, [trendMaterials, selectedTrendInputAssetId])
  const videoWorkflowMediaAssets = useMemo(
    () =>
      selectedVideoWorkflowMediaAssetIds
        .map((assetId) => mediaAssets.find((asset) => asset.id === assetId))
        .filter((asset): asset is MediaAsset => Boolean(asset)),
    [mediaAssets, selectedVideoWorkflowMediaAssetIds],
  )

  return {
    accountProfileMaterials,
    selectedProfileMaterial,
    historicalMaterials,
    commentsMaterials,
    trendMaterials,
    videoCreatorSamplesMaterials,
    xhsCreatorProfileMaterials,
    historicalMaterial,
    commentsMaterial,
    videoCreatorSamplesMaterial,
    xhsCreatorProfileMaterial,
    matchingXhsPackageMaterial,
    trendMaterial,
    videoWorkflowMediaAssets,
  }
}
