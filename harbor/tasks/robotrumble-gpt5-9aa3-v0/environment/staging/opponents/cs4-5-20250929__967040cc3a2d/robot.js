let targetId = null;

function initTurn(state) {
  // Reset target if it's been defeated
  if (targetId && !state.objById(targetId)) {
    targetId = null;
  }

  // Pick a new target if we don't have one
  if (!targetId) {
    const allies = state.objsByTeam(state.ourTeam);
    const enemies = state.objsByTeam(state.otherTeam);
    
    if (enemies.length > 0) {
      // Find the enemy that's closest to our team overall
      const totalDistanceForTeam = (enemy) =>
        _.sum(allies.map(ally => ally.coords.distanceTo(enemy.coords)));
      
      const closestEnemyForTeam = _.minBy(enemies, totalDistanceForTeam);
      targetId = closestEnemyForTeam.id;
    }
  }
}

function robot(state, unit) {
  const enemies = state.objsByTeam(state.otherTeam);
  
  if (enemies.length === 0) {
    return null; // No enemies left
  }
  
  // Find the closest enemy to this unit, with slight preference for weakened enemies
  const scoreEnemy = (enemy) => {
    const distance = enemy.coords.distanceTo(unit.coords);
    // Slightly prefer lower health enemies (but distance is more important)
    return distance + enemy.health * 0.1;
  };
  
  const closestEnemy = _.minBy(enemies, scoreEnemy);
  const direction = unit.coords.directionTo(closestEnemy.coords);
  const distance = unit.coords.distanceTo(closestEnemy.coords);
  
  // If we're adjacent to an enemy, attack
  if (distance === 1) {
    return Action.attack(direction);
  }
  
  // Try to move toward the closest enemy
  const targetCoords = unit.coords.add(direction.toCoords);
  
  // Check if the target cell is occupied (obstacle avoidance)
  if (!state.objByCoords(targetCoords)) {
    return Action.move(direction);
  }
  
  // If blocked, try rotating clockwise
  const cwDir = direction.rotateCw;
  const cwCoords = unit.coords.add(cwDir.toCoords);
  if (!state.objByCoords(cwCoords)) {
    return Action.move(cwDir);
  }
  
  // If still blocked, try rotating counter-clockwise
  const ccwDir = direction.rotateCcw;
  const ccwCoords = unit.coords.add(ccwDir.toCoords);
  if (!state.objByCoords(ccwCoords)) {
    return Action.move(ccwDir);
  }
  
  // If all directions blocked, just pass (wait for path to clear)
  return null;
}