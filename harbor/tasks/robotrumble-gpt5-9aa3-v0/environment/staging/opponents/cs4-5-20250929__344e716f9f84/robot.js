// Round 13: Reverting to Round 11 strategy (67.6% win rate)
// Round 12: 42.0% win rate - health-weighted target selection failed
// Round 11: 67.6% win rate - simple distance-based targeting worked best
// Keeping adaptive aggression with simple target selection

let targetId = null;
let teamAdvantage = 0;

function initTurn(state) {
  const allies = state.objsByTeam(state.ourTeam);
  const enemies = state.objsByTeam(state.otherTeam);
  
  // Calculate team advantage
  teamAdvantage = allies.length - enemies.length;
  
  // Reset target if defeated
  if (targetId && !state.objById(targetId)) {
    targetId = null;
  }
  
  // Select target: closest enemy to our team center (Round 11 strategy)
  if (!targetId && enemies.length > 0 && allies.length > 0) {
    const centerX = _.sumBy(allies, a => a.coords.x) / allies.length;
    const centerY = _.sumBy(allies, a => a.coords.y) / allies.length;
    
    // Target enemy closest to our center (simple distance)
    const target = _.minBy(enemies, e => {
      const dx = e.coords.x - centerX;
      const dy = e.coords.y - centerY;
      return Math.sqrt(dx * dx + dy * dy);
    });
    targetId = target.id;
  }
}

function robot(state, unit) {
  const enemies = state.objsByTeam(state.otherTeam);
  const allies = state.objsByTeam(state.ourTeam);
  
  if (enemies.length === 0) return null;
  
  // Calculate team center
  const centerX = _.sumBy(allies, a => a.coords.x) / allies.length;
  const centerY = _.sumBy(allies, a => a.coords.y) / allies.length;
  const distanceFromCenter = Math.sqrt(
    Math.pow(unit.coords.x - centerX, 2) + 
    Math.pow(unit.coords.y - centerY, 2)
  );
  
  // Count nearby units (within 3 tiles)
  const NEARBY_RADIUS = 3;
  const nearbyAllies = allies.filter(a => 
    a.coords.distanceTo(unit.coords) <= NEARBY_RADIUS && a.id !== unit.id
  );
  const nearbyEnemies = enemies.filter(e => 
    e.coords.distanceTo(unit.coords) <= NEARBY_RADIUS
  );
  
  // Calculate local strength
  const allyStrength = nearbyAllies.reduce((sum, a) => sum + a.health, unit.health);
  const enemyStrength = nearbyEnemies.reduce((sum, e) => sum + e.health, 0);
  
  // Find adjacent enemies
  const adjacentEnemies = enemies.filter(e => 
    e.coords.distanceTo(unit.coords) === 1
  );
  
  // Combat logic
  if (adjacentEnemies.length > 0) {
    // Always prioritize killing blows
    const killable = adjacentEnemies.filter(e => e.health === 1);
    if (killable.length > 0) {
      const target = killable[0];
      const direction = unit.coords.directionTo(target.coords);
      return Action.attack(direction);
    }
    
    // Retreat if critically low health AND outnumbered
    if (unit.health === 1 && enemyStrength > allyStrength * 1.5) {
      const retreatDir = getRetreatDirection(unit, centerX, centerY, state);
      if (retreatDir) {
        return Action.move(retreatDir);
      }
    }
    
    // Retreat if severely outnumbered
    if (enemyStrength > allyStrength * 2.0 && unit.health <= 3) {
      const retreatDir = getRetreatDirection(unit, centerX, centerY, state);
      if (retreatDir) {
        return Action.move(retreatDir);
      }
    }
    
    // Attack the weakest adjacent enemy (focus fire)
    const weakestAdjacent = _.minBy(adjacentEnemies, e => e.health);
    const direction = unit.coords.directionTo(weakestAdjacent.coords);
    return Action.attack(direction);
  }
  
  // Movement logic - adaptive based on team advantage
  
  // Dynamic formation threshold based on advantage
  let formationThreshold = 5.5;
  let minAlliesForAdvance = 1;
  
  if (teamAdvantage >= 3) {
    // We're ahead - be more aggressive
    formationThreshold = 6.5;
    minAlliesForAdvance = 1;
  } else if (teamAdvantage <= -3) {
    // We're behind - tighten formation
    formationThreshold = 4.5;
    minAlliesForAdvance = 2;
  }
  
  // Regroup if too far from center and isolated
  if (distanceFromCenter > formationThreshold && nearbyAllies.length < minAlliesForAdvance) {
    return moveToward(unit, centerX, centerY, state);
  }
  
  // Advance toward target if we have support OR we're healthy and ahead
  const target = state.objById(targetId);
  if (target) {
    // Allow healthy units to advance alone when we have significant advantage
    const canAdvanceAlone = unit.health >= 4 && teamAdvantage >= 2;
    
    if (nearbyAllies.length >= minAlliesForAdvance || canAdvanceAlone) {
      return moveToward(unit, target.coords.x, target.coords.y, state);
    }
  }
  
  // Default: move toward center to regroup
  return moveToward(unit, centerX, centerY, state);
}

function moveToward(unit, targetX, targetY, state) {
  const dx = targetX - unit.coords.x;
  const dy = targetY - unit.coords.y;
  
  // Determine primary direction
  let direction;
  if (Math.abs(dx) > Math.abs(dy)) {
    direction = dx > 0 ? Direction.East : Direction.West;
  } else {
    direction = dy > 0 ? Direction.South : Direction.North;
  }
  
  // Try primary direction
  const newCoords = unit.coords.add(direction);
  if (state.isPassable(newCoords) && !state.objByCoords(newCoords)) {
    return Action.move(direction);
  }
  
  // Try perpendicular directions
  const perpendicular = [
    Math.abs(dx) > Math.abs(dy) ? 
      (dy > 0 ? Direction.South : Direction.North) :
      (dx > 0 ? Direction.East : Direction.West),
    Math.abs(dx) > Math.abs(dy) ?
      (dy > 0 ? Direction.North : Direction.South) :
      (dx > 0 ? Direction.West : Direction.East)
  ];
  
  for (const dir of perpendicular) {
    const coords = unit.coords.add(dir);
    if (state.isPassable(coords) && !state.objByCoords(coords)) {
      return Action.move(dir);
    }
  }
  
  // Try opposite direction as last resort
  const opposite = dx > 0 ? Direction.West : 
                   dx < 0 ? Direction.East :
                   dy > 0 ? Direction.North : Direction.South;
  const oppCoords = unit.coords.add(opposite);
  if (state.isPassable(oppCoords) && !state.objByCoords(oppCoords)) {
    return Action.move(opposite);
  }
  
  return null;
}

function getRetreatDirection(unit, centerX, centerY, state) {
  // Move toward center
  const dx = centerX - unit.coords.x;
  const dy = centerY - unit.coords.y;
  
  let direction;
  if (Math.abs(dx) > Math.abs(dy)) {
    direction = dx > 0 ? Direction.East : Direction.West;
  } else {
    direction = dy > 0 ? Direction.South : Direction.North;
  }
  
  const newCoords = unit.coords.add(direction);
  if (state.isPassable(newCoords) && !state.objByCoords(newCoords)) {
    return direction;
  }
  
  return null;
}