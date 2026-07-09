function robot(state, unit) {
    // Get enemy and ally units
    const enemies = state.objsByTeam(state.otherTeam);
    const allies = state.objsByTeam(state.ourTeam);
    
    if (enemies.length === 0) {
        return null; // No enemies left
    }
    
    // Helper function to check if a position is free
    function isPositionFree(coords) {
        const obj = state.objByCoords(coords);
        return !obj || (obj.objType !== 'Terrain' && obj.objType !== 'Unit');
    }
    
    // Helper function to move in a direction with fallbacks
    function moveWithFallback(direction) {
        const nextCoords = unit.coords.add(direction);
        if (isPositionFree(nextCoords)) {
            return Action.move(direction);
        }
        
        // Try alternative directions
        const alternatives = [direction.rotateCw, direction.rotateCcw];
        for (const altDir of alternatives) {
            if (isPositionFree(unit.coords.add(altDir))) {
                return Action.move(altDir);
            }
        }
        
        return null; // Can't move
    }
    
    // Count allies in a square area around a position
    function countAlliesNear(coords, radius) {
        let count = 0;
        for (let i = -radius; i <= radius; i++) {
            for (let j = -radius; j <= radius; j++) {
                const checkCoords = new Coords(coords.x + i, coords.y + j);
                const obj = state.objByCoords(checkCoords);
                if (obj && obj.team === unit.team && obj.id !== unit.id) {
                    count++;
                }
            }
        }
        return count;
    }
    
    // ABSOLUTE PRIORITY: Attack ANY adjacent enemy immediately
    // Use Round 7's reliable approach - simple for loop with distanceTo
    for (const enemy of enemies) {
        const distance = unit.coords.distanceTo(enemy.coords);
        if (distance === 1) {
            const direction = unit.coords.directionTo(enemy.coords);
            return Action.attack(direction);
        }
    }
    
    // Find the closest enemy - use distanceTo like Round 7, not walkingDistanceTo
    const closestEnemy = _.minBy(enemies, e => 
        e.coords.distanceTo(unit.coords) + e.health/10
    );
    
    const distance = unit.coords.distanceTo(closestEnemy.coords);
    const direction = unit.coords.directionTo(closestEnemy.coords);
    
    // Look for high-priority targets (enemies attacking our allies) - attack them first
    const priorityTarget = _.find(enemies, enemy => {
        const threatenedAlly = _.find(allies, ally => 
            ally.id !== unit.id && ally.coords.distanceTo(enemy.coords) === 1
        );
        
        if (threatenedAlly) {
            const distanceToThreat = unit.coords.distanceTo(enemy.coords);
            return distanceToThreat <= 3; // We can reach the threat quickly
        }
        return false;
    });
    
    if (priorityTarget) {
        const priorityDirection = unit.coords.directionTo(priorityTarget.coords);
        return moveWithFallback(priorityDirection);
    }
    
    // Only consider retreat if we're critically weak AND significantly outnumbered
    if (unit.health === 1 && distance <= 2) {
        const nearbyAllies = countAlliesNear(unit.coords, 2);
        const nearbyEnemies = enemies.filter(e => 
            e.coords.distanceTo(unit.coords) <= 2
        ).length;
        
        // Only retreat if we have no allies nearby and multiple enemies
        if (nearbyAllies === 0 && nearbyEnemies >= 2) {
            const retreatDirection = direction.opposite;
            const retreatAction = moveWithFallback(retreatDirection);
            if (retreatAction) return retreatAction;
        }
    }
    
    // Default behavior: aggressively move toward closest enemy (like chaser)
    return moveWithFallback(direction);
}