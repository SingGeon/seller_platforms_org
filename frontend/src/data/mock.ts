import type { Company, Service, SignalQuestion, SourceStatus } from './types'

const ago = (hours: number) => new Date(Date.now() - hours * 3600_000).toISOString()

export const SERVICES: Service[] = [
  { id: 'automation', name: 'Automatizare cu agenți AI', short: 'Automatizare' },
  { id: 'cyber', name: 'Securitate cibernetică', short: 'Cyber' },
  { id: 'digital', name: 'Transformare digitală', short: 'Digital' },
]

export const QUESTIONS: SignalQuestion[] = [
  { id: 'q1', service: 'automation', weight: 'high', polarity: 'positive', active: true, text: 'Compania angajează RPA developers, automation engineers, specialiști AI sau roluri de process excellence?' },
  { id: 'q2', service: 'automation', weight: 'medium', polarity: 'positive', active: true, text: 'Compania menționează optimizarea proceselor, reducerea costurilor sau eficiența operațională?' },
  { id: 'q3', service: 'automation', weight: 'medium', polarity: 'positive', active: true, text: 'Compania folosește sau caută platforme de automatizare (UiPath, Power Automate, Celonis)?' },
  { id: 'q4', service: 'cyber', weight: 'high', polarity: 'positive', active: true, text: 'Compania a avut recent un incident de securitate sau o scurgere de date?' },
  { id: 'q5', service: 'cyber', weight: 'high', polarity: 'positive', active: true, text: 'Compania angajează roluri de securitate (CISO, SOC analyst, security engineer)?' },
  { id: 'q6', service: 'cyber', weight: 'medium', polarity: 'positive', active: true, text: 'Compania are cerințe noi de conformitate (NIS2, DORA, GDPR, ISO 27001)?' },
  { id: 'q7', service: 'digital', weight: 'high', polarity: 'positive', active: true, text: 'Compania are o inițiativă de transformare digitală, implementare ERP sau migrare în cloud?' },
  { id: 'q8', service: 'digital', weight: 'medium', polarity: 'positive', active: true, text: 'A existat o schimbare recentă în conducere (CEO, CIO, CTO, CISO)?' },
  { id: 'q9', service: 'digital', weight: 'low', polarity: 'positive', active: true, text: 'Compania a primit o finanțare nouă sau a anunțat o achiziție?' },
  { id: 'n1', service: null, weight: 'high', polarity: 'negative', active: true, text: 'Compania este un concurent direct (furnizor de servicii IT sau telecom)?' },
  { id: 'n2', service: null, weight: 'high', polarity: 'negative', active: true, text: 'Compania vinde exclusiv către consumatori (B2C)?' },
  { id: 'n3', service: null, weight: 'medium', polarity: 'negative', active: true, text: 'Compania are sub 20 de angajați?' },
]

export const COMPANIES: Company[] = [
  {
    id: 'carpathia-bank', name: 'Carpathia Bank', domain: 'carpathiabank.example', industry: 'Servicii bancare', country: 'RO', countryName: 'România', employees: '2.400',
    stage: 'nou', owner: null, score: 91, prevScore: 78, serviceScores: { automation: 88, cyber: 64, digital: 55 },
    whyNow: 'Banca a deschis 4 posturi de automatizare într-o singură săptămână și a anunțat public un program de reducere a costurilor operaționale cu 15% până în 2027. Combinația dintre buget declarat și echipă în construcție indică o fereastră de cumpărare pentru Agentic Process Automation.',
    firstSeen: ago(30), updatedAt: ago(2),
    signals: [
      { id: 's1', questionId: 'q1', service: 'automation', title: 'Angajează „Head of Intelligent Automation” și 3 RPA developers', quote: 'We are looking for a Head of Intelligent Automation to scale our RPA and AI agent programme across retail banking operations.', source: 'Greenhouse (pagina de cariere)', sourceType: 'job', url: 'https://boards.greenhouse.io/carpathiabank', date: ago(2), confidence: 0.96, points: 28 },
      { id: 's2', questionId: 'q2', service: 'automation', title: 'Program de reducere a costurilor operaționale cu 15%', quote: 'Banca își propune reducerea costurilor operaționale cu 15% până în 2027, prin digitalizarea și automatizarea proceselor de back-office.', source: 'Google News', sourceType: 'news', url: 'https://news.example/carpathia-costuri', date: ago(20), confidence: 0.88, points: 18 },
      { id: 's3', questionId: 'q3', service: 'automation', title: 'Cerință UiPath în anunțul de angajare', quote: 'Experience with UiPath or Microsoft Power Automate in a regulated environment is required.', source: 'Greenhouse (pagina de cariere)', sourceType: 'job', url: 'https://boards.greenhouse.io/carpathiabank/jobs/rpa', date: ago(2), confidence: 0.92, points: 12 },
      { id: 's4', questionId: 'q6', service: 'cyber', title: 'Pregătire pentru conformitatea DORA', quote: 'În raportul semestrial, banca menționează proiectul de aliniere la regulamentul DORA până la finalul anului.', source: 'Site companie — rapoarte', sourceType: 'website', url: 'https://carpathiabank.example/investitori', date: ago(160), confidence: 0.74, points: 9 },
    ],
  },
  {
    id: 'medispro', name: 'MedisPro Clinics', domain: 'medispro.example', industry: 'Sănătate privată', country: 'MD', countryName: 'Moldova', employees: '650',
    stage: 'nou', owner: 'Ana Rusu', score: 88, prevScore: 52, serviceScores: { automation: 22, cyber: 94, digital: 40 },
    whyNow: 'Rețeaua de clinici apare pe lista victimelor unui atac ransomware de acum 3 zile, iar a doua zi a publicat un anunț pentru un Security Engineer. Au nevoie de răspuns la incident și de o evaluare de securitate acum, nu peste un trimestru.',
    firstSeen: ago(70), updatedAt: ago(5),
    signals: [
      { id: 's5', questionId: 'q4', service: 'cyber', title: 'Listată ca victimă ransomware', quote: 'Victim: MedisPro Clinics · Sector: Healthcare · Country: MD · Data size: 180 GB', source: 'ransomware.live', sourceType: 'breach', url: 'https://www.ransomware.live/', date: ago(70), confidence: 0.9, points: 34 },
      { id: 's6', questionId: 'q5', service: 'cyber', title: 'Angajează Security Engineer (urgent)', quote: 'Căutăm un Security Engineer pentru consolidarea infrastructurii după incidentul recent. Angajare imediată.', source: 'Site companie — cariere', sourceType: 'job', url: 'https://medispro.example/cariere', date: ago(46), confidence: 0.93, points: 24 },
      { id: 's7', questionId: 'q6', service: 'cyber', title: 'Date medicale — obligații GDPR', quote: 'Clinica prelucrează date medicale ale pacienților și a notificat autoritatea de protecție a datelor.', source: 'Google News', sourceType: 'news', url: 'https://news.example/medispro', date: ago(30), confidence: 0.71, points: 10 },
    ],
  },
  {
    id: 'quanta-fintech', name: 'Quanta Fintech', domain: 'quanta.example', industry: 'Fintech', country: 'RO', countryName: 'România', employees: '310',
    stage: 'calificat', owner: 'Mihai Ceban', score: 86, prevScore: 81, serviceScores: { automation: 70, cyber: 58, digital: 84 },
    whyNow: 'Runda Series B de 22 mil. EUR anunțată săptămâna trecută finanțează explicit „automatizarea operațiunilor și AI”. Angajează în paralel 2 ML engineers — echipa internă nu va acoperi singură tot planul.',
    firstSeen: ago(400), updatedAt: ago(9),
    signals: [
      { id: 's8', questionId: 'q9', service: 'digital', title: 'Finanțare Series B — 22 mil. EUR', quote: 'Quanta Fintech closes €22M Series B to expand AI-driven operations and automate onboarding.', source: 'PR Newswire', sourceType: 'press', url: 'https://www.prnewswire.com/', date: ago(150), confidence: 0.98, points: 10 },
      { id: 's9', questionId: 'q7', service: 'digital', title: 'Plan de modernizare a platformei', quote: 'Fondurile vor fi folosite pentru migrarea platformei în cloud și automatizarea operațiunilor.', source: 'PR Newswire', sourceType: 'press', url: 'https://www.prnewswire.com/', date: ago(150), confidence: 0.9, points: 20 },
      { id: 's10', questionId: 'q1', service: 'automation', title: 'Angajează 2 Machine Learning Engineers', quote: 'Join us as a Machine Learning Engineer to build AI agents that automate KYC and onboarding workflows.', source: 'Lever (pagina de cariere)', sourceType: 'job', url: 'https://jobs.lever.co/quanta', date: ago(9), confidence: 0.91, points: 22 },
    ],
  },
  {
    id: 'nordvik', name: 'Nordvik Logistics', domain: 'nordvik.example', industry: 'Logistică', country: 'PL', countryName: 'Polonia', employees: '1.100',
    stage: 'contactat', owner: 'Ana Rusu', score: 84, prevScore: 84, serviceScores: { automation: 86, cyber: 30, digital: 61 },
    whyNow: 'Trei anunțuri pentru RPA developers în depozitele din Łódź și Poznań, plus un proiect de digitalizare a depozitelor anunțat în presă. Automatizarea e deja pe agenda operațională.',
    firstSeen: ago(500), updatedAt: ago(26),
    signals: [
      { id: 's11', questionId: 'q1', service: 'automation', title: '3 posturi RPA Developer', quote: 'RPA Developer (UiPath) — warehouse operations automation, Łódź.', source: 'Arbeitnow', sourceType: 'job', url: 'https://www.arbeitnow.com/', date: ago(26), confidence: 0.95, points: 27 },
      { id: 's12', questionId: 'q7', service: 'digital', title: 'Digitalizarea rețelei de depozite', quote: 'Nordvik invests in warehouse digitalisation across its Polish network.', source: 'GDELT', sourceType: 'news', url: 'https://news.example/nordvik', date: ago(90), confidence: 0.82, points: 16 },
    ],
  },
  {
    id: 'danubius', name: 'Danubius Energy', domain: 'danubius.example', industry: 'Energie', country: 'RO', countryName: 'România', employees: '3.800',
    stage: 'nou', owner: null, score: 81, prevScore: 70, serviceScores: { automation: 35, cyber: 86, digital: 48 },
    whyNow: 'Ca operator de energie intră sub NIS2 și a lansat o licitație pentru audit de securitate. Angajează și un CISO — bugetul de securitate e în curs de alocare.',
    firstSeen: ago(60), updatedAt: ago(12),
    signals: [
      { id: 's13', questionId: 'q6', service: 'cyber', title: 'Licitație: audit de securitate NIS2', quote: 'Servicii de audit de securitate informatică și conformitate NIS2 pentru infrastructura OT/IT.', source: 'TED (licitații UE)', sourceType: 'tender', url: 'https://ted.europa.eu/', date: ago(60), confidence: 0.97, points: 22 },
      { id: 's14', questionId: 'q5', service: 'cyber', title: 'Angajează Chief Information Security Officer', quote: 'Danubius Energy recrutează un CISO care să conducă programul de conformitate NIS2.', source: 'The Muse', sourceType: 'job', url: 'https://www.themuse.com/', date: ago(12), confidence: 0.9, points: 24 },
    ],
  },
  {
    id: 'brightline', name: 'Brightline Software', domain: 'brightline.example', industry: 'SaaS B2B', country: 'US', countryName: 'SUA', employees: '900',
    stage: 'calificat', owner: 'Mihai Ceban', score: 79, prevScore: 66, serviceScores: { automation: 40, cyber: 80, digital: 62 },
    whyNow: 'Au raportat la SEC numirea unui nou CISO (Item 5.02) și angajează 3 SOC analysts. Un CISO nou își construiește echipa și furnizorii în primele 90 de zile.',
    firstSeen: ago(200), updatedAt: ago(30),
    signals: [
      { id: 's15', questionId: 'q8', service: 'digital', title: 'CISO nou — raportare SEC 8-K Item 5.02', quote: 'Item 5.02 — Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers.', source: 'SEC EDGAR', sourceType: 'filing', url: 'https://www.sec.gov/edgar/search/', date: ago(200), confidence: 0.99, points: 14 },
      { id: 's16', questionId: 'q5', service: 'cyber', title: 'Angajează 3 SOC Analysts', quote: 'SOC Analyst (Tier 2) — help us build our 24/7 security operations centre.', source: 'Ashby (pagina de cariere)', sourceType: 'job', url: 'https://jobs.ashbyhq.com/brightline', date: ago(30), confidence: 0.94, points: 24 },
    ],
  },
  {
    id: 'agrovia', name: 'Agrovia Group', domain: 'agrovia.example', industry: 'Agribusiness', country: 'MD', countryName: 'Moldova', employees: '480',
    stage: 'nou', owner: null, score: 76, prevScore: 76, serviceScores: { automation: 45, cyber: 20, digital: 79 },
    whyNow: 'Grupul a publicat pe MTender o achiziție pentru implementarea unui sistem ERP și digitalizarea gestiunii stocurilor — proiect cu termen de depunere în 12 zile.',
    firstSeen: ago(100), updatedAt: ago(100),
    signals: [
      { id: 's17', questionId: 'q7', service: 'digital', title: 'Achiziție: implementare ERP', quote: 'Servicii de implementare a unui sistem ERP și digitalizarea evidenței stocurilor.', source: 'MTender', sourceType: 'tender', url: 'https://mtender.gov.md/', date: ago(100), confidence: 0.95, points: 26 },
    ],
  },
  {
    id: 'aurelia', name: 'Aurelia Pharma', domain: 'aurelia.example', industry: 'Farmaceutic', country: 'RO', countryName: 'România', employees: '1.250',
    stage: 'negociere', owner: 'Ana Rusu', score: 74, prevScore: 77, serviceScores: { automation: 52, cyber: 71, digital: 44 },
    whyNow: 'Amendă GDPR primită în august pentru măsuri tehnice insuficiente. Compania trebuie să demonstreze remedieri autorității — oportunitate pentru evaluare și servicii gestionate de securitate.',
    firstSeen: ago(900), updatedAt: ago(48),
    signals: [
      { id: 's18', questionId: 'q4', service: 'cyber', title: 'Amendă GDPR — măsuri tehnice insuficiente', quote: 'Autoritatea a aplicat o amendă pentru lipsa măsurilor tehnice și organizatorice adecvate (art. 32 GDPR).', source: 'GDPR Enforcement Tracker', sourceType: 'registry', url: 'https://enforcementtracker.com/', date: ago(720), confidence: 0.86, points: 20 },
      { id: 's19', questionId: 'q2', service: 'automation', title: 'Eficientizarea lanțului de aprovizionare', quote: 'Our 2026 priorities include operational efficiency in supply chain and quality processes.', source: 'Site companie — rapoarte', sourceType: 'website', url: 'https://aurelia.example/raport-anual', date: ago(48), confidence: 0.7, points: 10 },
    ],
  },
  {
    id: 'vetra', name: 'Vetra Insurance', domain: 'vetra.example', industry: 'Asigurări', country: 'RO', countryName: 'România', employees: '870',
    stage: 'contactat', owner: 'Mihai Ceban', score: 72, prevScore: 69, serviceScores: { automation: 74, cyber: 45, digital: 58 },
    whyNow: 'Noul COO a declarat într-un interviu că vrea să reducă timpul de procesare a daunelor la jumătate. Procesarea daunelor e un caz clasic pentru agenți AI.',
    firstSeen: ago(300), updatedAt: ago(70),
    signals: [
      { id: 's20', questionId: 'q8', service: 'digital', title: 'COO nou numit', quote: 'Vetra Insurance anunță numirea unui nou Chief Operating Officer.', source: 'GlobeNewswire', sourceType: 'press', url: 'https://www.globenewswire.com/', date: ago(300), confidence: 0.95, points: 12 },
      { id: 's21', questionId: 'q2', service: 'automation', title: '„Timpul de procesare a daunelor, redus la jumătate”', quote: 'Obiectivul nostru este să reducem la jumătate timpul de procesare a daunelor până anul viitor.', source: 'Google News', sourceType: 'news', url: 'https://news.example/vetra', date: ago(70), confidence: 0.87, points: 18 },
    ],
  },
  {
    id: 'helix', name: 'Helix Retail', domain: 'helix.example', industry: 'Retail B2B', country: 'DE', countryName: 'Germania', employees: '5.200',
    stage: 'nou', owner: null, score: 69, prevScore: 69, serviceScores: { automation: 71, cyber: 38, digital: 50 },
    whyNow: 'Angajează un Process Mining Analyst cu experiență Celonis — primul pas tipic înainte de un program de automatizare.',
    firstSeen: ago(120), updatedAt: ago(120),
    signals: [
      { id: 's22', questionId: 'q3', service: 'automation', title: 'Angajează Process Mining Analyst (Celonis)', quote: 'Process Mining Analyst (Celonis) to identify automation opportunities in procurement.', source: 'Arbeitnow', sourceType: 'job', url: 'https://www.arbeitnow.com/', date: ago(120), confidence: 0.9, points: 16 },
    ],
  },
  {
    id: 'terranova', name: 'Terranova Construct', domain: 'terranova.example', industry: 'Construcții', country: 'MD', countryName: 'Moldova', employees: '350',
    stage: 'contactat', owner: 'Ana Rusu', score: 63, prevScore: 60, serviceScores: { automation: 30, cyber: 18, digital: 66 },
    whyNow: 'Caută un ERP Implementation Lead — proiectul de digitalizare e aprobat intern, dar încă nu au partener de implementare.',
    firstSeen: ago(600), updatedAt: ago(96),
    signals: [
      { id: 's23', questionId: 'q7', service: 'digital', title: 'Angajează ERP Implementation Lead', quote: 'Căutăm un ERP Implementation Lead pentru proiectul de digitalizare a companiei.', source: 'Site companie — cariere', sourceType: 'job', url: 'https://terranova.example/cariere', date: ago(96), confidence: 0.88, points: 18 },
    ],
  },
  {
    id: 'codru', name: 'Codru Beverages', domain: 'codru.example', industry: 'Producție băuturi', country: 'MD', countryName: 'Moldova', employees: '420',
    stage: 'negociere', owner: 'Mihai Ceban', score: 58, prevScore: 58, serviceScores: { automation: 60, cyber: 25, digital: 41 },
    whyNow: 'Raportul anual menționează „automatizarea proceselor administrative” ca prioritate pentru 2027.',
    firstSeen: ago(1200), updatedAt: ago(200),
    signals: [
      { id: 's24', questionId: 'q2', service: 'automation', title: 'Automatizarea proceselor administrative — prioritate 2027', quote: 'Una dintre prioritățile pentru 2027 este automatizarea proceselor administrative și financiare.', source: 'Site companie — rapoarte', sourceType: 'website', url: 'https://codru.example/raport', date: ago(200), confidence: 0.78, points: 14 },
    ],
  },
  {
    id: 'moldagrotech', name: 'Moldagrotech', domain: 'moldagrotech.example', industry: 'Echipamente agricole', country: 'MD', countryName: 'Moldova', employees: '85',
    stage: 'nou', owner: null, score: 38, prevScore: 38, serviceScores: { automation: 36, cyber: 12, digital: 30 },
    whyNow: 'Semnal slab: o singură mențiune despre digitalizarea vânzărilor. De urmărit, nu de contactat încă.',
    firstSeen: ago(40), updatedAt: ago(40),
    signals: [
      { id: 's25', questionId: 'q7', service: 'digital', title: 'Mențiune despre digitalizarea vânzărilor', quote: 'Compania intenționează să-și digitalizeze procesul de vânzări către dealeri.', source: 'Google News', sourceType: 'news', url: 'https://news.example/moldagrotech', date: ago(40), confidence: 0.62, points: 8 },
    ],
  },
  {
    id: 'stellar', name: 'Stellar Hotels', domain: 'stellarhotels.example', industry: 'Ospitalitate', country: 'RO', countryName: 'România', employees: '1.600',
    stage: 'descalificat', owner: null, score: 22, prevScore: 61, serviceScores: { automation: 48, cyber: 30, digital: 35 },
    whyNow: 'Descalificat automat: regula „doar B2B” — compania vinde exclusiv către consumatori.',
    firstSeen: ago(300), updatedAt: ago(15),
    signals: [
      { id: 's26', questionId: 'q1', service: 'automation', title: 'Angajează Automation Specialist', quote: 'Automation Specialist for our booking and guest-service processes.', source: 'Jobicy', sourceType: 'job', url: 'https://jobicy.com/', date: ago(15), confidence: 0.85, points: 20 },
      { id: 's27', questionId: 'n2', service: null, title: 'Model de business B2C', quote: 'Lanț de hoteluri care vinde direct către turiști (B2C).', source: 'Wikidata', sourceType: 'registry', url: 'https://www.wikidata.org/', date: ago(15), confidence: 0.9, points: -39 },
    ],
  },
  {
    id: 'lumen', name: 'Lumen Telecom Services', domain: 'lumentelecom.example', industry: 'Telecom și IT', country: 'MD', countryName: 'Moldova', employees: '700',
    stage: 'descalificat', owner: null, score: 0, prevScore: 67, serviceScores: { automation: 60, cyber: 55, digital: 70 },
    whyNow: 'Descalificat automat: concurent direct (furnizor de servicii IT și telecom).',
    firstSeen: ago(500), updatedAt: ago(20),
    signals: [
      { id: 's28', questionId: 'n1', service: null, title: 'Concurent direct', quote: 'Furnizor de servicii de integrare IT și telecomunicații pentru companii.', source: 'GLEIF + site companie', sourceType: 'registry', url: 'https://www.gleif.org/', date: ago(20), confidence: 0.95, points: -67 },
    ],
  },
]

export const SOURCES: SourceStatus[] = [
  { id: 'greenhouse', name: 'Greenhouse / Lever / Ashby', category: 'Joburi', tier: 'snapshot', lastRun: ago(0.6), status: 'ok', newItems: 14 },
  { id: 'arbeitnow', name: 'Arbeitnow', category: 'Joburi', tier: 'snapshot', lastRun: ago(1.2), status: 'ok', newItems: 38 },
  { id: 'themuse', name: 'The Muse', category: 'Joburi', tier: 'incremental', lastRun: ago(0.8), status: 'ok', newItems: 22 },
  { id: 'google-news', name: 'Google News RSS', category: 'Știri', tier: 'rss', lastRun: ago(0.1), status: 'ok', newItems: 57 },
  { id: 'gdelt', name: 'GDELT', category: 'Știri', tier: 'incremental', lastRun: ago(1.5), status: 'warn', newItems: 0, note: 'Limită de request-uri (429) — reîncercare automată' },
  { id: 'prnewswire', name: 'PR Newswire / GlobeNewswire', category: 'Comunicate', tier: 'rss', lastRun: ago(0.2), status: 'ok', newItems: 9 },
  { id: 'ted', name: 'TED — licitații UE', category: 'Licitații', tier: 'incremental', lastRun: ago(0.9), status: 'ok', newItems: 41 },
  { id: 'mtender', name: 'MTender — Moldova', category: 'Licitații', tier: 'incremental', lastRun: ago(0.9), status: 'ok', newItems: 6 },
  { id: 'sec', name: 'SEC EDGAR (8-K, Form D)', category: 'Raportări oficiale', tier: 'rss', lastRun: ago(0.15), status: 'ok', newItems: 12 },
  { id: 'wikimedia', name: 'Wikimedia EventStreams', category: 'Raportări oficiale', tier: 'stream', lastRun: ago(0.01), status: 'ok', newItems: 3 },
  { id: 'ransomware', name: 'ransomware.live', category: 'Cyber', tier: 'rss', lastRun: ago(0.25), status: 'ok', newItems: 4 },
  { id: 'hibp', name: 'Have I Been Pwned', category: 'Cyber', tier: 'rss', lastRun: ago(0.25), status: 'ok', newItems: 1 },
  { id: 'gleif', name: 'GLEIF / Wikidata', category: 'Date firme', tier: 'daily', lastRun: ago(7), status: 'ok', newItems: 120 },
  { id: 'crtsh', name: 'crt.sh (certificate)', category: 'Tech', tier: 'daily', lastRun: ago(7), status: 'error', newItems: 0, note: 'Serviciul a răspuns 502' },
]
