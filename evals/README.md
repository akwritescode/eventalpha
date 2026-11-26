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

The noon–2 p.m. case has synthetic article controls for an exact-return recap, the same return for
a different window or ticker, the opposite direction, explicit attribution with a rounded return
and slightly different quote times, and explicit attribution without a percentage. The measured
returns for the two paired cases come from replay fixture candles, including the earlier opening
candle in the sparse 11 a.m. fixture. The synthetic articles do not represent market news.

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

## Article-level cases

`article_judgments.json` adds 27 article judgments in five groups, on top of those in
`move_explanations.json` (34 in all). Real events (NVDA's Nov 23 reinstatement rally and Nov 24
giveback, SPY's Nov 25 morning selloff) are paraphrased in our own words with their `sources`;
measured returns come from warehouse candles. Everything else is marked `synthetic`, including a
fictional ticker (XQZR) so no claim is made about a real company. Each article has a `kind`:
real-paraphrase, buried-cause (the cause in the last paragraph of a long recap), multiple-causes,
attributed-by-analysts and explicit-cause should be accepted; recap-no-cause, hedged-speculation,
despite, wrong-date, wrong-ticker, wrong-direction, cause-after-window, no-move-described and
prompt-injection should not. A CI fixture check requires unique ids, a label on every article,
sources for every non-synthetic article, and both labels in every group.

## Live article-level scoring

CI uses fixtures and mocks. To run the same JEV question and Claude extraction prompts with live
services, export `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY`, then run from `api/`.

```sh
EVENTALPHA_RUN_LIVE_MOVE_EVAL=1 ./gradlew test --rerun-tasks --tests '*LiveMoveModelEvalTest'
```

`EVENTALPHA_LIVE_EVAL_RUNS=3` repeats every JEV judgment (and Claude extraction) to expose
variance. The report gives JEV-level precision and recall, what users would see (a cause is shown
only when JEV accepts and Claude grounds a reason), misses by kind, verdicts that flip between
runs, and articles within 0.15 of the threshold. Both prompt variants run: direction only, and with
the measured return; assertions apply to the variant production uses (direction only since the
Nov 26 rollback: with the return, JEV accepted a same-size move from another day and Claude dropped
causes of gap moves).

The eval runs the same articles and prompts with direction alone and with the measured return and
actual candle close times. The JUnit XML under `api/build/test-results/test/` records model IDs,
the JEV threshold, scores, extracted reasons, and false-positive and false-negative counts for both
variants. The measured-return variant is checked against the labels. The direction-only variant
provides a comparison. Scores and wording may vary on repeat runs. No live model call is made by
the default test suite.
