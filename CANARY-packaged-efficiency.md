# TEST packaged Mac efficiency canary

This disposable repository proves the draft-to-full policy for immutable product
commit `a04d16b92e261e3648b54649db16b875344ed185`. Product code is checked out into
`product`; the root `window.ts` is a TEST classifier fixture and is never packaged.
The three source policy files and their source TypeScript configurations are
byte-identical to the product candidate. The product policy typecheck is retained
and a separate narrow TEST configuration checks the canary evidence helper.

The TEST workflow has only a pull-request trigger and exactly two Mac jobs:
Namespace macOS 15 ARM64 and GitHub macOS 15 Intel. It retains the native rebuild,
runtime/terminal staging, application build, architecture verification,
SQLite/PTY/MCP smokes, macOS 13 minimum and application smoke commands. Other
platforms remain covered separately by product PR #841. The TEST Mac slice gate
is explicitly not the product's five-platform merge gate.

`app` packages must contain an `.app` and no top-level DMG/ZIP. `full` packages
must contain the `.app`, architecture-specific DMG and ZIP, with UDIF/ZIP header
checks. Small per-job evidence records contain scope, product SHA, TEST PR head,
run ID, artifact names and byte sizes. Neither mode publishes a release.

Prepare two commits so the draft PR diff contains only `M window.ts`. Do not open
a PR for the base branch, change source policy on the head branch, or dispatch an
extra run. Source files are prepared in the current `test/packaged-efficiency`
checkout; no commit or push has been performed by the preparation agent.

```sh
cd /tmp/TEST-packaged-efficiency-canary
git config user.name iliya
git config user.email iliyazelenkog@gmail.com
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
git add .github/workflows/TEST-packaged-efficiency.yml .node-version scripts/ci/packaged-ci-*.mts scripts/ci/packaged-canary-*.mts tsconfig.json tsconfig.packaged-ci.json tsconfig.packaged-canary.json src/main/ipc/window.ts CANARY-packaged-efficiency.md
git commit -m 'test: prepare packaged Mac efficiency canary'
git branch test/packaged-efficiency-base
git push origin test/packaged-efficiency-base

git apply /tmp/TEST-packaged-efficiency-draft-window.patch
git diff --name-status test/packaged-efficiency-base
# Required output: M src/main/ipc/window.ts only.
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
git add src/main/ipc/window.ts
git commit -m 'test: exercise draft app-only packaged smoke'
git push origin test/packaged-efficiency

# ci:full already exists in this TEST repository; no label mutation is needed here.
gh pr create --repo 777genius/ci-runner-sandbox-20261005 --base test/packaged-efficiency-base --head test/packaged-efficiency --draft --title 'TEST packaged Mac efficiency on immutable product candidate' --body-file /tmp/TEST-packaged-efficiency-PR.md
```

Before committing, both identity outputs must begin with
`iliya <iliyazelenkog@gmail.com>`. Do not bypass hooks. After creating the PR,
attach its URL to the current Codex chat with `attach_artifact`.

Record the TEST PR number and immutable head. Wait for the first PR run to
finish. Both `TEST packaged smoke (darwin-*)` jobs must succeed; `TEST mac slice
full gate` must fail because the scope is `app`. Its failed overall conclusion
is expected evidence, not permission to ignore a failed Mac job.

```sh
test_canary_pr=$(gh pr view test/packaged-efficiency --repo 777genius/ci-runner-sandbox-20261005 --json number --jq .number)
test_canary_head=$(gh pr view "$test_canary_pr" --repo 777genius/ci-runner-sandbox-20261005 --json headRefOid --jq .headRefOid)
gh run list --repo 777genius/ci-runner-sandbox-20261005 --workflow TEST-packaged-efficiency.yml --branch test/packaged-efficiency --event pull_request --json databaseId,headSha,event,status,conclusion
gh run view APP_RUN_ID --repo 777genius/ci-runner-sandbox-20261005 --json jobs,headSha,event,conclusion
gh run download APP_RUN_ID --repo 777genius/ci-runner-sandbox-20261005 --dir /tmp/TEST-packaged-efficiency-app-evidence

# Only after complete APP evidence, add the label. Do not push another commit.
gh pr edit "$test_canary_pr" --repo 777genius/ci-runner-sandbox-20261005 --add-label ci:full
test "$(gh pr view "$test_canary_pr" --repo 777genius/ci-runner-sandbox-20261005 --json headRefOid --jq .headRefOid)" = "$test_canary_head"
gh run list --repo 777genius/ci-runner-sandbox-20261005 --workflow TEST-packaged-efficiency.yml --branch test/packaged-efficiency --event pull_request --json databaseId,headSha,event,status,conclusion
gh run view FULL_RUN_ID --repo 777genius/ci-runner-sandbox-20261005 --json jobs,headSha,event,conclusion
gh run download FULL_RUN_ID --repo 777genius/ci-runner-sandbox-20261005 --dir /tmp/TEST-packaged-efficiency-full-evidence
```

Require a fresh second run, both Mac jobs and the TEST gate successful, and the
same TEST PR head in both runs and all evidence records. In full evidence both
architectures must report DMG/ZIP with nonzero sizes. In app evidence both report
zero archives. Review logs for the actual `--dir` argument only in the app run.
Record run URLs and product PR #841's independent non-Mac evidence separately.
Do not claim this Mac slice proves all five product platforms.

Any app, terminal and native checks happen only on these TEST runner checkouts.
No live team, provider agent or real user project is launched. Do not change
runner capacity, repository protection, or publish a release.
