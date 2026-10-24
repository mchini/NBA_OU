// The same calculations power the table, charts, history and tests.
export const EPSILON = 1e-9;

export function projectedWins(record, games = 82) {
  if (!record || !Number.isInteger(record.wins) || !Number.isInteger(record.losses)
      || record.wins < 0 || record.losses < 0 || record.wins + record.losses > games) return null;
  const played = record.wins + record.losses;
  return played ? games * record.wins / played : null;
}

export function margin(team, player, record, games = 82) {
  const projection = projectedWins(record, games);
  if (projection === null) return null;
  return (projection - team.line) * (team.picks[player].side === 'O' ? 1 : -1);
}

export function outcome(value) {
  return value === null ? 'pending' : value > EPSILON ? 'correct' : value < -EPSILON ? 'wrong' : 'push';
}

export function summary(config, records, player, locksOnly = false) {
  const result = { player, total: 0, correct: 0, wrong: 0, push: 0, pending: 0, margin: 0, averageMargin: null, percentage: null };
  for (const team of config.teams) {
    if (locksOnly && !team.picks[player].lock) continue;
    result.total++;
    const value = margin(team, player, records[team.id], config.games);
    result[outcome(value)]++;
    if (value !== null) result.margin += value;
  }
  const decided = result.correct + result.wrong;
  const projected = decided + result.push;
  result.percentage = decided ? 100 * result.correct / decided : null;
  result.averageMargin = projected ? result.margin / projected : null;
  return result;
}

export function agreement(config, first, second, locksOnly = false) {
  const teams = config.teams.filter(t => !locksOnly || (t.picks[first].lock && t.picks[second].lock));
  return { same: teams.filter(t => t.picks[first].side === t.picks[second].side).length, total: teams.length };
}

export function clinched(team, player, record, games = 82) {
  if (!record) return null;
  const maxWins = games - record.losses;
  const side = team.picks[player].side;
  if (record.wins > team.line) return side === 'O' ? 'correct' : 'wrong';
  if (maxWins < team.line) return side === 'U' ? 'correct' : 'wrong';
  return null;
}
