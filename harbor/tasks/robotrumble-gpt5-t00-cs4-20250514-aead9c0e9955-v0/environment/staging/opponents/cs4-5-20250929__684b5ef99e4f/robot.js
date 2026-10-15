// Aggressive bot with team coordination

let targetId = null;

function initTurn(state) {
  // Select a shared target for the team to focus fire
  if (targetId && !state.objById(targetId)) {
    targetId = null;
  }
  
  if (!targetId) {
    const enemies = state.objsByTeam(state.otherTeam);
    
    if (enemies.length > 0) {
      // Target the weakest enemy that's closest to our team
      const allies = state.objsByTeam(state.ourTeam);
      const enemyScore = (enemy) => {
        const avgDist = _.sum(allies.map(ally => ally.coords.distanceTo(enemy.coords))) / allies.length;
        // Prioritize weak and close enemies
        return avgDist + enemy.health * 2;
      };
      
      const bestTarget = _.minBy(enemies, enemyScore);
      targetId = bestTarget.id;
    }
  }
}

function robot(state, unit) {
  const enemies = state.objsByTeam(state.otherTeam);
  
  if (enemies.length === 0) {
    return null;
  }
  
  // Find adjacent enemies
  const adjacentEnemies = enemies.filter(e => 
    unit.coords.distanceTo(e.coords) === 1
  );
  
  // Attack if adjacent - prioritize weakest
  if (adjacentEnemies.length > 0) {
    const weakest = _.minBy(adjacentEnemies, e => e.health);
    const direction = unit.coords.directionTo(weakest.coords);
    return Action.attack(direction);
  }
  
  // Move toward team target if available, otherwise closest enemy
  let target = state.objById(targetId);
  if (!target) {
    target = _.minBy(enemies, e => e.coords.distanceTo(unit.coords));
  }
  
  const direction = unit.coords.directionTo(target.coords);
  
  // Try to move in that direction
  const newCoords = unit.coords.add(direction.toCoords);
  if (!state.objByCoords(newCoords)) {
    return Action.move(direction);
  }
  
  // Try rotating if blocked
  for (let dir of [direction.rotateCw, direction.rotateCcw, direction.opposite]) {
    const testCoords = unit.coords.add(dir.toCoords);
    if (!state.objByCoords(testCoords)) {
      return Action.move(dir);
    }
  }
  
  return null;
}