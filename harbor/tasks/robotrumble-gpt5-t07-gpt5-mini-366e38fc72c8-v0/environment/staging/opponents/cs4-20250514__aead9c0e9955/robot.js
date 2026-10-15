// Improved chaser bot with collision avoidance
// Based on the winning Round 2 simple chaser, but with better pathfinding
function robot(state, unit) {
  const enemies = state.objsByTeam(state.otherTeam);
  
  if (enemies.length === 0) {
    return null;
  }
  
  const closestEnemy = _.minBy(enemies, e => e.coords.distanceTo(unit.coords));
  const direction = unit.coords.directionTo(closestEnemy.coords);
  
  // If adjacent to enemy, attack
  if (unit.coords.distanceTo(closestEnemy.coords) === 1) {
    return Action.attack(direction);
  }
  
  // Try to move toward enemy, with collision avoidance
  const targetCoords = unit.coords.add(direction);
  
  // If direct path is clear, take it
  if (!state.objByCoords(targetCoords)) {
    return Action.move(direction);
  }
  
  // If blocked, try alternative directions (clockwise then counterclockwise)
  const altDirection1 = direction.rotateCw;
  const altCoords1 = unit.coords.add(altDirection1);
  if (!state.objByCoords(altCoords1)) {
    return Action.move(altDirection1);
  }
  
  const altDirection2 = direction.rotateCcw;
  const altCoords2 = unit.coords.add(altDirection2);
  if (!state.objByCoords(altCoords2)) {
    return Action.move(altDirection2);
  }
  
  // If all adjacent moves blocked, try moving in opposite direction to get unstuck
  const oppositeDirection = direction.opposite;
  const oppositeCoords = unit.coords.add(oppositeDirection);
  if (!state.objByCoords(oppositeCoords)) {
    return Action.move(oppositeDirection);
  }
  
  // If completely surrounded, just try the original direction anyway
  return Action.move(direction);
}