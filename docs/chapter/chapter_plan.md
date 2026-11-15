# Plan for the revised chapter on the new corpus

Proposal for Ricardo and Fernando (15-nov-2026). Based on `ISABELCHAPTER REV.docx` (2025 version, with the two
reviewers' reports), the seven syntheses and the cross-reading in this folder, and the run `isabel_chapter_v1`.
The 2025 chapter has four sections (Introduction; Method; Application and statistics; Policy recommendations in
six blocks) and no conclusion. Body ≈ 6,500 words (Introduction 1,000; Method 1,850; Application 950; Section 4
2,700) plus ≈ 6,100 words of references.

Principle: keep the four-section skeleton and the chapter's distinctive angle (the spatial reading, left-behind
places, discontent), and change what the reviewers and the new corpus force: the method is reported as what was
done, Section 4 is reorganised so that every claim traces to a study of the corpus, and a conclusion is added.

## 0. What the new corpus changes, in one paragraph

The 2025 corpus (142 papers) was replaced because the explicit criteria the reviewers asked for excluded most of
it. The new review identified 2,419 records, screened 2,119, found 372 eligible and synthesises the 170 that are
core to at least one question. Five of the six old policy blocks survive with new references; one does not: the
block on the workplace, flexible work, remote work and urban form has **no support in the new corpus** (nothing on
remote work or urban form passed the criteria), and its German Digital Strategy material was outside the corpus
anyway (reviewer 2, M5). Conversely, the largest body of new evidence, economic-policy recommendations for the
green transition (RQ1, 40 studies), had no block of its own in 2025.

## 1. Introduction (keep; trim to ≈ 800 words)

- Keep the framing (2030 Agenda, twin transition, JCD) but cut the two pages on EU crises and the list of 17 SDGs
  (reviewer 2, minor). Fix the dated or wrong figures the reviewers flagged (Green Deal 2019; 244 indicators; coal
  jobs; Howorth) — Fernando's list.
- New paragraph, "Objective and structure": state the seven questions (Table 1, moved here from Section 3), say
  that the chapter reports a scoping review following PRISMA-ScR, and **declare the change of corpus**: as a
  result of the method improvements requested in review, the corpus differs from the first version and the
  findings are rewritten on it. One sentence on RQ3's reformulation.
- Keep the authors' wider reading (Rodríguez-Pose, left-behind places) here as motivation, so that Section 4 can
  stay within the corpus.

## 2. Method: what PALET did in this review (rewrite; ≈ 1,500 words + appendix)

Answers reviewer 2 M1 and M2 and reviewer 1's first three comments.

- 2.1 PALET in one paragraph: a protocol-driven, AI-assisted scoping-review tool; the agent-theory pages
  (Wooldridge and Jennings, Shoham, Green) reduced to two or three sentences with one recent reference on
  LLM agents. Drop "objective" and "complete sweep".
- 2.2 Protocol: the seven questions; criteria IC1–IC5 and EC1–EC3 in a table (geography = EU-27, UK, EFTA;
  period 2013–2025; English and Spanish; articles and reviews; journals in SCIE, SSCI or ESCI; labour dimension
  and twin-transition link mandatory); protocol v2 approved by both authors on 14-nov-2026.
- 2.3 Information sources: the Scopus export of May 2025 (235 records; string not archived, declared) and the
  seven OpenAlex searches (title and abstract, English, strings and counts in the appendix). Scopus API not
  available: declared.
- 2.4 Screening: metadata checks first (type, language, period, journal indexing, abstract available: 88 excluded
  for no abstract); then two models (`claude-opus-5-5`, `claude-sonnet-5-5`) answer each criterion with a verified
  quote; fixed decision rule `agreement_or_exclude`; 53 records decided by the authors (14 included). Report the
  inter-model agreement (842/967, 87.1 %, κ = 0.794) **as agreement between two models, not as validation against
  human screening**, and the absence of a formal validation as a limitation (M2, as decided on 11-nov).
- 2.5 Charting and selection: one model assigns each eligible study to the questions it answers, core or partial,
  with a verified quote; the chapter synthesises only core studies (170 of 372) and says so; no second model or
  author review of this classification (limitation).
- 2.6 Figure 1: the eight-step workflow diagram (new, from the dashboard) replacing the 2025 four-step figure, with
  every step named in the text (reviewer 1). Figure 2: PRISMA flow (the one regenerated on 14-nov, no database
  named in the boxes; databases in the caption).
- 2.7 Limitations of the method (one paragraph here, developed in Section 5): abstracts only; two AI screeners
  without human validation; conservative rule may have excluded relevant studies; journal lists as of June 2026
  and August 2025, not at publication date; Scopus string not archived; English-only supplementary searches.
- Appendix A (online or end of chapter): search strings, filters, dates, counts; prompts' hashes and model
  versions; PRISMA-ScR checklist (`report/prisma_scr_checklist.md`); full list of the 170 core studies by
  question (`report/selected_studies.csv`). All generated by PALET from the run.

## 3. Results of the review: the corpus (rewrite; ≈ 700 words; rename, no "meta-analysis")

- Table 2: counts per question — identified by the question's search, eligible, core, partial, overlap — from
  `prisma_counts.json` and `table_included_by_rq.md`. Core per question: RQ1 40, RQ2 38, RQ3 5, RQ4 31, RQ5 4,
  RQ6 57, RQ7 7 (12 studies core to two questions).
- Figure 3: included studies by question, core and partial (`fig_included_by_rq`). Figure 4: by year
  (`fig_included_by_year`, 2025 partial).
- Two sentences on geography (Germany, UK, Poland, Italy, Spain, Greece dominate; regional-resolution studies are
  a minority) and on the uneven coverage: three questions are thin (RQ3, RQ5, RQ7) and this is itself a result.
- The old Table 3 (the 142 references by question) becomes Appendix A's list; in the text, only counts.

## 4. Policy recommendations from the review (rewrite; ≈ 3,500–4,000 words)

Two options. **Option A (recommended): seven subsections, one per question.** It answers M5 directly (the blocks
map onto the questions; each subsection has its summary table of supporting studies), it lets the thin questions
be reported honestly, and the syntheses already exist in that shape. The headings keep the 2025 block names where
they fit:

| New subsection | 2025 block it absorbs | Source synthesis | Length |
|---|---|---|---|
| 4.1 Economic policy for job creation and destruction in the green transition (RQ1) | none (new) | RQ1 §1–§4 | 700 |
| 4.2 Digitalisation, AI and the labour market (RQ2) | part of "workplace" | RQ2 §1, §2, §4, §5 | 600 |
| 4.3 Education at all levels and continuing training (RQ4, with the skills studies of RQ2) | "education" | RQ4 + RQ2 §3 | 600 |
| 4.4 Immigration and labour mobility (RQ5) | "immigration" | RQ5 | 250 |
| 4.5 Just transition and "green discontent" in dependent territories (RQ6) | "green discontent / left behind" | RQ6 §1–§5 | 900 |
| 4.6 Cohesion policy and smart specialisation (RQ3) | "smart specialisation" | RQ3 + the regional strands of RQ1/RQ2 | 350 |
| 4.7 What we know and what we need to measure better (RQ7) | "more research" | RQ7 | 350 |

Order: RQ1, RQ2, RQ4, RQ5, RQ6, RQ3, RQ7 keeps the 2025 reading order (education → immigration → discontent →
research → smart specialisation) while putting the two transition questions first. Each subsection: one
paragraph of what the evidence says, two or three paragraphs of the thematic clusters from the synthesis with
citations, and a closing line on how strong the evidence is. Each subsection ends with (or Section 4 opens with)
**Table 3: recommendation → supporting studies**, generated from `evidence_by_rq.md` (reviewer 1 and M5).

Option B: keep six blocks and remap them (education ← RQ4+RQ2; "economic policy for the green transition" ←
RQ1 replacing "workplace"; immigration ← RQ5; discontent ← RQ6; research ← RQ7; smart specialisation ← RQ3). It
keeps the 2025 look but still needs the block-to-question table and loses the distinction between RQ1 and RQ2.
Not recommended: the reviewers asked for the mapping, and Option A gives it for free.

Rules for the rewrite, whichever option: every claim cites a core study of the corpus that supports it; the
authors' wider reading (German Digital Strategy, Rodríguez-Pose, the authors' own regional work) goes to the
Introduction or to Section 5 in clearly marked sentences ("beyond the corpus, …"); no study from the appendix
list of 31 is used for a claim until its full text has been read; the 12 overlapping studies appear where the
cross-reading assigns them.

What is dropped from 2025 Section 4 because the corpus does not support it: flexible-work legislation, remote work
and urban form (block 2); the German Digital Strategy as a source for EU measures; the immigration paragraph's
claims about EU selective-immigration policy (M4); Pacca, Ramajo, Lee and Rodríguez-Pose as supports for claims
they do not make (M4).

## 5. Discussion and conclusions (new; ≈ 900 words) — reviewer 2, M6

- What the review adds, in three conclusions from the cross-reading: C1 (aggregate optimism, local pessimism: the
  design problem is the gap between the two scales); C2 (the literature recommends territorial targeting but
  barely evaluates the EU's territorial instruments, and judges the Just Transition Fund narrow and unevenly
  allocated); C5 (the green transition has a just-transition architecture and a literature evaluating it; the
  digital transition has neither, although the regional divergence is documented).
- How strong the evidence is for each block (one sentence each, from the cross-reading table), and where it is
  thin: RQ3, RQ5, the digital half of RQ6, the policy-evaluation half of RQ7. C7: only a handful of policy
  evaluations with an identification strategy in 170 studies.
- Limitations of the method (from 2.7, developed) and of the corpus (geographic skew, C8).
- Implications for EU and regional policy: the five design principles of RQ6 and the skills principles of RQ4, in
  one paragraph each, as the chapter's answer to the volume's question.

## 6. References

Only the studies cited. The 2025 list (≈ 6,100 words) is replaced by the new corpus's references, exported from
the run (`report/citations_by_rq.csv` → BibTeX) plus the non-corpus references of the Introduction and Section 5.
`check-citations` on the final manuscript before submission (HANDOFF step 8).

## Open points for the authors

1. Option A or B for Section 4.
2. Word limit of the publisher: the plan above gives ≈ 7,500–8,000 words of body, about 1,000 more than 2025.
   If the limit is tighter, cut 4.1 and 4.5 first (they are the longest) and move the limitations to the appendix.
3. Whether to run the extra searches for RQ3 and RQ5 or to present them as gaps (DECISIONES_METODO, 14-nov).
4. The 31 studies of the cross-reading appendix: read in full or leave out of the claims.
5. The co-authors from Western Macedonia (Kanteler, Topaloglou): RQ6 now has seven Greek lignite-region studies
   (Tranoulidis; Kruczek; Kaldellis; Koukouzas; Boulogiorgou and Kaldellis; Kourkouridis; Apostolopoulos); they may
   want to write that part.
6. Response letter: with the new corpus, the answers to M3 (off-topic papers), M4 (unsupported claims) and M5
   (synthesis not connected to the review) become one answer: the corpus was rebuilt with explicit criteria and
   Section 4 was rewritten on it with a study-to-claim table. Fernando's planned citation check (M4) is replaced
   by `check-citations` plus the full-text reading of the appendix list.
