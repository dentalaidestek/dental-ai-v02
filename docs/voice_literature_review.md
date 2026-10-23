# Voice examination evidence review

The transcription/extraction call selects speech-anchored topics from the approved dental concept vocabulary. The final review retrieves professional documents and publication abstracts, then makes the existing single final Gemini call. No additional model call is used for search planning. Queries to source services contain public clinical concepts only, never names, quotes, patient identifiers, or transcripts.

## Source selection

- ADA: professional topic documents plus official guideline landing pages for pain, pulpal/periapical antibiotic use, and restorative caries treatment. The guideline collection currently links these pages: https://www.ada.org/resources/research/science/evidence-based-dental-research . Landing-page excerpts are not a substitute for full guideline text.
- PubMed: independent searches for up to six selected topics, up to two IDs per topic, one abstract fetch. Separate searches prevent one topic from consuming every result. Publication type/date, DOI, topic association, retraction/expression-of-concern flags and animal-only indexing are inspected. Search is bounded in time; an incomplete/failed topic remains explicit, including on cached empty results.
- DergiPark: public OAI metadata for **Selcuk Dental Journal** (2148-7529) and **ADO Klinik Bilimler Dergisi** (1307-3540). Discovery examines at most the first 100 recently updated records per journal (120-day update window). It does not search the full archive. Resumption tokens produce a partial-catalogue status. At most one canonical article page per journal is fetched; the ISSN, article type, publication date and abstract are checked there. OAI dc:date is not used as publication date because it may be a submission date.

Journal policy references inspected on 2026-10-23:

- https://dergipark.org.tr/en/pub/selcukdentj/indexes
- https://dergipark.org.tr/tr/pub/adoklinikbilimler/indexes
- https://www.ado.org.tr/dergimiz
- https://trdizin.gov.tr/yardim/

DergiPark is a hosting/editorial platform, not an index or an article-quality certificate. Neither indexing, DOI, journal reputation, nor a systematic-review label establishes that a specific clinical claim is correct.

## Clinical use

Current, dated guidelines/systematic reviews/meta-analyses can be submitted as candidate evidence. General/narrative reviews, case reports/editorials, preclinical publications, undated/old reports, and publications with unresolved correction flags cannot ground clinical suggestions. Retracted publications and expressions of concern are excluded. These are conservative metadata filters, not a formal risk-of-bias/GRADE assessment.

The final prompt prioritizes professional guidelines and checks population, uncertainty, relevance and evidence limits. The server requires exact patient-field and source-excerpt anchors. It rejects clinical items using a source marked clinical_use=false. This verifies provenance; it does not independently prove semantic or clinical correctness. Questions cannot be used to bypass the source requirement for treatment suggestions. Unsupported suggestions are counted and omitted. Source type, date and related topic labels are visible in the interface. DOI deduplication prevents a paper indexed in two services from inflating the evidence count.

## Load and verification

Source caches are bounded and last up to 24 hours; NCBI requests are rate limited, and each literature provider has a nonblocking single-flight concurrency limit per process. No PDF downloading, bulk indexing, or source retrieval happens on each audio segment. External source retrieval is still synchronous at final review, and cold-cache requests can be slow or fail; partial coverage must remain visible.

93 Python tests and seven browser-controller harnesses passed during this update. The tests cover per-topic PubMed coverage, retraction exclusion, cache-status retention, patient-query privacy, OAI partial catalogues, wrong-journal/URL rejection, publication-date provenance, and blocking background evidence from clinical suggestions.

Real public-service checks returned PubMed diabetes reviews (PMIDs 35420698 and 31939522); the endodontic query timed out in that run and remained explicitly unavailable. Real DergiPark article 1615782 was parsed as a 2025 systematic review of in-vitro work and correctly marked unsuitable for direct clinical suggestions. A cold DergiPark discovery check found no eligible endodontic/radiography publication within the bounded update window. This is not evidence that no such publications exist.

No new-version actual Gemini/audio quality measurement or production deployment has been performed. No patient records were changed.
