import {readerAvatarModel, type ReaderAvatarModel} from './readerAvatarModel'

const headPaths: Record<ReaderAvatarModel['head'], string> = {
  oval: 'M13 20Q13 9 24 9Q35 9 35 20V23Q35 34 24 34Q13 34 13 23Z',
  rounded: 'M13 16Q13 10 19 10H29Q35 10 35 16V27Q35 34 28 34H20Q13 34 13 27Z',
  tapered: 'M13 18Q13 9 24 9Q35 9 35 18L33 27Q30 34 24 35Q18 34 15 27Z',
  narrow: 'M15 18Q15 9 24 9Q33 9 33 18V25Q33 35 24 35Q15 35 15 25Z',
  'soft-square': 'M12 19Q12 10 24 10Q36 10 36 19V25Q36 33 28 33H20Q12 33 12 25Z',
}

const hairPaths: Record<ReaderAvatarModel['hair'], string> = {
  swept: 'M12 21Q10 7 24 7Q38 7 36 18Q27 19 21 13Q18 19 12 21Z',
  crop: 'M12 18Q11 7 24 7Q37 7 36 18L32 14L27 16L21 14L16 17Z',
  curls: 'M12 19Q8 15 12 11Q11 6 17 7Q20 3 24 7Q29 3 32 8Q39 8 37 14Q39 19 34 20L31 15Q27 18 24 14Q20 18 17 14Z',
  bob: 'M11 24V17Q11 6 24 6Q37 6 37 17V25L33 20V15Q26 16 21 12Q18 17 15 18V25Z',
  parted: 'M12 21Q10 7 24 7Q38 7 36 21L32 17Q27 15 24 11Q21 15 16 17Z',
  quiff: 'M12 20Q9 12 15 10Q14 5 20 7Q24 1 30 7Q39 9 36 21L32 15Q25 18 19 14L16 20Z',
  bun: 'M12 20Q10 8 24 8Q38 8 36 20L32 17Q25 17 20 12L16 19Z',
  waves: 'M12 22Q9 12 14 10Q15 6 22 7Q30 4 35 10Q40 14 35 22L32 16Q29 19 26 15Q21 19 18 15L16 21Z',
}

const mouthPaths: Record<ReaderAvatarModel['mouth'], string> = {
  smile: 'M20.5 28Q24 32 27.5 28',
  grin: 'M20.5 27.5H27.5Q27 32 24 32Q21 32 20.5 27.5Z',
  soft: 'M21 28.5Q24 30 27 28.5',
  open: 'M22 28Q24 26.5 26 28V30Q24 32 22 30Z',
  side: 'M21 29Q25 30 27 27.5',
  small: 'M22.5 29H25.5',
}

function AvatarEyes({eyes, color}: {eyes: ReaderAvatarModel['eyes']; color: string}) {
  if (eyes === 'smile' || eyes === 'calm') {
    return <path d={eyes === 'smile' ? 'M17.5 23Q19.5 19 21.5 23M26.5 23Q28.5 19 30.5 23' : 'M18 22.5h3M27 22.5h3'} fill="none" stroke="#3d3437" strokeWidth="1.5" strokeLinecap="round" />
  }
  return <>
    <circle cx="19.5" cy="22" r={eyes === 'wide' ? 1.7 : 1.25} fill="#3d3437" />
    <circle cx="28.5" cy="22" r={eyes === 'wide' ? 1.7 : 1.25} fill="#3d3437" />
    {eyes === 'wide' && <path d="M17.5 18.5l3-.5M27.5 18l3 .5" stroke="#3d3437" strokeWidth="1.2" strokeLinecap="round" />}
    {eyes === 'round-glasses' && <g fill="none" stroke={color} strokeWidth="1.3">
      <circle cx="19.5" cy="22" r="4" /><circle cx="28.5" cy="22" r="4" />
      <path d="M23.5 21.5h1M14 21l1.5.5M32.5 21.5 34 21" />
    </g>}
    {eyes === 'square-glasses' && <g fill="none" stroke={color} strokeWidth="1.3">
      <rect x="15.5" y="19" width="8" height="6" rx="1.5" /><rect x="24.5" y="19" width="8" height="6" rx="1.5" />
      <path d="M23.5 21h1M14 20l1.5 1M32.5 21l1.5-1" />
    </g>}
  </>
}

function AvatarClothing({clothing, color}: {clothing: ReaderAvatarModel['clothing']; color: string}) {
  return <>
    <path d="M5 48Q7 34 19 34H29Q41 34 43 48Z" fill={color} />
    {clothing === 'tee' && <path d="M19 35Q24 41 29 35" fill="none" stroke="#fffaf0" strokeWidth="1.8" opacity=".9" />}
    {clothing === 'collar' && <><path d="M19 34 24 38 20 42 16 35M29 34 24 38 28 42 32 35" fill="#fffaf0" /><path d="M24 39v9" stroke="#fffaf0" strokeWidth="1.2" opacity=".7" /></>}
    {clothing === 'jacket' && <><path d="M19 34H29L27 48H21Z" fill="#fffaf0" /><path d="M17 35 20 41 18 44 21 48M31 35 28 41 30 44 27 48" fill="none" stroke="#fffaf0" strokeWidth="1.2" opacity=".7" /></>}
    {clothing === 'hoodie' && <><path d="M18 34Q13 38 17 41L24 38 31 41Q35 38 30 34" fill="none" stroke="#fffaf0" strokeWidth="1.7" opacity=".8" /><path d="M20 39v5M28 39v5" stroke="#fffaf0" strokeWidth="1.3" strokeLinecap="round" /></>}
    {clothing === 'stripes' && <path d="M11 39h26M8 44h32" stroke="#fffaf0" strokeWidth="2" opacity=".75" />}
    {clothing === 'scarf' && <><path d="M16 35Q24 40 32 35L30 39Q24 43 18 39Z" fill="#f1d5af" /><path d="M26 40h5l-1 8h-5Z" fill="#f1d5af" /></>}
  </>
}

/** Stable, composable portraits. An ID selects visual parts, not personal attributes. */
export function ReaderAvatar({id, name, size = 36}: {id: string; name: string; size?: number}) {
  const portrait = readerAvatarModel(id)
  return <svg className="reader-avatar" width={size} height={size} viewBox="0 0 48 48" role="img" aria-label={`${name}的头像`} style={{flexShrink: 0, borderRadius: size * 14 / 48}}>
    <rect width="48" height="48" rx="14" fill={portrait.background} />
    {portrait.hair === 'bob' && <path d="M11 18H37V35Q24 39 11 35Z" fill={portrait.hairColor} />}
    {portrait.hair === 'bun' && <circle cx="29" cy="8" r="5.5" fill={portrait.hairColor} />}
    <AvatarClothing clothing={portrait.clothing} color={portrait.clothingColor} />
    <path d="M20 30h8v5q-4 4-8 0Z" fill="#f3dfcf" />
    <path d={headPaths[portrait.head]} fill="#fffaf0" />
    <path d={hairPaths[portrait.hair]} fill={portrait.hairColor} />
    <AvatarEyes eyes={portrait.eyes} color={portrait.hairColor} />
    <path d={mouthPaths[portrait.mouth]} fill={portrait.mouth === 'grin' || portrait.mouth === 'open' ? '#a76d70' : 'none'} stroke="#945e65" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
