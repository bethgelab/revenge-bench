let targetId = null;

function initTurn(state) {
  if (targetId) {
    if (!state.objById(targetId)) {
      // target has been defeated
      targetId = null;
    }
  }

  if (!targetId) {
    const allies = state.objsByTeam(state.ourTeam);

    const totalDistanceForTeam = (enemy) =>
      _.sum(allies.map(ally => ally.coords.distanceTo(enemy.coords)));

    const enemies = state.objsByTeam(state.otherTeam);
    // Prioritize enemies with lower health and closer to our team
    const closestEnemyForTeam = _.minBy(enemies, enemy => {
      const distanceFactor = totalDistanceForTeam(enemy);
      const healthFactor = (10 - enemy.health) * 5; // Lower health = higher priority
      return distanceFactor + healthFactor;
    });
    
    if (closestEnemyForTeam) {
      targetId = closestEnemyForTeam.id;
    }
  }
}

function robot(state, unit) {
  const allies = state.objsByTeam(state.ourTeam);
  const enemies = state.objsByTeam(state.otherTeam);
  
  // Check if we need to flee due to low health
  if (unit.health <= 2) {
    // Find safest direction to move (away from nearest enemy)
    const closestEnemy = _.minBy(enemies, e => e.coords.distanceTo(unit.coords));
    if (closestEnemy && unit.coords.distanceTo(closestEnemy.coords) <= 2) {
      const fleeDirection = closestEnemy.coords.directionTo(unit.coords);
      return Action.move(fleeDirection);
    }
  }

  // Check if there's an ally under attack that needs help
  for (const ally of allies) {
    if (ally.id !== unit.id && ally.health < 4) { // If ally has low health
      // Find the enemy attacking this ally
      const closestEnemyToAlly = _.minBy(enemies, e => e.coords.distanceTo(ally.coords));
      if (closestEnemyToAlly && ally.coords.distanceTo(closestEnemyToAlly.coords) <= 2) {
        // Move to help the ally
        const directionToAlly = unit.coords.directionTo(ally.coords);
        return Action.move(directionToAlly);
      }
    }
  }

  // Check if we're attacking alone - if so, consider retreating or waiting for backup
  const target = state.objById(targetId);
  if (!target) {
    // If no target, just move toward center
    return Action.move(unit.coords.directionTo(new Coords(10, 10)));
  }
  
  debug.locate(target);
  
  // Count how many of our units are near the target
  const alliesNearTarget = allies.filter(ally => 
    ally.coords.distanceTo(target.coords) <= 3
  );
  
  // Calculate if we have sufficient force to attack
  const ourTotalHealthNearTarget = alliesNearTarget.reduce((sum, ally) => sum + ally.health, 0);
  const enemyUnitsNearTarget = enemies.filter(enemy => 
    enemy.coords.distanceTo(target.coords) <= 3
  );
  const enemyTotalHealthNearTarget = enemyUnitsNearTarget.reduce((sum, enemy) => sum + enemy.health, 0);
  
  // If we're outnumbered or outgunned, be more cautious
  if (alliesNearTarget.length < enemyUnitsNearTarget.length || 
      ourTotalHealthNearTarget < enemyTotalHealthNearTarget) {
    // Move toward target but maintain distance
    if (unit.coords.distanceTo(target.coords) > 2) {
      const direction = unit.coords.directionTo(target.coords);
      return Action.move(direction);
    } else {
      // If too close and outgunned, try to move away slightly
      const closestEnemy = _.minBy(enemies, e => e.coords.distanceTo(unit.coords));
      if (closestEnemy && unit.coords.distanceTo(closestEnemy.coords) <= 1) {
        const fleeDirection = closestEnemy.coords.directionTo(unit.coords);
        return Action.move(fleeDirection);
      }
      return null; // Hold position
    }
  }

  // Strategic positioning: try to position optimally around the target
  const distanceToTarget = unit.coords.distanceTo(target.coords);
  
  if (distanceToTarget === 1) {
    // we're right next to them, attack
    const direction = unit.coords.directionTo(target.coords);
    return Action.attack(direction);
  } else if (distanceToTarget <= 3) {
    // We're in range, move to attack position
    const direction = unit.coords.directionTo(target.coords);
    return Action.move(direction);
  } else {
    // Move toward target
    const direction = unit.coords.directionTo(target.coords);
    return Action.move(direction);
  }
}