# Label-drafting prompts

`build/draft_labels.py` sends these to the API model to draft gold labels. **A draft isn't gold.** One teammate checks every draft against the paper text and fixes it. A second teammate re-checks a random 20%. Record the drafting model, the verifier, and the second checker for each item in `gold/provenance.csv`.

Each prompt asks for a quote and a section for every label, so checking means finding a quote with Ctrl+F, not rereading the paper.

## Writing the task items (people, before drafting)

- **find_papers.** Phrase the topic the way a researcher would type it, not as a paper title. Aim for 4–10 relevant papers. Fewer makes recall jumpy, and more won't fit in the top 10. At least a third of the topics should cross two clusters (for example "RAG systems as an attack surface").
- **comparison_table.** Pick 4–5 papers that really report comparable numbers. Fix the setting per column (dataset, model, metric, unit). Mix types: at least one numeric, one enum, and one text column per table.
- **citation_links.** Pick 8–12 papers that are densely linked in `gold/citations_s2.jsonl`, plus 2–3 from the same cluster that link to none of the others.
- **grounded_claims.** Ask a question that needs 2–4 papers to answer, such as "How do retrieval-time and generation-time defenses against poisoned RAG documents differ in cost?" Skip questions with a one-paper answer.
- **followup_questions.** Pick 3–5 papers that have real limitations sections.
- **Traps (5, spread across types).** Write a topic that sounds like it fits the corpus but doesn't (for example a subfield the clusters don't cover). Or ask about a real, well-known paper that you checked is **not** in the corpus. Set `"trap": true` only in the gold file.

## 1. find_papers: relevance grading

`draft_labels.py` builds the pool first: the union of the top 20 from BM25, the top 20 from embedding search, and the top 20 the API model picks from the title list. Then it sends batches of 10 pooled papers:

```
Topic: {topic}

For each paper below, grade how relevant it is to the topic:
2 = directly about this topic; a researcher would read it first.
1 = partly relevant: covers the topic as a secondary part, or a closely related method.
0 = not relevant, or only mentions the topic in passing.

{for each paper: ID | title | abstract}

For each paper, return the grade and the sentence from the abstract that decided it.
Return JSON only:
{"grades": [{"paper_id": "<id>", "grade": 0 | 1 | 2, "evidence": "<verbatim sentence>"}]}
```

The verifier checks every 1 and 2 and spot-checks the 0s. Gold `relevant` holds the papers graded 1 or 2. Gold `pooled` holds every paper that got a grade.

## 2. comparison_table: cell drafting

Send one paper at a time with its full text, because a whole table's worth of papers won't fit cleanly in one context:

```
Paper ID: {paper_id}
Paper text:
"""
{full text}
"""

Fill these columns for this paper:
{one line per column: name | type | unit or allowed values | setting}

Use the exact setting for each column. If the paper reports several numbers, pick
the one that matches the setting and nothing else. If the paper doesn't report a
value for this setting, write NOT_REPORTED. Don't estimate or convert unless the
column's unit requires it, and if you convert, say so in the note.

Return JSON only:
{"cells": {"<column>": {"value": "<value or NOT_REPORTED>",
  "quote": "<exact text from the paper, a sentence or a table line>",
  "section": "<section name>", "note": "<empty, or what you converted or why it is ambiguous>"}}}
```

The verifier finds each quote in the paper and confirms the setting matches. Every non-empty `note` gets a second look. If a cell is ambiguous even to a person, change the column's setting or drop the column. Don't guess.

## 3. citation_links: cross-check of S2 edges

Semantic Scholar edges are the starting gold, but S2 misses some references. For each paper in the set, send its References section:

```
Here is the reference list of paper {paper_id}:
"""
{References section text}
"""

Which of these papers appear in that reference list?
{for each other paper in the set: ID | title | first author | year}

Match on title. Treat small differences in wording, capitalization, or punctuation
as the same title. Return JSON only:
{"cited": [{"paper_id": "<id>", "reference_line": "<the matching line, verbatim>"}]}
```

Gold edges are the union of the S2 edges and the edges this finds. The verifier checks every edge where the two sources disagree.

## 4. grounded_claims: supporting papers

```
Question: {question}

Below are candidate papers (ID, title, abstract). For each one, decide whether it
contains information needed to answer the question. If it does, give one quote from
its abstract or full text that supports your decision.

{candidate papers}

Return JSON only:
{"supporting": [{"paper_id": "<id>", "quote": "<verbatim>", "why": "<one sentence>"}],
 "draft_answer": "<2-4 sentences, using only the supporting papers>"}
```

Gold keeps `supporting_ids`. The verifier saves `draft_answer` as a note to check judge decisions against. It isn't scored.

## 5. followup_questions: gap notes

```
Papers:
{for each paper: ID | title | Limitations, Discussion, and Conclusion section text}

List the open problems these papers state or clearly imply. For each one, give the
paper ID and the exact sentence that states it. Then write a 3-5 sentence summary
of the main gaps. The summary is context for a grader, so be concrete.

Return JSON only:
{"gaps": [{"paper_id": "<id>", "quote": "<verbatim>"}], "gap_notes": "<summary>"}
```

Gold keeps `gap_notes`. The verifier removes any gap whose quote doesn't appear in the paper.
