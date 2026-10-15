let targetEnemy = null;

function robot(state, unit) {
  function getObj(x, y) {
    return state.objByCoords(new Coords(x, y));
  }

  function moveTowards(dir) {
    let D = dir;
    if (!getObj(unit.coords.x + D.toCoords.x, unit.coords.y + D.toCoords.y)) {
      return Action.move(D);
    }
    D = dir.rotateCw;
    if (!getObj(unit.coords.x + D.toCoords.x, unit.coords.y + D.toCoords.y)) {
      return Action.move(D);
    }
    D = dir.rotateCcw;
    if (!getObj(unit.coords.x + D.toCoords.x, unit.coords.y + D.toCoords.y)) {
      return Action.move(D);
    }
    return Action.move(dir); // fallback
  }

  function fleeTowards(dir) {
    let D = dir;
    if (!getObj(unit.coords.x + D.toCoords.x, unit.coords.y + D.toCoords.y)) {
      return Action.move(D);
    }
    D = dir.rotateCw;
    if (!getObj(unit.coords.x + D.toCoords.x, unit.coords.y + D.toCoords.y)) {
      return Action.move(D);
    }
    D = dir.rotateCcw;
    if (!getObj(unit.coords.x + D.toCoords.x, unit.coords.y + D.toCoords.y)) {
      return Action.move(D);
    }
    return Action.attack(dir.opposite); // attack if can't flee
  }

const enemies = state.objsByTeam(state.otherTeam);
const allies = state.objsByTeam(state.myTeam).filter(a => a !== unit);
let threatenedAlly = null;
for (let ally of allies) {
  for (let enemy of enemies) {
    if (ally.coords.distanceTo(enemy.coords) === 1) {
      threatenedAlly = ally;
      targetEnemy = enemy;
      break;
    }
  }
  if (threatenedAlly) break;
}
let lowHealthAlly = _.minBy(allies.filter(a => a.health <= 1), a => a.coords.distanceTo(unit.coords));
if (lowHealthAlly && lowHealthAlly.coords.distanceTo(unit.coords) > 1) {
  const dirToAlly = unit.coords.directionTo(lowHealthAlly.coords);
  return moveTowards(dirToAlly);
}
  if (enemies.length === 0) {
    targetEnemy = null;
    return null;
  }

  // Set shared target if not set: weakest enemy (lowest health, then closest)
  if (!targetEnemy || !enemies.includes(targetEnemy)) {
    targetEnemy = _.minBy(enemies, e => [e.health, e.coords.distanceTo(unit.coords)]);
  }

  const direction = unit.coords.directionTo(targetEnemy.coords);
  const dist = unit.coords.distanceTo(targetEnemy.coords);

  // If low health, flee (move away from enemy)
  if (unit.health <= 3) {
    return fleeTowards(direction.opposite);
  }

  // Attack if adjacent, else move towards
  // Check for nearby allies
  const nearbyAllies = allies.filter(a => a.coords.distanceTo(unit.coords) <= 2);
  if (nearbyAllies.length < 0 && dist <= 3) {
    return moveTowards(direction.opposite);
  }
  if (dist === 1) {
    return Action.attack(direction);
  } else {
    return moveTowards(direction);
  }
}