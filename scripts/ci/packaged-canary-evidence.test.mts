import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { verifyMacArtifacts } from './packaged-canary-evidence.mts';

// Turns red if --dir accidentally produces archives or full packaging loses/writes invalid targets.
test('APP archive absence and FULL DMG/ZIP presence are separate observable contracts', () => {
  const cwd = mkdtempSync(join(tmpdir(), 'TEST-packaged-targets-'));
  try {
    mkdirSync(join(cwd, 'release/mac-arm64/Agent Teams AI.app'), { recursive: true });
    assert.equal(verifyMacArtifacts(cwd, 'app', 'arm64').archives.length, 0);
    assert.throws(() => verifyMacArtifacts(cwd, 'full', 'arm64'));
    const dmg = join(cwd, 'release/Agent.Teams.AI-2.17.4-arm64.dmg');
    const zip = join(cwd, 'release/Agent.Teams.AI-2.17.4-arm64-mac.zip');
    const trailer = Buffer.alloc(512);
    trailer.write('koly');
    writeFileSync(dmg, trailer);
    writeFileSync(zip, Buffer.from([0x50, 0x4b, 0x03, 0x04]));
    assert.equal(verifyMacArtifacts(cwd, 'full', 'arm64').archives.length, 2);
    assert.throws(() => verifyMacArtifacts(cwd, 'app', 'arm64'));
    writeFileSync(zip, 'invalid zip');
    assert.throws(() => verifyMacArtifacts(cwd, 'full', 'arm64'));
    writeFileSync(zip, Buffer.from([0x50, 0x4b, 0x03, 0x04]));
    writeFileSync(dmg, Buffer.alloc(512));
    assert.throws(() => verifyMacArtifacts(cwd, 'full', 'arm64'));
  } finally {
    rmSync(cwd, { recursive: true, force: true });
  }
});
