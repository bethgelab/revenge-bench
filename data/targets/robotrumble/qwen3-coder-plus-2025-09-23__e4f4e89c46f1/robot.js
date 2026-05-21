let targetId = null;

function initTurn(state) {
  if (targetId) {
    if (!state.objById(targetId)) {
      // target has been defeated
      targetId = null;
    }
  }

  if (!targetId) {
    allies = state.objsByTeam(state.ourTeam);

    const totalDistanceForTeam = (enemy) =>
      _.sum(allies.map(ally => ally.coords.distanceTo(enemy.coords)));

    enemies = state.objsByTeam(state.otherTeam);
    closestEnemyForTeam = _.minBy(enemies, totalDistanceForTeam);
    if (closestEnemyForTeam) {
      targetId = closestEnemyForTeam.id;
    }
  }
}

function robot(state, unit) {
  // Health-based fleeing when health is low
  if (unit.health <= 1) {
    // Try to move away from the closest enemy
    enemies = state.objsByTeam(state.otherTeam);
    closestEnemy = _.minBy(enemies,
      e => e.coords.distanceTo(unit.coords)
    );
    if (closestEnemy) {
      direction = unit.coords.directionTo(closestEnemy.coords);
      // Try to move opposite to the enemy direction
      if (state.objByCoords(unit.coords.add(direction.opposite.toCoords))) {
        // If we can't move directly away, try other directions
        for (let dir of [direction.rotateCw, direction.rotateCcw, direction.opposite.rotateCw]) {
          if (!state.objByCoords(unit.coords.add(dir.toCoords))) {
            return Action.move(dir);
          }
        }
      } else {
        return Action.move(direction.opposite);
      }
    }
  }

  // Use the persistent target if available
  if (targetId) {
    const target = state.objById(targetId);
    if (target) {
      debug.locate(target);
      direction = unit.coords.directionTo(target.coords);

      if (unit.coords.distanceTo(target.coords) === 1) {
        // we're right next to them
        return Action.attack(direction);
      } else {
        // Try to move toward the target, but handle obstacles
        if (state.objByCoords(unit.coords.add(direction.toCoords))) {
          // If path is blocked, try alternative directions
          for (let dir of [direction.rotateCw, direction.rotateCcw, direction.opposite]) {
            if (!state.objByCoords(unit.coords.add(dir.toCoords))) {
              return Action.move(dir);
            }
          }
          // If all paths are blocked, attack in current direction
          return Action.attack(direction);
        } else {
          return Action.move(direction);
        }
      }
    }
  }

  // Fallback to original behavior if no target
  enemies = state.objsByTeam(state.otherTeam);
  closestEnemy = _.minBy(enemies,
    e => e.coords.distanceTo(unit.coords)
  );
  if (closestEnemy) {
    direction = unit.coords.directionTo(closestEnemy.coords);

    if (unit.coords.distanceTo(closestEnemy.coords) === 1) {
      // we're right next to them
      return Action.attack(direction);
    } else {
      return Action.move(direction);
    }
  }

  // If no enemies found, do nothing
  return null;
}