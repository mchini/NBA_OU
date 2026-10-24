import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { projectedWins, margin, outcome, summary, agreement, clinched } from '../assets/model.mjs';

const config = JSON.parse(readFileSync(new URL('../data/picks.json', import.meta.url), 'utf8'));
const history = JSON.parse(readFileSync(new URL('../data/history.json', import.meta.url), 'utf8'));
const records = history.snapshots.at(-1).records;
const sample = { line: 45.5, picks: { Met: { side: 'O', lock: true }, Sasso: { side: 'U', lock: false } } };

test('linear projection and opposite signs reproduce the requested +10/-10 example', () => {
  assert.equal(projectedWins({ wins: 30, losses: 10 }), 61.5);
  const team = { ...sample, line: 51 };
  assert.equal(margin(team, 'Met', { wins: 20, losses: 20 }), -10);
  assert.equal(margin(team, 'Sasso', { wins: 20, losses: 20 }), 10);
});
test('zero games and missing/invalid records stay pending, never 0-win predictions', () => {
  for (const record of [undefined, { wins: 0, losses: 0 }, { wins: -1, losses: 2 }, { wins: 60, losses: 30 }]) {
    assert.equal(projectedWins(record), null);
    assert.equal(outcome(margin(sample, 'Met', record)), 'pending');
  }
});
test('wins/losses without rounding determine outcome, with exact ties neutral', () => {
  assert.equal(outcome(.0001), 'correct');
  assert.equal(outcome(-.0001), 'wrong');
  assert.equal(outcome(1e-12), 'push');
  assert.equal(projectedWins({ wins: 0, losses: 5 }), 0);
  assert.equal(projectedWins({ wins: 5, losses: 0 }), 82);
});
test('all 150 imported picks have valid sides and explicit lock flags', () => {
  assert.equal(config.teams.length, 30);
  assert.deepEqual(config.players, ['Met', 'Sasso', 'Zach', 'Bill', 'House']);
  for (const team of config.teams) for (const player of config.players) {
    assert.ok(['O', 'U'].includes(team.picks[player].side));
    assert.equal(typeof team.picks[player].lock, 'boolean');
  }
});
test('all summaries partition picks correctly and lock denominators stay individual', () => {
  for (const player of config.players) {
    for (const locksOnly of [false, true]) {
      const s = summary(config, records, player, locksOnly);
      assert.equal(s.correct + s.wrong + s.push + s.pending, s.total);
      assert.equal(s.total, locksOnly ? config.teams.filter(t => t.picks[player].lock).length : 30);
      if (s.percentage !== null) assert.equal(s.percentage, 100 * s.correct / (s.correct + s.wrong));
    }
  }
});
test('ties and unplayed games do not enter success-rate denominators', () => {
  const c = { games: 82, teams: [{ ...sample, id: 'A', line: 41 }, { ...sample, id: 'B', line: 40 }, { ...sample, id: 'C', line: 42 }] };
  const s = summary(c, { A: { wins: 1, losses: 1 }, B: { wins: 1, losses: 1 }, C: { wins: 0, losses: 0 } }, 'Met');
  assert.deepEqual([s.correct, s.wrong, s.push, s.pending, s.percentage], [1, 0, 1, 1, 100]);
});
test('agreement is symmetric and independent of current results', () => {
  for (const a of config.players) for (const b of config.players) {
    assert.equal(agreement(config, a, b).same, agreement(config, b, a).same);
    assert.equal(agreement(config, a, a).same, 30);
  }
});
test('mathematical clinching uses possible final records, not projections', () => {
  assert.equal(clinched(sample, 'Met', { wins: 46, losses: 0 }), 'correct');
  assert.equal(clinched(sample, 'Sasso', { wins: 46, losses: 0 }), 'wrong');
  assert.equal(clinched(sample, 'Sasso', { wins: 0, losses: 37 }), 'correct');
  assert.equal(clinched(sample, 'Met', { wins: 1, losses: 0 }), null);
});
