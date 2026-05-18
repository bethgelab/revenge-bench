function robot(state, unit) {
    const enemies = state.objsByTeam(state.otherTeam);
    const allies = state.objsByTeam(state.ourTeam);
    
    // NEW STRATEGY: SMART AGGRESSIVE COMBAT
    // Focus on winning individual battles and staying alive
    // Be aggressive but pick fights we can win
    
    // Attack adjacent enemies - prioritize weak ones
    const adjacentEnemies = enemies.filter(enemy => 
        unit.coords.walkingDistanceTo(enemy.coords) === 1
    );
    
    if (adjacentEnemies.length > 0) {
        // Always attack the weakest adjacent enemy
        const weakestEnemy = adjacentEnemies.reduce((weakest, enemy) => 
            enemy.health < weakest.health ? enemy : weakest
        );
        return Action.attack(weakestEnemy.coords);
    }
    
    // Find the nearest enemy to engage
    let nearestEnemy = null;
    let minEnemyDist = Infinity;
    for (const enemy of enemies) {
        const dist = unit.coords.walkingDistanceTo(enemy.coords);
        if (dist < minEnemyDist) {
            minEnemyDist = dist;
            nearestEnemy = enemy;
        }
    }
    
    if (nearestEnemy) {
        // Move toward the nearest enemy, but be smart about positioning
        const allDirections = [Direction.North, Direction.South, Direction.East, Direction.West];
        let bestDirection = null;
        let bestScore = -Infinity;
        
        for (const dir of allDirections) {
            const newCoords = unit.coords.add(dir.toCoords);
            const obj = state.objByCoords(newCoords);
            
            // Can't move to occupied spaces
            if (obj && (obj.objType === "Terrain" || obj.objType === "Unit")) {
                continue;
            }
            
            // Calculate score for this position
            let score = 0;
            
            // Primary goal: get closer to nearest enemy
            const distToEnemy = newCoords.walkingDistanceTo(nearestEnemy.coords);
            score -= distToEnemy * 10; // Negative because we want smaller distance
            
            // Secondary goal: stay near allies for support
            const nearbyAllies = allies.filter(ally => 
                newCoords.walkingDistanceTo(ally.coords) <= 2
            ).length;
            score += nearbyAllies * 5;
            
            // Avoid being surrounded by too many enemies
            const nearbyEnemies = enemies.filter(enemy => 
                newCoords.walkingDistanceTo(enemy.coords) <= 2
            ).length;
            score -= nearbyEnemies * 3;
            
            // Prefer positions that don't put us adjacent to multiple enemies
            const adjacentEnemiesAtNewPos = enemies.filter(enemy => 
                newCoords.walkingDistanceTo(enemy.coords) === 1
            ).length;
            if (adjacentEnemiesAtNewPos > 1) {
                score -= 20; // Heavy penalty for being adjacent to multiple enemies
            }
            
            if (score > bestScore) {
                bestScore = score;
                bestDirection = dir;
            }
        }
        
        if (bestDirection) {
            return Action.move(bestDirection);
        }
    }
    
    // Fallback: move toward center of map
    const mapCenter = new Coords(9, 9); // Assuming 19x19 map
    const allDirections = [Direction.North, Direction.South, Direction.East, Direction.West];
    let bestDirection = null;
    let bestDistance = Infinity;
    
    for (const dir of allDirections) {
        const newCoords = unit.coords.add(dir.toCoords);
        const obj = state.objByCoords(newCoords);
        
        if (!obj || (obj.objType !== "Terrain" && obj.objType !== "Unit")) {
            const distToCenter = newCoords.walkingDistanceTo(mapCenter);
            if (distToCenter < bestDistance) {
                bestDistance = distToCenter;
                bestDirection = dir;
            }
        }
    }
    
    if (bestDirection) {
        return Action.move(bestDirection);
    }
    
    // Last resort: try any valid move
    for (const dir of [Direction.North, Direction.South, Direction.East, Direction.West]) {
        const newCoords = unit.coords.add(dir.toCoords);
        const obj = state.objByCoords(newCoords);
        
        if (!obj || (obj.objType !== "Terrain" && obj.objType !== "Unit")) {
            return Action.move(dir);
        }
    }
    
    // Can't move anywhere
    return Action.move(Direction.North);
}