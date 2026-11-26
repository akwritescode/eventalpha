# Move explanation evals

The starter set in `move_explanations.json` includes a real NVDA catalyst and four Nov 25 SPY
windows. The positive case expects the [April 15 NVIDIA 8-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581025000082/nvda-20250409.htm)
that disclosed H20 export restrictions and expected charges. The label uses the SEC document
URL so it works across warehouses with different database IDs. For a reproducible local replay,
`examples/move-window.sql` supplies the real filing with simulated observation times and X posts.
The linked 11 a.m.–2 p.m. and 8:30 a.m.–2 p.m. SPY cases ask different questions.

- **11 a.m.–2 p.m.** The warehouse result abstains. The web recaps are summarized as inputs
  for an article-level JEV eval. A recap that describes improving breadth or easing tech losses
  does not identify what triggered the bounce.
- **8:30 a.m.–2 p.m.** The timeline should retrieve the GDP and PCE releases. In manual
  review, check the morning dip and afternoon recovery independently. PCE can be a possible
  contributor to the dip when a source explicitly connects them. Dip buying after heavy selling
  is a hypothesis for the recovery. A reversal on a price chart does not establish who bought or why.

A synthetic positive control checks that the model can accept an article with explicit attribution.
The control is an article-level fixture and does not represent market news.

## Repeatable API scoring

Run against an API with the case's market data and archived evidence.

```sh
python3 scripts/eval_move_explanations.py --base-url http://localhost:8081 --save-responses /tmp/move-baseline.json
python3 scripts/eval_move_explanations.py --responses /tmp/move-baseline.json
```

The report scores the three-article shortlist, catalyst decisions, citation targets, required context,
and evidence observed after the cutoff. Candidate recall is computed for labeled IDs or URLs.
A missing required release is a coverage failure. Compare saved runs using the
same corpus, warehouse snapshot, and cutoff. The model-generated prose and the live web search
require manual review. The API grader checks whether citations are eligible and labeled,
while the reviewer checks whether they support the stated reason.

## Live article-level scoring

CI uses fixtures and mocks. To run the same JEV question and Claude extraction prompts with live
services, export `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY`, then run from `api/`.

```sh
EVENTALPHA_RUN_LIVE_MOVE_EVAL=1 ./gradlew test --rerun-tasks --tests '*LiveMoveModelEvalTest'
```

The JUnit XML under `api/build/test-results/test/` records model IDs, the JEV threshold, scores,
and extracted reasons. The test checks verdicts and whether Claude can extract a supported
reason. Scores and wording may vary on repeat runs, so retain multiple runs before changing
the threshold. No live model call is made by the default test suite.
