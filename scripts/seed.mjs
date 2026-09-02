import pg from "../lib/db/node_modules/pg/lib/index.js";
import fs from "fs";
import path from "path";

const dir = typeof import.meta !== "undefined" && import.meta.dirname ? import.meta.dirname : process.cwd();
const possibleEnvPaths = [
  path.resolve(dir, "../.env"),
  path.resolve(process.cwd(), ".env"),
  ".env",
];

for (const envPath of possibleEnvPaths) {
  try {
    process.loadEnvFile(envPath);
    if (process.env.DATABASE_URL) break;
  } catch {}
}

const databaseUrl = process.env.DATABASE_URL || "postgresql://postgres:123456@localhost:5432/legal_case_sim";
const client = new pg.Client({ connectionString: databaseUrl });

/**
 * The corpus, read from the same JSON the ingest script reads.
 *
 * Seed cases used to carry `applicableLaws` as hand-written prose, and three of
 * them cited instruments the corpus has never held — CPC 1908, the Specific
 * Relief Act 1877, the West Pakistan Land Revenue Act 1967. Nothing caught it:
 * the citation audit only extracts instruments it has an alias for, so an
 * unknown Act is not reported as fabricated, it is not seen at all. The library
 * therefore displayed law the simulator could not argue, on the first screen a
 * student opens.
 *
 * So provisions are now declared as [statuteCode, sectionNumber] pairs and
 * resolved here. `applicableLaws` is derived from what resolves, never typed by
 * hand, which is the same rule generated cases already follow in
 * routes/cases.ts. A pair that does not resolve aborts the seed.
 */
function loadCorpus() {
  const corpusDir = path.resolve(dir, "../data/statutes");
  const byKey = new Map();
  const instruments = [];

  for (const file of fs.readdirSync(corpusDir).filter((f) => f.endsWith(".json"))) {
    const instrument = JSON.parse(fs.readFileSync(path.join(corpusDir, file), "utf8"));
    instruments.push({
      statuteCode: instrument.statuteCode,
      // The exact string a citation is rendered with, e.g. "QSO 1984 Art. ".
      prefix: `${instrument.citationPrefix} ${instrument.citationUnit}`,
    });
    for (const section of instrument.sections) {
      byKey.set(`${instrument.statuteCode}:${section.sectionNumber.toUpperCase()}`, {
        citation: `${instrument.citationPrefix} ${instrument.citationUnit}${section.sectionNumber}`,
        statuteCode: instrument.statuteCode,
        heading: section.heading,
        // Per-provision flag wins; absent means inherit the instrument default.
        verified: section.verified ?? Boolean(instrument.verified),
      });
    }
  }

  return { byKey, instruments };
}

/** Resolves a case's declared provisions, or throws naming every miss. */
function resolveCitations(corpus, title, provisions) {
  const resolved = [];
  const missing = [];

  for (const [statuteCode, sectionNumber] of provisions) {
    const entry = corpus.get(`${statuteCode}:${sectionNumber.toUpperCase()}`);
    if (entry) resolved.push(entry);
    else missing.push(`${statuteCode} ${sectionNumber}`);
  }

  if (missing.length > 0) {
    throw new Error(
      `"${title}" cites provisions absent from the corpus: ${missing.join(", ")}. ` +
        `Add them to data/statutes and re-run statutes:ingest, or cite something else.`
    );
  }

  return resolved;
}

/**
 * The same rule applied to the prose of a brief.
 *
 * `applicableLaws` is derived from resolved pairs and cannot lie. A brief
 * cannot be: its facts and grounds are prose, and a ground is precisely where a
 * wrong section number does the most damage, because it reads to a student as a
 * pleaded proposition of law and is fed to every agent through
 * `case_context()`. Nothing downstream would catch it — the runtime audit runs
 * over what agents *say*, not over what the case file already asserted.
 *
 * So every citation written in a brief must be spelled the way the corpus
 * renders one ("QSO 1984 Art. 141", "PPC 1860 s.302"), and every one of them
 * must resolve. The pattern is built from the corpus's own prefixes rather than
 * from a second alias table, so it cannot drift from the statute book.
 *
 * What this does not catch: a citation written in a looser form the Python
 * extractor would still read, such as "Article 999 of the QSO". That is the
 * price of not reimplementing `app/rag/citations.py` here in a second language.
 * House rendering in brief prose is the convention that makes the check bite.
 */
function verifyBriefCitations(corpus, title, brief) {
  if (!brief) return;

  const pattern = new RegExp(
    `(${corpus.instruments
      .map((i) => i.prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join("|")})\\s*(\\d+(?:-?[A-Za-z])?)`,
    "g"
  );
  const codeByPrefix = new Map(corpus.instruments.map((i) => [i.prefix, i.statuteCode]));

  const prose = [
    brief.jurisdictionInvoked,
    ...[...brief.facts, ...brief.grounds, ...brief.prayer],
  ].filter(Boolean);

  const missing = [];
  for (const text of prose) {
    for (const [raw, prefix, sectionNumber] of text.matchAll(pattern)) {
      const statuteCode = codeByPrefix.get(prefix);
      if (!corpus.byKey.has(`${statuteCode}:${sectionNumber.toUpperCase()}`)) {
        missing.push(raw);
      }
    }
  }

  if (missing.length > 0) {
    throw new Error(
      `The brief for "${title}" cites provisions absent from the corpus: ` +
        `${missing.join(", ")}.`
    );
  }
}

const sampleCases = [
  {
    title: "State v. Muhammad Aslam",
    areaOfLaw: "Criminal",
    difficulty: "Intermediate",
    summary: "The State charges the accused with murder following a dispute over agricultural land in District Kasur. The defense contends alibi and eyewitness testimony inconsistency under Qanun-e-Shahadat Order 1984 Article 17.",
    // Was "PPC 1860 s. 302, QSO 1984 Art. 17 & 22". QSO Art. 22 is not in the
    // corpus, and the extractor never saw it — an ampersand-joined number
    // carries no provision word, so it parsed as one citation, not two.
    provisions: [
      ["PPC_1860", "300"],
      ["PPC_1860", "302"],
      ["QSO_1984", "17"],
      ["QSO_1984", "71"],
    ],
    petitionerName: "State Prosecutor",
    petitionerRole: "Complainant / State",
    respondentName: "Muhammad Aslam",
    respondentRole: "Accused / Defense",
    witnesses: JSON.stringify([
      {
        name: "Tariq Mahmood",
        role: "Eyewitness",
        statement: "I saw the altercation near the canal bridge at dusk. The accused was carrying a blunt weapon."
      },
      {
        // Cited "Article 40 of QSO" — a provision the corpus does not hold, and
        // unlike the instrument-level misses this one the extractor *does* read,
        // so seeded testimony was feeding the audit a fabricated citation.
        name: "Inspector Chaudhry Raza",
        role: "Investigating Officer",
        statement: "I recovered the weapon of offence from the spot pointed out by the accused during investigation."
      }
    ]),
    source: "library"
  },
  {
    title: "Tariq Khan v. Capital Development Authority",
    areaOfLaw: "Civil",
    difficulty: "Beginner",
    summary: "Petitioner seeks a permanent injunction restraining the CDA from demolishing a commercial property in Sector F-7, Islamabad, alleging valid lease deed and procedural non-compliance.",
    // Was CPC 1908 Order 39 and Specific Relief Act 1877 — neither instrument is
    // in the corpus, and neither has an alias in the extractor, so both passed
    // the audit by being invisible to it. The corpus holds no civil substantive
    // law at all, so this case is now pinned to what genuinely governs it on the
    // evidence and on the authority's conduct: proving the lease deed, and Art. 4.
    // Restore the Order 39 / Specific Relief citations once those Acts are
    // ingested — they are the better answer, they are simply not available.
    provisions: [
      ["CONST_1973", "4"],
      ["QSO_1984", "75"],
      ["QSO_1984", "76"],
    ],
    petitionerName: "Tariq Khan",
    petitionerRole: "Petitioner / Property Owner",
    respondentName: "CDA Enforcement Directorate",
    respondentRole: "Respondent / Public Authority",
    witnesses: JSON.stringify([
      {
        name: "Ghulam Nabi",
        role: "Revenue Officer (Patwari)",
        statement: "The land ownership entry in Khasra Girdawari matches the allotment record from 2012."
      },
      {
        name: "Zubair Ahmad",
        role: "Urban Architect",
        statement: "The construction plan was submitted for approval prior to building commencement."
      }
    ]),
    source: "library"
  },
  {
    title: "Asma Bibi v. Board of Revenue",
    areaOfLaw: "Constitutional",
    difficulty: "Advanced",
    // The summary called this a writ petition from the day it was seeded. It
    // was still run as a trial, because a trial was the only thing the
    // courtroom could run — so it offered examination-in-chief and
    // cross-examination of witnesses in a matter heard on affidavits.
    proceedingType: "writ",
    summary: "Constitutional writ petition under Article 199 challenging executive revenue circulars that deny female heirs equal mutation rights in ancestral agricultural land under Article 25.",
    // Dropped the West Pakistan Land Revenue Act 1967 s. 42 — not in the corpus,
    // and invisible to the extractor for want of an alias. Art. 4 replaces it as
    // the hook for circulars that depart from the law.
    provisions: [
      ["CONST_1973", "4"],
      ["CONST_1973", "25"],
      ["CONST_1973", "199"],
    ],
    petitionerName: "Asma Bibi",
    petitionerRole: "Petitioner",
    respondentName: "Board of Revenue Punjab",
    respondentRole: "Respondent",
    // Emptied with the proceeding. A writ has no witness box, so a scholar's
    // opinion and a Tehsildar's account are not testimony here — they belong
    // in the affidavits and the counter-affidavit. Leaving them would put
    // names in every agent prompt that no phase can ever call.
    witnesses: JSON.stringify([]),
    source: "library"
  },
  // The demo case. It existed only as a generated row in one local database,
  // which meant the case the presentation is built on would not survive a reset
  // and could not be recreated on another machine. Seeding it puts it in git.
  // Its three witnesses are what the beats turn on: Sana Arif and Ali Shah
  // support the State, Reema Khan is the alibi — so examination-in-chief and
  // cross-examination each have a witness who properly belongs to that side.
  {
    title: "State v. Yasir Alam",
    areaOfLaw: "Criminal",
    difficulty: "Advanced",
    summary: "Yasir Alam has been charged with the murder of his business partner, Asad Raza, following an alleged dispute over the financial mismanagement of their jointly owned enterprise. The prosecution's case is based on circumstantial evidence including testimony from witnesses who claim to have heard arguments between the two partners prior to the incident. Yasir Alam maintains his innocence, alleging that he was at a business meeting at the time of the murder. The trial court convicted Yasir, sentencing him to life imprisonment, which he now appeals.",
    provisions: [
      ["PPC_1860", "300"],
      ["PPC_1860", "302"],
      ["QSO_1984", "17"],
      ["CRPC_1898", "342"],
    ],
    petitionerName: "Yasir Alam",
    petitionerRole: "Appellant",
    respondentName: "State",
    respondentRole: "Respondent",
    witnesses: JSON.stringify([
      {
        name: "Sana Arif",
        role: "Eyewitness",
        statement: "I heard Yasir and Asad arguing loudly the day before Asad was murdered. Yasir threatened Asad, saying he would regret his actions. I saw Yasir leaving Asad's office looking visibly agitated around the time of the murder."
      },
      {
        name: "Ali Shah",
        role: "Neighbor",
        statement: "On the afternoon in question, I saw Yasir Alam leaving his house hurriedly around 2:00 PM, which was unusual. I later learned that it was the same afternoon that Asad was reportedly killed."
      },
      {
        name: "Reema Khan",
        role: "Business Associate",
        statement: "I was with Yasir at a business meeting from 1:30 PM to 3:30 PM the day Asad was murdered. During this time, Yasir received no calls or messages that I was aware of, and he seemed calm throughout the meeting."
      }
    ]),
    source: "library"
  },
  // The voice-demo case, and the only seeded case carrying a full brief.
  //
  // It exists because hearing all three AI voices in one sitting needs a case
  // built for it, not a case that happens to allow it. Every beat of the demo
  // has a witness who properly belongs to the side that calls them, and the
  // facts are laid so that each of the seven objection grounds in
  // app/grounding.py has something real to bite on:
  //
  //   hearsay (Art. 71)          Nadia Sattar was *told* about the motorcyclist
  //   leading (Art. 137)         she is the prosecution's own witness in chief
  //   secondary evidence (75)    the CCTV survives only as a copy on a USB
  //   police statement (s.162)   her s.161 statement omits the accused's name
  //   insulting (Art. 148)       Junaid Farooq is the accused's cousin
  //   improper impeachment (151) the alibi rests on that relationship
  //   irrelevant (Art. 133)      nothing in the file turns on the parties' politics
  //
  // Nadia Sattar, Inspector Qureshi and Dr. Malik are the prosecution's, so a
  // student arguing for the State examines them in chief where leading is
  // objectionable; Junaid Farooq is the alibi, so he is the one they cross,
  // where leading is proper. Arguing as the accused inverts that cleanly, which
  // is why the parties are named "The State" and "Bilal Hussain" rather than
  // appellant and respondent — either side is a coherent demo.
  //
  // The brief is what makes it a *detailed* case rather than a long summary:
  // grounds are read into every agent prompt, so the bench and opposing counsel
  // can press a student on a proposition the file actually pleads. That is not
  // free — see docs/voice-demo.md for what it adds to the per-turn prompt.
  {
    title: "State v. Bilal Hussain",
    areaOfLaw: "Criminal",
    difficulty: "Advanced",
    summary: "Asim Javed, who managed the Al-Barq filling station on Adiala Road, Rawalpindi, was shot dead in the station's cabin at about 9:40 pm on 14 March 2025. The prosecution says the assailant was Bilal Hussain, a pump attendant dismissed three weeks earlier over a cash shortfall, identified by the cashier Nadia Sattar as he walked out with a pistol in his hand, and that a second man waited for him on a motorcycle. The defence pleads alibi at a family function in Chakwal, ninety kilometres away, and attacks the proof rather than the story: the cashier's statement to the police does not name the accused, and the station's camera footage survives only as a copy on a USB drive. The trial turns on identification, on the alibi, and on whether the documentary and recovery evidence is proved as the Qanun-e-Shahadat requires.",
    provisions: [
      ["PPC_1860", "34"],
      ["PPC_1860", "300"],
      ["PPC_1860", "302"],
      ["QSO_1984", "17"],
      ["QSO_1984", "71"],
      ["QSO_1984", "75"],
      ["QSO_1984", "76"],
      ["QSO_1984", "141"],
      ["CRPC_1898", "161"],
      ["CONST_1973", "10A"],
    ],
    petitionerName: "The State",
    petitionerRole: "Prosecution / Complainant",
    respondentName: "Bilal Hussain",
    respondentRole: "Accused / Defence",
    // Four witnesses, three for the prosecution and one for the defence, so
    // examination-in-chief and cross-examination each have a witness who
    // belongs to that side whichever side the student takes.
    witnesses: JSON.stringify([
      {
        name: "Nadia Sattar",
        role: "Cashier at the filling station (eyewitness)",
        // The last sentence is deliberate: it marks the motorcyclist as
        // something she was told, not something she saw, so a question about
        // him is genuinely hearsay rather than hearsay by stipulation.
        statement: "I was at the cash counter, about fifteen feet from the manager's cabin, when I heard two loud bangs. When I looked up, a man was walking out of the cabin with a pistol in his hand, and the forecourt lights were on, so I saw his face — it was Bilal, who worked with us until last month. The other staff told me afterwards that a second man was waiting for him on a motorcycle; I did not see that myself."
      },
      {
        name: "Inspector Rehan Qureshi",
        role: "Investigating Officer",
        // He must know about the copy, because fact 6 says the police took the
        // recorder. Without that sentence the secondary-evidence beat produces
        // an honest "I don't recall" instead of an objection — the witness
        // agent is right and the case file was incomplete.
        statement: "I reached the filling station a little after eleven that night, prepared the site plan, and took the blood-stained earth, two empties and the camera recorder into possession. The accused was arrested on the seventeenth, and on the nineteenth he took us to a drain off Dhamial Road where a pistol was recovered in my presence. The recorder's disk would not read at the laboratory, so what has been produced is a copy of the footage on a USB drive, made by the station's own operator."
      },
      {
        name: "Dr. Ayesha Malik",
        role: "Medico-legal Officer",
        // Says nothing about who fired. A question asking her to is the
        // cleanest demonstration of the witness declining to speculate, and it
        // only works if the statement leaves that gap open.
        statement: "I conducted the post-mortem on the morning of the fifteenth. There were two entry wounds on the chest with corresponding exit wounds at the back, and I gave the cause of death as haemorrhage and shock from firearm injuries. From the condition of the body, I put the time of death at roughly twelve to fourteen hours before I examined him."
      },
      {
        name: "Junaid Farooq",
        role: "Cousin of the accused (alibi witness)",
        statement: "Bilal is my cousin. On the night of the fourteenth he was at my sister's mehndi in Chakwal — he came at about eight in the evening and was still there when the dholak was going after midnight. Chakwal is about ninety kilometres from Rawalpindi, and he had no car with him that night."
      }
    ]),
    // Facts, grounds and prayer are declared as plain strings; labels are
    // assigned below, exactly as casegen.py assigns them, so a hand-written
    // brief and a drafted one are the same shape in the record.
    brief: {
      court: "Court of Session, Rawalpindi",
      caseNumber: "Sessions Case No. 214/2025",
      jurisdictionInvoked: "Trial on a challan submitted under CrPC 1898 s.173",
      petitioners: [
        {
          name: "The State",
          role: "Prosecution",
          description: "Through the District Public Prosecutor, Rawalpindi.",
        },
        {
          name: "Imran Javed",
          role: "Complainant",
          description: "Brother of the deceased and the maker of the first information report.",
        },
      ],
      respondents: [
        {
          name: "Bilal Hussain",
          role: "Accused",
          description: "Pump attendant at the Al-Barq filling station until his dismissal on 21 February 2025.",
        },
        {
          name: "Unidentified co-accused",
          role: "Absconder",
          description: "The second man said to have waited on the motorcycle; not before the court.",
        },
      ],
      facts: [
        "The deceased Asim Javed managed the Al-Barq filling station on Adiala Road, Rawalpindi. The accused Bilal Hussain worked there as a pump attendant until 21 February 2025, when he was dismissed after a shortfall of Rs. 84,000 was found in night takings he had handled.",
        "On the night of 14 March 2025, at about 9:40 pm, two shots were fired inside the manager's cabin. The cashier Nadia Sattar says she looked up and saw a man leaving the cabin with a pistol in his hand, whom she recognised as the accused, while a second man waited on a motorcycle at the forecourt.",
        "FIR No. 411/2025 was registered at Police Station Saddar Bairuni the same night on the report of Imran Javed, brother of the deceased, for an offence under PPC 1860 s.302 read with PPC 1860 s.34.",
        "The post-mortem conducted on 15 March 2025 recorded two firearm entry wounds on the chest with corresponding exit wounds, and gave the cause of death as haemorrhage and shock.",
        "The accused was arrested on 17 March 2025. On 19 March 2025 a .30 bore pistol was recovered from a drain off Dhamial Road on his pointation, and was sent with the crime empties to the Punjab Forensic Science Agency.",
        "The station's recorder was taken into possession but its hard disk is said to be damaged. The prosecution tenders the footage as a copy on a USB drive, with a certificate from the operator who made it.",
        "The statement of Nadia Sattar recorded under CrPC 1898 s.161 on 15 March 2025 does not name the accused; the identification first appears in a supplementary statement made on 20 March 2025, after the arrest. The accused denies the occurrence and pleads alibi at Chakwal.",
      ],
      grounds: [
        "The prosecution says the killing is qatl-e-amd within PPC 1860 s.300, the shots having been fired with the intention of causing death, and is punishable under PPC 1860 s.302.",
        "The prosecution says the man who waited on the motorcycle shared a common intention with the assailant, so PPC 1860 s.34 fixes each with the act of the other.",
        "The prosecution relies on a single eyewitness and says QSO 1984 Art. 17 requires no particular number of witnesses. The defence answers that her account of the second man is what she was told afterwards, and that QSO 1984 Art. 71 admits only what she perceived herself.",
        "The defence says the recording on the USB drive is not the original. QSO 1984 Art. 75 requires a document to be proved by primary evidence, and the copy is receivable only if the prosecution first brings the case within QSO 1984 Art. 76.",
        "The defence says the omission of the accused's name from the statement under CrPC 1898 s.161 may be put to the witness in cross-examination under QSO 1984 Art. 141, and that a conviction on this record would not answer Constitution 1973 Art. 10A.",
      ],
      prayer: [
        "The prosecution prays that the accused be convicted of qatl-e-amd under PPC 1860 s.302 and sentenced in accordance with law.",
        "The prosecution prays that the pistol recovered on the accused's pointation, the crime empties and the forensic report be exhibited and read against him.",
        "The defence prays that the accused be acquitted, identification and the documentary evidence being unproved, and that the plea of alibi be accepted.",
      ],
    },
    source: "library"
  }
];

/**
 * Labels a declared brief. Mirrors casegen.py: facts are numbered, grounds are
 * lettered and prayer items are parenthesised lowercase, assigned by position
 * rather than typed, so the labels are always contiguous.
 */
function buildBrief(brief) {
  if (!brief) return null;
  const GROUND_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const PRAYER_LABELS = "abcdefghijklmnopqrstuvwxyz";
  return {
    court: brief.court ?? null,
    caseNumber: brief.caseNumber ?? null,
    jurisdictionInvoked: brief.jurisdictionInvoked ?? null,
    petitioners: brief.petitioners ?? [],
    respondents: brief.respondents ?? [],
    facts: brief.facts.map((text, i) => ({ label: String(i + 1), text })),
    grounds: brief.grounds.map((text, i) => ({ label: GROUND_LABELS[i], text })),
    prayer: brief.prayer.map((text, i) => ({ label: PRAYER_LABELS[i], text })),
  };
}

async function seed() {
  try {
    const corpus = loadCorpus();

    // Resolved before the first write, so a case citing law the corpus lacks
    // fails the whole seed rather than leaving the library half-updated.
    const prepared = sampleCases.map((c) => {
      const citations = resolveCitations(corpus.byKey, c.title, c.provisions);
      verifyBriefCitations(corpus, c.title, c.brief);
      return {
        ...c,
        // Every case seeded before proceeding types existed is a trial, and
        // that is a fact about them rather than a missing value.
        proceedingType: c.proceedingType ?? "trial",
        citations,
        brief: buildBrief(c.brief),
        // Identical to how routes/cases.ts renders a generated case, so a
        // library case and a drafted one are indistinguishable in the UI.
        applicableLaws: citations
          .map((entry) => `${entry.citation} (${entry.heading})`)
          .join(", "),
      };
    });

    await client.connect();
    console.log("Connected to DB for seeding...");

    for (const c of prepared) {
      const existing = await client.query("SELECT id FROM cases WHERE title = $1", [c.title]);
      if (existing.rows.length === 0) {
        await client.query(
          `INSERT INTO cases (title, area_of_law, difficulty, proceeding_type, summary, applicable_laws, petitioner_name, petitioner_role, respondent_name, respondent_role, witnesses, citations, brief, source)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb, $13::jsonb, $14)`,
          [c.title, c.areaOfLaw, c.difficulty, c.proceedingType, c.summary, c.applicableLaws, c.petitionerName, c.petitionerRole, c.respondentName, c.respondentRole, c.witnesses, JSON.stringify(c.citations), c.brief === null ? null : JSON.stringify(c.brief), c.source]
        );
        console.log(`Seeded case: ${c.title}`);
      } else {
        // Re-running the seed repairs the law on a case that is already stored.
        // Skipping it would leave every existing install showing the uncovered
        // citations this change exists to remove, since these rows are only ever
        // written here. Student-facing fields the seed owns are refreshed;
        // sessions reference the case by id and are untouched.
        await client.query(
          `UPDATE cases SET applicable_laws = $2, citations = $3::jsonb, witnesses = $4::jsonb, summary = $5, brief = $6::jsonb, proceeding_type = $7
           WHERE title = $1 AND source = 'library'`,
          [c.title, c.applicableLaws, JSON.stringify(c.citations), c.witnesses, c.summary, c.brief === null ? null : JSON.stringify(c.brief), c.proceedingType]
        );
        console.log(`Refreshed case: ${c.title} (${c.citations.length} provisions)`);
      }
    }
    console.log("Seeding complete!");
  } catch (err) {
    console.error("Seeding error:", err.message);
    // Exit non-zero: the old handler logged and returned 0, so a failed seed
    // was indistinguishable from a clean one to anything scripting this.
    process.exitCode = 1;
  } finally {
    await client.end();
  }
}

seed();
