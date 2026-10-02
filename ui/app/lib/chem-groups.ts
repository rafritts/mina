/**
 * The only chemistry slider list (RES-125).
 *
 * Union of the retired Control pane groups and the Lab Chemistry page.
 * `crh` stays under Stress (the Chemistry page), not Other (Control).
 * `substance_p` and `vasopressin` are included; they were Lab-only before.
 * Do not mount a second slider list in a sheet or chat column.
 */
export const CHEM_EDITOR_GROUPS: { label: string; chemicals: readonly string[] }[] = [
  { label: 'Monoamines', chemicals: ['dopamine', 'serotonin', 'norepinephrine'] },
  { label: 'Bonding & social', chemicals: ['oxytocin', 'endorphins'] },
  { label: 'Stress', chemicals: ['cortisol', 'epinephrine', 'crh'] },
  { label: 'Sleep & clock', chemicals: ['adenosine', 'melatonin', 'orexin'] },
  { label: 'Other peptides', chemicals: ['anandamide', 'ghrelin', 'substance_p', 'vasopressin'] },
]

/** Flat union. Kept so a later sheet cannot quietly drop a chemical. */
export const CHEM_EDITOR_FIELDS: readonly string[] = CHEM_EDITOR_GROUPS.flatMap(
  (group) => group.chemicals,
)

/** Control's set plus the two chemicals that used to exist only on the Lab page. */
const REQUIRED_CHEMICALS = [
  'dopamine',
  'serotonin',
  'norepinephrine',
  'oxytocin',
  'endorphins',
  'cortisol',
  'epinephrine',
  'crh',
  'adenosine',
  'melatonin',
  'orexin',
  'anandamide',
  'ghrelin',
  'substance_p',
  'vasopressin',
] as const

const editorFields = new Set<string>(CHEM_EDITOR_FIELDS)
for (const name of REQUIRED_CHEMICALS) {
  if (!editorFields.has(name)) {
    throw new Error(`CHEM_EDITOR_GROUPS is missing ${name}`)
  }
}
