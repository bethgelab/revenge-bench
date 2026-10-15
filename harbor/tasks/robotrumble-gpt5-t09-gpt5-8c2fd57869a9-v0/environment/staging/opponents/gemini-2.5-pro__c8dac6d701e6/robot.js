// A reliable function to determine the direction from one coordinate to another.
// Replaces the buggy built-in `directionTo`.
// Coordinate system determined from log analysis: +y is South, +x is East.
function getDirection(c1, c2) {
    const dx = c2.x - c1.x;
    const dy = c2.y - c1.y;

    if (Math.abs(dx) > Math.abs(dy)) {
        // Horizontal movement is primary
        return dx > 0 ? Direction.East : Direction.West;
    } else {
        // Vertical movement is primary (or diagonal)
        return dy > 0 ? Direction.South : Direction.North;
    }
}

// Runs once per turn for the team.
// Designates a single priority target for all robots to focus on.
function init_turn(state, team_memory) {
    const enemies = state.objsByTeam(state.otherTeam);
    if (enemies.length > 0) {
        // Find the weakest enemy and designate it as the priority target.
        const priorityTarget = _.minBy(enemies, enemy => enemy.health);
        team_memory.priorityTargetId = priorityTarget.id;
    } else {
        // No enemies, clear any previous target.
        team_memory.priorityTargetId = null;
    }
}

// Runs for each robot individually every turn.
function robot(state, unit) {
    const HEALTH_THRESHOLD = 30;

    // --- 1. Self-preservation Logic (Highest Priority) ---
    if (unit.health <= HEALTH_THRESHOLD) {
        const enemies = state.objsByTeam(state.otherTeam);
        if (enemies.length > 0) {
            // Find the closest enemy to flee from
            const closestEnemy = _.minBy(enemies, enemy => unit.coords.walkingDistanceTo(enemy.coords));

            if (closestEnemy) {
                // Get the direction TOWARDS the enemy, then reverse it to flee.
                const directionToEnemy = getDirection(unit.coords, closestEnemy.coords);
                const fleeDirection = directionToEnemy.opposite;
                return Action.move(fleeDirection);
            }
        }
    }

    // --- 2. Offensive Logic ---
    let target = null;
    const enemies = state.objsByTeam(state.otherTeam);

    if (enemies.length === 0) {
        // No enemies, move randomly.
        const directions = [Direction.North, Direction.South, Direction.East, Direction.West];
        const randomDirection = directions[Math.floor(Math.random() * directions.length)];
        return Action.move(randomDirection);
    }
    
    // --- Team Coordination: Focus on the priority target if it exists ---
    const priorityTargetId = state.team_memory.priorityTargetId;
    if (priorityTargetId) {
        const priorityTarget = state.objById(priorityTargetId);
        // Check if the target is still alive and on the enemy team
        if (priorityTarget && priorityTarget.team === state.otherTeam) {
            target = priorityTarget;
        }
    }

    // --- Fallback: If no priority target, find the weakest/closest enemy ---
    if (!target) {
        // Find the weakest enemy, using distance as a tie-breaker.
        // A lower score is better. We weight health much higher than distance.
        target = _.minBy(enemies, enemy => {
            return enemy.health * 1000 + unit.coords.walkingDistanceTo(enemy.coords);
        });
    }

    // --- Execute Action ---
    if (target) {
        const distance = unit.coords.walkingDistanceTo(target.coords);
        const direction = getDirection(unit.coords, target.coords);

        if (distance === 1) {
            return Action.attack(direction);
        } else {
            return Action.move(direction);
        }
    }
    
    // Absolute fallback: If something is wrong and there are no enemies, do nothing.
    return;
}