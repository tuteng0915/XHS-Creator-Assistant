/** Decorative identity only: none of these choices infer a reader's appearance. */
export const readerAvatarOptions = {
  background: ['#f6dde3', '#f7e3c9', '#efdfe5', '#f6e1d9', '#d9ede8', '#e4e9dc', '#f4e9da', '#efe4dc', '#f4d5d4', '#e9e4da'],
  hairColor: ['#3d3437', '#69453f', '#875241', '#5e5146', '#955469', '#425b50'],
  clothingColor: ['#af3f56', '#8f4f60', '#9c6240', '#4e7966', '#716355', '#b26145'],
  head: ['oval', 'rounded', 'tapered', 'narrow', 'soft-square'],
  hair: ['swept', 'crop', 'curls', 'bob', 'parted', 'quiff', 'bun', 'waves'],
  eyes: ['dots', 'wide', 'smile', 'calm', 'round-glasses', 'square-glasses'],
  mouth: ['smile', 'grin', 'soft', 'open', 'side', 'small'],
  clothing: ['tee', 'collar', 'jacket', 'hoodie', 'stripes', 'scarf'],
} as const

type AvatarOptions = typeof readerAvatarOptions
export type ReaderAvatarModel = {[K in keyof AvatarOptions]: AvatarOptions[K][number]}

/** Domain-separated hashes avoid coupling, for example, glasses to one palette. */
function avatarHash(id: string, dimension: keyof ReaderAvatarModel): number {
  const value = `${id.length}:${id}:${dimension}`
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(hash ^ value.charCodeAt(index), 16777619)
  }
  hash ^= hash >>> 16
  hash = Math.imul(hash, 0x7feb352d)
  hash ^= hash >>> 15
  hash = Math.imul(hash, 0x846ca68b)
  return (hash ^ (hash >>> 16)) >>> 0
}

export function readerAvatarModel(id: string): ReaderAvatarModel {
  function pick<K extends keyof ReaderAvatarModel>(dimension: K): ReaderAvatarModel[K] {
    const options = readerAvatarOptions[dimension]
    // The selected array and return type share the same dimension key.
    return options[avatarHash(id, dimension) % options.length] as ReaderAvatarModel[K]
  }
  return {
    background: pick('background'),
    hairColor: pick('hairColor'),
    clothingColor: pick('clothingColor'),
    head: pick('head'),
    hair: pick('hair'),
    eyes: pick('eyes'),
    mouth: pick('mouth'),
    clothing: pick('clothing'),
  }
}
