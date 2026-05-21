// Global variable to track team target
let targetId = null;

function initTurn(state) {
  // Check if current target is still alive
  if (targetId) {
    if (!state.objById(targetId)) {
      targetId = null;
    }
  }

  // If no target, find the best enemy to focus on
  if (!targetId) {
    const allies = state.objsByTeam(state.ourTeam);
    const enemies = state.objsByTeam(state.otherTeam);
    
    if (enemies.length > 0 && allies.length > 0) {
      // Calculate center of our army
      const centerX = _.mean(allies.map(a => a.coords.x));
      const centerY = _.mean(allies.map(a => a.coords.y));
      
      // Score enemies based on distance to our center
      const scoreEnemy = (enemy) => {
        const distToCenter = Math.abs(enemy.coords.x - centerX) + 
                            Math.abs(enemy.coords.y - centerY);
        
        // Count nearby enemy allies (within 3 tiles)
        const nearbyEnemyAllies = enemies.filter(e => 
          e.id !== enemy.id && e.coords.distanceTo(enemy.coords) <= 3
        ).length;
        
        // Prefer: enemies close to our center, low health, isolated enemies
        // Lower score = better target
        return distToCenter + (enemy.health * 2) + (nearbyEnemyAllies * 8);
      };
      
      const bestTarget = _.minBy(enemies, scoreEnemy);
      targetId = bestTarget.id;
    }
  }
}

function robot(state, unit) {
  const enemies = state.objsByTeam(state.otherTeam);
  const allies = state.objsByTeam(state.ourTeam);
  
  if (enemies.length === 0) {
    return null;
  }
  
  // Calculate center of our army
  const centerX = _.mean(allies.map(a => a.coords.x));
  const centerY = _.mean(allies.map(a => a.coords.y));
  
  // Count how many allies are nearby (within 3 tiles)
  const nearbyAllies = allies.filter(a => 
    a.id !== unit.id && unit.coords.distanceTo(a.coords) <= 3
  ).length;
  
  // Calculate distance from center
  const distFromCenter = Math.abs(unit.coords.x - centerX) + Math.abs(unit.coords.y - centerY);
  
  // CRITICAL: If we have few nearby allies OR we're far from center, move toward center
  // This ensures we stay grouped
  if (nearbyAllies < 2 || distFromCenter > 5) {
    const directionToCenter = unit.coords.directionTo({x: Math.round(centerX), y: Math.round(centerY)});
    
    // Check if there's an adjacent enemy we should attack instead of moving
    const adjacentEnemies = enemies.filter(e => unit.coords.distanceTo(e.coords) === 1);
    if (adjacentEnemies.length > 0) {
      const closestEnemy = _.minBy(adjacentEnemies, e => e.health);
      const directionToEnemy = unit.coords.directionTo(closestEnemy.coords);
      return Action.attack(directionToEnemy);
    }
    
    return Action.move(directionToCenter);
  }
  
  // If we're well-grouped, attack the team target
  let target = state.objById(targetId);
  
  // If team target doesn't exist, find closest enemy
  if (!target) {
    target = _.minBy(enemies, e => e.coords.distanceTo(unit.coords));
  }
  
  const direction = unit.coords.directionTo(target.coords);
  const distance = unit.coords.distanceTo(target.coords);
  
  // Attack if adjacent, otherwise move toward target
  if (distance === 1) {
    return Action.attack(direction);
  } else {
    return Action.move(direction);
  }
}