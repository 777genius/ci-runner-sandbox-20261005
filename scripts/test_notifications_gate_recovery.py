#!/usr/bin/env python3
"""Disposable TEST-only decision recovery; never repairs or reruns native CI."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO = '777genius/ci-runner-sandbox-20261005'
PRODUCT = '777genius/agent-notifications'
PRODUCTION = 'e3e00016d3c6fd4887608d5aa5d62444ef4f5f74'
RUN = 37646308943
MERGE = '3ed6b2645913a7119a3dd11c5cc63da124460864'
HEAD = 'd039148ae27ca8f70eb38ccba6b20a1eae7e5aca'
BASE = '44b3b278d78e7f4913c4a83d57ff43fc4956baa9'
TREE = 'a94e13c58412f474e3e1159811d23897eb9dc070'
BLOBS = {
    'scripts/ci_macos_scope.py': 'ba82e31287048303c1a1431d1f7d4730e1c7f1bd',
    'scripts/ci_macos_scope_test.py': '993d07e6d5daa679ed5ef82acd7067dee140de16',
    '.github/workflows/ci-macos.yml': 'deacf95dbc03a092a09d6b9a8a44653993a3fcfe',
    '.github/workflows/install-recovery-e2e.yml': '695e04c9db4a7ba9f04e3e9620b957dba40c3068',
    'docs/CI_RUNNERS.md': 'd0dd10ae64c051260004236743ed971cacfa6a17',
}
FIXTURES = {
    '.github/workflows/navigation-windows-appsdk-build.yml': '62cdb1ca45aa121af53b78376a54f18802dbe98fb07ff556553d445cf578fd36',
    'tests/integration/windows_appsdk_build/README.md': 'ffdf4252d25a5f5e6e5b640dadb73e1504b12391304b3f3cbe3ab11130242b92',
    'tests/integration/windows_appsdk_build/SDKContract.cpp': 'c44bccb2276d3b8b8c71e414dd3f7896f068a0d8bc700a72e5671760bf0c97b9',
    'tests/integration/windows_appsdk_build/SDKContract.vcxproj': '5f8b8f42416fa2131d24a97708aab719f8b33530ac29e05d693b1b4d9e7cac4e',
    'tests/integration/windows_appsdk_build/packages.lock.json': 'a934c725e24227fbce8ec55b5fb338d18b4dd2731661fe3c426af893f177525c',
}
JOBS = {
    112877868377: ('Classify macOS CI scope', 'ubuntu-latest', None),
    112881152969: ('Test on macOS (1.25)', 'macos-15', 'go1.25.14'),
    112881152813: ('Test on macOS (1.26)', 'macos-26', 'go1.26.8'),
    112881152725: ('Swift notifier tests', 'macos-15', None),
}
GO_STEPS = [
    'Set up job', 'Checkout code', 'Set up Go', 'Display Go version',
    'Download dependencies', 'Verify dependencies', 'Run go vet',
    'Run go fmt check', 'Build binary', 'Run tests', 'Run install.sh unit tests',
    'Parallel group', 'Test binary execution (help)',
    'Qualify native selector bootstrap E2E (isolated, offline)',
    'Upload selector bootstrap evidence',
    'Test python/node installer runtime fallback (isolated, offline)',
    'Build sound preview binary', 'Build list-sounds binary', 'Check for system sounds',
    'Test one-line setup loader (isolated, offline)',
    'Run install.sh E2E tests (offline + mock)', 'Parallel group',
    'Run install.sh E2E diagnostics (real network)', 'Post Set up Go',
    'Post Checkout code', 'Complete job',
]
GO25_SKIPS = {
    'Qualify native selector bootstrap E2E (isolated, offline)',
    'Upload selector bootstrap evidence', 'Run install.sh E2E diagnostics (real network)',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_pr(pr):
    require(pr['number'] == 6 and pr['state'] == 'open' and pr['draft'] is True, 'PR state changed')
    require(pr['head']['sha'] == HEAD and pr['base']['sha'] == BASE, 'PR revision changed')
    require(pr['head']['ref'] == 'test/notifications-windows-draft-36053aa', 'PR head branch changed')
    require(pr['base']['ref'] == 'test/notifications-platform-base-36053aa', 'PR base branch changed')
    require(all(pr[s]['repo']['full_name'] == REPO for s in ('base', 'head')), 'PR repository changed')
    require([label['name'] for label in pr['labels']] == ['ci:full'], 'PR labels changed')


def validate_run(run):
    require(run['id'] == RUN and run['run_attempt'] == 1, 'Wrong run or attempt')
    require(run['repository']['full_name'] == run['head_repository']['full_name'] == REPO, 'Wrong run repository')
    require(run['head_sha'] == HEAD and run['head_branch'] == 'test/notifications-windows-draft-36053aa', 'Wrong run source')
    require(run['event'] == 'pull_request' and run['path'] == '.github/workflows/ci-macos.yml', 'Wrong workflow/event')
    require(run['workflow_id'] == 377408323, 'Wrong workflow ID')
    require(run['status'] == 'completed' and run['conclusion'] == 'failure', 'Original terminal failure changed')


def validate_jobs(response):
    jobs = response['jobs']
    require(response['total_count'] == len(jobs) == 4, 'Missing/unknown jobs or gate appeared')
    require({job['id'] for job in jobs} == set(JOBS), 'Wrong native job IDs')
    for job in jobs:
        name, label, version = JOBS[job['id']]
        require(job['run_id'] == RUN and job['run_attempt'] == 1 and job['head_sha'] == HEAD, 'Wrong job source')
        require(job['name'] == name and job['status'] == 'completed' and job['conclusion'] == 'success', 'Native job did not succeed')
        require(job['labels'] == [label] and job['runner_id'] > 0 and bool(job['runner_name']), 'Native runner missing/wrong profile')
        require(job['runner_name'].startswith('GitHub Actions '), 'Unexpected runner provider')
        steps = job['steps']
        expected = GO_STEPS if version else (
            ['Set up job', 'Checkout code', 'Run Swift tests', 'Post Checkout code', 'Complete job']
            if label == 'macos-15' else
            ['Set up job', 'Run actions/checkout@v7', 'Test conservative classification and installer mode contracts',
             'Classify exact PR revision (errors retain full CI)', 'Post Run actions/checkout@v7', 'Complete job'])
        require([step['name'] for step in steps] == expected, 'Mandatory step contract changed')
        for step in steps:
            allowed = 'skipped' if version == 'go1.25.14' and step['name'] in GO25_SKIPS else 'success'
            require(step['status'] == 'completed' and step['conclusion'] == allowed, 'Mandatory step failed/skipped')
    return {job['id']: job for job in jobs}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_api(endpoint, filename, out, calls, raw=False):
    require(not raw or endpoint in {f'repos/{REPO}/actions/jobs/{job_id}/logs' for job_id in JOBS},
            'Raw output is restricted to authenticated original job logs')
    for attempt in (1, 2):
        require(calls[0] < 24, 'API call budget exceeded')
        calls[0] += 1
        try:
            command = ['gh', 'api', '--method', 'GET', endpoint]
            if raw:
                command.append('--allow-escape-sequences')
            result = subprocess.run(command, capture_output=True, timeout=90)
            stderr = result.stderr.decode('utf-8', errors='replace')
            timed_out = False
        except subprocess.TimeoutExpired as error:
            stderr = (error.stderr or b'').decode('utf-8', errors='replace')
            result = None
            timed_out = True
        statuses = [int(code) for code in re.findall(r'\bHTTP[ \t]+(\d{3})\b', stderr)]
        status = statuses[-1] if statuses else None
        if any(code in (401, 403) for code in statuses):
            transient = False
        elif status is not None:
            transient = status == 429 or 500 <= status <= 599 or (
                status == 404 and re.fullmatch(r'repos/[^/]+/[^/]+/actions/jobs/\d+/logs', endpoint) is not None)
        else:
            transient = timed_out or re.search(
                r'(?i)connection reset by peer|TLS handshake timeout|i/o timeout|unexpected EOF|context deadline exceeded|temporary failure in name resolution',
                stderr) is not None
        # Redirect URLs can carry signed credentials. Never persist URLs or response bodies on failure.
        safe_stderr = re.sub(r'https?://\S+', '[redacted URL]', stderr)
        safe_stderr = re.sub(r'(?i)authorization:[^\r\n]*|bearer\s+\S+', '[redacted authorization]', safe_stderr)
        safe_stderr = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b', '[redacted token]', safe_stderr)
        safe_stderr = re.sub(r'(?i)((?:token|signature|credential|secret|password)\s*[=:]\s*)\S+', r'\1[redacted]', safe_stderr)
        retry = (timed_out or result.returncode != 0) and transient and attempt == 1 and calls[0] < 24
        diagnostic = {'apiCall': calls[0], 'attempt': attempt, 'endpoint': endpoint.split('?', 1)[0],
                      'exitCode': None if timed_out else result.returncode, 'timedOut': timed_out,
                      'httpStatus': status, 'redactedStderr': safe_stderr[:8192], 'retrying': retry}
        (out / f'{filename}.attempt-{attempt}.transport.json').write_text(json.dumps(diagnostic, indent=2) + '\n')
        if retry:
            time.sleep(1)
            continue
        if timed_out:
            raise RuntimeError('Read-only GitHub API request timed out; see redacted transport receipt')
        result.check_returncode()
        require(len(result.stdout) <= 16 << 20, 'API response exceeded receipt bound')
        (out / filename).write_bytes(result.stdout)
        return result.stdout if raw else json.loads(result.stdout)


def main():
    original = Path(sys.argv[1]).resolve()
    out = Path(os.environ['RECOVERY_RECEIPTS'])
    out.mkdir(exist_ok=False)
    calls = [0]

    def api(endpoint, filename, raw=False):
        return read_api(endpoint, filename, out, calls, raw)

    def git(*args):
        return subprocess.check_output(['git', *args], cwd=original).decode().strip()

    require(os.environ['GITHUB_REPOSITORY'] == REPO and os.environ['GITHUB_EVENT_NAME'] == 'push', 'Wrong recovery surface')
    require(os.environ['GITHUB_REF'] == 'refs/heads/test/notifications-gate-recovery-d039', 'Wrong recovery branch')
    require(git('rev-parse', 'HEAD') == MERGE and git('rev-parse', 'HEAD^{tree}') == TREE, 'Wrong immutable checkout')
    require(git('show', '-s', '--format=%P', MERGE).split() == [BASE, HEAD], 'Wrong original merge parents')
    pr = api(f'repos/{REPO}/pulls/6', 'pr-before.json')
    run = api(f'repos/{REPO}/actions/runs/{RUN}', 'run-before.json')
    response = api(f'repos/{REPO}/actions/runs/{RUN}/attempts/1/jobs?per_page=100', 'jobs-before.json')
    validate_pr(pr)
    validate_run(run)
    jobs = validate_jobs(response)
    commit = api(f'repos/{REPO}/git/commits/{MERGE}', 'original-merge.json')
    require(commit['tree']['sha'] == TREE and [p['sha'] for p in commit['parents']] == [BASE, HEAD], 'Remote merge binding mismatch')
    for path, blob in BLOBS.items():
        require(git('rev-parse', MERGE + ':' + path) == blob, 'Original policy blob mismatch')
        content = api(f'repos/{PRODUCT}/contents/{path}?ref={PRODUCTION}', 'production-' + path.replace('/', '_') + '.json')
        require(content['type'] == 'file' and content['sha'] == blob and content['path'] == path, 'Production policy blob mismatch')
    raw = subprocess.check_output(['git', 'diff', '--raw', '-z', '--no-abbrev', BASE, HEAD], cwd=original)
    (out / 'original-raw-diff.bin').write_bytes(raw)
    require(git('merge-base', BASE, HEAD) == BASE, 'Wrong merge base')
    require(git('diff', '--name-status', BASE, HEAD).splitlines() == ['A\t' + p for p in FIXTURES], 'Wrong fixture-only change')
    for path, digest in FIXTURES.items():
        require(hashlib.sha256((original / path).read_bytes()).hexdigest() == digest, 'Fixture content mismatch')
    for job_id, (_, label, version) in JOBS.items():
        log = api(f'repos/{REPO}/actions/jobs/{job_id}/logs', f'job-{job_id}.log', raw=True).decode('utf-8-sig')
        require(re.search(r'git log -1 --format=%H\r?\n[^\r\n]* ' + MERGE + r'\r?\n', log), 'Actual checkout SHA unproven')
        if version:
            require('Image: ' + label + '-arm64' in log and 'go version ' + version + ' darwin/arm64' in log, 'Wrong native Go/OS profile')
        elif label == 'macos-15':
            require('Image: macos-15-arm64' in log, 'Wrong Swift image')
        else:
            require('CI mode: full' in log, 'Original scope output not full')
        errors = re.findall(r'##\[error\][^\r\n]*', log)
        if version == 'go1.26.8':
            require(errors == ['##[error]Process completed with exit code 1.'], 'Unknown diagnostic failure')
            require('test_real_full_install' in log and 'Install completed successfully (exit code: 1, expected: 0)' in log, 'Undocumented diagnostic failure')
            diagnostic = '##[group]Run bash bin/install_e2e_test.sh --real-network-only'
            require(diagnostic in log and log.index(errors[0]) > log.index(diagnostic), 'Error outside nonblocking diagnostic')
        else:
            require(not errors, 'Native log error')
    event = {'action': 'labeled', 'number': 6, 'repository': {'full_name': REPO}, 'pull_request': pr}
    (out / 'authenticated-pr-event.json').write_text(json.dumps(event) + '\n')
    env = os.environ.copy()
    env.update(GITHUB_EVENT_NAME='pull_request', GITHUB_EVENT_PATH=str(out / 'authenticated-pr-event.json'),
               GITHUB_OUTPUT=str(out / 'classifier-output.txt'))
    classify = subprocess.run(['python3', 'scripts/ci_macos_scope.py', 'classify'], cwd=original, env=env, capture_output=True, text=True)
    (out / 'classifier.log').write_text(classify.stdout + classify.stderr)
    require(classify.returncode == 0 and (out / 'classifier-output.txt').read_text() == 'mode=full\n', 'Authenticated classifier failed')
    mode = (out / 'classifier-output.txt').read_text().strip().split('=', 1)[1]
    matrix = [jobs[i]['conclusion'] for i in (112881152969, 112881152813)]
    needs = {'scope': {'result': jobs[112877868377]['conclusion'], 'outputs': {'mode': mode}},
             'test': {'result': matrix[0] if matrix[0] == matrix[1] else 'failure'},
             'swift-test': {'result': jobs[112881152725]['conclusion']}}
    (out / 'derived-needs.json').write_text(json.dumps(needs, indent=2) + '\n')
    final_pr = api(f'repos/{REPO}/pulls/6', 'pr-final.json')
    final_run = api(f'repos/{REPO}/actions/runs/{RUN}', 'run-final.json')
    final_jobs = api(f'repos/{REPO}/actions/runs/{RUN}/attempts/1/jobs?per_page=100', 'jobs-final.json')
    validate_pr(final_pr)
    validate_run(final_run)
    validate_jobs(final_jobs)
    require(fingerprint(response) == fingerprint(final_jobs), 'Native evidence changed during recovery')
    env.update(CI_MODE=mode, NEEDS_JSON=json.dumps(needs))
    gate = subprocess.run(['python3', 'scripts/ci_macos_scope.py', 'gate', 'test', 'swift-test'], cwd=original, env=env, capture_output=True, text=True)
    (out / 'gate.log').write_text(gate.stdout + gate.stderr)
    validate_pr(api(f'repos/{REPO}/pulls/6', 'pr-after-gate.json'))
    validate_run(api(f'repos/{REPO}/actions/runs/{RUN}', 'run-after-gate.json'))
    receipt = {'scope': 'TEST recovered final decision only', 'originalRunID': RUN, 'originalAttempt': 1,
               'originalWorkflowConclusion': run['conclusion'], 'originalGateWasMissing': True,
               'originalRunNotRepaired': True, 'nativeJobsNotRerun': True, 'testHeadSHA': HEAD,
               'checkoutSHA': MERGE, 'checkoutTree': TREE, 'productionPolicyBlobSource': PRODUCTION,
               'laterProductionDependenciesNotQualifiedByThisCanary': True, 'apiCalls': calls[0],
               'derivedNeeds': needs, 'gateCommand': ['python3', 'scripts/ci_macos_scope.py', 'gate', 'test', 'swift-test'],
               'gateExitCode': gate.returncode, 'fixtureBinding': FIXTURES, 'policyBlobs': BLOBS,
               'recoveryRunID': os.environ['GITHUB_RUN_ID'], 'recoveryAttempt': os.environ['GITHUB_RUN_ATTEMPT'],
               'helperSourceSHA': os.environ['GITHUB_SHA'], 'nativeFingerprint': fingerprint(response),
               'evidenceSHA256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}}
    (out / 'recovered-gate-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(gate.stdout, end='')
    print('TEST recovered decision only; original workflow remains failure; no native rerun.')
    return gate.returncode


if __name__ == '__main__':
    sys.exit(main())
