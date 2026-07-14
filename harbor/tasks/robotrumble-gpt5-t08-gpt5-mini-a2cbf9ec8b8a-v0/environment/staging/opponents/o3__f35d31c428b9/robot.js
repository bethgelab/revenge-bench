// RobotRumble bot â round 3
//
// Key improvements compared with previous revision:
// 1. Situational awareness: counts nearby friends vs enemies (radius 4).
// 2. Flee logic: if outnumbered or low health, retreat away from nearest threat.
// 3. Keeps previous aggressive chase/attack behaviour when situation is favourable.
//
// Decision order per unit:
//   a) Finish off adjacent enemy with health â¤1.
//   b) If adjacent enemy and we are not outnumbered or weaker, attack.
//   c) If outnumbered or low health, attempt to flee (preferring open opposite tile).
//   d) Otherwise chase closest enemy, trying primary direction then CW/CCW fallbacks.
//   e) Pass if no valid moves.

const NEARBY_RADIUS = 4
const LOW_HEALTH = 3 // flee threshold

function robot(state, unit) {
  const enemies = state.objsByTeam(state.otherTeam)
  const friends = state.objsByTeam(state.ourTeam)
  if (!enemies || enemies.length === 0) return null

  // Helper to filter objs within radius
  const nearby = (list, r) => list.filter(o => unit.coords.distanceTo(o.coords) <= r)

  const nearbyEnemies = nearby(enemies, NEARBY_RADIUS)
  const nearbyFriends = nearby(friends, NEARBY_RADIUS)

  // Adjacent enemies handling
  const adjacentEnemies = enemies.filter(e => unit.coords.distanceTo(e.coords) === 1)
  if (adjacentEnemies.length) {
    const killable = adjacentEnemies.find(e => e.health <= 1)
    if (killable) {
      return Action.attack(unit.coords.directionTo(killable.coords))
    }
    const weakest = _.minBy(adjacentEnemies, e => e.health)
    // If not outnumbered or healthier, fight
    if (unit.health >= weakest.health || nearbyFriends.length >= nearbyEnemies.length) {
      return Action.attack(unit.coords.directionTo(weakest.coords))
    }
    // else fall through to flee logic
  }

  // Determine flee condition
  const outnumbered = nearbyEnemies.length > nearbyFriends.length + 1
  if (outnumbered || unit.health <= LOW_HEALTH) {
    const closestThreat = _.minBy(enemies, e => e.coords.distanceTo(unit.coords))
    if (closestThreat) {
      const threatDir = unit.coords.directionTo(closestThreat.coords)
      const fleeOrder = [
        threatDir.opposite,
        threatDir.opposite.rotateCw,
        threatDir.opposite.rotateCcw,
        threatDir.rotateCw,
        threatDir.rotateCcw
      ]
      for (const dir of fleeOrder) {
        if (!dir) continue
        const target = new Coords(unit.coords.x + dir.toCoords.x, unit.coords.y + dir.toCoords.y)
        if (!state.objByCoords(target)) {
          return Action.move(dir)
        }
      }
      // If stuck, attack weakest adjacent to go down fighting
      if (adjacentEnemies.length) {
        const weakest = _.minBy(adjacentEnemies, e => e.health)
        return Action.attack(unit.coords.directionTo(weakest.coords))
      }
    }
  }

  // Chase closest enemy
  const closestEnemy = _.minBy(enemies, e =>
    e.coords.distanceTo(unit.coords) * 100 + e.health
  )
  const dist = unit.coords.distanceTo(closestEnemy.coords)
  const primaryDir = unit.coords.directionTo(closestEnemy.coords)

  if (dist === 1) return Action.attack(primaryDir)

  const dirs = [primaryDir, primaryDir.rotateCw, primaryDir.rotateCcw, primaryDir.opposite]
  for (const dir of dirs) {
    if (!dir) continue
    const target = new Coords(unit.coords.x + dir.toCoords.x, unit.coords.y + dir.toCoords.y)
    if (!state.objByCoords(target)) {
      return Action.move(dir)
    }
  }

  return null
}