// Global variable to track target
let targetId = null;

function robot(state, unit) {
    // Find all enemy robots
    const enemyTeam = state.otherTeam;
    const enemies = state.objsByTeam(enemyTeam);
    
    // If there are enemies, find the closest one
    let target = null;
    if (enemies.length > 0) {
        if (targetId) {
            // Try to get the previously targeted enemy
            target = state.objById(targetId);
            // If the target no longer exists (was destroyed), find a new one
            if (!target) {
                targetId = null;
            }
        }
        
        // If no target yet, find the closest enemy
        if (!target && enemies.length > 0) {
            // Find the closest enemy (considering health as a factor)
            let closestValue = Infinity;
            for (const enemy of enemies) {
                // Using distance + health/10 as the value to minimize
                // This makes the bot prefer closer enemies or enemies with lower health
                const value = enemy.coords.distanceTo(unit.coords) + enemy.health / 10;
                if (value < closestValue) {
                    closestValue = value;
                    target = enemy;
                }
            }
            if (target) {
                targetId = target.id;
            }
        }
    }
    
    // If we have a target, decide what to do
    if (target) {
        const distance = unit.coords.walkingDistanceTo(target.coords);
        
        // Check if we should flee based on health comparison
        if (unit.health <= 2 && target.health > unit.health) {
            // Try to move away from the enemy
            const fleeDirection = getFleeDirection(state, unit, target.coords.directionTo(unit.coords));
            return fleeDirection || Action.move(target.coords.directionTo(unit.coords));
        }
        
        // Check if we're close to the enemy
        if (distance <= 2) {
            // Count nearby friendly units
            const friendlyTeam = state.ourTeam;
            const friends = state.objsByTeam(friendlyTeam);
            let closeFriends = 0;
            
            for (const friend of friends) {
                if (friend.coords.walkingDistanceTo(target.coords) <= 3) {
                    closeFriends++;
                }
            }
            
            // If we don't have enough support, be more cautious
            if (closeFriends < 2) {
                if (distance === 1) {
                    return Action.attack(unit.coords.directionTo(target.coords));
                } else {
                    // Move toward target but be careful
                    const direction = unit.coords.directionTo(target.coords);
                    return getSafeMove(state, unit, direction) || Action.move(direction);
                }
            } else {
                // We have support, engage more aggressively
                if (distance === 1) {
                    return Action.attack(unit.coords.directionTo(target.coords));
                } else {
                    const direction = unit.coords.directionTo(target.coords);
                    return getSafeMove(state, unit, direction) || Action.move(direction);
                }
            }
        } else {
            // Far from target, move toward it
            const direction = unit.coords.directionTo(target.coords);
            return getSafeMove(state, unit, direction) || Action.move(direction);
        }
    } else {
        // If no enemies, move toward center of map
        const center = new Coords(10, 10);
        const direction = unit.coords.directionTo(center);
        return getSafeMove(state, unit, direction) || Action.move(direction);
    }
}

// Function to get a safe move (tries preferred direction, then alternatives if blocked)
function getSafeMove(state, unit, preferredDirection) {
    // Check if preferred direction is blocked by another unit
    const nextCoords = new Coords(
        unit.coords.x + preferredDirection.toCoords.x,
        unit.coords.y + preferredDirection.toCoords.y
    );
    
    const objAtNext = state.objByCoords(nextCoords);
    if (!objAtNext) {
        return Action.move(preferredDirection);
    }
    
    // Try clockwise rotation
    const cwDirection = preferredDirection.rotateCw;
    const cwCoords = new Coords(
        unit.coords.x + cwDirection.toCoords.x,
        unit.coords.y + cwDirection.toCoords.y
    );
    
    if (!state.objByCoords(cwCoords)) {
        return Action.move(cwDirection);
    }
    
    // Try counter-clockwise rotation
    const ccwDirection = preferredDirection.rotateCcw;
    const ccwCoords = new Coords(
        unit.coords.x + ccwDirection.toCoords.x,
        unit.coords.y + ccwDirection.toCoords.y
    );
    
    if (!state.objByCoords(ccwCoords)) {
        return Action.move(ccwDirection);
    }
    
    // If all directions are blocked, just move in preferred direction (might attack)
    return Action.move(preferredDirection);
}

// Function to get a flee direction (opposite of threat)
function getFleeDirection(state, unit, preferredDirection) {
    // Check if preferred direction (away from threat) is available
    const nextCoords = new Coords(
        unit.coords.x + preferredDirection.toCoords.x,
        unit.coords.y + preferredDirection.toCoords.y
    );
    
    const objAtNext = state.objByCoords(nextCoords);
    if (!objAtNext) {
        return Action.move(preferredDirection);
    }
    
    // Try clockwise rotation
    const cwDirection = preferredDirection.rotateCw;
    const cwCoords = new Coords(
        unit.coords.x + cwDirection.toCoords.x,
        unit.coords.y + cwDirection.toCoords.y
    );
    
    if (!state.objByCoords(cwCoords)) {
        return Action.move(cwDirection);
    }
    
    // Try counter-clockwise rotation
    const ccwDirection = preferredDirection.rotateCcw;
    const ccwCoords = new Coords(
        unit.coords.x + ccwDirection.toCoords.x,
        unit.coords.y + ccwDirection.toCoords.y
    );
    
    if (!state.objByCoords(ccwCoords)) {
        return Action.move(ccwDirection);
    }
    
    // If all directions are blocked, we can't flee
    return null;
}