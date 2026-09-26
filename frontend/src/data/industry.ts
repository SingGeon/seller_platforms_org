// Registries give hundreds of raw industry labels ("Porcelain", "Nightclub", "Web design"...). The leads filter groups
// them into a short list of sectors a sales manager thinks in. First match wins, so the specific patterns come first.
const GROUPS: [RegExp, string][] = [
  [/bank|banc/i, 'Bănci'],
  [/insur|asigur/i, 'Asigurări'],
  [/financ|invest|asset|payment|fintech|stock exchange|credit|leasing/i, 'Servicii financiare'],
  [/airline|aviation|aerospace|airport|aviați/i, 'Aviație'],
  [/logistic|freight|shipping|courier|postal|parcel|mail|maritime|warehous|distribution/i, 'Logistică și distribuție'],
  [/rail|transport|bus |shipbuild/i, 'Transport'],
  [/telecom|mobile network|internet service|broadband/i, 'Telecomunicații'],
  [/software|information|\bit\b|\bict\b|computer|internet|cloud|cyber|\bweb\b|saas|technology|tehnolog/i, 'IT și tehnologie'],
  [/energy|energ|electric|oil|petrol|gas|utility|power|renewable|nuclear|mining|water|waste/i, 'Energie și utilități'],
  [/health|pharma|farma|hospital|medical|clinic|biotech|phyto|sănăt/i, 'Sănătate și farma'],
  [/retail|supermarket|e-commerce|marketplace|wholesale|trade|consumer|fashion|jewel|store|comerț/i, 'Retail și comerț'],
  [/agri|farm|wine|food|beverage|brew|tobacco|stimulant|băutur|alimen/i, 'Agricultură și alimentație'],
  [/real estate|property|construct|imobil|construc/i, 'Imobiliare și construcții'],
  [/hotel|ospital|horeca|travel|touris|restaurant|nightclub|betting|casino|sport|entertain|leisure/i, 'Turism și divertisment'],
  [/media|broadcast|publish|news|television|radio|film|marketing|advertis/i, 'Media și marketing'],
  [/government|public|state-owned|sector public/i, 'Sector public'],
  [/manufactur|steel|chemical|machinery|industr|engineering|metal|porcelain|press|textile|electronics|automotive|echipamente|producție/i, 'Producție și industrie'],
  [/legal|law|consult|translation|service|holding|audit|account|outsourc/i, 'Servicii profesionale'],
]

export const OTHER_INDUSTRY = 'Altele'

export function industryGroup(raw: string | null | undefined): string | null {
  if (!raw || raw === '—') return null
  for (const [re, group] of GROUPS) if (re.test(raw)) return group
  return OTHER_INDUSTRY
}
