let targetId = null

function initTurn(state) {
  if (targetId) {
    if (!state.objById(targetId)) {
      // target has been defeated
      targetId = null
    }
  }

  if (!targetId) {
    allies = state.objsByTeam(state.ourTeam)

    const totalDistanceForTeam = (enemy) =>
      _.sum(allies.map(ally => ally.coords.distanceTo(enemy.coords)))

    enemies = state.objsByTeam(state.otherTeam)
    closestEnemyForTeam = _.minBy(enemies, totalDistanceForTeam)
    targetId = closestEnemyForTeam.id
  }
}

function robot(state, unit) {
  const target = state.objById(targetId)
  debug.locate(target)

  direction = unit.coords.directionTo(target.coords)

  if (unit.coords.distanceTo(target.coords) === 1) {
    // we're right next to them
    return Action.attack(direction)
  } else {
    return Action.move(direction)
  }
}