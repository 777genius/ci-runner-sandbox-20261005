import assert from 'node:assert/strict';
import {
  closeSync,
  mkdirSync,
  openSync,
  readSync,
  readdirSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { assertFullPackagedGate } from './packaged-ci-policy.mts';

export const PRODUCT_SHA = '78b7a1d6bb4cd88e0a2c9bde2244959f7295ec33';

function signature(path: string, position: number): Buffer {
  const fd = openSync(path, 'r');
  try {
    const bytes = Buffer.alloc(4);
    assert.equal(readSync(fd, bytes, 0, 4, position), 4, `Short package header: ${path}`);
    return bytes;
  } finally {
    closeSync(fd);
  }
}

export function verifyMacArtifacts(
  cwd: string,
  scope: string | undefined,
  arch: string | undefined
) {
  assert.ok(scope === 'app' || scope === 'full', 'Unknown TEST scope');
  assert.ok(arch === 'arm64' || arch === 'x64', 'Unknown TEST architecture');
  const release = join(cwd, 'release');
  const bundle = join(release, arch === 'arm64' ? 'mac-arm64' : 'mac', 'Agent Teams AI.app');
  assert.ok(statSync(bundle).isDirectory(), 'Packaged .app is missing');
  const archives = readdirSync(release).filter((name) => /\.(dmg|zip)$/i.test(name));
  if (scope === 'app') {
    assert.equal(archives.length, 0, 'APP scope unexpectedly created DMG/ZIP');
    return { scope, arch, bundle, archives: [] };
  }
  assert.equal(archives.length, 2, 'FULL scope must create exactly one DMG and one ZIP');
  const dmg = archives.find(
    (name) => name.startsWith('Agent.Teams.AI-') && name.endsWith(`-${arch}.dmg`)
  );
  const zip = archives.find(
    (name) => name.startsWith('Agent.Teams.AI-') && name.endsWith(`-${arch}-mac.zip`)
  );
  assert.ok(dmg, 'Architecture-specific DMG is missing');
  assert.ok(zip, 'Architecture-specific ZIP is missing');
  const dmgPath = join(release, dmg);
  const zipPath = join(release, zip);
  const dmgSize = statSync(dmgPath).size;
  const zipSize = statSync(zipPath).size;
  assert.ok(dmgSize >= 512, 'DMG is too short for a real UDIF trailer');
  assert.equal(
    signature(dmgPath, dmgSize - 512).toString('ascii'),
    'koly',
    'DMG UDIF trailer missing'
  );
  assert.deepEqual(
    signature(zipPath, 0),
    Buffer.from([0x50, 0x4b, 0x03, 0x04]),
    'ZIP header missing'
  );
  return {
    scope,
    arch,
    bundle,
    archives: [
      { name: dmg, bytes: dmgSize },
      { name: zip, bytes: zipSize },
    ],
  };
}

function main(): void {
  if (process.argv[2] === 'artifacts') {
    assert.equal(process.env.PRODUCT_SHA, PRODUCT_SHA, 'Unexpected product candidate');
    assert.match(process.env.PR_HEAD_SHA ?? '', /^[a-f0-9]{40}$/i, 'Missing TEST PR head identity');
    const evidence = {
      testOnly: true,
      productSha: PRODUCT_SHA,
      prHeadSha: process.env.PR_HEAD_SHA,
      runId: process.env.GITHUB_RUN_ID,
      ...verifyMacArtifacts(process.cwd(), process.env.PACKAGED_SCOPE, process.env.CANARY_ARCH),
    };
    const directory = process.env.EVIDENCE_DIR;
    assert.ok(directory, 'Missing TEST evidence directory');
    mkdirSync(directory, { recursive: true });
    writeFileSync(join(directory, 'packages.json'), JSON.stringify(evidence, null, 2) + '\n');
    console.log(JSON.stringify(evidence));
    return;
  }
  if (process.argv[2] === 'gate') {
    // Reuse the immutable product policy predicate; this TEST matrix is explicitly a Mac slice.
    assertFullPackagedGate({
      scope: process.env.PACKAGED_SCOPE,
      scopeResult: process.env.SCOPE_RESULT,
      packagedResult: process.env.PACKAGED_RESULT,
    });
    console.log(
      'TEST Mac slice FULL gate passed for both architectures. Other platforms require product CI.'
    );
    return;
  }
  throw new Error('Usage: node scripts/ci/packaged-canary-evidence.mts artifacts|gate');
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) main();
