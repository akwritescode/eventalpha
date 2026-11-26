# Changelog

## [0.7.1](https://github.com/akwritescode/eventalpha/compare/v0.7.0...v0.7.1) (2026-11-26)


### Bug fixes

* **moves:** keep measured returns out of model prompts ([82ef04c](https://github.com/akwritescode/eventalpha/commit/82ef04c63e67dd1cd219aa3cab3693d458567454))
* **moves:** keep periods out of release names in summaries ([5259154](https://github.com/akwritescode/eventalpha/commit/5259154c564817eb57f9afbed30b9fb329755f1a))
* **web:** clarify move conclusions and calendar context ([3f1809a](https://github.com/akwritescode/eventalpha/commit/3f1809a192f3de700cc9e674a7351722c5b4357f))

## [0.7.0](https://github.com/akwritescode/eventalpha/compare/v0.6.0...v0.7.0) (2026-11-26)


### Features

* **moves:** explain moves with macro releases and the price path ([3bdb666](https://github.com/akwritescode/eventalpha/commit/3bdb6664ce86d57637f6c9faa69d6c16fe722c8e))
* **moves:** fall back to a cited web search when our sources are silent ([36b913e](https://github.com/akwritescode/eventalpha/commit/36b913e29de0f374d6aa99c712930c1c5ca1bc82))
* **moves:** ground explanations and add model evals ([87be3b3](https://github.com/akwritescode/eventalpha/commit/87be3b3e2fdc0c5517ebc0f54b0cf0219da5fbea))
* **moves:** let JEV judge whether articles explain a move ([ebad287](https://github.com/akwritescode/eventalpha/commit/ebad2870c7ee1195c4cbd27911653f8020aaac2e))
* **moves:** look back three trading days for releases and articles ([feb8ae5](https://github.com/akwritescode/eventalpha/commit/feb8ae545b69b13def0c3a4b845497fd145a1080))
* **moves:** pass measured returns to models and compare verdicts ([bc7b888](https://github.com/akwritescode/eventalpha/commit/bc7b888585277a7feb1db8299e186ad3f137e6c3))
* **moves:** rank sector ETF gainers and decliners ([504b594](https://github.com/akwritescode/eventalpha/commit/504b594733de3c8dcc4e8e3e09c417cd144b7573))


### Bug fixes

* **moves:** describe the price path without assigning a cause ([c55798f](https://github.com/akwritescode/eventalpha/commit/c55798fc7f304695193db2068a0b34cab37f4eeb))
* **moves:** handle web search failures and cached answers ([bc9c562](https://github.com/akwritescode/eventalpha/commit/bc9c562994228419b4de1d03b278e9a87222762f))
* **moves:** label pre-window returns with candle times ([1c69177](https://github.com/akwritescode/eventalpha/commit/1c69177d270facb910d35f95c5cbf67cd09179d0))
* **moves:** stabilize eval imports and model inputs ([83c3f86](https://github.com/akwritescode/eventalpha/commit/83c3f86d2ec6df1c26a40b35beb0aef1ea238a9e))

## [0.6.0](https://github.com/akwritescode/eventalpha/compare/v0.5.0...v0.6.0) (2026-11-25)


### Features

* mark telegram messages from the local stack with [local] ([06f04b5](https://github.com/akwritescode/eventalpha/commit/06f04b54bd4f1587e293be17e2cc4fc4fcb75033))
* **web:** drop the browser-only note under past conversations ([1400bbb](https://github.com/akwritescode/eventalpha/commit/1400bbb73f9e3403fd97735e03918f82477f4a24))


### Bug fixes

* **api:** clarify missing catalyst for SPY noon rebound ([a905c65](https://github.com/akwritescode/eventalpha/commit/a905c6506a9ea1f21d70521c91e51a82b247bcc2))

## [0.5.0](https://github.com/akwritescode/eventalpha/compare/v0.4.0...v0.5.0) (2026-11-25)


### Features

* allow move windows of up to two weeks ([d331028](https://github.com/akwritescode/eventalpha/commit/d331028eb15ad7cb189523fa2705f4815416e375))
* **web:** compact the custom range into a chip-height pill ([1482689](https://github.com/akwritescode/eventalpha/commit/14826898c628654d51aa2ced16873fc1a54ac0ff))

## [0.4.0](https://github.com/akwritescode/eventalpha/compare/v0.3.0...v0.4.0) (2026-11-25)


### Features

* **web:** keep past conversations and paginate the chat ([5206648](https://github.com/akwritescode/eventalpha/commit/52066485d2ef499649b5e7ec63a1d2a77747c70d))
* **web:** single range field for any past window up to 7 days ([474043b](https://github.com/akwritescode/eventalpha/commit/474043b61c7a24cb85f318f1313149e25518e7b7))

## [0.3.0](https://github.com/akwritescode/eventalpha/compare/v0.2.0...v0.3.0) (2026-11-25)


### Features

* **api:** resolve chat questions to move windows with claude ([f5d153d](https://github.com/akwritescode/eventalpha/commit/f5d153dc250eff366ce771a7425a95a26b7e33a5))
* **web:** merge the move panels into one ask eventalpha chat ([268fc64](https://github.com/akwritescode/eventalpha/commit/268fc64e5c92030e4f21b0bbb1ac44cb7369c9d2))

## [0.2.0](https://github.com/akwritescode/eventalpha/compare/v0.1.1...v0.2.0) (2026-11-24)


### Features

* **api:** explain move windows with replay-safe source timelines ([a198ab6](https://github.com/akwritescode/eventalpha/commit/a198ab675df55775a5452649dd88599af15bdf72))
* **index:** use tickers from major indexes only everywhere ([8772153](https://github.com/akwritescode/eventalpha/commit/877215363eb4ec9bc67cd08180293537221d6865))
* **ingestion:** record manually reviewed discovery leads ([126ac0b](https://github.com/akwritescode/eventalpha/commit/126ac0b503d5d86b866866da8284113f107d8af8))
* **marketdata:** collect and archive partitioned minute candles ([159d7f2](https://github.com/akwritescode/eventalpha/commit/159d7f205df5baed9c01732d950ca8804d31ba3b))
* **web:** explore recent stock moves in chat and window controls ([3a357ab](https://github.com/akwritescode/eventalpha/commit/3a357ab1e0fa13b23996fdd4da74b7b41b371864))


### Bug fixes

* **hooks:** preserve machine-local guard execution ([fad83fa](https://github.com/akwritescode/eventalpha/commit/fad83fa7d5a9467121abbb1d39f37504f30a2950))

## [0.1.1](https://github.com/akwritescode/eventalpha/compare/v0.1.0...v0.1.1) (2026-11-16)


### Bug fixes

* **deploy:** make the first-boot script run on Lightsail and give deploy its directory ([392c852](https://github.com/akwritescode/eventalpha/commit/392c852acd0c1b7b9a0ca03d49e5cff91ca3811a))

## 0.1.0 (2026-11-15)


### Features

* add pipeline watchdog, ticker filter and market-cap earnings order ([020cc03](https://github.com/akwritescode/eventalpha/commit/020cc0392813f4b6774f762ad36a647d429e94ad))
* **dags:** prioritize SEC pool work and document local tools ([7549994](https://github.com/akwritescode/eventalpha/commit/7549994bb79538553eed29d05ae2b513e935afda))
* **deploy:** serve the web UI from Vercel ([166054f](https://github.com/akwritescode/eventalpha/commit/166054f1c697a20f6683116bac92e0f308de5a4d))
* initial EventAlpha pipeline, API and deployment setup ([888287a](https://github.com/akwritescode/eventalpha/commit/888287ac2b924790960df185c6cda9b1cdf152a9))
* **news:** tag news items with the companies they name ([340ccdb](https://github.com/akwritescode/eventalpha/commit/340ccdba692f62ed80d76d3cc633c82536e047fe))
* **signals:** add trading signals, market/macro data and classifier ([77946db](https://github.com/akwritescode/eventalpha/commit/77946db715dae08f7ab932ff1282403982160b1e))
* **web:** add Market Intelligence Stream UI, feed API and notifications ([c812adc](https://github.com/akwritescode/eventalpha/commit/c812adc491c825175978a13a399134de1dafb426))


### Bug fixes

* **alerts:** send watchdog alerts to ops chat; never log the bot token ([035b350](https://github.com/akwritescode/eventalpha/commit/035b350daaa5affe5bcc51b8b35072f8740a1f37))
* **api:** stop SSE slot leaks, unblock the Telegram relay and page the feed exactly ([82ca960](https://github.com/akwritescode/eventalpha/commit/82ca96042c43d503bf1042547149967af754cabf))
* **maintenance:** pass the metadata DB URL to airflow db clean ([8e6fd22](https://github.com/akwritescode/eventalpha/commit/8e6fd22b38935ab594683d8462490cdb46c9f696))
* **pipeline:** keep one bad record from failing a batch and fix date, ticker and alert edge cases ([878b853](https://github.com/akwritescode/eventalpha/commit/878b85375d41a934e76ac02511abd46a45f3fc2f))
* **security:** require production secrets and escape channel preview links ([33e53c2](https://github.com/akwritescode/eventalpha/commit/33e53c2114bad2152ad5ce193c11c9ab8650a3c1))
* **web:** regenerate package-lock.json with Node 22's npm ([b451c8f](https://github.com/akwritescode/eventalpha/commit/b451c8f9612cfa825e81e272dff7d13e8e4df9b8))


### Documentation

* add a working quickstart, the full API reference, examples and demo data ([99fb0a0](https://github.com/akwritescode/eventalpha/commit/99fb0a026a005187fa805603c243efb9fc12e982))
* add community files, architecture decision records and README badges ([a7d2c91](https://github.com/akwritescode/eventalpha/commit/a7d2c91eef0a6238a73850c91dc3f21b0b15a241))
* **readme:** explain how to view the Redis event stream locally ([11da4ab](https://github.com/akwritescode/eventalpha/commit/11da4ab79bc9e51e838d6c86e3ee491c3a796f5d))
* **web:** document running and exploring the web UI locally ([016371a](https://github.com/akwritescode/eventalpha/commit/016371a3998997a2c970cfa6347523fcd487d376))
