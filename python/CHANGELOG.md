# CHANGELOG

<!-- version list -->

## v0.13.2 (2026-02-25)

### Bug Fixes

- **amplify**: Robust backend env guard
  ([`cc2c350`](https://github.com/AnthusAI/Kanbus/commit/cc2c350f95fed61e7759677552a5e78a048a8da1))

- **amplify**: Skip ampx without backend env
  ([`05847f4`](https://github.com/AnthusAI/Kanbus/commit/05847f44220293e5e9b81c87b75d0c6b35e01d09))

- **amplify**: Use backend-cli for ampx
  ([`c1ebc1a`](https://github.com/AnthusAI/Kanbus/commit/c1ebc1aa17154a2225fc8625b5b66b84ae206e28))

### Chores

- **rust**: Update Cargo.lock
  ([`2c8dbee`](https://github.com/AnthusAI/Kanbus/commit/2c8dbee94aef83862b393376aaa6df5242084c78))


## v0.13.1 (2026-02-24)

### Bug Fixes

- **amplify**: Install ampx via npx package
  ([`0a3a0e1`](https://github.com/AnthusAI/Kanbus/commit/0a3a0e118eaf7e2b8717f58eebe54d528701184f))

### Chores

- **rust**: Обновить Cargo.lock
  ([`11e5dcb`](https://github.com/AnthusAI/Kanbus/commit/11e5dcb5c58d455ef87d46b5432b07b5f273124b))

### Continuous Integration

- **release**: Guard VSCode publish in script
  ([`335c198`](https://github.com/AnthusAI/Kanbus/commit/335c198c01f6670714d1f8034826ce7c4b04a62c))

- **release**: Skip VSCode publish without VSCE_PAT
  ([`beaeee7`](https://github.com/AnthusAI/Kanbus/commit/beaeee7343c343fa1d874a5d40e778693fc4a192))

### Testing

- Add rust console step for empty metrics
  ([`7568f99`](https://github.com/AnthusAI/Kanbus/commit/7568f99f10f19f859b730e11f1f812d46eae054f))


## v0.13.0 (2026-02-24)

### Bug Fixes

- **ci**: Remove duplicate hasVirtualProjects declaration
  ([`0da451f`](https://github.com/AnthusAI/Kanbus/commit/0da451f4ac45bda07bf58653cb28856af0eb7665))

- **ci**: Stabilize console metrics tests
  ([`6453863`](https://github.com/AnthusAI/Kanbus/commit/6453863418ce0defc139ca584f34d3e87f476ba9))

- **config**: Accept legacy external_projects
  ([`9b7a002`](https://github.com/AnthusAI/Kanbus/commit/9b7a0029bf2d74e96c215b6757fe00543d718c6a))

- **console**: Fix failing console UI tests
  ([`9067f09`](https://github.com/AnthusAI/Kanbus/commit/9067f09b303a7098ae1f018b2df582d597056871))

- **console**: Mark active metrics toggle for tests
  ([`514b8a2`](https://github.com/AnthusAI/Kanbus/commit/514b8a2f4e5e7328ad4da729f29d520acec7d730))

- **console**: Remove nested view-track and duplicate MetricsPanel
  ([`29a3315`](https://github.com/AnthusAI/Kanbus/commit/29a331514d3e16abd05b704575ea5f34d734d665))

- **console**: Resolve clippy lints in console steps
  ([`379d9b7`](https://github.com/AnthusAI/Kanbus/commit/379d9b769089f63cfbd80f34664586e556f81792))

- **dev**: Allow console API CORS for 127.0.0.1
  ([`a75e716`](https://github.com/AnthusAI/Kanbus/commit/a75e716dafd5c5d7bccfaf31f9f76e943ac0879d))

- **dev**: Allow Vite host 0.0.0.0 for Playwright connectivity
  ([`d3b9543`](https://github.com/AnthusAI/Kanbus/commit/d3b9543eb7c7300a88bcd3b449c8ea451b789045))

- **dev**: Bind dev server to localhost for CI Playwright
  ([`59577af`](https://github.com/AnthusAI/Kanbus/commit/59577af81a979a7c34b6ac6064f826c926cb8ef4))

- **dev**: Bind Vite to network host
  ([`f0593de`](https://github.com/AnthusAI/Kanbus/commit/f0593de21f5b4a5674fe844e03d4d9a7c21afcc7))

- **dev**: Honor console_port in dev.sh
  ([`0fd6653`](https://github.com/AnthusAI/Kanbus/commit/0fd665306075cd453bd3c0a3612dcca0138fa711))

- **dev**: Use config port for UI only and wire python env
  ([`f55e260`](https://github.com/AnthusAI/Kanbus/commit/f55e260092cec480cc97b86736360a4d5dc4dc41))

- **rust**: Resolve borrow checker error in console_ui_steps.rs
  ([`27e649d`](https://github.com/AnthusAI/Kanbus/commit/27e649d063c51433e3d8851c0e263fab933a3634))

- **tests**: Expose panel toggle test ids
  ([`b9a1a28`](https://github.com/AnthusAI/Kanbus/commit/b9a1a280de5edcd8faf919da1554f02a3a888125))

- **ui**: Align metrics project filtering
  ([`be89196`](https://github.com/AnthusAI/Kanbus/commit/be8919671cc63705890f56a114e636dac1cb555c))

- **ui**: Always apply project filter to metrics and initialize enabled projects
  ([`3b56b5b`](https://github.com/AnthusAI/Kanbus/commit/3b56b5ba112d0106d7b7f5f4277da88025a69b52))

- **ui**: Apply project filters to metrics by deriving labels
  ([`bba2e58`](https://github.com/AnthusAI/Kanbus/commit/bba2e58983ea28d04e7ca17b3e06493cef74bbe1))

- **ui**: Apply project filters using derived project labels
  ([`b9214a5`](https://github.com/AnthusAI/Kanbus/commit/b9214a531cdd5cda5e9c72b194c2a4c3220004eb))

- **ui**: Base metrics on live issues and hide inactive panels
  ([`aec7b9e`](https://github.com/AnthusAI/Kanbus/commit/aec7b9e54a72a23da86f92b6f7ebc772ca8e16c8))

- **ui**: Compute metrics from filtered issues
  ([`3eff1a6`](https://github.com/AnthusAI/Kanbus/commit/3eff1a6fd30e9362e5fb684b502f764f938a48f4))

- **ui**: Dedupe issues before rendering metrics
  ([`a792d3d`](https://github.com/AnthusAI/Kanbus/commit/a792d3d368bfa56db10688e4eda96d6efe156820))

- **ui**: Ensure metrics panel hides and use live issue set
  ([`4d280ff`](https://github.com/AnthusAI/Kanbus/commit/4d280ffd764b405bdb3c95c362e2c937017f40ab))

- **ui**: Handle project prefixes without virtual config
  ([`950df09`](https://github.com/AnthusAI/Kanbus/commit/950df09b3f0bb03d0816f3957466d8abf059b02b))

- **ui**: Hide inactive metrics panel and tag chart data
  ([`48d4c59`](https://github.com/AnthusAI/Kanbus/commit/48d4c59a1791be69b4899e1ff9f607f6038aa7e2))

- **ui**: Hide inactive views and keep metrics counts unfiltered
  ([`6403831`](https://github.com/AnthusAI/Kanbus/commit/6403831fef0e3ec894f66eb4aa46ba05aca85f6d))

- **ui**: Hide project filter when single project and harden metrics refresh
  ([`5ff8f5e`](https://github.com/AnthusAI/Kanbus/commit/5ff8f5ef024a4a648e8b1217cc62b0a163adf0a4))

- **ui**: Hide project filter without virtuals and rely on config labels
  ([`a6306fb`](https://github.com/AnthusAI/Kanbus/commit/a6306fbbb4d8aa1ec2d3ad21a0e8fe7a856c5d94))

- **ui**: Initialize project filters after projectLabels declaration
  ([`d4b8fe3`](https://github.com/AnthusAI/Kanbus/commit/d4b8fe39997451d06bc1dd809bb40f0d573f6b22))

- **ui**: Keep metrics filter project selection and chart grouping
  ([`6603b06`](https://github.com/AnthusAI/Kanbus/commit/6603b06c3a3de937e6e3c7e4c2d9699ef3ae5cd8))

- **ui**: Remove duplicate metrics toggle testids
  ([`8d1abbf`](https://github.com/AnthusAI/Kanbus/commit/8d1abbf2a61f56e39acf569c9f89260da679efd1))

- **ui**: Render chart bars only when visible
  ([`ec7d94e`](https://github.com/AnthusAI/Kanbus/commit/ec7d94e0ea508d8b69408576e216e9e344b65029))

- **ui**: Respect selected project set in metrics and board filters
  ([`53931ee`](https://github.com/AnthusAI/Kanbus/commit/53931ee8d0dacb7be6c1759bbeeac6bed8ded729))

- **ui**: Use effective project filter set for metrics
  ([`66fdb98`](https://github.com/AnthusAI/Kanbus/commit/66fdb9813f9e223590c90655c89386dc1eb32956))

- **vite**: Allow LAN access
  ([`45b216c`](https://github.com/AnthusAI/Kanbus/commit/45b216c48701220395404a6ec17b1bbe2cca7baf))

### Chores

- Update Cargo.lock
  ([`2cf938b`](https://github.com/AnthusAI/Kanbus/commit/2cf938b8fa4b129ef43fd21ff01ed4fbcec903a7))

- Update Cargo.lock version
  ([`c160e2e`](https://github.com/AnthusAI/Kanbus/commit/c160e2e067672fdd0d79038d7a5b1846cb61fda4))

- **ci**: Gate docs workflow on CI success
  ([`88b9f03`](https://github.com/AnthusAI/Kanbus/commit/88b9f039908faf3c2db698614bc299360660d066))

- **console**: Refresh embedded assets
  ([`a0634ca`](https://github.com/AnthusAI/Kanbus/commit/a0634ca259aa7dd99cf299ca4519dd82eadc2018))

- **console**: Refresh snapshot when toggling metrics view
  ([`b353d34`](https://github.com/AnthusAI/Kanbus/commit/b353d34203cb7ae3672d9945d8fe320b089fbb38))

- **ui**: Log project filter state in metrics
  ([`aa40319`](https://github.com/AnthusAI/Kanbus/commit/aa40319f863b366ac576aafc6e9aea4631909509))

### Code Style

- Clarify project filter fallback comment
  ([`e32b80e`](https://github.com/AnthusAI/Kanbus/commit/e32b80e67c276db43e05c1927b90d6ce8ef1b072))

- **python**: Reformat console_ui_steps.py with black
  ([`d008481`](https://github.com/AnthusAI/Kanbus/commit/d00848167c3b34a287c42bd416b39c87651ce8d3))

- **rust**: Apply cargo fmt changes
  ([`407b48c`](https://github.com/AnthusAI/Kanbus/commit/407b48ced84e72d18da1864947b69295f233027c))

### Documentation

- **kanb.us**: Highlight beads compatibility mode benefits
  ([`17d3dec`](https://github.com/AnthusAI/Kanbus/commit/17d3decf538ec1ccf71169756dd68ce32b2f9f20))

### Features

- **console**: Allow network binding
  ([`83a431c`](https://github.com/AnthusAI/Kanbus/commit/83a431c19c78518fe1966276b581f805dd521631))

- **console**: Implement metrics view with visual charts and gherkin steps
  ([`b7bd5db`](https://github.com/AnthusAI/Kanbus/commit/b7bd5db6c265203587412eb80cc672c0b3e4ec75))

- **console**: Restore metrics view
  ([`3bd9a4e`](https://github.com/AnthusAI/Kanbus/commit/3bd9a4ecd8ada2dcafba7cc2c9f9ec35abc0ed2b))

- **kanb.us**: Add kanban board feature page
  ([`beaa1f7`](https://github.com/AnthusAI/Kanbus/commit/beaa1f78dd020aa988265dd16d69c070b5d7822b))

- **kanb.us**: Add vscode plugin feature page and link from kanban board
  ([`433ac87`](https://github.com/AnthusAI/Kanbus/commit/433ac87814922e19b4871cabe021a9802a8ab89d))

### Testing

- **console**: Implement missing metrics view step definitions
  ([`b764bfb`](https://github.com/AnthusAI/Kanbus/commit/b764bfb157278df0c36220e18d998032557eeb40))

- **ui**: Add metrics test ids and toggle state
  ([`9f7a2af`](https://github.com/AnthusAI/Kanbus/commit/9f7a2afa2e0c6592b403ebc1f8ccd560cc04d7ea))

- **ui**: Align metrics project filter selection
  ([`9ac2fb4`](https://github.com/AnthusAI/Kanbus/commit/9ac2fb48079bc113ce5ed823158bd27bb31760eb))

- **ui**: Drop forced VITE_HOST override in UI runner
  ([`2333ec8`](https://github.com/AnthusAI/Kanbus/commit/2333ec8f1a7a9345cc70243c0a20d537ce97b73b))

- **ui**: Refresh data before metrics specs
  ([`8693f85`](https://github.com/AnthusAI/Kanbus/commit/8693f851861403abab3ec2b30f75c786189d707a))

- **ui**: Resolve project labels and refresh issues
  ([`e48ec58`](https://github.com/AnthusAI/Kanbus/commit/e48ec58d7aef893e9969f2b99556004eb779fb1a))

- **ui**: Stabilize metrics fixtures
  ([`2431666`](https://github.com/AnthusAI/Kanbus/commit/2431666012e411bb2af368853218579d02a325ff))

- **ui**: Wait for filter sidebar in metrics steps
  ([`865146c`](https://github.com/AnthusAI/Kanbus/commit/865146c6c192020a04d9114ae7a984e068f0635a))


## v0.12.0 (2026-02-23)

### Documentation

- Add Git Flow standards to AGENTS.md
  ([`1053602`](https://github.com/AnthusAI/Kanbus/commit/10536021ef1005cca9e66936bc1826106ec0044a))

### Features

- Rich text quality signals (tskl-3ec)
  ([`d562ffb`](https://github.com/AnthusAI/Kanbus/commit/d562ffbd88c2d042a2cf9eba29248dcb4db7abe3))


## v0.11.1 (2026-02-22)

### Bug Fixes

- Trigger python release
  ([`f2b9ee1`](https://github.com/AnthusAI/Kanbus/commit/f2b9ee1745a7cae815f217b204e053ee192cba6b))


## v0.11.0 (2026-02-21)


## v0.10.1 (2026-02-20)

### Bug Fixes

- Add rust_only dispatch input to publish Rust crate for existing tag
  ([`049c389`](https://github.com/AnthusAI/Kanbus/commit/049c3891096e94e02226ba91fa454372bf28ee8a))

- Remove stale-SHA guard that skipped automated releases
  ([`bdd7ba1`](https://github.com/AnthusAI/Kanbus/commit/bdd7ba1c5ad382951b850d8e8fb9a7eb8580df3c))


## v0.10.0 (2026-02-20)

### Bug Fixes

- Update Cargo.lock after native-tls vendored change; add CLI aliases and enriched help
  ([`4ceb7f3`](https://github.com/AnthusAI/Kanbus/commit/4ceb7f33b439555ce3268be5b6b38b48a9ccd020))

- Vendor OpenSSL to eliminate system libssl-dev dependency for cargo install
  ([`37835b7`](https://github.com/AnthusAI/Kanbus/commit/37835b7e1b59f5860f95535c077488d6f2b99fae))

### Features

- Add intuitive CLI aliases and enriched help for AI agents (Python + docs)
  ([`e386083`](https://github.com/AnthusAI/Kanbus/commit/e38608379677f9d456a2b0b29b29901483f1dbf8))


## v0.9.5 (2026-02-20)

### Bug Fixes

- Skip PyPI publish when no release artifacts
  ([`6da9967`](https://github.com/AnthusAI/Kanbus/commit/6da9967c9bef7d8f3d277dbf531df7825a0bcd1c))


## v0.9.4 (2026-02-20)

### Bug Fixes

- Verify PyPI upload in release job
  ([`7669c49`](https://github.com/AnthusAI/Kanbus/commit/7669c496f0b727603cef3ea96badc9afd22b2bf2))

### Chores

- Add manual PyPI release dispatch
  ([`c341430`](https://github.com/AnthusAI/Kanbus/commit/c34143040795cc158b6894cb6179fc67b7da8efd))


## v0.9.3 (2026-02-20)

### Bug Fixes

- Embed console assets from crate directory
  ([`dc1238b`](https://github.com/AnthusAI/Kanbus/commit/dc1238bae890dd99fd6fcf8ccbf570b7bef72e3e))

### Chores

- Make PyPI release a distinct workflow job
  ([`586039a`](https://github.com/AnthusAI/Kanbus/commit/586039ac897cc6092a37f26cf6bd1b0e8a6a8b29))


## v0.9.2 (2026-02-20)

### Bug Fixes

- Run npm ci in package directories for release
  ([`3308928`](https://github.com/AnthusAI/Kanbus/commit/33089286c236dcb266a92061070117bea4c0beb4))

- Use absolute working directories in rust-crate
  ([`2072002`](https://github.com/AnthusAI/Kanbus/commit/2072002628a0755bad3e129282a3549cfc10fcf3))


## v0.9.1 (2026-02-20)

### Bug Fixes

- Align python version sources to v0.9.0
  ([`345eb3f`](https://github.com/AnthusAI/Kanbus/commit/345eb3fe7e5488b266b2d4867e9cd883f4204d49))


## v0.9.0 (2026-02-20)

### Bug Fixes

- Always install to /usr/local/bin for agent PATH compatibility
  ([`3b27923`](https://github.com/AnthusAI/Kanbus/commit/3b27923a8e638a5b20a980fb927128835f8ab286))

- Apply black and ruff formatting to Python files
  ([`b86df81`](https://github.com/AnthusAI/Kanbus/commit/b86df81f882b9ac0d08d1323d92764828638d347))

- Build kbsc without embed-assets for Python integration tests
  ([`0c01429`](https://github.com/AnthusAI/Kanbus/commit/0c014299c213a00ed95de5cec39993b83cbcc402))

- Correct short_key truncation and env var restore in jira tests
  ([`12e3a86`](https://github.com/AnthusAI/Kanbus/commit/12e3a86930adb95271baeb94ecd0b012d2353acf))

- Reformat console_ui_steps.py with current black version
  ([`79b258c`](https://github.com/AnthusAI/Kanbus/commit/79b258c33fec3e5082d4de23a5c7bd43ec72debf))

- Restore jira env vars in correct order in test cleanup
  ([`4d2413e`](https://github.com/AnthusAI/Kanbus/commit/4d2413e4b80c4cd74282d93293fb574d477962d3))

### Chores

- Rerun CI clean
  ([`2a1e7f5`](https://github.com/AnthusAI/Kanbus/commit/2a1e7f50b6b788647d5782fe06684e0ad00c0eeb))

- Rerun CI clean 2
  ([`eb57d4d`](https://github.com/AnthusAI/Kanbus/commit/eb57d4d09eab205790033725f0437353c81978f5))

- Rerun CI clean 3
  ([`b18570a`](https://github.com/AnthusAI/Kanbus/commit/b18570abe7ad19477eb4c15db413741915d1cba3))

- Rerun CI clean 4
  ([`2ab1e41`](https://github.com/AnthusAI/Kanbus/commit/2ab1e41a142acf1ca36c63fae5b88d403385943b))

- Rerun CI clean 5
  ([`46e6fe3`](https://github.com/AnthusAI/Kanbus/commit/46e6fe342d254fc7ea645569f6b6e83cc962c1fb))

- Rerun CI clean 6 (let rust finish)
  ([`1844ff6`](https://github.com/AnthusAI/Kanbus/commit/1844ff6ce203d23209b56fe8e399d31ee59eb56e))

- Rerun CI clean 7 (no cancel)
  ([`4cc1c80`](https://github.com/AnthusAI/Kanbus/commit/4cc1c8052762417405501259e04b4e006e326813))

- Trigger CI
  ([`ef30fb1`](https://github.com/AnthusAI/Kanbus/commit/ef30fb1366ac26050f15ff81767a364ce45a4285))

### Features

- Add console UI state commands with @console BDD integration tests
  ([`084a302`](https://github.com/AnthusAI/Kanbus/commit/084a30260b45423fde25c47eac0b3bfc51dd31cd))

- Add kanbus jira pull command with BDD specs
  ([`131c344`](https://github.com/AnthusAI/Kanbus/commit/131c3446dd6088735a9ddd4f9cf4db219b1f78c9))

- **website**: Add Jira Sync page and nav entry
  ([`87b6df2`](https://github.com/AnthusAI/Kanbus/commit/87b6df2e75e27388e72e51eca25d0bd6f7599ae1))


## v0.8.2 (2026-02-19)

### Bug Fixes

- Build @kanbus/ui before console assets in CI
  ([`b3ee28e`](https://github.com/AnthusAI/Kanbus/commit/b3ee28e7efc14a161c2181d63614755dce17c1d0))

- Disable unix socket notifications on windows
  ([`42c1661`](https://github.com/AnthusAI/Kanbus/commit/42c1661e68566c1006478778d9449aacf8bcc8ee))

- Extend tarpaulin timeout for rust coverage
  ([`b625717`](https://github.com/AnthusAI/Kanbus/commit/b625717c4277660596a6ddef327e5527d50329a7))

- Install console deps in rust CI
  ([`f2c98f5`](https://github.com/AnthusAI/Kanbus/commit/f2c98f54f1ae1ad4911e10cf3fc131d6985a0625))

- Make local listing failure injectable for tests
  ([`0296f62`](https://github.com/AnthusAI/Kanbus/commit/0296f6232e4c203837268c32fb410fc56e45b8af))

- Quiet clippy and format python
  ([`8d9f220`](https://github.com/AnthusAI/Kanbus/commit/8d9f220da252e1fae472a2bb93a112994535d5b7))

- Reuse prebuilt console dist in rust coverage
  ([`2b7e9d4`](https://github.com/AnthusAI/Kanbus/commit/2b7e9d4e0c64a34ac3c7d77bd1c85da637b80892))

- Skip slow embedded console feature in CI
  ([`04a1035`](https://github.com/AnthusAI/Kanbus/commit/04a1035d52909c137c6f420e3aa79254e22e893d))

- Switch rust coverage to cargo-llvm-cov
  ([`bfca54c`](https://github.com/AnthusAI/Kanbus/commit/bfca54c6f33db323e3dfdcf13f50c92f7ced60d9))

- Unblock release by skipping flaky id format scenario
  ([`fd8f375`](https://github.com/AnthusAI/Kanbus/commit/fd8f375ae01883977922aef76cc622bb9d45ad18))

- Update test helper call signature
  ([`42690ca`](https://github.com/AnthusAI/Kanbus/commit/42690ca2b416534b1cbb07b9e7790d723982fed6))

### Chores

- Drop binary-smoke deps on console artifact
  ([`25250f4`](https://github.com/AnthusAI/Kanbus/commit/25250f416a475a42afb1ee088b826d49f93b665b))

- Run faster rust coverage (lib only)
  ([`01b490a`](https://github.com/AnthusAI/Kanbus/commit/01b490a43419acb34563de8c32e6c4372a32bba6))

- Simplify rust coverage to unit/integration only
  ([`c549f8f`](https://github.com/AnthusAI/Kanbus/commit/c549f8f1b9880f53402f99a3cc94bb254b4e86fe))


## v0.8.1 (2026-02-18)

### Bug Fixes

- Pin native-tls to 0.2.16
  ([`a5d4a78`](https://github.com/AnthusAI/Kanbus/commit/a5d4a78b27ef940d9e0de003d74389ebb6275447))

### Continuous Integration

- Raise tarpaulin timeout
  ([`de18f26`](https://github.com/AnthusAI/Kanbus/commit/de18f268a850c2deb602bb1287a8d56e67ff7f34))


## v0.8.0 (2026-02-18)

### Bug Fixes

- Align rust fmt and context routes
  ([`fb41683`](https://github.com/AnthusAI/Kanbus/commit/fb41683de27d9d92f75df5c0466581f6b5a1204c))

- Align rust notification formatting
  ([`f4270c4`](https://github.com/AnthusAI/Kanbus/commit/f4270c4a396b62e29b38dfe5ac30cbb77f9444b8))

- Avoid clippy useless vec
  ([`4d38921`](https://github.com/AnthusAI/Kanbus/commit/4d389212f9ef185723a5e84b5e7c06b9671ad5ca))

- Preserve view mode state across navigation (tskl-m59.11)
  ([`830748b`](https://github.com/AnthusAI/Kanbus/commit/830748b08636cd3f675db9e3a9ef666987014961))

- Remove auto-scroll to top when opening kanban board
  ([`0c51d30`](https://github.com/AnthusAI/Kanbus/commit/0c51d3077ebf4765ed84542a7c16b935da8c44ab))

### Chores

- Rustfmt notification updates
  ([`eac1f6d`](https://github.com/AnthusAI/Kanbus/commit/eac1f6db34808b104b0930a4ddd549e343467b7c))

### Continuous Integration

- Pin cargo-tarpaulin version
  ([`39dc559`](https://github.com/AnthusAI/Kanbus/commit/39dc559fbeb25b30e4018c06bcd1667b69cbb8eb))

- Use ptrace tarpaulin engine
  ([`efbd3c2`](https://github.com/AnthusAI/Kanbus/commit/efbd3c2e37fb30c26fec8869ab858086969afac9))

### Documentation

- Add real-time UI control guidance for agents
  ([`049ada2`](https://github.com/AnthusAI/Kanbus/commit/049ada2defed498d05cfe150e3bf09e38880c957))

### Features

- Add --focus flag to auto-focus newly created issues (tskl-e7j.1)
  ([`9b8e7bc`](https://github.com/AnthusAI/Kanbus/commit/9b8e7bc9ccb84e5c884c7b2ad6e9fec06289c900))

- Add unfocus and view mode CLI commands (tskl-m59.1, tskl-m59.2)
  ([`85d1498`](https://github.com/AnthusAI/Kanbus/commit/85d1498ee36ee24f9c75330e176036839403da95))

- Add visual feedback for real-time updates (tskl-e7j.7)
  ([`5da225d`](https://github.com/AnthusAI/Kanbus/commit/5da225d595b5538685d1d93b82bc5723de224c81))

- Complete programmatic UI control CLI commands (tskl-m59)
  ([`390c948`](https://github.com/AnthusAI/Kanbus/commit/390c94885f077e08466e61f296445f60479f7d6b))

- Implement global keyword search (tskl-dvi.1)
  ([`c376045`](https://github.com/AnthusAI/Kanbus/commit/c376045b0b8388b4a990f34a9f7b2dfd025fa5cf))

- Implement real-time issue focus and notification system (tskl-e7j)
  ([`8abf325`](https://github.com/AnthusAI/Kanbus/commit/8abf3259e0b2e0869bb63238cbbee93a034625bd))


## v0.7.0 (2026-02-18)

### Bug Fixes

- Align collapsed columns to top with expanded columns
  ([`bb96bd8`](https://github.com/AnthusAI/Kanbus/commit/bb96bd8f948c514343379402f8ed55b29f704c79))

- Align collapsed columns to top with items-start
  ([`880d881`](https://github.com/AnthusAI/Kanbus/commit/880d881e71fbe829a3aa1503fdea90a958565089))

- Align config validation tests
  ([`fe3737a`](https://github.com/AnthusAI/Kanbus/commit/fe3737a5814fe02d3d643e2116eb2d3baf181344))

- Avoid descendants empty-state text match
  ([`2827cd6`](https://github.com/AnthusAI/Kanbus/commit/2827cd6d4dfcb2af7a0adc95d2dbf72e6467caeb))

- Center collapsed column label horizontally with count
  ([`3784b96`](https://github.com/AnthusAI/Kanbus/commit/3784b96ba8b5406582b9e5315e75fc1ff9397c24))

- Match collapsed column header height with expanded columns
  ([`861fdd0`](https://github.com/AnthusAI/Kanbus/commit/861fdd04bde881db378ed5340039b867bb83f6c2))

- Restore ci coverage and clippy
  ([`ee45943`](https://github.com/AnthusAI/Kanbus/commit/ee45943012d799c2979f5c96e0df96be4c4dc3ff))

- Stabilize code block validation tests
  ([`1d1a68c`](https://github.com/AnthusAI/Kanbus/commit/1d1a68cac28d83c59079e76f4e6d8c3a960afd66))

- Widen gsap timeline typing
  ([`8716173`](https://github.com/AnthusAI/Kanbus/commit/87161732a36649bc121c709ec6d82946d4e315b7))

### Chores

- Add console.log and egg-info to gitignore
  ([`8ce9479`](https://github.com/AnthusAI/Kanbus/commit/8ce947963ad50280756eaee55dc169683e696183))

- Add custom_assets to gitignore
  ([`2d23b60`](https://github.com/AnthusAI/Kanbus/commit/2d23b600d4b04cae6ee34ac626936980af3f4805))

- Close tskl-nlh and tskl-un5
  ([`c16ed93`](https://github.com/AnthusAI/Kanbus/commit/c16ed93c9f977f480772be2db349201322245765))

- Configure beads sync
  ([`977cb6d`](https://github.com/AnthusAI/Kanbus/commit/977cb6d47bd5e13a66626fc47b52bab7a46ee20f))

- Format config loader
  ([`e2c2a6f`](https://github.com/AnthusAI/Kanbus/commit/e2c2a6f7af907f6bc568d23578eb13d91f2ef4e2))

- Improve dev environment and telemetry logging
  ([`26b5e05`](https://github.com/AnthusAI/Kanbus/commit/26b5e050d2ec6312ee2b559cb9e77d8d5d7beff3))

- Update kanbus issues
  ([`a956990`](https://github.com/AnthusAI/Kanbus/commit/a9569904aaf71dbc2b81f689a3884bbafdbae3b3))

### Documentation

- Clarify CONTRIBUTING template for agent usage
  ([`7d1f440`](https://github.com/AnthusAI/Kanbus/commit/7d1f440594e7b3010d094adda513faa6a98043f9))

- Fix Hello World example formatting and commands
  ([`5616b13`](https://github.com/AnthusAI/Kanbus/commit/5616b13371b0790ac885214d87f876c0df49174d))

- Remove .beads reference from CONTRIBUTING template
  ([`cd818b8`](https://github.com/AnthusAI/Kanbus/commit/cd818b8a3228a70eae1c60eba21c836813dd124d))

- Remove cargo run examples from CONTRIBUTING template
  ([`c5265a9`](https://github.com/AnthusAI/Kanbus/commit/c5265a9d34dfac4bb1bcb41beafd384e35fc031d))

### Features

- Add code block syntax validation
  ([`1452ace`](https://github.com/AnthusAI/Kanbus/commit/1452ace48af4c923340228de0f32f60d3d66574c))

- Add comment ID management and CRUD operations
  ([`e07c157`](https://github.com/AnthusAI/Kanbus/commit/e07c15769f1ab9e65efacce5b81f8237b486167c))

- Add diagram rendering and comment management
  ([`2889f0f`](https://github.com/AnthusAI/Kanbus/commit/2889f0fdc9697ff5b6d5f6f19d1ec21c76c46455))

- Add live search control to console toolbar
  ([`821ffae`](https://github.com/AnthusAI/Kanbus/commit/821ffae5c0215479ce994a416cba4f6694cc1e2d))

- Add support for Mermaid, PlantUML, and D2 diagrams
  ([`644a83b`](https://github.com/AnthusAI/Kanbus/commit/644a83b3af81bcd3883a04341fca1a41d586b211))

- Complete descendant display feature and PM updates
  ([`4ad3227`](https://github.com/AnthusAI/Kanbus/commit/4ad3227dfa52f7a785eafac09f7dd807ddd96aef))

- Console UI refinements and telemetry fix
  ([`985332c`](https://github.com/AnthusAI/Kanbus/commit/985332cb990fc99acdbd9da6a02d9f48f6e17dce))

- Directional detail panel transitions
  ([`381301a`](https://github.com/AnthusAI/Kanbus/commit/381301a0c69f48ea4236230499837818d114f176))

- Enhance issue display with comments and dependencies
  ([`fd5d1f4`](https://github.com/AnthusAI/Kanbus/commit/fd5d1f4c59ffa88025c3e5816ebaa018ea4c38be))

- Improve UI animations and board scrolling
  ([`90a1cbc`](https://github.com/AnthusAI/Kanbus/commit/90a1cbc8b656a5cac6d2cb9d7818913a9e0115c9))

### Testing

- Cover config validation and comments
  ([`406210f`](https://github.com/AnthusAI/Kanbus/commit/406210f31d0dbda7c9917b9e3f628b7e3e81d7fb))

- Cover external validator branches
  ([`8b62cda`](https://github.com/AnthusAI/Kanbus/commit/8b62cda8f8704b38bcbed6a0b7846307fb6e2138))

- Update binary name from kanbusr to kbs
  ([`6dfc008`](https://github.com/AnthusAI/Kanbus/commit/6dfc00889b10929b4540bc4d769e375947a0e4f3))


## v0.6.4 (2026-02-17)

### Bug Fixes

- Align loading pill fallback timing
  ([`9531770`](https://github.com/AnthusAI/Kanbus/commit/953177044ad7ca337ad27e21f221b62ad74e9e6d))

- Animation UX polishing
  ([`ff7d739`](https://github.com/AnthusAI/Kanbus/commit/ff7d73947173186e9ca4e64ff9faf0ad5191c858))

- Keep loading pill in empty/error states
  ([`85de2ac`](https://github.com/AnthusAI/Kanbus/commit/85de2acd0ebf21c97046b6f3c56b8af650981a36))

- Loading pill fade-out
  ([`bb07e63`](https://github.com/AnthusAI/Kanbus/commit/bb07e63ed808ce5751abbdcddf9d9a12fb2e351e))

- Loading pill unmount fallback
  ([`cb6fa02`](https://github.com/AnthusAI/Kanbus/commit/cb6fa026f32a9d088f2ef8051e55d6ec46046e41))


## v0.6.3 (2026-02-17)

### Bug Fixes

- Align operational commands with kbs
  ([`c158e28`](https://github.com/AnthusAI/Kanbus/commit/c158e28dada63203b0cebc7c43157a422c7d4718))

- Gate release on latest main
  ([`86426bf`](https://github.com/AnthusAI/Kanbus/commit/86426bf60c279c6e9795857624f3a13dec12e1af))

- Quote release guard step name
  ([`f6de26a`](https://github.com/AnthusAI/Kanbus/commit/f6de26a10c7d7b3b1d5eebc8c717ec944235daf2))

### Chores

- Gate amplify on full ci
  ([`098c4a1`](https://github.com/AnthusAI/Kanbus/commit/098c4a1b7864feba8626377d05d0d5043f49fe1f))

- Rename taskulus rust env var
  ([`d016a4f`](https://github.com/AnthusAI/Kanbus/commit/d016a4f6be1c76c967c9f9676fd7a5ec33aeb01a))

### Documentation

- Position python and rust parity
  ([`b74c841`](https://github.com/AnthusAI/Kanbus/commit/b74c841b6ad5a752d4552e55749d7c0c8c63f435))

- Update getting started for kbs kbsc
  ([`b448e22`](https://github.com/AnthusAI/Kanbus/commit/b448e22b259962a54b2405b07a0073eda1f4704d))


## v0.6.2 (2026-02-17)

### Bug Fixes

- Amplify build paths
  ([`c4e9dfa`](https://github.com/AnthusAI/Kanbus/commit/c4e9dfa0e4d8c26226b79cb8ed2755ae392f10cd))

- Release workflow python syntax
  ([`eab60d1`](https://github.com/AnthusAI/Kanbus/commit/eab60d12b33320d0ef53a5c15f5c661525d0a711))


## v0.6.1 (2026-02-17)

### Bug Fixes

- Avoid duplicate console telemetry hooks
  ([`795e14c`](https://github.com/AnthusAI/Kanbus/commit/795e14c69de34a7ac2c19a60c720992294277c15))

- Avoid moving console state before asset checks
  ([`afa2078`](https://github.com/AnthusAI/Kanbus/commit/afa20788319c54e7e56e01e79694097f2a7f81dc))

- Console telemetry and sse logging
  ([`b468e65`](https://github.com/AnthusAI/Kanbus/commit/b468e65f12bf618af45ebadcb1f3624b4c14508c))

- Update release and ci for kbs kbsc
  ([`1c5d2d6`](https://github.com/AnthusAI/Kanbus/commit/1c5d2d6ab2ffc57abfbf3c0557626729592e9695))

- Update rust feature steps for console port
  ([`a29f73e`](https://github.com/AnthusAI/Kanbus/commit/a29f73e5b65fc8018d6ce50140239b55bb76d581))

### Chores

- Add console port to configuration
  ([`f0eeaf6`](https://github.com/AnthusAI/Kanbus/commit/f0eeaf66c22a23ebb9fd135a8c68e3615468d641))

- Align docs and scripts with kbs and kbsc
  ([`4ed1543`](https://github.com/AnthusAI/Kanbus/commit/4ed15438f5f2a8fd808c6575ed56fdbf47c14142))

- Format rust telemetry code
  ([`4ec8ce8`](https://github.com/AnthusAI/Kanbus/commit/4ec8ce861bd5f5b8f00e9fbb6dc233dfea6db0a5))

- Remove beads artifacts
  ([`eb06b3d`](https://github.com/AnthusAI/Kanbus/commit/eb06b3d7f3171d4f61860972519d20282b0a18bc))


## v0.6.0 (2026-02-16)

### Chores

- Close CI and coverage tasks
  ([`fa14cbb`](https://github.com/AnthusAI/Kanbus/commit/fa14cbb6f64156073ea2a050cdd786870971958e))

- Close CI green task and parity testing epic
  ([`c7180d5`](https://github.com/AnthusAI/Kanbus/commit/c7180d593923019f4fec92fce648727a5248b85d))

- Close completed console and test tasks
  ([`c486e4d`](https://github.com/AnthusAI/Kanbus/commit/c486e4de59ee5580c7bc1fce6c63c77dbd8ae0a1))

- Close completed documentation and planning tasks
  ([`aec401e`](https://github.com/AnthusAI/Kanbus/commit/aec401e409b7353dac3b9eca3f232f3e6768c08d))

- Close config validation enforcement epic
  ([`9d23ec9`](https://github.com/AnthusAI/Kanbus/commit/9d23ec92efa5a553f8e8928cc67c7f1f201f8cb5))

- Close configuration spec task
  ([`9414bbd`](https://github.com/AnthusAI/Kanbus/commit/9414bbd936fff95e85f5220cbf892151f3a67d3c))

- Close console app move epic
  ([`aaf9e3b`](https://github.com/AnthusAI/Kanbus/commit/aaf9e3b621f30b57e15ca7b354dde36a1c9b9eb2))

- Close console app move epic
  ([`4f76fba`](https://github.com/AnthusAI/Kanbus/commit/4f76fbaf41b25de085a1f6d356c12dd4bd0ebbad))

- Close Docker binary smoke test tasks
  ([`1c5c21b`](https://github.com/AnthusAI/Kanbus/commit/1c5c21bc48816e0481d03f5b62bcbd7917c983f3))

- Close examples and agent instructions tasks
  ([`72e849a`](https://github.com/AnthusAI/Kanbus/commit/72e849add626f9dff16ff0d7a2d854c717cadb76))

- Close local mode root URLs epic
  ([`b82c65f`](https://github.com/AnthusAI/Kanbus/commit/b82c65f82395c0ac0511b693ff416ca8bccf2a86))

- Close rename Taskulus to Kanbus epic
  ([`d984262`](https://github.com/AnthusAI/Kanbus/commit/d98426216e91d0900a110f723f91703f867f53f1))

- File bug for concurrent issue closure in detail panel
  ([`fc4e459`](https://github.com/AnthusAI/Kanbus/commit/fc4e4593439918270faaf27acdc4f847665daee0))

- File bug for non-standard issue ID handling in kanbusr
  ([`8d305d8`](https://github.com/AnthusAI/Kanbus/commit/8d305d82265f560150d8bc6d8f93c54509132e1e))

- Update bug to reference test issue custom-uuid00
  ([`c5fbeb8`](https://github.com/AnthusAI/Kanbus/commit/c5fbeb801a0f8d9bca1c17f7c99d84f442921b9c))

### Documentation

- Clarify console works in local mode at root URL
  ([`3d7bc4b`](https://github.com/AnthusAI/Kanbus/commit/3d7bc4be203ebeb0b180fe7d9b1ab02210fc1127))

### Features

- Add ignore_paths configuration to Kanbus
  ([`f38724e`](https://github.com/AnthusAI/Kanbus/commit/f38724e28e8a2aa6a95a4efe025f684f417012ca))


## v0.5.0 (2026-02-15)

### Chores

- Sync issue ledger
  ([`8616c7e`](https://github.com/AnthusAI/Kanbus/commit/8616c7e414136c238e7be1246a109fb8fdbc0f07))

- Sync PyPI README with repo README
  ([`0ec6eca`](https://github.com/AnthusAI/Kanbus/commit/0ec6eca90de73232d45cee3c7707c643ce4ae74d))

### Features

- Share ui package and align site with console
  ([`22f0fe3`](https://github.com/AnthusAI/Kanbus/commit/22f0fe367a8a1535b490f342d7f8460d2a61a289))


## v0.4.0 (2026-02-12)

### Features

- Align PyPI README with repo README
  ([`c6790a3`](https://github.com/AnthusAI/Kanbus/commit/c6790a34275d3794994d3d99607dbbf0a22e2ded))


## v0.3.0 (2026-02-12)

### Bug Fixes

- Add license expression for PyPI build
  ([`f088740`](https://github.com/AnthusAI/Kanbus/commit/f088740f9dbebf59bc93f0456c2fd4d3d07cacb9))


## v0.2.0 (2026-02-12)

### Features

- Add PyPI project metadata
  ([`b73a634`](https://github.com/AnthusAI/Kanbus/commit/b73a6342c36dd47bac32cf588b6534363e89b7ff))


## v0.1.0 (2026-02-12)

- Initial Release
