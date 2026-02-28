# Changelog

## [0.14.0](https://github.com/AnthusAI/Kanbus/compare/kanbus-rust-0.13.2...kanbus-rust-0.14.0) (2026-02-28)


### Features

* add --focus flag to auto-focus newly created issues (tskl-e7j.1) ([9b8e7bc](https://github.com/AnthusAI/Kanbus/commit/9b8e7bc9ccb84e5c884c7b2ad6e9fec06289c900))
* add console UI state commands with [@console](https://github.com/console) BDD integration tests ([084a302](https://github.com/AnthusAI/Kanbus/commit/084a30260b45423fde25c47eac0b3bfc51dd31cd))
* add diagram rendering and comment management ([2889f0f](https://github.com/AnthusAI/Kanbus/commit/2889f0fdc9697ff5b6d5f6f19d1ec21c76c46455))
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
