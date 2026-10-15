// Coordinated, risk-aware chaser with collision avoidance, weakest-adjacent targeting,
// ally support, and simple flee behavior with improved team targeting and hold-position logic.
// Round 3: add per-turn caching for threat/support, improved adjacent target choice, refined kiting,
// and tweaked cohesion thresholds.

let targetId = null

// Per-turn caches
let alliesList = []
let enemiesList = []
let threatCache = new Map() // key: "x,y" -> int (count of enemies within 1)
let supportCache = new Map() // key: "x,y" -> int (count of allies within 1)

function keyOf(c) {
  return `${c.x},${c.y}`
}

function inBounds(c) {
  const min = 1
  const max = MAP_SIZE - 2
  return c.x >= min && c.x <= max && c.y >= min && c.y <= max
}

// Count nearby within walking distance radius using per-turn lists for speed
function countNearby(state, coords, team, radius) {
  const objs = team === state.ourTeam ? alliesList : enemiesList
  let cnt = 0
  for (const o of objs) {
    if (o.coords.walkingDistanceTo(coords) <= radius) cnt++
  }
  return cnt
}

function threatAt(state, coords) {
  const k = keyOf(coords)
  if (threatCache.has(k)) return threatCache.get(k)
  const v = countNearby(state, coords, state.otherTeam, 1)
  threatCache.set(k, v)
  return v
}

function supportAt(state, coords) {
  const k = keyOf(coords)
  if (supportCache.has(k)) return supportCache.get(k)
  const v = countNearby(state, coords, state.ourTeam, 1)
  supportCache.set(k, v)
  return v
}

function initTurn(state) {
  // Reset per-turn caches and lists
  alliesList = state.objsByTeam(state.ourTeam) || []
  enemiesList = state.objsByTeam(state.otherTeam) || []
  threatCache = new Map()
  supportCache = new Map()

  // Clear target if it no longer exists
  if (targetId) {
    const t = state.objById(targetId)
    if (!t) targetId = null
  }
  // Pick a new shared target
  if (!targetId) {
    const enemies = enemiesList
    const allies = alliesList
    if (enemies && enemies.length) {
      // Minimize total walking distance of our team, prefer isolated enemies, lightly bias high HP up
      const score = (enemy) => {
        const allyDist = _.sum(allies.map(ally => ally.coords.walkingDistanceTo(enemy.coords)))
        const allyNear = supportAt(state, enemy.coords) // our allies near enemy
        const enemyNear = threatAt(state, enemy.coords) // their allies near enemy
        const hp = enemy.health ?? 0
        // Lower is better: close for us, many of us nearby (good), fewer of them nearby (bad), and lower hp
        return allyDist - 2 * allyNear + 1 * enemyNear + 0.5 * hp
      }
      const target = _.minBy(enemies, score)
      if (target) targetId = target.id
    }
  }
}

// Risk-aware forward move with hold-position when no safe improvement exists
function safeAdvanceToward(state, unit, goalCoords) {
  const primary = unit.coords.directionTo(goalCoords)
  const candidates = [primary, primary.rotateCw, primary.rotateCcw]
  const baseDist = unit.coords.walkingDistanceTo(goalCoords)

  const scored = candidates.map(dir => {
    const next = unit.coords.add(dir)
    const occupied = state.objByCoords(next)
    const dist = next.walkingDistanceTo(goalCoords)
    const thr = threatAt(state, next)
    const sup = supportAt(state, next)
    return { dir, next, occupied: Boolean(occupied), dist, thr, sup }
  })

  // If no safe step strictly improves distance and current tile is reasonably safe, hold
  const currThr = threatAt(state, unit.coords)
  const currSup = supportAt(state, unit.coords)
  const safeImprovers = scored.filter(s =>
    !s.occupied && inBounds(s.next) && s.dist < baseDist && s.thr <= s.sup + 1
  )
  if (safeImprovers.length === 0 && currThr <= currSup + 1) {
    return null
  }

  // Prefer reductions in distance that don't step into overwhelming threats
  let viable = scored.filter(s => !s.occupied && inBounds(s.next) && s.dist <= baseDist)
  let safe = viable.filter(s => s.thr <= s.sup + 1)
  const composite = s => (s.dist * 10) + Math.max(0, s.thr - s.sup)
  if (safe.length) {
    const best = _.minBy(safe, composite)
    return Action.move(best.dir)
  }
  if (viable.length) {
    const best = _.minBy(viable, composite)
    return Action.move(best.dir)
  }

  // If nothing improves distance, try any safe lateral step
  const lateralSafe = scored.filter(s => !s.occupied && inBounds(s.next) && s.thr <= s.sup + 1)
  if (lateralSafe.length) {
    const best = _.minBy(lateralSafe, composite)
    return Action.move(best.dir)
  }

  // Fallbacks
  const anyFree = scored.find(s => !s.occupied && inBounds(s.next))
  if (anyFree) return Action.move(anyFree.dir)

  const opp = primary.opposite
  const oppNext = unit.coords.add(opp)
  if (!state.objByCoords(oppNext) && inBounds(oppNext)) return Action.move(opp)

  return null
}

function fleeFrom(state, unit, threatCoords) {
  const away = unit.coords.directionTo(threatCoords).opposite
  const candidates = [away, away.rotateCw, away.rotateCcw]
  const baseDist = unit.coords.walkingDistanceTo(threatCoords)

  const scored = candidates.map(dir => {
    const next = unit.coords.add(dir)
    const occupied = state.objByCoords(next)
    const dist = next.walkingDistanceTo(threatCoords)
    const thr = threatAt(state, next)
    const sup = supportAt(state, next)
    return { dir, next, occupied: Boolean(occupied), dist, thr, sup }
  })

  // Prefer increasing distance and safer tiles
  const viable = scored.filter(s => !s.occupied && inBounds(s.next) && s.dist >= baseDist)
  const safe = viable.filter(s => s.thr <= s.sup + 1)
  if (safe.length) {
    const best = _.maxBy(safe, s => s.dist)
    return Action.move(best.dir)
  }
  if (viable.length) {
    const best = _.maxBy(viable, s => s.dist)
    return Action.move(best.dir)
  }

  const anyFree = scored.find(s => !s.occupied && inBounds(s.next))
  if (anyFree) return Action.move(anyFree.dir)

  // If blocked, at least face the threat
  return Action.attack(away.opposite)
}

function adjacentEnemies(state, unit) {
  const dirs = [Direction.North, Direction.South, Direction.East, Direction.West]
  const enemies = []
  for (const d of dirs) {
    const pos = unit.coords.add(d)
    const obj = state.objByCoords(pos)
    if (obj && obj.team && obj.team !== unit.team) {
      enemies.push({ obj, dir: d, pos })
    }
  }
  return enemies
}

function closestEnemyTo(state, coords) {
  const enemies = enemiesList
  if (!enemies || enemies.length === 0) return null
  return _.minBy(enemies, e => e.coords.walkingDistanceTo(coords))
}

function friendToSupport(state, unit, friendlyProx = 2) {
  const friends = alliesList || []
  let best = null
  let bestDist = Infinity
  for (const f of friends) {
    if (f.id === unit.id) continue
    const ce = closestEnemyTo(state, f.coords)
    if (!ce) continue
    const dFE = f.coords.walkingDistanceTo(ce.coords)
    if (dFE <= friendlyProx) {
      const dUF = unit.coords.walkingDistanceTo(f.coords)
      if (dUF < bestDist) {
        bestDist = dUF
        best = { friend: f, enemy: ce }
      }
    }
  }
  return best
}

function robot(state, unit) {
  const enemiesListLocal = enemiesList.length ? enemiesList : state.objsByTeam(state.otherTeam)
  if (!enemiesListLocal || enemiesListLocal.length === 0) return null

  let target = targetId ? state.objById(targetId) : null
  if (!target) target = _.minBy(enemiesListLocal, e => e.coords.walkingDistanceTo(unit.coords))
  if (!target) return null

  try { debug.locate(target) } catch (_) {}

  const adj = adjacentEnemies(state, unit)
  const closestEnemy = closestEnemyTo(state, unit.coords)
  const distToClosest = closestEnemy ? unit.coords.distanceTo(closestEnemy.coords) : Infinity

  const alliesNear2 = countNearby(state, unit.coords, state.ourTeam, 2)
  const enemiesNear2 = countNearby(state, unit.coords, state.otherTeam, 2)

  // Low health: finish weak adjacent if possible; otherwise, if local support is OK, trade; else flee
  if (unit.health != null && unit.health <= 2) {
    if (adj.length) {
      const killables = adj.filter(x => (x.obj.health ?? 999) <= 1)
      if (killables.length) {
        const weakestKill = _.minBy(killables, x => x.obj.health ?? 999)
        return Action.attack(weakestKill.dir)
      }
      const currThr = threatAt(state, unit.coords)
      const currSup = supportAt(state, unit.coords)
      if (currSup >= currThr) {
        const weakestAdj = _.minBy(adj, x => x.obj.health ?? 999)
        return Action.attack(weakestAdj.dir)
      }
    }
    if (closestEnemy) return fleeFrom(state, unit, closestEnemy.coords)
  }

  // If adjacent enemies exist, attack using a focus-fire aware heuristic
  if (adj.length) {
    const scored = adj.map(a => {
      const os = supportAt(state, a.pos) // our allies adjacent to that enemy (includes us)
      const ts = threatAt(state, a.pos)  // their allies adjacent to that enemy
      const hp = a.obj.health ?? 999
      // Lower is better: prioritize low hp, many of us adjacent, few of them adjacent
      // Strong bonus if likely kill this turn (os >= hp)
      const killBonus = (os >= hp) ? -2 : 0
      return {
        a,
        score: hp - os + 0.5 * ts + killBonus
      }
    })
    const best = _.minBy(scored, s => s.score).a
    return Action.attack(best.dir)
  }

  // If outnumbered locally near enemies, kite away a bit (more conservative trigger)
  if (distToClosest <= 2 && enemiesNear2 >= alliesNear2 + 2 && closestEnemy) {
    return fleeFrom(state, unit, closestEnemy.coords)
  }

  // Movement goal: primary is the chosen target; optionally support friend engaged in combat
  let goal = target.coords
  const toTargetWD = unit.coords.walkingDistanceTo(goal)
  if (toTargetWD >= 3) {
    const support = friendToSupport(state, unit, 3)
    if (support && support.enemy) {
      goal = support.enemy.coords
    }
  }

  const advance = safeAdvanceToward(state, unit, goal)
  return advance || null
}