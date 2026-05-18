function robot(state, unit) {
    const enemies = state.objsByTeam(state.otherTeam);
    const allies = state.objsByTeam(state.ourTeam);
    
    if (enemies.length === 0) {
        const center = new Coords(Math.floor(MAP_SIZE / 2), Math.floor(MAP_SIZE / 2));
        const direction = unit.coords.directionTo(center);
        return Action.move(direction);
    }
    
    // Priority 1: Attack adjacent enemies (prioritize wounded ones)
    const adjacentEnemies = enemies.filter(e => unit.coords.distanceTo(e.coords) === 1);
    if (adjacentEnemies.length > 0) {
        const target = _.minBy(adjacentEnemies, e => e.health);
        const direction = unit.coords.directionTo(target.coords);
        return Action.attack(direction);
    }
    
    // Priority 2: Move toward closest enemy (like chaser but with better target selection)
    const target = selectBestTarget(unit, enemies);
    if (target) {
        const direction = unit.coords.directionTo(target.coords);
        const targetCoords = unit.coords.add(direction);
        
        // Check if we can move there
        if (canMoveTo(targetCoords, [...allies, ...enemies], unit)) {
            return Action.move(direction);
        }
        
        // Try alternative directions if blocked
        const alternatives = [Direction.North, Direction.East, Direction.South, Direction.West];
        for (const altDir of alternatives) {
            if (!altDir.equals(direction) && canMoveTo(unit.coords.add(altDir), [...allies, ...enemies], unit)) {
                return Action.move(altDir);
            }
        }
    }
    
    // Fallback: move toward center
    const center = new Coords(Math.floor(MAP_SIZE / 2), Math.floor(MAP_SIZE / 2));
    const direction = unit.coords.directionTo(center);
    return Action.move(direction);
}

function selectBestTarget(unit, enemies) {
    if (enemies.length === 0) return null;
    
    // Score enemies based on distance and health (prefer closer and wounded)
    const scoredEnemies = enemies.map(enemy => {
        const distance = unit.coords.distanceTo(enemy.coords);
        const score = (10 - enemy.health) * 2 + (20 - distance);
        return { enemy, score };
    });
    
    return _.maxBy(scoredEnemies, s => s.score).enemy;
}

function canMoveTo(targetCoords, allUnits, currentUnit) {
    // Check bounds
    if (targetCoords.x < 0 || targetCoords.x >= MAP_SIZE || 
        targetCoords.y < 0 || targetCoords.y >= MAP_SIZE) {
        return false;
    }
    
    // Check if occupied by another unit
    return !allUnits.some(u => u.id !== currentUnit.id && u.coords.equals(targetCoords));
}