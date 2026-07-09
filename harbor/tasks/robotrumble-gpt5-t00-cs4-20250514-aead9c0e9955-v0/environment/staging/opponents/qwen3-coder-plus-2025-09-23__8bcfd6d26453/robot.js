function robot(state, unit) {
  // Get all enemy units
  const enemies = state.objsByTeam(state.otherTeam);
  
  // If there are enemies, find the closest one
  if (enemies && enemies.length > 0) {
    const closestEnemy = _.minBy(enemies,
      e => e.coords.distanceTo(unit.coords)
    );
    
    // Calculate direction to the closest enemy
    const direction = unit.coords.directionTo(closestEnemy.coords);

    // If we're adjacent to the enemy, attack
    if (unit.coords.distanceTo(closestEnemy.coords) === 1) {
      return Action.attack(direction);
    } 
    // If we're low on health, consider fleeing
    else if (unit.health <= 1) {
      // Try to move away from the closest enemy
      return Action.move(direction.opposite);
    }
    // Otherwise, move toward the enemy
    else {
      return Action.move(direction);
    }
  }
  
  // If no enemies are found, move randomly
  const directions = [Direction.North, Direction.South, Direction.East, Direction.West];
  const randomDirection = directions[Math.floor(Math.random() * directions.length)];
  return Action.move(randomDirection);
}