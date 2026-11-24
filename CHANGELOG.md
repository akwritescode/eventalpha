# Changelog

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
