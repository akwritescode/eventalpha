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
sources for every non-synthetic article, both labels in every group, and a valid
`expectedReasonPattern` on each positive fixture. The case-insensitive pattern describes the
expected cause using common paraphrases. When a fixture lists several causes, any supported
cause satisfies the pattern.

## Live article-level scoring

CI uses fixtures and mocks. To run the same JEV question and Claude extraction prompts with live
services, export `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY`, then run from `api/`.

```sh
EVENTALPHA_RUN_LIVE_MOVE_EVAL=1 ./gradlew test --rerun-tasks --tests '*LiveMoveModelEvalTest'
```

`EVENTALPHA_LIVE_EVAL_RUNS=3` repeats every JEV judgment (and Claude extraction) to expose
variance. The direction-only arm uses the current production prompts and checks whether each cause
should be shown and whether its text matches the expected cause. A pattern match checks the
expected attribution and can still miss extra claims in the reason.

The comparison arm uses the measured return, actual candle close times, and the JEV and Claude
instructions from commit `54019d0`. Both arms use the same configured model IDs. The JUnit XML
under `api/build/test-results/test/` records reasons for each run, false positives, hidden causes,
reason mismatches, JEV precision and recall, verdicts that flip, and scores near the threshold.
The direction-only arm determines the test result. The default suite uses no live model calls.
