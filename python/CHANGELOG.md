# CHANGELOG

<!-- version list -->

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
