var target_id = null;

function init_turn(state) {
    if (state.turn === 1) {
        let enemies = state.objsByTeam(state.otherTeam);
        let teammates = state.objsByTeam(state.ourTeam);
        if (enemies.length > 0) {
            let bestEnemy = null;
            let minSum = Infinity;
            for (let enemy of enemies) {
                let sum = 0;
                for (let mate of teammates) {
                    sum += mate.coords.distanceTo(enemy.coords);
                }
                if (sum < minSum) {
                    minSum = sum;
                    bestEnemy = enemy;
                }
            }
            target_id = bestEnemy ? bestEnemy.id : null;
        }
    }
}

function robot(state, unit) {
    let enemies = state.objsByTeam(state.otherTeam);
    if (enemies.length === 0) {
        return Action.move(Direction.East);
    }
    
    let target = null;
    if (target_id) {
        target = state.objById(target_id);
        if (!target || target.health <= 0) {
            target_id = null;
        }
    }
    if (!target) {
        let closestEnemy = null;
        let minDistance = Infinity;
        for (let enemy of enemies) {
            let dist = unit.coords.distanceTo(enemy.coords);
            if (dist < minDistance) {
                minDistance = dist;
                closestEnemy = enemy;
            }
        }
        target = closestEnemy;
    }
    
    if (target) {
        let direction = unit.coords.directionTo(target.coords);
        let walkingDist = unit.coords.walkingDistanceTo(target.coords);
        if (walkingDist <= 1) {
            return Action.attack(direction);
        } else {
            // Avoid moving out of bounds
            let newCoords = unit.coords.add(direction.toCoords());
            if (newCoords.x >= 0 && newCoords.x < MAP_SIZE && newCoords.y >= 0 && newCoords.y < MAP_SIZE) {
                return Action.move(direction);
            } else {
                // Try other directions towards target or fallback
                return Action.move(Direction.East);
            }
        }
    }
    
    return Action.move(Direction.East);
}