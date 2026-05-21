function robot(state, unit) {
  // Lightweight persistent memory for micro-loop avoidance and momentum
  if (!globalThis.__rrMemory) globalThis.__rrMemory = {};
  const oldMem = globalThis.__rrMemory[unit.id] || { prev: null, prev2: null, lastDirStr: null };
  const lastDir = oldMem.prev ? oldMem.prev.directionTo(unit.coords) : null;
  const lastDirStr = lastDir ? lastDir.toString() : null;
  // Write updated mem (prev track), retain lastDirStr for momentum use this turn
  const mem = {
    prev2: oldMem.prev || null,
    prev: unit.coords,
    lastDirStr
  };
  globalThis.__rrMemory[unit.id] = mem;

  // Helper utilities
  function getObj(coords) { return state.objByCoords(coords); }
  function isFree(coords) { return !getObj(coords); }
  function neighbor(coords, dir) {
    const d = dir.toCoords;
    return new Coords(coords.x + d.x, coords.y + d.y);
  }
  function isSpawn(coords) {
    try { return coords.isSpawn && coords.isSpawn(); } catch (_) { return false; }
  }
  function eqCoords(a, b) { return !!(a && b) && a.x === b.x && a.y === b.y; }

  function countNearby(team, center, radius) {
    let count = 0;
    for (let dx = -radius; dx <= radius; dx++) {
      for (let dy = -radius; dy <= radius; dy++) {
        if (Math.abs(dx) + Math.abs(dy) > radius) continue;
        const c = new Coords(center.x + dx, center.y + dy);
        const obj = state.objByCoords(c);
        if (obj && obj.team === team && obj.id !== unit.id) count++;
      }
    }
    return count;
  }

  // Extended danger: consider immediate adjacency more heavily, but also nearby (radius 2)
  function extendedDanger(coords) {
    const adjE = countNearby(state.otherTeam, coords, 1);
    const near2E = countNearby(state.otherTeam, coords, 2) - adjE;

    const adjA = countNearby(state.ourTeam, coords, 1);
    const near2A = countNearby(state.ourTeam, coords, 2) - adjA;

    // Weights tuned to prioritize safety; allies offset risk
    return (adjE * 1.5 + near2E * 0.5) - (adjA * 1.0 + near2A * 0.25);
  }

  function scoreTile(coords, progressTerm = 0, dangerWeight = 100) {
    const danger = extendedDanger(coords);
    const spawnPenalty = isSpawn(coords) ? 20 : 0; // reduced from 50 to be less rigid
    // Anti-oscillation: avoid moving back to the tile from two turns ago (bounce)
    const bouncePenalty = eqCoords(coords, mem.prev2) ? 2 : 0;
    // Lower score is better
    return danger * dangerWeight + spawnPenalty + bouncePenalty + progressTerm;
  }

  // candidates: array of Direction; optionally allow staying if it's safer
  function chooseBestBySafety(candidates, allowStay = true, dangerWeight = 100) {
    let bestDir = null;
    let bestScore = Infinity;

    // Compare candidate moves
    for (const d of candidates) {
      const dest = neighbor(unit.coords, d);
      if (!isFree(dest)) continue;
      const momentumBonus = (mem.lastDirStr && d.toString() === mem.lastDirStr) ? -0.25 : 0;
      const score = scoreTile(dest, momentumBonus, dangerWeight);
      if (score < bestScore) {
        bestScore = score;
        bestDir = d;
      }
    }

    // Consider staying if allowed (require clear margin to avoid stalling)
    if (allowStay) {
      const stayScore = scoreTile(unit.coords, 0, dangerWeight);
      if (stayScore + 1 <= bestScore) {
        return null; // clearly safer to stay
      }
    }

    return bestDir ? Action.move(bestDir) : null;
  }

  function tryRetreat(awayDir, dangerWeight = 100, allowStay = true) {
    const dirs = [awayDir, awayDir.rotateCw, awayDir.rotateCcw];
    return chooseBestBySafety(dirs, allowStay, dangerWeight);
  }

  // Greedy advance: when advantaged, push toward target without heavy safety scoring
  function greedyAdvance(primaryDir) {
    let d = primaryDir;
    for (let i = 0; i < 4; i++) {
      const dest = neighbor(unit.coords, d);
      if (isFree(dest)) return Action.move(d);
      d = d.rotateCw;
    }
    return null;
  }

  // Prefer forward, then small sidesteps; pick free tiles that are safer and reduce distance
  function chooseBestAdvance(target, primaryDir, dangerWeight = 100, allowStayWhenAdvancing = false) {
    // Evaluate all four directions; still bias original primary and sidesteps via momentum/progress
    const dirs = [primaryDir, primaryDir.rotateCw, primaryDir.rotateCcw, primaryDir.rotateCw.rotateCw];

    let best = null;
    let bestScore = Infinity;
    for (const d of dirs) {
      const dest = neighbor(unit.coords, d);
      if (!isFree(dest)) continue;

      const newDist = dest.walkingDistanceTo(target.coords);
      // Encourage moving to attack range (distance 1)
      const closeBonus = (newDist === 1) ? -1.0 : 0;
      // Small preference for ally support nearby when advancing
      const allySupport = countNearby(state.ourTeam, dest, 1) * -0.25;
      // Momentum bias
      const momentumBonus = (mem.lastDirStr && d.toString() === mem.lastDirStr) ? -0.25 : 0;

      const score = scoreTile(dest, newDist + closeBonus + allySupport + momentumBonus, dangerWeight);
      if (score < bestScore) {
        best = d;
        bestScore = score;
      }
    }

    // If moving is worse than staying, don't move unless staying is disallowed
    const stayScore = scoreTile(unit.coords, unit.coords.walkingDistanceTo(target.coords), dangerWeight);
    if (best !== null && (bestScore < stayScore || !allowStayWhenAdvancing)) {
      return Action.move(best);
    }
    return null;
  }

  const enemies = state.objsByTeam(state.otherTeam);
  if (!enemies || enemies.length === 0) {
    // Fallback behavior if no enemies found
    return Action.move(Direction.East);
  }

  // Immediate adjacency handling: attack with focus fire
  const adjacentEnemies = enemies.filter(e => unit.coords.distanceTo(e.coords) === 1);
  const enemyClose = countNearby(state.otherTeam, unit.coords, 1);
  const allyClose = countNearby(state.ourTeam, unit.coords, 1);
  // Dynamic danger weighting and stay policy: treat slight advantage as advantaged to push vs simple bots
  const advantaged = (allyClose + 1) >= enemyClose && (unit.health == null || unit.health > 2);
  const dangerW = advantaged ? 40 : 130;

  if (adjacentEnemies.length > 0) {
    // Score adjacent enemies: lower health, and more allied adjacency (focus fire)
    const scored = adjacentEnemies.map(e => {
      const allyAdj = countNearby(state.ourTeam, e.coords, 1);
      const health = (e.health == null ? 0 : e.health);
      // Lower is better: prioritize low health and higher allied adjacency
      const score = health - allyAdj * 0.75;
      return { e, score };
    });
    const targetAdj = _.minBy(scored, s => s.score).e;
    const dirToTargetAdj = unit.coords.directionTo(targetAdj.coords);

    const badlyOutnumbered = enemyClose > allyClose;
    const lowHealth = unit.health != null && unit.health <= 2;

    if (badlyOutnumbered || lowHealth) {
      const retreat = tryRetreat(dirToTargetAdj.opposite, dangerW, true);
      if (retreat) return retreat;
      // If stuck, attack the focus target adjacent
      return Action.attack(dirToTargetAdj);
    }
    // Otherwise, engage the focus target adjacent
    return Action.attack(dirToTargetAdj);
  }

  // Select a target to move toward: nearest by walking distance, tie-breaker by lower health and isolation
  const target = _.minBy(enemies, e => {
    const distTerm = unit.coords.walkingDistanceTo(e.coords) * 10;
    const healthTerm = (e.health || 0);
    // Prefer isolated enemies (fewer allies nearby)
    const supportPenalty = countNearby(state.ourTeam, e.coords, 2); // lower is better
    return distTerm + healthTerm + supportPenalty;
  });

  const dirToTarget = unit.coords.directionTo(target.coords);

  // If we are outnumbered nearby and relatively low health, kite away
  if (enemyClose > allyClose && unit.health != null && unit.health <= 3) {
    const retreat = tryRetreat(dirToTarget.opposite, dangerW, true);
    if (retreat) return retreat;
    // If stuck, proceed cautiously (fall through)
  }

  // When advantaged, push aggressively with greedy advance to avoid hesitation
  if (advantaged) {
    const g = greedyAdvance(dirToTarget);
    if (g) return g;
  }

  // Advance toward target with safety checks; do not allow staying while advancing to reduce stalling
  const advance = chooseBestAdvance(target, dirToTarget, dangerW, false);
  if (advance) return advance;

  // If we can't advance (blocked), try a safe sidestep opposite of target's angle
  const sidestep =
    tryRetreat(dirToTarget.rotateCw.opposite, dangerW, !advantaged) ||
    tryRetreat(dirToTarget.rotateCcw.opposite, dangerW, !advantaged);
  if (sidestep) return sidestep;

  // Avoid stalling at the end: do not choose to stay here
  // Absolute fallback
  return Action.move(Direction.East);
}