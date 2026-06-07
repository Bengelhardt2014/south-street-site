// Source of truth for the History page timeline. Eras are listed in
// chronological order. Year ranges are first-pass values and will be fine-tuned
// against the vibrancy chart; `summary` and `beats` are intentionally empty here
// and get filled in a later step.

export type EraPhase = 'prologue' | 'collapse' | 'reinvention' | 'commercialization';

/** A narrative beat within an era. */
export interface EraBeat {
  text: string;
}

export interface Era {
  /** url-safe slug */
  id: string;
  /** short display name; matches the vibrancy chart band names */
  name: string;
  /** longer chapter title, for later use */
  title?: string;
  yearStart: number;
  yearEnd: number;
  /** true for an era still in progress */
  ongoing?: boolean;
  /** 0 = prologue, 1 = first cycle, 2 = second cycle */
  cycle: 0 | 1 | 2;
  phase: EraPhase;
  /** band accent color */
  color: string;
  /** one-line summary — filled in a later step */
  summary: string;
  /** narrative beats — filled in a later step */
  beats: EraBeat[];
}

export const eras: Era[] = [
  // ---- Prologue (cycle 0): deep history, the muted "before" ----
  {
    id: 'citys-edge',
    name: "The City's Edge",
    title: "The City's Edge",
    yearStart: 1682,
    yearEnd: 1854,
    cycle: 0,
    phase: 'prologue',
    color: '#B7AC9A',
    summary:
      "South Street began as the southern edge of William Penn's 1682 city plan. From the start, the uses Quaker Philadelphia would not allow inside its limits clustered just across the line.",
    beats: [
      { text: "The New Market sheds opened at Second Street in 1744, the start of the corridor's market trade." },
      { text: 'The Southwark Theatre opened just south of the line in 1766, after the city banned live performance inside its limits.' },
      { text: 'The market reached South Street by 1797, and the brick Head House followed in 1804 and 1805.' },
      { text: 'Crossing the street meant crossing police jurisdictions, which kept gray-market trade alive until the city consolidated in 1854.' },
    ],
  },
  {
    id: 'immigrant-corridor',
    name: 'Immigrant Corridor',
    title: 'The Immigrant Retail Corridor',
    yearStart: 1854,
    yearEnd: 1929,
    cycle: 0,
    phase: 'prologue',
    color: '#A99B85',
    summary:
      'After the city consolidated in 1854, two corridors hardened along South Street over the next seventy years, one Jewish and one Black, both drawing shoppers from across the city.',
    beats: [
      { text: "The eastern blocks became Philadelphia's Jewish garment and household-goods district, anchored by Fabric Row and its synagogues." },
      { text: "The western blocks, part of W.E.B. Du Bois's Seventh Ward, grew into one of the city's leading Black commercial districts." },
      { text: "The Royal Theater anchored the corridor's Black entertainment scene after 1920." },
      { text: 'Throughout, South Street pulled customers from well beyond the adjacent blocks, a pattern that would define it for the next century.' },
    ],
  },
  {
    id: 'working-main-street',
    name: 'Working Main Street',
    title: 'Working Main Street',
    yearStart: 1929,
    yearEnd: 1954,
    cycle: 0,
    phase: 'prologue',
    color: '#97876F',
    summary:
      'By the postwar years South Street was a thriving everyday main street, even as planners began drawing the highway that would target it.',
    beats: [
      { text: 'In the 1930s, city planners sketched a ring road of highways around Center City, with a southern crosstown route they would later settle on South Street.' },
      { text: 'The Foremost kosher butchery opened just off the corridor on South 4th Street in 1945 and ran for decades.' },
      { text: 'A 1949 inventory found the eastern blocks thriving, with stores like Tri-plex Shoes and L. Dubrow & Sons furniture.' },
      { text: "The corridor stayed the place where the region's Jewish families planned weddings and bar mitzvahs, right up to the highway era." },
    ],
  },
  // ---- Modern arc (cycles 1 & 2) ----
  {
    id: 'expressway',
    name: 'Crosstown Expressway Threat',
    title: 'Crosstown Expressway Threat',
    yearStart: 1954,
    yearEnd: 1973,
    cycle: 1,
    phase: 'collapse',
    color: '#C4533A',
    summary:
      'The plan to run a highway down South Street emptied it out. The fight to stop that highway is what brought it back.',
    beats: [
      { text: 'The state issued eminent domain notices in 1954 and held public hearings in 1965, turning a working corridor into a clearance zone.' },
      { text: 'Banks redlined the blocks and property values collapsed as merchants and residents left.' },
      { text: 'Artists and students moved into the cheap, empty space; the TLA opened on the 300 block in 1965 and the Zagars bought a 400-block house in 1968.' },
      { text: "Alice Lipscomb's Hawthorne coalition joined the artist-led South Street Renaissance, and the expressway was killed in 1974." },
    ],
  },
  {
    id: 'counter-culture',
    name: 'Counter Culture Renaissance',
    title: 'Counter Culture Renaissance',
    yearStart: 1973,
    yearEnd: 1992,
    cycle: 1,
    phase: 'reinvention',
    color: '#5B9A4E',
    summary:
      'The anti-expressway victory left cheap rent on a historic strip, and a wave of independent operators turned South Street into a national counterculture destination.',
    beats: [
      { text: 'Banks lifted the redline in 1974, and twenty-five tenants bought the buildings they had been renting.' },
      { text: "Zipperhead opened at 407 South Street in 1980, one of the country's first punk-rock boutiques." },
      { text: "Grendel's Lair, Ripley Music Hall, and the TLA drew U2, the Ramones, and Bruce Springsteen to the strip." },
      { text: 'Michael Axelrod bought thirteen buildings by 1987 and recruited the corridor\'s first national chains, Tower Records and the Gap.' },
    ],
  },
  {
    id: 'mallification',
    name: 'Mall Era',
    title: 'Mall Era',
    yearStart: 1992,
    yearEnd: 2008,
    cycle: 1,
    phase: 'commercialization',
    color: '#3A6FA5',
    summary:
      'A new business district professionalized the corridor just as suburban malls pulled shoppers away, and South Street chased national chains to compete.',
    beats: [
      { text: "City Council created the South Street Headhouse District in 1992, the city's second business improvement district." },
      { text: 'As malls in King of Prussia and Cherry Hill drew shoppers off, the corridor added chains like Starbucks, Blockbuster, and Adidas, what the Inquirer called a "walkable mall."' },
      { text: 'Rising rents pushed the counterculture anchors out, with J.C. Dobbs closing in 1996 and Zipperhead in 2005.' },
      { text: "The 2001 Mardi Gras melee and the collapse of Will Smith's $63.5 million W Hotel signaled the corridor's momentum was running out." },
    ],
  },
  {
    id: 'e-commerce',
    name: 'E-Commerce Era',
    title: 'The E-Commerce Era',
    yearStart: 2008,
    yearEnd: 2026,
    ongoing: true,
    cycle: 2,
    phase: 'collapse',
    color: '#C98A2E',
    summary:
      'The 2008 recession broke the chain formula, and a string of shocks since has left the corridor at a low it has not climbed out of.',
    beats: [
      { text: "The 2008 recession emptied the chains within three years, and vacancy became the corridor's defining condition." },
      { text: "A partial recovery from 2015 to 2020, including Midwood's 2016 purchase of 11 Axelrod buildings, never caught up to the city's broader revival." },
      { text: 'COVID hollowed out what retail was left, and a mass shooting struck the 200 block in June 2022.' },
      { text: "The Headhouse District's 2022 to 2023 financial crisis capped a decade that, by 2026, left South Street the emptiest it has felt in a generation." },
    ],
  },
];
