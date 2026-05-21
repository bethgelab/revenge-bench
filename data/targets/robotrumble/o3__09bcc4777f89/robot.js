/**
 * Coordinated RobotRumble bot â round 4
 *
 * Strategy (per robot):
 *  1. Global focus-fire: all robots share `targetId`, chosen as the enemy that
 *     minimises the sum of walking distances to our team (ties by health).
 *  2. If adjacent to any enemy â attack the weakest adjacent one.
 *  3. If low health (â¤2) and an enemy is within 3 tiles â flee (opposite / Â±90Â°).
 *  4. Otherwise move toward the shared target using a greedy step, but randomise
 *     among equally-good directions to reduce ally congestion.
 *  5. If no valid moves â pass.
 *
 * Requires stdlib globals (Action, Direction, _, etc.).
 */

let targetId = null // shared across our robots

function robot(state, unit) {
  // âââââââââââââââââââââââââââââââââââââââââ TARGET MANAGEMENT
  const enemies = state.objsByTeam(state.otherTeam)
  if (!enemies || enemies.length === 0) {
    return null
  }

  // Reset target if it no longer exists
  if (targetId && !state.objById(targetId)) {
    targetId = null
  }

  // Choose new target when none selected
  if (!targetId) {
    const allies = state.objsByTeam(state.ourTeam)
    const score = (enemy) =>
      _.sumBy(allies, (ally) => ally.coords.walkingDistanceTo(enemy.coords)) *
        100 +
      enemy.health // prioritise low-distance, then low-HP
    const chosen = _.minBy(enemies, score)
    targetId = chosen ? chosen.id : null
  }

  const target =
    (targetId && state.objById(targetId)) || _.minBy(enemies, 'health')
  const distToTarget = unit.coords.distanceTo(target.coords)
  const dirToTarget = unit.coords.directionTo(target.coords)

  // âââââââââââââââââââââââââââââââââââââââââ ATTACK
  const adjacent = enemies.filter((e) => unit.coords.distanceTo(e.coords) === 1)
  if (adjacent.length > 0) {
    const weakest = _.minBy(adjacent, 'health')
    return Action.attack(unit.coords.directionTo(weakest.coords))
  }

  // âââââââââââââââââââââââââââââââââââââââââ FLEE
  if (unit.health <= 2 && distToTarget <= 3) {
    const fleeDirs = [
      dirToTarget.opposite,
      dirToTarget.opposite.rotateCw,
      dirToTarget.opposite.rotateCcw,
    ]
    for (const d of fleeDirs) {
      const next = unit.coords.add(d.toCoords)
      if (!state.objByCoords(next)) {
        return Action.move(d)
      }
    }
    // fall through if blocked
  }

  // âââââââââââââââââââââââââââââââââââââââââ ADVANCE
  const dirs = [Direction.North, Direction.East, Direction.South, Direction.West]
  const sorted = _.sortBy(dirs, (d) =>
    unit.coords.add(d.toCoords).distanceTo(target.coords),
  )
  const bestDist = unit.coords.add(sorted[0].toCoords).distanceTo(target.coords)
  const top = sorted.filter(
    (d) => unit.coords.add(d.toCoords).distanceTo(target.coords) <= bestDist + 0.01,
  )
  const tryDirs = _.shuffle(top).concat(_.difference(sorted, top))

  for (const d of tryDirs) {
    const next = unit.coords.add(d.toCoords)
    if (!state.objByCoords(next)) {
      return Action.move(d)
    }
  }

  // âââââââââââââââââââââââââââââââââââââââââ IDLE
  return null
}