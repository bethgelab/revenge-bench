// RobotRumble JS bot - Focus-fire with cohesion, isolation targeting, threat-aware micro, and interception
// Round 2.6 improvements by gpt-5
//
// Strategy updates:
// - Targeting: team total distance + isolation penalty (favor isolated targets).
// - Cohesion: soft attraction to allies to keep formation tight.
// - Rally mode: if alone and not threatened, move toward nearest ally (disabled in late game).
// - Late-game aggression: after a turn threshold, increase push toward goal and relax fallback threat tolerance.
// - Interception: predict enemy motion using last-turn velocity and aim ahead to intercept rather than chase directly.
// - Micro:
//   - Attack lowest-health adjacent enemy.
//   - Avoid tiles adjacent to 3+ enemies at all times.
//   - Additional safety: avoid stepping into tiles with 2+ enemies when alone and still alone there (relaxed late if strictly reducing goal distance).
//   - Retreat when surrounded or lonely-under-threat.
//   - Sidestep + backstep evaluation.
//   - Safe fallback advance if no improving move is found.
//
// Tunable parameters below.

let targetId = null;

// For interception: track enemy positions across turns
let lastEnemyPosPrev = {};  // id -> {x,y,turn}
let lastEnemyPos = {};      // id -> {x,y,turn}

const DIRECTIONS = [Direction.North, Direction.East, Direction.South, Direction.West];

// Tunable parameters
const DISTANCE_WEIGHT = 0.9;         // base weight for reducing distance to primary goal
const THREAT_WEIGHT = 1.8;           // penalty per additional adjacent enemy on candidate tile
const SPAWN_PENALTY = 2.5;           // avoid stepping onto spawn tiles (late game reduces this)
const COHESION_WEIGHT = 0.16;        // favor staying closer to allies (sum of distances change)
const ISOLATION_WEIGHT = 0.7;        // in target selection: penalty per adjacent enemy around candidate target
const RALLY_DISTANCE_WEIGHT = 1.2;   // when rallying to allies, stronger pull
const AVOID_3_THREAT = true;         // hard-avoid stepping to tiles adjacent to 3+ enemies
const LATE_GAME_TURN = 60;           // after this turn, increase aggression
const LATE_DIST_BONUS = 1.2;         // extra distance weight in late game
const LATE_THREAT_MULT = 0.85;       // reduce threat weight in late game
const LATE_COHESION_MULT = 0.5;      // reduce cohesion weight in late game
const LATE_SPAWN_MULT = 0.6;         // reduce spawn penalty in late game
const INTERCEPT_MAX_STEPS = 4;       // cap on how far ahead to lead
const INTERCEPT_SCALE = 0.33;        // fraction of current distance used to choose lead steps

function initTurn(state) {
  // Roll enemy position history for interception
  lastEnemyPosPrev = lastEnemyPos;
  lastEnemyPos = {};
  const enemiesForCache = state.objsByTeam(state.otherTeam) || [];
  for (const e of enemiesForCache) {
    lastEnemyPos[e.id] = { x: e.coords.x, y: e.coords.y, turn: state.turn };
  }

  // Clear target if gone
  if (targetId) {
    const stillExists = state.objById(targetId);
    if (!stillExists) {
      targetId = null;
    }
  }

  // Select team-centric target if needed
  if (!targetId) {
    const allies = state.objsByTeam(state.ourTeam) || [];
    const enemies = state.objsByTeam(state.otherTeam) || [];

    if (enemies.length === 0) {
      targetId = null;
      return;
    }

    const totalDistanceForTeam = (enemy) =>
      _.sum(allies.map(ally => ally.coords.distanceTo(enemy.coords)));

    // Isolation: count adjacent enemies around the enemy (their allies)
    const enemySupport = (enemy) => {
      let cnt = 0;
      for (const dir of DIRECTIONS) {
        const n = enemy.coords.add(dir);
        const obj = state.objByCoords(n);
        if (obj && obj.team === state.otherTeam) cnt += 1;
      }
      return cnt;
    };

    // Combined score: distance + isolation penalty; tie-break on lower health
    const score = (enemy) => {
      const dist = totalDistanceForTeam(enemy);
      const iso = enemySupport(enemy);
      const hp = enemy.health ?? 9999;
      return dist + ISOLATION_WEIGHT * iso + 0.01 * hp;
    };

    const best = _.minBy(enemies, score);
    targetId = best ? best.id : null;
  }
}

function getAdjacentEnemies(state, unit) {
  const here = unit.coords;
  const out = [];
  for (const dir of DIRECTIONS) {
    const n = here.add(dir);
    const obj = state.objByCoords(n);
    if (obj && obj.team === state.otherTeam) {
      out.push({ dir, enemy: obj });
    }
  }
  return out;
}

function countAdjacentEnemiesAt(state, coords) {
  let cnt = 0;
  for (const dir of DIRECTIONS) {
    const n = coords.add(dir);
    const obj = state.objByCoords(n);
    if (obj && obj.team === state.otherTeam) cnt += 1;
  }
  return cnt;
}

function countAdjacentAlliesAt(state, coords) {
  let cnt = 0;
  for (const dir of DIRECTIONS) {
    const n = coords.add(dir);
    const obj = state.objByCoords(n);
    if (obj && obj.team === state.ourTeam) cnt += 1;
  }
  return cnt;
}

function isOccupied(state, coords) {
  return !!state.idByCoords(coords);
}

function isOccupiedByAlly(state, coords) {
  const obj = state.objByCoords(coords);
  return !!(obj && obj.team === state.ourTeam);
}

function isSpawn(coords) {
  return (coords.isSpawn && coords.isSpawn()) ? true : false;
}

function safeToStep(state, coords) {
  if (isOccupied(state, coords)) return false;
  // Note: stepping onto spawn allowed; scoring applies SPAWN_PENALTY (reduced late).
  return true;
}

function sumAllyDistancesAt(state, coords, selfId) {
  const allies = state.objsByTeam(state.ourTeam) || [];
  let sum = 0;
  for (const ally of allies) {
    if (ally.id === selfId) continue;
    sum += coords.distanceTo(ally.coords);
  }
  return sum;
}

function nearestAlly(state, unit) {
  const allies = state.objsByTeam(state.ourTeam) || [];
  let best = null;
  let bestDist = Infinity;
  for (const ally of allies) {
    if (ally.id === unit.id) continue;
    const d = unit.coords.distanceTo(ally.coords);
    if (d < bestDist) {
      bestDist = d;
      best = ally;
    }
  }
  return { ally: best, dist: bestDist };
}

function predictedEnemyCoordsFor(state, enemyObj, fromCoords) {
  const cur = lastEnemyPos[enemyObj.id];
  const prev = lastEnemyPosPrev[enemyObj.id];
  if (!cur || !prev) return enemyObj.coords;

  // Use last-turn delta only if consecutive turns
  if ((cur.turn ?? 0) !== (prev.turn ?? -1) + 1) {
    return enemyObj.coords;
  }
  const dx = cur.x - prev.x;
  const dy = cur.y - prev.y;

  // If no motion detected, no prediction
  if (dx === 0 && dy === 0) return enemyObj.coords;

  // Lead steps based on distance to enemy
  const dist = fromCoords.distanceTo(enemyObj.coords);
  const leadSteps = Math.max(1, Math.min(INTERCEPT_MAX_STEPS, Math.floor(dist * INTERCEPT_SCALE)));

  return new Coords(enemyObj.coords.x + dx * leadSteps, enemyObj.coords.y + dy * leadSteps);
}

function robot(state, unit) {
  // Opportunistic adjacent attack: pick lowest-health adjacent enemy
  const adj = getAdjacentEnemies(state, unit);
  if (adj.length > 0) {
    const best = _.minBy(adj, pair => pair.enemy.health ?? 9999);
    return Action.attack(best.dir);
  }

  // Quick target bootstrap if needed
  if (!targetId) {
    const enemies = state.objsByTeam(state.otherTeam) || [];
    if (enemies.length > 0) {
      const closest = _.minBy(enemies, e => e.coords.distanceTo(unit.coords));
      if (closest) targetId = closest.id;
    }
  }

  const target = targetId ? state.objById(targetId) : null;

  if (!target) {
    // Conservative fallback: move off spawn if on one; otherwise pass
    if (isSpawn(unit.coords)) {
      for (const dir of DIRECTIONS) {
        const nc = unit.coords.add(dir);
        if (safeToStep(state, nc)) {
          return Action.move(dir);
        }
      }
    }
    return null;
  }

  // Visual aid in the UI to see what we're focusing
  debug.locate(target);

  const here = unit.coords;

  const distFnName = (here.walkingDistanceTo ? 'walkingDistanceTo' : 'distanceTo');
  const currentThreat = countAdjacentEnemiesAt(state, here);
  const currentAlliesAdj = countAdjacentAlliesAt(state, here);

  const late = (state.turn || 0) >= LATE_GAME_TURN;

  const { ally: nearest, dist: nearestDist } = nearestAlly(state, unit);
  // Rally disabled in late game to push engagements
  const rally = (!late && currentThreat === 0 && currentAlliesAdj === 0 && nearest && nearestDist >= 2);

  // Compute interception goal for the current target
  const tgt = target.coords;
  const predictedTgt = predictedEnemyCoordsFor(state, target, here);
  // Choose predicted goal if it brings us closer than chasing the current position (with a small bias)
  const directDist = here[distFnName](tgt);
  const predictedDist = here[distFnName](predictedTgt);
  const usePredicted = predictedDist + 0.0 <= directDist; // no penalty; prefer predicted if not worse
  const chaseGoal = usePredicted ? predictedTgt : tgt;

  const targetDist = here[distFnName](tgt);

  // Lonely under threat: try to step to reduce threat or move closer to allies
  if (currentThreat >= 1 && currentAlliesAdj === 0) {
    let bestDirLonely = null;
    let bestScoreLonely = Infinity;
    const currCohesion = sumAllyDistancesAt(state, here, unit.id);

    for (const dir of DIRECTIONS) {
      const next = here.add(dir);
      if (!safeToStep(state, next)) continue;

      const newThreat = countAdjacentEnemiesAt(state, next);
      if (AVOID_3_THREAT && newThreat >= 3) continue;

      const newAlliesAdj = countAdjacentAlliesAt(state, next);
      // Also avoid stepping into tiles with 2+ enemies if we'd still be alone
      if (newThreat >= 2 && newAlliesAdj === 0) continue;

      const newCohesion = sumAllyDistancesAt(state, next, unit.id);
      const newDist = next[distFnName](tgt);
      const spawnPenalty = isSpawn(next) ? SPAWN_PENALTY * (late ? LATE_SPAWN_MULT : 1.0) : 0;

      const score = (newThreat * 2.0) + 0.5 * (newCohesion - currCohesion) + 0.15 * (newDist - targetDist) + spawnPenalty;

      if (score < bestScoreLonely) {
        bestScoreLonely = score;
        bestDirLonely = dir;
      }
    }

    if (bestDirLonely !== null) {
      const next = here.add(bestDirLonely);
      const newThreat = countAdjacentEnemiesAt(state, next);
      const newCohesion = sumAllyDistancesAt(state, next, unit.id);

      // Move if it reduces threat OR keeps threat same but improves cohesion
      if (newThreat < currentThreat || (newThreat === currentThreat && newCohesion < sumAllyDistancesAt(state, here, unit.id))) {
        return Action.move(bestDirLonely);
      }
    }
    // Fall through to normal logic if no good lonely retreat found
  }

  // If we're surrounded (2+ adjacent enemies), try to retreat to reduce threat or increase ally support
  if (currentThreat >= 2) {
    let bestDir = null;
    let bestScore = Infinity;

    for (const dir of DIRECTIONS) {
      const next = here.add(dir);
      if (!safeToStep(state, next)) continue;

      const newThreat = countAdjacentEnemiesAt(state, next);
      if (AVOID_3_THREAT && newThreat >= 3) continue;

      const newAlliesAdj = countAdjacentAlliesAt(state, next);
      // Avoid stepping into tiles with 2+ enemies if we'd still be alone
      if (newThreat >= 2 && newAlliesAdj === 0 && currentAlliesAdj === 0) continue;

      const newDist = next[distFnName](tgt);
      const spawnPenalty = isSpawn(next) ? SPAWN_PENALTY * (late ? LATE_SPAWN_MULT : 1.0) : 0;

      // Prefer reducing threat; reward being near allies; mild penalty for increasing distance
      const score = (newThreat * 2) - newAlliesAdj + 0.2 * (newDist - targetDist) + spawnPenalty;

      if (score < bestScore) {
        bestScore = score;
        bestDir = dir;
      }
    }

    if (bestDir !== null) {
      const next = here.add(bestDir);
      const newThreat = countAdjacentEnemiesAt(state, next);
      const newAlliesAdj = countAdjacentAlliesAt(state, next);

      // Move if it reduces threat OR keeps threat the same but increases ally support
      if (newThreat < currentThreat || (newThreat === currentThreat && newAlliesAdj > currentAlliesAdj)) {
        return Action.move(bestDir);
      }
      // Otherwise fall through to normal movement logic
    }
  }

  // Normal movement toward goal with threat-aware + cohesion scoring
  // Goal can be the interception point, or nearest ally if in rally mode
  const goal = (rally && nearest) ? nearest.coords : chaseGoal;
  let primary = here.directionTo(goal);
  const cw = primary.rotateCw();
  const ccw = primary.rotateCcw();
  const back = cw.rotateCw(); // opposite direction
  const candidates = [primary, cw, ccw, back];
  const uniqDirs = _.uniqBy(candidates, d => d.name || d.toString());

  const currCohesion = sumAllyDistancesAt(state, here, unit.id);
  const goalDist = here[distFnName](goal);

  function moveCandidateScore(dir) {
    const next = here.add(dir);
    // Reject occupied tiles
    if (isOccupied(state, next) || isOccupiedByAlly(state, next)) return Infinity;

    const newThreat = countAdjacentEnemiesAt(state, next);
    if (AVOID_3_THREAT && newThreat >= 3) return Infinity;

    const newAlliesAdj = countAdjacentAlliesAt(state, next);

    const newGoalDist = next[distFnName](goal);
    // Safety: if stepping into 2+ adjacent enemies while we are currently alone and would remain alone:
    if (newThreat >= 2 && currentAlliesAdj === 0 && newAlliesAdj === 0) {
      // Allow only in late game if we strictly reduce distance to the goal
      if (!(late && newGoalDist < goalDist)) return Infinity;
    }

    const spawnPenalty = isSpawn(next) ? SPAWN_PENALTY * (late ? LATE_SPAWN_MULT : 1.0) : 0;
    const threatDelta = newThreat - currentThreat;

    // Cohesion: prefer reducing sum of distances to allies
    const newCohesion = sumAllyDistancesAt(state, next, unit.id);
    const cohesionDelta = newCohesion - currCohesion;

    const baseDistWeight = rally ? RALLY_DISTANCE_WEIGHT : DISTANCE_WEIGHT;
    const distWeight = baseDistWeight + (late ? LATE_DIST_BONUS : 0);
    const threatWeight = (late ? LATE_THREAT_MULT : 1.0) * THREAT_WEIGHT;
    const cohesionWeight = (late ? LATE_COHESION_MULT : 1.0) * COHESION_WEIGHT;

    // Lower is better
    return distWeight * (newGoalDist - goalDist)
         + spawnPenalty
         + threatWeight * threatDelta
         + cohesionWeight * cohesionDelta;
  }

  let bestDir = null;
  let bestScore = Infinity;
  for (const d of uniqDirs) {
    const score = moveCandidateScore(d);
    if (score < bestScore) {
      bestScore = score;
      bestDir = d;
    }
  }

  // Only move if we actually improve the overall score
  if (bestDir !== null && bestScore < 0) {
    return Action.move(bestDir);
  }

  // Safe fallback advance: if no improving move, try a cautious step that shortens/keeps distance to goal
  // and doesn't increase threat too much; more permissive late-game to break stalemates.
  for (const d of uniqDirs) {
    const next = here.add(d);
    if (!safeToStep(state, next)) continue;

    const newThreat = countAdjacentEnemiesAt(state, next);
    if (AVOID_3_THREAT && newThreat >= 3) continue;

    const newAlliesAdj = countAdjacentAlliesAt(state, next);
    const newGoalDist = next[distFnName](goal);

    // Relax "2+ enemies while alone" safety in late game only if we reduce goal distance
    if (newThreat >= 2 && currentAlliesAdj === 0 && newAlliesAdj === 0 && !(late && newGoalDist < goalDist)) {
      continue;
    }

    const threatTolerance = late ? 3 : 1; // allow slightly more exposure late
    const lateralAllowance = late ? 1 : 0; // allow small lateral movement late
    if (newGoalDist <= goalDist + lateralAllowance && newThreat <= currentThreat + threatTolerance) {
      return Action.move(d);
    }
  }

  // As last resort: if we're on a spawn, try to move off it even if it doesn't improve score
  if (isSpawn(here)) {
    for (const dir of DIRECTIONS) {
      const nc = here.add(dir);
      if (!isOccupied(state, nc)) {
        return Action.move(dir);
      }
    }
  }

  // No beneficial move available; pass
  return null;
}