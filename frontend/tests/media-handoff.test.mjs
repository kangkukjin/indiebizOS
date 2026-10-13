import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handoff } from '../src/lib/media/handoff.ts';

test('handoff waits for target playback before pausing source', async () => {
  let paused = false, polls = 0;
  const player = { currentSrc: 'https://media.test/song.mp3', currentTime: 37, volume: .5, pause() { paused = true; } };
  const s = await handoff(player, 'phone', {
    async create(body) { assert.equal(body.content.position_s, 37); return { session_id: 's' }; },
    async status() { assert.equal(paused, false); return { session_id: 's', content: { playing: ++polls === 2 } }; },
    async end() { assert.fail('successful handoff must keep the target alive'); },
  }, { pollMs: 0 });
  assert.equal(s.session_id, 's'); assert.equal(paused, true);
});

test('handoff failure ends only the target and keeps the source playing', async () => {
  let ended = false;
  const player = { currentSrc: 'https://media.test/song.mp3', currentTime: 37, volume: .5, pause() { assert.fail('source paused'); } };
  await assert.rejects(handoff(player, 'phone', {
    async create() { return { session_id: 's' }; },
    async status() { return { state: 'ended', end_reason: 'decode_failed' }; },
    async end() { ended = true; },
  }), /decode_failed/);
  assert.equal(ended, true);
});
