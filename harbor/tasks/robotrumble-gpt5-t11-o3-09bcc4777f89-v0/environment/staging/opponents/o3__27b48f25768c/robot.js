// Enhanced RobotRumble bot â round 9
//
// Strategy summary
// ----------------
// 1. Global focusId: all robots concentrate fire on one enemy at a time.
// 2. If low HP (<=2) and disadvantaged, flee.
// 3. Adjacent logic: attack when stronger or have support; else kite.
// 4. Movement: moveTowards with side-stepping fallback, then greedy
//    distance-reducing step, then same-distance shuffle step.
//
// NOTE: Uses only stdlib helpers and lodash (_) provided by RR.


// -------- Team-wide coordination (added round 9) -----------------------------
// Robots share this module-level variable to agree on a single enemy.
// It is reset when the enemy dies or disappears.
let focusId = null

function robot(state, unit) {
  // Helper to get any object at coords
  const objAt = c => state.objByCoords(c)

  // Try to move in preferred dir; if blocked fall back CW/CCW (order varies by id)
  function moveTowards(dir) {
    const cw = dir.rotateCw
    const ccw = dir.rotateCcw
    const tryDirs = unit.id % 2 === 0 ? [dir, ccw, cw] : [dir, cw, ccw]
    for (const d of tryDirs) {
      const target = unit.coords.add(d.toCoords)
      if (!objAt(target)) return Action.move(d)
    }
    return null
  }

  // Flee opposite; fallbacks around opposite; attack if surrounded
  function moveAway(fromDir) {
    const primary = fromDir.opposite
    const cw = primary.rotateCw
    const ccw = primary.rotateCcw
    const tryDirs = unit.id % 2 === 0 ? [primary, ccw, cw] : [primary, cw, ccw]
    for (const d of tryDirs) {
      const target = unit.coords.add(d.toCoords)
      if (!objAt(target)) return Action.move(d)
    }
    return Action.attack(fromDir)
  }

  // ---------------------- Acquire lists --------------------------------------
  const enemies = state.objsByTeam(state.otherTeam)
  if (!enemies || enemies.length === 0) return null

  // Opportunistic adjacent attack on weakest neighbour
  const adjEnemies = enemies.filter(e => e.coords.distanceTo(unit.coords) === 1)
  if (adjEnemies.length) {
    const weak = _.minBy(adjEnemies, 'health')
    const dirToWeak = unit.coords.directionTo(weak.coords)
    const friendAdjWeak = state.objsByTeam(state.ourTeam)
      .filter(f => f.id !== unit.id && f.coords.distanceTo(weak.coords) === 1).length
    if (weak.health <= unit.health || weak.health <= 2 || friendAdjWeak > 0) {
      return Action.attack(dirToWeak)
    }
  }

  // ---------------- Determine team focus target ------------------------------
  // Validate existing focusId
  if (focusId) {
    const cur = state.objById ? state.objById(focusId) : null
    if (!cur || cur.team !== state.otherTeam) focusId = null
  }

  let target
  if (focusId) {
    target = state.objById(focusId)
  } else {
    // Choose enemy minimising (sum distance to allies) + health
    const allies = state.objsByTeam(state.ourTeam)
    const score = e =>
      _.sumBy(allies, a => a.coords.distanceTo(e.coords)) + e.health
    target = _.minBy(enemies, score)
    if (target) focusId = target.id
  }

  if (!target) return null // safety

  // Precompute values
  const dist = unit.coords.distanceTo(target.coords)
  const dirToTarget = unit.coords.directionTo(target.coords)
  const friends = state.objsByTeam(state.ourTeam).filter(f => f.id !== unit.id)
  const friendAdj = friends.filter(
    f => f.coords.distanceTo(target.coords) === 1
  ).length

  // ------------------------- Flee logic --------------------------------------
  if (unit.health <= 2 && dist <= 2 && target.health > unit.health) {
    const flee = moveAway(dirToTarget)
    if (flee) return flee
  }

  // ------------------------- Adjacent logic ----------------------------------
  if (dist === 1) {
    if (unit.health >= target.health || friendAdj > 0) {
      return Action.attack(dirToTarget)
    }
    const kite = moveAway(dirToTarget)
    if (kite) return kite
    return Action.attack(dirToTarget) // no escape
  }

  // ------------------------- Movement ----------------------------------------
  const mv = moveTowards(dirToTarget)
  if (mv) return mv

  // Greedy distance-reducing step when blocked
  const dirs = [Direction.North, Direction.East, Direction.South, Direction.West]
  let bestDir = null
  let bestDist = dist
  for (const d of dirs) {
    const newPos = unit.coords.add(d.toCoords)
    if (!objAt(newPos)) {
      const newDist = newPos.distanceTo(target.coords)
      if (newDist < bestDist) {
        bestDist = newDist
        bestDir = d
      }
    }
  }
  if (bestDir) return Action.move(bestDir)

  // Same-distance shuffle to relieve congestion
  const sameDistDirs = _.shuffle(dirs).filter(d => {
    const newPos = unit.coords.add(d.toCoords)
    return !objAt(newPos) && newPos.distanceTo(target.coords) === dist
  })
  if (sameDistDirs.length) return Action.move(sameDistDirs[0])

  return null
}