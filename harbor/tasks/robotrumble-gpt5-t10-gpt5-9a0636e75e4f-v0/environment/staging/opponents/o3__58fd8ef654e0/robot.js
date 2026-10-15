// Shared state across all our robots (persists for the match process)
let globalTargetId = null
let globalLastTurn = -1
let reservedDestinations = new Set()  // strings "x,y"

/**
 * Helper to stringify Coords for Set/Map usage
 */
function key(c) {
  return `${c.x},${c.y}`
}

function robot(state, unit) {
  // ---------- Per-turn global maintenance ----------
  if (state.turn !== globalLastTurn) {
    // New turn, reset reservations and (re)pick a focus target for the whole team
    globalLastTurn = state.turn
    reservedDestinations.clear()

    const enemies = state.objsByTeam(state.otherTeam) || []
    if (enemies.length > 0) {
      // Pick the enemy that is closest (on average) to our robots; use this robot's
      // distance as a proxy (cheap but works reasonably well)
      const focus = _.minBy(enemies, e => unit.coords.walkingDistanceTo(e.coords))
      globalTargetId = focus ? focus.id : null
    }
  }

  // ---------- Spawn evacuation ----------
  if (unit.coords.isSpawn() && (state.turn % 10) >= 7) {
    // Spawns become lava every 10th turn â leave if weâre still on one late in the cycle
    const center = new Coords(9, 9)
    const dirCenter = unit.coords.directionTo(center)
    const evacDirs = [dirCenter, dirCenter.rotateCw, dirCenter.rotateCcw]
    const evac = moveIfPossible(evacDirs)
    if (evac) return evac
  }

  // ---------- Gather / validate enemy target ----------
  let target = globalTargetId ? state.objById(globalTargetId) : null
  if (!target) {
    // fallback: choose nearest enemy
    const enemies = state.objsByTeam(state.otherTeam) || []
    if (enemies.length === 0) return null
    target = _.minBy(enemies, e => unit.coords.walkingDistanceTo(e.coords))
    globalTargetId = target.id
  }

  const dist = unit.coords.walkingDistanceTo(target.coords)
  const dirTo = unit.coords.directionTo(target.coords)

  // ---------- Attack if adjacent ----------
  if (dist === 1) {
    return Action.attack(dirTo)
  }

  // ---------- Flee if weak and outmatched ----------
  if (unit.health < 3 && dist <= 2 && target.health >= unit.health) {
    const fleeDirs = [dirTo.opposite, dirTo.opposite.rotateCw, dirTo.opposite.rotateCcw]
    const flee = moveIfPossible(fleeDirs)
    if (flee) return flee
    // else, fall through and maybe advance or stand still
  }

  // ---------- Advance toward target ----------
  const advanceDirs = [dirTo, dirTo.rotateCw, dirTo.rotateCcw]
  for (const d of advanceDirs) {
    const next = unit.coords.add(d)
    if (isEmptyDir(d) && next.walkingDistanceTo(target.coords) < dist) {
      reservedDestinations.add(key(next))
      return Action.move(d)
    }
  }

  // ---------- Fallback: any available move incl. backing away ----------
  const fallback = moveIfPossible([...advanceDirs, dirTo.opposite])
  if (fallback) return fallback

  // ---------- Nothing worth doing ----------
  return null

  // ===== Helper functions (hoisted) =====
  function isEmptyDir(dir) {
    const next = unit.coords.add(dir)
    return state.objByCoords(next) === undefined && !reservedDestinations.has(key(next))
  }

  function moveIfPossible(directions) {
    for (const d of directions) {
      if (isEmptyDir(d)) {
        const dest = unit.coords.add(d)
        reservedDestinations.add(key(dest))
        return Action.move(d)
      }
    }
    return null
  }
}