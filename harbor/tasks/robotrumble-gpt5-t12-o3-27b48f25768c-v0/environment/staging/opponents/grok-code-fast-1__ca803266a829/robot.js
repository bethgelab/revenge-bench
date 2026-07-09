let globalAvgHealth = 20; // default
let globalAvgCoords = new Coords(9, 9); // default

function init_turn(state) {
  let myUnits = state.objsByTeam(state.myTeam);
  if (myUnits.length > 0) {
    globalAvgHealth = _.sumBy(myUnits, u => u.health) / myUnits.length;
    let totalX = _.sumBy(myUnits, u => u.coords.x);
    let totalY = _.sumBy(myUnits, u => u.coords.y);
    globalAvgCoords = new Coords(Math.round(totalX / myUnits.length), Math.round(totalY / myUnits.length));
  } else {
    globalAvgHealth = 0;
  }
}

function robot(state, unit) {
  let enemies = state.objsByTeam(state.otherTeam);
  let friends = state.objsByTeam(state.myTeam).filter(f => f.id !== unit.id);

  let targetEnemy = null;

  // Assist: If any friend has low health, target enemy closest to weakest friend
  let weakestFriend = _.minBy(friends, f => f.health);
  if (weakestFriend && weakestFriend.health < 10) {
    targetEnemy = _.minBy(enemies, e => weakestFriend.coords.distanceTo(e.coords));
  }

  // If no assist target, target closest enemy
  if (!targetEnemy && enemies.length > 0) {
    targetEnemy = _.minBy(enemies, e => unit.coords.distanceTo(e.coords));
  }

  if (targetEnemy) {
    // Attack any adjacent enemy
    let adjacentEnemies = enemies.filter(e => unit.coords.distanceTo(e.coords) === 1);
    if (adjacentEnemies.length > 0) {
      let adjTarget = adjacentEnemies[0];
      let direction = unit.coords.directionTo(adjTarget.coords);
      let targetCoords = unit.coords.add(direction);
      let targetObj = state.objByCoords(targetCoords);
      if (targetObj && targetObj.team === state.otherTeam) {
        // Avoid friendly fire: check if friends adjacent to target
        let friendAdjacent = false;
        let dirs = [Direction.North, Direction.South, Direction.East, Direction.West];
        for (let d of dirs) {
          let adj = targetCoords.add(d);
          let obj = state.objByCoords(adj);
          if (obj && obj.team === state.myTeam) {
            friendAdjacent = true;
            break;
          }
        }
        if (!friendAdjacent) {
          return Action.attack(direction);
        }
      }
    }

    // Fleeing logic: If low health and outnumbered nearby, flee
    let nearbyEnemies = enemies.filter(e => unit.coords.distanceTo(e.coords) <= 3);
    let nearbyFriends = friends.filter(f => unit.coords.distanceTo(f.coords) <= 3);
    if (unit.health < 10 && nearbyEnemies.length > nearbyFriends.length) {
      // Flee: Move away from closest enemy
      let closestEnemy = _.minBy(enemies, e => unit.coords.distanceTo(e.coords));
      if (closestEnemy) {
        let directionAway = unit.coords.directionTo(closestEnemy.coords).opposite();
        let targetCoords = unit.coords.add(directionAway);
        let nextObj = state.objByCoords(targetCoords);
        if (!nextObj) {
          return Action.move(directionAway);
        } else {
          // Try alternatives
          let altDir = directionAway.rotateCw();
          let altCoords = unit.coords.add(altDir);
          if (!state.objByCoords(altCoords)) {
            return Action.move(altDir);
          }
          altDir = directionAway.rotateCcw();
          altCoords = unit.coords.add(altDir);
          if (!state.objByCoords(altCoords)) {
            return Action.move(altDir);
          }
        }
      }
    }

    // Move towards target, with obstacle avoidance
    let direction = unit.coords.directionTo(targetEnemy.coords);
    let targetCoords = unit.coords.add(direction);
    let nextObj = state.objByCoords(targetCoords);
    if (nextObj && nextObj.team === state.otherTeam) {
      return Action.attack(direction);
    }
    if (!nextObj) {
      return Action.move(direction);
    } else {
      let altDir = direction.rotateCw;
      let altCoords = unit.coords.add(altDir);
      if (!state.objByCoords(altCoords)) {
        return Action.move(altDir);
      }
      altDir = direction.rotateCcw;
      altCoords = unit.coords.add(altDir);
      if (!state.objByCoords(altCoords)) {
        return Action.move(altDir);
      }
    }
  } else {
    // No enemies, move to average team position
    let direction = unit.coords.directionTo(globalAvgCoords);
    let targetCoords = unit.coords.add(direction);
    let nextObj = state.objByCoords(targetCoords);
    if (nextObj && nextObj.team === state.otherTeam) {
      return Action.attack(direction);
    }
    if (!nextObj) {
      return Action.move(direction);
    } else {
      // Alternatives
      let altDir = direction.rotateCw;
      let altCoords = unit.coords.add(altDir);
      if (!state.objByCoords(altCoords)) {
        return Action.move(altDir);
      }
      altDir = direction.rotateCcw;
      altCoords = unit.coords.add(altDir);
      if (!state.objByCoords(altDir)) {
        return Action.move(altDir);
      }
    }
  }

  return Action.attack(Direction.North); // Fallback
}