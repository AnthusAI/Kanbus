# Changelog

## [0.17.0](https://github.com/AnthusAI/Kanbus/compare/kanbus-rust-0.16.0...kanbus-rust-0.17.0) (2026-03-09)


### Features

* AI-powered wiki, lifecycle hooks, and init default pages ([b9fd52d](https://github.com/AnthusAI/Kanbus/commit/b9fd52d7deea1a3b748461538022b1e8fc741895))
* **cloud-realtime:** add mqtt-first client transport and ops runbook alarms ([ed2c192](https://github.com/AnthusAI/Kanbus/commit/ed2c1925e0df0c7112864a47f376ff99b1f6f093))
* **cloud:** scaffold Python CDK foundation and lambda realtime bootstrap ([118d3e1](https://github.com/AnthusAI/Kanbus/commit/118d3e104eda03097114fa50f439fb100f06edbf))
* **console:** add wiki workspace with deep links, resize, and tests ([52f8c9f](https://github.com/AnthusAI/Kanbus/commit/52f8c9f0ac5574bd87a389be2f9ae493fe3fbc13))
* **console:** support stage-prefixed cloud routes and relative asset base ([137575c](https://github.com/AnthusAI/Kanbus/commit/137575c2baa57869cb141660827eb49b0374d984))
* **event-history:** expand event coverage and fix beads dependency events ([a249c23](https://github.com/AnthusAI/Kanbus/commit/a249c23e0d81109e99cbafa595e84ded6ef9d77d))
* **realtime:** ship pub-sub collaboration hub, overlay cache, and docs ([a0a55bf](https://github.com/AnthusAI/Kanbus/commit/a0a55bff0a5d56656d6794ca1b7fffdc9f38ddc9))
* **sync:** add GitHub Dependabot pull sync with Beads support and Rust/Python parity ([df13ee7](https://github.com/AnthusAI/Kanbus/commit/df13ee73327c47d02ab3dd149f2adc68e574a239))


### Bug Fixes

* **ci:** add wiki panel console steps and apply fmt ([acf63b1](https://github.com/AnthusAI/Kanbus/commit/acf63b109acf3f95d1411946484100b35b800b73))
* **ci:** address clippy and overlay test regressions ([961968e](https://github.com/AnthusAI/Kanbus/commit/961968e9099cc74a55f9a9bbde35545393586c8f))
* **ci:** resolve clippy needless borrow in beads delete path ([d4f0603](https://github.com/AnthusAI/Kanbus/commit/d4f0603052735867f3d591723359861ec6f81eb8))
* **ci:** restore parity env and normalize formatting ([cce8253](https://github.com/AnthusAI/Kanbus/commit/cce825378721d9eca8ed15a5731213eed163fe77))
* **ci:** restore persisted console UI state across kbsc restart ([16ce9c5](https://github.com/AnthusAI/Kanbus/commit/16ce9c530a369f956e9ca0c4a7a534fa6225b760))
* **ci:** restore rust hooks clippy compliance and behave env cleanup ([eaee32f](https://github.com/AnthusAI/Kanbus/commit/eaee32fdf677e4aaac7ad6d9dc9789cc306f3c26))
* **ci:** stabilize console wiki ui regression checks ([88cf9b7](https://github.com/AnthusAI/Kanbus/commit/88cf9b7eb89fa07c8765d3c8d18d34e8a1e4bf58))
* **cloud:** harden console lambda routing and tenant data resolution ([78a3a3b](https://github.com/AnthusAI/Kanbus/commit/78a3a3b7babf8026e64f6bcd42e92db242d410e0))
* **codeql:** derive console state path from trusted project dir ([49a4554](https://github.com/AnthusAI/Kanbus/commit/49a455458794cf08594d4596762e9eb3517364aa))
* **console:** accept mqtt realtime config in python snapshot path ([03399e7](https://github.com/AnthusAI/Kanbus/commit/03399e7da6ba96d44aec4da70afc5238a886e1c5))
* quality gates - behave config steps, delete --yes, clippy, list_format ([5505cec](https://github.com/AnthusAI/Kanbus/commit/5505cec79ef6763b2c3df61e6fad5a7b98094d98))
* **rust:** resolve clippy warnings in console_lambda ([587a508](https://github.com/AnthusAI/Kanbus/commit/587a508e75d25a791eec65a0674ade76356f1fdc))

## [0.16.0](https://github.com/AnthusAI/Kanbus/compare/kanbus-rust-0.15.0...kanbus-rust-0.16.0) (2026-03-06)


### Features

* add --full-ids list option and lock show output keys ([70943b4](https://github.com/AnthusAI/Kanbus/commit/70943b48e4fa8bfe1a82f5c3652cc7ee1269dd3b))
* **cli:** add bulk issue update command ([7f53078](https://github.com/AnthusAI/Kanbus/commit/7f530789630fbd623122bf913b81ec11bd4bf391))
* **kanban:** add config-driven column sorting with FIFO defaults ([0ac17b6](https://github.com/AnthusAI/Kanbus/commit/0ac17b6d3398463fe98812d8ef082d3890f9cab6))
* **workspace:** improve project discovery and show lookup ([254a737](https://github.com/AnthusAI/Kanbus/commit/254a7376245215e4bef3ac1b376d8391ff7ab271))


### Bug Fixes

* **ci:** restore discovery fallback and complete console sort test support ([5f27f84](https://github.com/AnthusAI/Kanbus/commit/5f27f846ef6a75e052ad4696b2e9d36f175da6c4))
* **console:** enforce recency sort in Done column ([393dbd2](https://github.com/AnthusAI/Kanbus/commit/393dbd23e535d8271aa2286de559d987559c56d2))
* **rust:** constrain console state path and avoid stderr log macros ([c646ced](https://github.com/AnthusAI/Kanbus/commit/c646cedba9bd194d0523ff255a80c4df9ed9f36b))

## [0.15.0](https://github.com/AnthusAI/Kanbus/compare/kanbus-rust-0.14.0...kanbus-rust-0.15.0) (2026-03-02)


### Features

* **cli:** add move command to change issue type with policy enforcement ([95ef383](https://github.com/AnthusAI/Kanbus/commit/95ef38359b314ce6d506519e30988456a6f0fad8))
* **policy:** enforce epic entry guardrails and surface guidance as rules ([3b1389c](https://github.com/AnthusAI/Kanbus/commit/3b1389c6a8d507a60df47c58390fa01c0b2a2ca4))


### Bug Fixes

* **policy:** distinguish top-level scenarios from rule scenarios in policy list ([e8823c1](https://github.com/AnthusAI/Kanbus/commit/e8823c1219b09000202f45d3e272065bcfb9a343))
* **policy:** enforce epic child guardrails in beads update path ([cc93452](https://github.com/AnthusAI/Kanbus/commit/cc9345220d471bd095abec85ed501d3fece85123))

## [0.14.0](https://github.com/AnthusAI/Kanbus/compare/kanbus-rust-0.13.2...kanbus-rust-0.14.0) (2026-03-01)


### Features

* add --focus flag to auto-focus newly created issues (tskl-e7j.1) ([9b8e7bc](https://github.com/AnthusAI/Kanbus/commit/9b8e7bc9ccb84e5c884c7b2ad6e9fec06289c900))
* add console UI state commands with [@console](https://github.com/console) BDD integration tests ([084a302](https://github.com/AnthusAI/Kanbus/commit/084a30260b45423fde25c47eac0b3bfc51dd31cd))
* add kanbus jira pull command with BDD specs ([131c344](https://github.com/AnthusAI/Kanbus/commit/131c3446dd6088735a9ddd4f9cf4db219b1f78c9))
* add unfocus and view mode CLI commands (tskl-m59.1, tskl-m59.2) ([85d1498](https://github.com/AnthusAI/Kanbus/commit/85d1498ee36ee24f9c75330e176036839403da95))
* complete descendant display feature and PM updates ([4ad3227](https://github.com/AnthusAI/Kanbus/commit/4ad3227dfa52f7a785eafac09f7dd807ddd96aef))
* complete programmatic UI control CLI commands (tskl-m59) ([390c948](https://github.com/AnthusAI/Kanbus/commit/390c94885f077e08466e61f296445f60479f7d6b))
* **console:** allow network binding ([83a431c](https://github.com/AnthusAI/Kanbus/commit/83a431c19c78518fe1966276b581f805dd521631))
* **console:** restore metrics view ([3bd9a4e](https://github.com/AnthusAI/Kanbus/commit/3bd9a4ecd8ada2dcafba7cc2c9f9ec35abc0ed2b))
* enhance Snyk sync functionality to support both package and code vulnerabilities ([84ced87](https://github.com/AnthusAI/Kanbus/commit/84ced875fbd617ccc335367c8ee56b1299bb785f))
* implement real-time issue focus and notification system (tskl-e7j) ([8abf325](https://github.com/AnthusAI/Kanbus/commit/8abf3259e0b2e0869bb63238cbbee93a034625bd))
* Rich text quality signals (tskl-3ec) ([d562ffb](https://github.com/AnthusAI/Kanbus/commit/d562ffbd88c2d042a2cf9eba29248dcb4db7abe3))
* Rich text quality signals + Git Flow standards (tskl-3ec) ([1111674](https://github.com/AnthusAI/Kanbus/commit/11116749eae735130a1497827343c1ead3fc2e4c))
* update video previews, branding, and fix gatsby builds ([73e008b](https://github.com/AnthusAI/Kanbus/commit/73e008b01eeb6a4641b89df7f4d76d86b1367b46))
* validate local tasks feature and fix console board to show local issues ([260bf6b](https://github.com/AnthusAI/Kanbus/commit/260bf6bda27e261a2eba3313476a0f14969f033a))


### Bug Fixes

* align rust fmt and context routes ([fb41683](https://github.com/AnthusAI/Kanbus/commit/fb41683de27d9d92f75df5c0466581f6b5a1204c))
* align rust notification formatting ([f4270c4](https://github.com/AnthusAI/Kanbus/commit/f4270c4a396b62e29b38dfe5ac30cbb77f9444b8))
* avoid clippy useless vec ([4d38921](https://github.com/AnthusAI/Kanbus/commit/4d389212f9ef185723a5e84b5e7c06b9671ad5ca))
* **ci:** stabilize console metrics tests ([6453863](https://github.com/AnthusAI/Kanbus/commit/6453863418ce0defc139ca584f34d3e87f476ba9))
* **config:** accept legacy external_projects ([9b7a002](https://github.com/AnthusAI/Kanbus/commit/9b7a0029bf2d74e96c215b6757fe00543d718c6a))
* **console:** resolve clippy lints in console steps ([379d9b7](https://github.com/AnthusAI/Kanbus/commit/379d9b769089f63cfbd80f34664586e556f81792))
* correct short_key truncation and env var restore in jira tests ([12e3a86](https://github.com/AnthusAI/Kanbus/commit/12e3a86930adb95271baeb94ecd0b012d2353acf))
* disable unix socket notifications on windows ([42c1661](https://github.com/AnthusAI/Kanbus/commit/42c1661e68566c1006478778d9449aacf8bcc8ee))
* embed console assets from crate directory ([dc1238b](https://github.com/AnthusAI/Kanbus/commit/dc1238bae890dd99fd6fcf8ccbf570b7bef72e3e))
* make local listing failure injectable for tests ([0296f62](https://github.com/AnthusAI/Kanbus/commit/0296f6232e4c203837268c32fb410fc56e45b8af))
* pin native-tls to 0.2.16 ([a5d4a78](https://github.com/AnthusAI/Kanbus/commit/a5d4a78b27ef940d9e0de003d74389ebb6275447))
* preserve view mode state across navigation (tskl-m59.11) ([830748b](https://github.com/AnthusAI/Kanbus/commit/830748b08636cd3f675db9e3a9ef666987014961))
* quiet clippy and format python ([8d9f220](https://github.com/AnthusAI/Kanbus/commit/8d9f220da252e1fae472a2bb93a112994535d5b7))
* restore ci coverage and clippy ([ee45943](https://github.com/AnthusAI/Kanbus/commit/ee45943012d799c2979f5c96e0df96be4c4dc3ff))
* restore jira env vars in correct order in test cleanup ([4d2413e](https://github.com/AnthusAI/Kanbus/commit/4d2413e4b80c4cd74282d93293fb574d477962d3))
* reuse prebuilt console dist in rust coverage ([2b7e9d4](https://github.com/AnthusAI/Kanbus/commit/2b7e9d4e0c64a34ac3c7d77bd1c85da637b80892))
* **rust:** resolve borrow checker error in console_ui_steps.rs ([27e649d](https://github.com/AnthusAI/Kanbus/commit/27e649d063c51433e3d8851c0e263fab933a3634))
* **snyk_sync:** reduce function argument count to satisfy linters ([f5ba153](https://github.com/AnthusAI/Kanbus/commit/f5ba153c80648e53102cdb2a1c634c11928ce35d))
* stabilize code block validation tests ([1d1a68c](https://github.com/AnthusAI/Kanbus/commit/1d1a68cac28d83c59079e76f4e6d8c3a960afd66))
* **tests:** expose panel toggle test ids ([b9a1a28](https://github.com/AnthusAI/Kanbus/commit/b9a1a280de5edcd8faf919da1554f02a3a888125))
* unblock release by skipping flaky id format scenario ([fd8f375](https://github.com/AnthusAI/Kanbus/commit/fd8f375ae01883977922aef76cc622bb9d45ad18))
* update Cargo.lock after native-tls vendored change; add CLI aliases and enriched help ([4ceb7f3](https://github.com/AnthusAI/Kanbus/commit/4ceb7f33b439555ce3268be5b6b38b48a9ccd020))
* update test helper call signature ([42690ca](https://github.com/AnthusAI/Kanbus/commit/42690ca2b416534b1cbb07b9e7790d723982fed6))
* vendor OpenSSL to eliminate system libssl-dev dependency for cargo install ([37835b7](https://github.com/AnthusAI/Kanbus/commit/37835b7e1b59f5860f95535c077488d6f2b99fae))
