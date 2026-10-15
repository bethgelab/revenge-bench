// This function is called at the beginning of each turn
function init_turn(state) {
    // No initialization needed for this strategy.
}

function robot(state, unit) {
    // Get a list of all enemy units
    const enemies = state.objsByTeam(state.otherTeam);

    // If there are no enemies, do nothing
    if (enemies.length === 0) {
        return null;
    }

    // Deterministically select the best target
    // Sort by health first to focus fire, then by distance, then by ID as a tie-breaker.
    const sortedEnemies = _.orderBy(enemies, [
        'health',
        e => unit.coords.walkingDistanceTo(e.coords),
        'id'
    ], ['asc', 'asc', 'asc']);
    const bestTarget = sortedEnemies[0];


    // If a target is found, decide whether to move or attack
    if (bestTarget) {
        const distanceToTarget = unit.coords.walkingDistanceTo(bestTarget.coords);

        // If we are next to the target, attack it
        if (distanceToTarget <= 1) {
            const direction = unit.coords.directionTo(bestTarget.coords);
            return Action.attack(direction);
        }
        // Otherwise, move towards the target with obstacle avoidance
        else {
            const primaryDirection = unit.coords.directionTo(bestTarget.coords);
            const destinationCoords = unit.coords.add(primaryDirection);
            const objectAtDestination = state.objByCoords(destinationCoords);

            // If the primary path is blocked by a friendly unit, try to move sideways.
            if (objectAtDestination && objectAtDestination.team === state.ourTeam) {
                // Attempt to move clockwise first for deterministic behavior
                const secondaryDirection = primaryDirection.rotateCw();
                const secondaryDestinationCoords = unit.coords.add(secondaryDirection);
                const objectAtSecondary = state.objByCoords(secondaryDestinationCoords);

                if (!objectAtSecondary || objectAtSecondary.team !== state.ourTeam) {
                    return Action.move(secondaryDirection);
                }

                // If clockwise is also blocked, try counter-clockwise
                const tertiaryDirection = primaryDirection.rotateCcw();
                const tertiaryDestinationCoords = unit.coords.add(tertiaryDirection);
                const objectAtTertiary = state.objByCoords(tertiaryDestinationCoords);
                
                if (!objectAtTertiary || objectAtTertiary.team !== state.ourTeam) {
                   return Action.move(tertiaryDirection);
                }
            }
            
            // If the primary path is clear or blocked by an enemy, move towards the target
            return Action.move(primaryDirection);
        }
    }

    // Default action if no target is found (should not happen if enemies exist)
    return null;
}