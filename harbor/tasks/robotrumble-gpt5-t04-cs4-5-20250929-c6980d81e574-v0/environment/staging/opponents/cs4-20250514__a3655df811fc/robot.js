function robot(state, unit) {
    // Simple aggressive configuration - inspired by successful Round 3 approach
    const FLEE_HEALTH_THRESHOLD = 1; // Only flee when critically low
    
    // Get all enemies and allies
    let enemies = state.objsByTeam(state.otherTeam);
    let allies = state.objsByTeam(state.ourTeam).filter(a => a.id !== unit.id);
    
    // If no enemies, move toward center with some randomness to avoid clustering
    if (!enemies || enemies.length === 0) {
        let centerCoords = new Coords(10, 10);
        let direction = unit.coords.directionTo(centerCoords);
        
        // Add some randomness to prevent clustering
        if (Math.random() < 0.3) {
            direction = direction.rotateLeft();
        } else if (Math.random() < 0.3) {
            direction = direction.rotateRight();
        }
        
        return tryMove(state, unit, direction);
    }
    
    // Simple but effective target selection: distance + health * 0.2
    let bestEnemy = _.minBy(enemies, e => {
        let distance = e.coords.distanceTo(unit.coords);
        let healthFactor = e.health * 0.2; // Prioritize weak enemies
        return distance + healthFactor;
    });
    
    let direction = unit.coords.directionTo(bestEnemy.coords);
    let distanceToEnemy = unit.coords.distanceTo(bestEnemy.coords);
    
    // Simple fleeing logic - only when critically low
    if (unit.health <= FLEE_HEALTH_THRESHOLD) {
        // Still attack if we can kill a weak enemy
        if (distanceToEnemy === 1 && bestEnemy.health <= unit.health) {
            return Action.attack(direction);
        }
        
        // Flee away from enemies
        return tryMove(state, unit, direction.opposite());
    }
    
    // Attack when adjacent
    if (distanceToEnemy === 1) {
        return Action.attack(direction);
    }
    
    // Simple coordination: only avoid 3+ enemies when alone and low health
    let nearbyEnemies = enemies.filter(enemy => 
        enemy.coords.distanceTo(unit.coords) <= 3
    );
    let nearbyAllies = allies.filter(ally => 
        ally.coords.distanceTo(unit.coords) <= 3
    );
    
    // Only retreat if facing 3+ enemies alone AND low on health
    if (nearbyEnemies.length >= 3 && nearbyAllies.length === 0 && unit.health <= 2) {
        if (allies.length > 0) {
            let nearestAlly = _.minBy(allies, ally => ally.coords.distanceTo(unit.coords));
            let regroupDirection = unit.coords.directionTo(nearestAlly.coords);
            return tryMove(state, unit, regroupDirection);
        }
    }
    
    // Default: aggressively move toward target
    return tryMove(state, unit, direction);
}

// Simple collision avoidance
function tryMove(state, unit, direction) {
    let targetCoords = unit.coords.add(direction.toCoords);
    let obstruction = state.objByCoords(targetCoords);
    
    if (!obstruction) {
        return Action.move(direction);
    }
    
    // Try alternative directions
    let alternatives = [
        direction.rotateLeft(),
        direction.rotateRight(),
        direction.rotateLeft().rotateLeft(),
        direction.rotateRight().rotateRight()
    ];
    
    for (let altDir of alternatives) {
        let altCoords = unit.coords.add(altDir.toCoords);
        let altObstruction = state.objByCoords(altCoords);
        
        if (!altObstruction) {
            return Action.move(altDir);
        }
    }
    
    // Attack if blocked by enemy
    if (obstruction && obstruction.team === state.otherTeam) {
        return Action.attack(direction);
    }
    
    // Stay put if all paths blocked
    return null;
}