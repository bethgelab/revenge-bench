// Helper function to find the closest enemy. Used for retreating.
function findClosestEnemy(state, unit) {
    const enemies = state.objsByTeam(state.otherTeam);
    if (enemies.length === 0) {
        return null;
    }

    let closestEnemy = null;
    let minDistance = Infinity;

    for (const enemy of enemies) {
        const distance = unit.coords.distanceTo(enemy.coords);
        if (distance < minDistance) {
            minDistance = distance;
            closestEnemy = enemy;
        }
    }
    return closestEnemy;
}

// Helper function to find the optimal target using a heuristic of health + distance.
function findNewFocusTarget(state, referenceCoords) {
    const enemies = state.objsByTeam(state.otherTeam);
    if (enemies.length === 0) {
        return null;
    }
    // Prioritize a balance of low health and proximity. Tie-break with ID.
    enemies.sort((a, b) => {
        const scoreA = a.health + a.coords.distanceTo(referenceCoords);
        const scoreB = b.health + b.coords.distanceTo(referenceCoords);
        if (scoreA !== scoreB) {
            return scoreA - scoreB;
        }
        return parseInt(a.id) - parseInt(b.id);
    });
    return enemies[0];
}


function robot(state, unit) {
    console.log(`[Turn ${state.turn}, Unit ${unit.id}] Robot starting.`);
    const LOW_HEALTH_THRESHOLD = 3;
    // The documentation (docs/tutorials/tutorial1.yaml) states that attacks are only possible
    // when "directly next to" an opponent, which implies a range of 1.
    const ATTACK_RANGE = 1;
    const THREAT_RANGE = 4;

    // 1. DEFENSIVE LOGIC: Retreat if health is low AND an enemy is close.
    if (unit.health <= LOW_HEALTH_THRESHOLD) {
        const closestEnemy = findClosestEnemy(state, unit);
        if (closestEnemy && unit.coords.distanceTo(closestEnemy.coords) <= THREAT_RANGE) {
            const direction = unit.coords.directionTo(closestEnemy.coords);
            console.log(`[Unit ${unit.id}] Low health (${unit.health}) and enemy ${closestEnemy.id} is close. Retreating.`);
            return Action.move(direction.opposite);
        }
    }

    // 2. OFFENSIVE LOGIC: Find the best target and engage.
    // Use the first unit in the list as a stable reference point for distance calculations.
    // This ensures all units agree on the same target.
    const referenceCoords = state.myUnits[0].coords;
    const target = findNewFocusTarget(state, referenceCoords);

    if (target) {
        const distance = unit.coords.distanceTo(target.coords);
        
        // If target is in range, ATTACK.
        if (distance <= ATTACK_RANGE) {
            const direction = unit.coords.directionTo(target.coords);
            console.log(`[Unit ${unit.id}] Attacking target ${target.id} from range ${distance}.`);
            return Action.attack(direction);
        } 
        // If target is out of range, MOVE towards it.
        else {
            const direction = unit.coords.directionTo(target.coords);
            console.log(`[Unit ${unit.id}] Moving towards target ${target.id}.`);
            return Action.move(direction);
        }
    } 
    // 3. FALLBACK LOGIC: If no enemies, move to the center.
    else {
        console.log(`[Unit ${unit.id}] No target found. Moving to center.`);
        const center = new Coords(Math.floor(MAP_SIZE / 2), Math.floor(MAP_SIZE / 2));
        const directionToCenter = unit.coords.directionTo(center);
        return Action.move(directionToCenter);
    }
}