function findBestTarget(state, unit) {
    // Initialize cache on the state object if it doesn't exist.
    // This leverages the fact that the 'state' object persists for all unit actions within a single turn.
    if (!state.bestTargetCache || state.bestTargetCache.turn !== state.turn) {
        // Cache is invalid or for a previous turn, so we must recalculate.
        const enemies = state.objsByTeam(state.otherTeam);

        if (enemies.length === 0) {
            state.bestTargetCache = {
                turn: state.turn,
                target: null,
            };
            return null;
        }

        // Find the enemy with the minimum health.
        let bestTarget = enemies.reduce((prev, curr) => {
            return prev.health < curr.health ? prev : curr;
        });
        
        // Store the found target and the current turn number in the cache.
        state.bestTargetCache = {
            turn: state.turn,
            target: bestTarget,
        };
    }

    // Return the cached target.
    return state.bestTargetCache.target;
}


function robot(state, unit) {
    try {
        const bestTarget = findBestTarget(state, unit);

        if (!bestTarget) {
            // No enemies, just move around aimlessly as a fallback.
            if (state.turn % 2 == 0) return Action.move(Direction.East);
            else return Action.move(Direction.South);
        }

        // --- Attack Logic ---
        // If we are adjacent to the target, attack it.
        if (unit.coords.manhattanDistanceTo(bestTarget.coords) === 1) {
            const directionToTarget = unit.coords.directionTo(bestTarget.coords);
            if (directionToTarget) {
                return Action.attack(directionToTarget);
            }
        }

        // --- Movement Logic ---
        // Find the best direction to move towards the target.
        const directions = [Direction.North, Direction.South, Direction.East, Direction.West];
        let bestDirection = null;
        let minDistance = unit.coords.manhattanDistanceTo(bestTarget.coords);

        for (const direction of directions) {
            const moveCoords = unit.coords.add(direction);

            // Basic map bounds check.
            if (moveCoords.x < 0 || moveCoords.y < 0 || moveCoords.x >= state.map_width || moveCoords.y >= state.map_height) {
                continue;
            }
            
            // Basic collision check: don't move into terrain or friendly units.
            const objAtNext = state.objByCoords(moveCoords);
            if (objAtNext && (objAtNext.objType === ObjType.Terrain || objAtNext.team === state.ourTeam)) {
                continue;
            }
            
            // Choose the direction that gets us closest to the target.
            const distance = moveCoords.manhattanDistanceTo(bestTarget.coords);
            if (distance < minDistance) {
                minDistance = distance;
                bestDirection = direction;
            }
        }

        if (bestDirection) {
            return Action.move(bestDirection);
        }

    } catch (e) {
        // It's good practice to log errors, but in a production environment,
        // we might not want to print to console. For now, this is disabled.
        // console.log(`Error for unit ${unit.id}: ${e}`);
    }

    // Fallback "dance" if no other action is taken.
    if (state.turn % 2 == 0) return Action.move(Direction.West);
    else return Action.move(Direction.North);
}