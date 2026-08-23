import type { TextInputAsset } from './types'

export type XhsCreatorProfileSummary = {
  displayName: string
  noteCount: number
  commentCount: number
  coverReferenceCount: number
  topNotes: Array<{
    noteId: string
    title: string
    liked: number | null
    collected: number | null
    comments: number | null
    shares: number | null
  }>
  warnings: string[]
}

export type XhsImportPackagePreview = XhsCreatorProfileSummary & {
  profileFileName: string
  selectedFileCount: number
  imageFileCount: number
  matchedCoverFileCount: number
  missingCoverCount: number
}

const IMAGE_FILE_PATTERN = /\.(jpe?g|png|webp)$/i

export function summarizeXhsCreatorProfileContent(
  content: string,
): XhsCreatorProfileSummary | null {
  try {
    return summarizeXhsCreatorProfile(JSON.parse(content))
  } catch {
    return null
  }
}

export function summarizeXhsCreatorProfile(
  raw: unknown,
): XhsCreatorProfileSummary | null {
  if (!raw || typeof raw !== 'object') return null
  const profile = raw as {
    schemaVersion?: unknown
    creator?: { displayName?: unknown }
    notes?: unknown
    warnings?: unknown
  }
  if (profile.schemaVersion !== 'xhs-creator-profile/v1') return null
  const notes = Array.isArray(profile.notes)
    ? profile.notes.filter((note): note is Record<string, unknown> =>
        Boolean(note && typeof note === 'object'),
      )
    : []
  const displayName = cleanText(profile.creator?.displayName) || '未知账号'
  const topNotes = [...notes]
    .map((note) => ({
      noteId: cleanText(note.noteId),
      title: cleanText(note.title) || '未命名笔记',
      liked: toNumber((note.metrics as Record<string, unknown> | undefined)?.liked),
      collected: toNumber(
        (note.metrics as Record<string, unknown> | undefined)?.collected,
      ),
      comments: toNumber(
        (note.metrics as Record<string, unknown> | undefined)?.comments,
      ),
      shares: toNumber((note.metrics as Record<string, unknown> | undefined)?.shares),
    }))
    .sort((left, right) => engagementScore(right) - engagementScore(left))
    .slice(0, 5)
  return {
    displayName,
    noteCount: notes.length,
    commentCount: notes.reduce((total, note) => {
      const comments = note.comments
      return total + (Array.isArray(comments) ? comments.length : 0)
    }, 0),
    coverReferenceCount: notes.filter((note) => coverRelativePath(note)).length,
    topNotes,
    warnings: Array.isArray(profile.warnings)
      ? profile.warnings.map(cleanText).filter(Boolean)
      : [],
  }
}

export async function previewXhsImportPackage(
  files: File[],
): Promise<XhsImportPackagePreview | null> {
  if (files.length === 0) return null
  const profileFile = findXhsProfileFile(files)
  if (!profileFile) return null
  const raw = JSON.parse(await readFileText(profileFile))
  const summary = summarizeXhsCreatorProfile(raw)
  if (!summary) return null
  const selectedPaths = new Set(xhsPackageRelativePaths(files))
  const imageFileCount = files.filter((file) =>
    IMAGE_FILE_PATTERN.test(packageRelativePathForFile(file, files)),
  ).length
  const notes = Array.isArray((raw as { notes?: unknown }).notes)
    ? ((raw as { notes: unknown[] }).notes.filter(
        (note): note is Record<string, unknown> =>
          Boolean(note && typeof note === 'object'),
      ) ?? [])
    : []
  const coverPaths = notes.map(coverRelativePath).filter(Boolean)
  const matchedCoverFileCount = coverPaths.filter((path) =>
    selectedPaths.has(path),
  ).length
  return {
    ...summary,
    profileFileName: profileFile.name,
    selectedFileCount: files.length,
    imageFileCount,
    matchedCoverFileCount,
    missingCoverCount: Math.max(coverPaths.length - matchedCoverFileCount, 0),
  }
}

export function xhsCreatorProfileSummaryFromAsset(
  asset?: TextInputAsset,
): XhsCreatorProfileSummary | null {
  if (!asset || asset.type !== 'xhs_creator_profile') return null
  return summarizeXhsCreatorProfileContent(asset.content)
}

export function xhsPackageRelativePaths(files: File[]): string[] {
  const rawPaths = files.map(fileRelativePath)
  const commonPrefix = commonTopLevelDirectory(rawPaths)
  return rawPaths.map((path) =>
    commonPrefix && path.startsWith(`${commonPrefix}/`)
      ? path.slice(commonPrefix.length + 1)
      : path,
  )
}

export function packageRelativePathForFile(file: File, files: File[]): string {
  const index = files.indexOf(file)
  return xhsPackageRelativePaths(files)[index] || file.name
}

function findXhsProfileFile(files: File[]): File | null {
  return (
    files.find((file) =>
      /(^|\/)(xhs_creator_profile|profile)\.json$/i.test(
        packageRelativePathForFile(file, files),
      ),
    ) ||
    files.find((file) =>
      packageRelativePathForFile(file, files).toLowerCase().endsWith('.json'),
    ) ||
    null
  )
}

function coverRelativePath(note: Record<string, unknown>): string {
  const cover = note.cover
  if (cover && typeof cover === 'object') {
    return cleanText(
      (cover as { relativePath?: unknown; relative_path?: unknown }).relativePath ||
        (cover as { relative_path?: unknown }).relative_path,
    )
  }
  return cleanText(note.coverRelativePath || note.cover_relative_path || note.coverPath)
}

function fileRelativePath(file: File): string {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
}

function commonTopLevelDirectory(paths: string[]): string {
  const parts = paths
    .map((path) => path.split('/').filter(Boolean))
    .filter((parts) => parts.length > 1)
  if (parts.length !== paths.length) return ''
  const first = parts[0]?.[0] || ''
  return first && parts.every((pathParts) => pathParts[0] === first) ? first : ''
}

function cleanText(value: unknown): string {
  return String(value || '').replace(/\u200b/g, '').trim()
}

async function readFileText(file: File): Promise<string> {
  if ('text' in file && typeof file.text === 'function') {
    return file.text()
  }
  return new Response(file).text()
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(String(value).replace(/,/g, ''))
  return Number.isFinite(numeric) ? numeric : null
}

function engagementScore(note: {
  liked: number | null
  collected: number | null
  comments: number | null
  shares: number | null
}): number {
  return (
    (note.liked || 0) +
    (note.collected || 0) +
    (note.comments || 0) +
    (note.shares || 0)
  )
}
