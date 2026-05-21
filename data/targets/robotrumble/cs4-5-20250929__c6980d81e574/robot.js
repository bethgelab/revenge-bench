// Aggressive but smart RobotRumble bot - focus fire with formation awareness

let targetId = null;

function initTurn(state) {
  // Select a shared target - prioritize weak enemies that are close to our team
  if (targetId && !state.objById(targetId)) {
    targetId = null;
  }
  
  if (!targetId) {
    const allies = state.objsByTeam(state.ourTeam);
    const enemies = state.objsByTeam(state.otherTeam);
    
    if (enemies.length > 0 && allies.length > 0) {
      // Calculate team center
      const teamCenterX = _.meanBy(allies, a => a.coords.x);
      const teamCenterY = _.meanBy(allies, a => a.coords.y);
      const teamCenter = new Coords(Math.round(teamCenterX), Math.round(teamCenterY));
      
      // Find enemy that's closest to our team center, with preference for weak enemies
      const target = _.minBy(enemies, e => {
        const dist = teamCenter.distanceTo(e.coords);
        const healthPenalty = e.health * 1.5; // Prefer weak enemies
        return dist + healthPenalty;
      });
      
      targetId = target.id;
    }
  }
}

function robot(state, unit) {
  const enemies = state.objsByTeam(state.otherTeam);
  const allies = state.objsByTeam(state.ourTeam);
  
  if (enemies.length === 0) return null;
  
  // Count nearby units (within 4 tiles)
  const NEARBY_RADIUS = 4;
  const nearbyAllies = allies.filter(a => 
    a.coords.distanceTo(unit.coords) <= NEARBY_RADIUS && a.id !== unit.id
  );
  const nearbyEnemies = enemies.filter(e => 
    e.coords.distanceTo(unit.coords) <= NEARBY_RADIUS
  );
  
  // Check for adjacent enemies
  const adjacentEnemies = enemies.filter(e => 
    unit.coords.distanceTo(e.coords) === 1
  );
  
  // Always attack if adjacent to an enemy - prioritize weakest
  if (adjacentEnemies.length > 0) {
    const weakest = _.minBy(adjacentEnemies, e => e.health);
    const direction = unit.coords.directionTo(weakest.coords);
    return Action.attack(direction);
  }
  
  // Determine if we should be aggressive or cautious
  const allyCount = nearbyAllies.length + 1; // +1 for self
  const enemyCount = nearbyEnemies.length;
  const isIsolated = allyCount <= 1 && enemyCount >= 2;
  const isOutnumbered = allyCount < enemyCount * 0.7;
  
  // Calculate overall team advantage
  const totalAllyHealth = _.sumBy(allies, a => a.health);
  const totalEnemyHealth = _.sumBy(enemies, e => e.health);
  const hasHealthAdvantage = totalAllyHealth > totalEnemyHealth * 1.2;
  
  // If very low health and isolated, try to regroup
  if (unit.health <= 2 && isIsolated && !hasHealthAdvantage) {
    // Find closest ally
    const closestAlly = _.minBy(allies.filter(a => a.id !== unit.id), 
      a => a.coords.distanceTo(unit.coords)
    );
    
    if (closestAlly) {
      const direction = unit.coords.directionTo(closestAlly.coords);
      if (canMove(state, unit.coords, direction)) {
        return Action.move(direction);
      }
    }
  }
  
  // Determine target
  let target = state.objById(targetId);
  const closestEnemy = _.minBy(enemies, e => e.coords.distanceTo(unit.coords));
  
  // If team target doesn't exist or is very far, go for closest
  if (!target || unit.coords.distanceTo(target.coords) > 10) {
    target = closestEnemy;
  }
  
  // Look for weak enemies nearby - prioritize finishing them off
  // In late game with advantage, be more aggressive about finishing weak enemies
  const weakThreshold = hasHealthAdvantage ? 3 : 2;
  const weakNearby = nearbyEnemies.filter(e => e.health <= weakThreshold);
  if (weakNearby.length > 0) {
    // Target the weakest one that's closest
    target = _.minBy(weakNearby, e => {
      const dist = unit.coords.distanceTo(e.coords);
      return e.health * 2 + dist;
    });
  }
  
  // If outnumbered and not close to target, move toward allies instead
  if (isOutnumbered && unit.coords.distanceTo(target.coords) > 3 && !hasHealthAdvantage) {
    // Find the ally closest to the team target
    const alliesNearTarget = allies.filter(a => a.id !== unit.id);
    if (alliesNearTarget.length > 0) {
      const bestAlly = _.minBy(alliesNearTarget, a => {
        const distToTarget = target.coords.distanceTo(a.coords);
        const distToMe = unit.coords.distanceTo(a.coords);
        return distToTarget + distToMe * 0.5;
      });
      
      // Move toward this ally (which should be near the target)
      const direction = unit.coords.directionTo(bestAlly.coords);
      if (canMove(state, unit.coords, direction)) {
        return Action.move(direction);
      }
    }
  }
  
  // Move toward target with smart collision avoidance
  const direction = unit.coords.directionTo(target.coords);
  
  // Try primary direction
  if (canMove(state, unit.coords, direction)) {
    return Action.move(direction);
  }
  
  // Try rotating to find a path
  const cwDir = direction.rotateCw;
  const ccwDir = direction.rotateCcw;
  
  // Prefer the rotation that keeps us closer to target
  const cwCoords = unit.coords.add(cwDir.toCoords);
  const ccwCoords = unit.coords.add(ccwDir.toCoords);
  
  const cwDist = cwCoords.distanceTo(target.coords);
  const ccwDist = ccwCoords.distanceTo(target.coords);
  
  if (cwDist <= ccwDist && canMove(state, unit.coords, cwDir)) {
    return Action.move(cwDir);
  }
  
  if (canMove(state, unit.coords, ccwDir)) {
    return Action.move(ccwDir);
  }
  
  if (canMove(state, unit.coords, cwDir)) {
    return Action.move(cwDir);
  }
  
  // Try opposite direction as last resort
  const oppositeDir = direction.opposite;
  if (canMove(state, unit.coords, oppositeDir)) {
    return Action.move(oppositeDir);
  }
  
  // If completely blocked, stay put
  return null;
}

function canMove(state, coords, direction) {
  const newCoords = coords.add(direction.toCoords);
  return !state.objByCoords(newCoords);
}