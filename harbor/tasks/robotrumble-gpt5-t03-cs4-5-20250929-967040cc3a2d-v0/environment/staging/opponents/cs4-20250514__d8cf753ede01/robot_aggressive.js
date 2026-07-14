// Global coordination variables
let COORDINATED_ACTIONS = {};
let LAST_TURN = -1;

function robot(state, unit) {
    // Only calculate coordinated actions once per turn for all units
    if (state.turn !== LAST_TURN) {
        LAST_TURN = state.turn;
        COORDINATED_ACTIONS = calculateCoordinatedActions(state);
    }
    
    // Return the pre-calculated action for this unit
    const action = COORDINATED_ACTIONS[unit.id];
    if (action) {
        return action;
    }
    
    // Fallback to simple behavior if coordination fails
    return simpleUnitBehavior(state, unit);
}

function calculateCoordinatedActions(state) {
    const allies = state.objsByTeam(state.ourTeam);
    const enemies = state.objsByTeam(state.otherTeam);
    const actions = {};
    
    if (enemies.length === 0) {
        // Move toward center if no enemies
        const center = new Coords(Math.floor(MAP_SIZE / 2), Math.floor(MAP_SIZE / 2));
        allies.forEach(unit => {
            const direction = unit.coords.directionTo(center);
            actions[unit.id] = Action.move(direction);
        });
        return actions;
    }
    
    // Enhanced target assignment with priority system
    allies.forEach(unit => {
        const action = getUnitAction(unit, allies, enemies);
        actions[unit.id] = action;
    });
    
    return actions;
}

function getUnitAction(unit, allies, enemies) {
    // Priority 1: Attack adjacent enemies (prioritize wounded ones)
    const adjacentEnemies = enemies.filter(e => unit.coords.distanceTo(e.coords) === 1);
    if (adjacentEnemies.length > 0) {
        // Target the most wounded adjacent enemy
        const target = _.minBy(adjacentEnemies, e => e.health);
        const direction = unit.coords.directionTo(target.coords);
        return Action.attack(direction);
    }
    
    // Priority 2: Move toward best target with more aggressive pathfinding
    const target = selectBestTarget(unit, enemies);
    if (target) {
        const moveAction = aggressiveMove(unit, target, allies, enemies);
        if (moveAction) {
            return moveAction;
        }
    }
    
    // Priority 3: Fallback movement
    return fallbackMove(unit, allies, enemies);
}

function selectBestTarget(unit, enemies) {
    if (enemies.length === 0) return null;
    
    // More aggressive targeting - prioritize closest enemies more heavily
    const scoredEnemies = enemies.map(enemy => {
        const distance = unit.coords.distanceTo(enemy.coords);
        // Heavily favor closer enemies, less emphasis on wounded enemies
        const score = (30 - distance * 2) + (10 - enemy.health);
        return { enemy, score };
    });
    
    // Return the highest scoring enemy
    return _.maxBy(scoredEnemies, s => s.score).enemy;
}

function aggressiveMove(unit, target, allies, enemies) {
    const allUnits = [...allies, ...enemies];
    const primaryDirection = unit.coords.directionTo(target.coords);
    
    // Try primary direction first - be more aggressive about moving toward target
    if (canMoveTo(unit, primaryDirection, allUnits)) {
        return Action.move(primaryDirection);
    }
    
    // Try alternative directions that still get us closer
    const alternativeDirections = getFlankingDirections(unit, target, primaryDirection);
    
    for (const direction of alternativeDirections) {
        if (canMoveTo(unit, direction, allUnits)) {
            // Less strict about spacing - be more aggressive
            return Action.move(direction);
        }
    }
    
    // Last resort: try any valid direction
    const allDirections = [Direction.North, Direction.East, Direction.South, Direction.West];
    for (const direction of allDirections) {
        if (canMoveTo(unit, direction, allUnits)) {
            return Action.move(direction);
        }
    }
    
    return null;
}

function getFlankingDirections(unit, target, primaryDirection) {
    const allDirections = [Direction.North, Direction.East, Direction.South, Direction.West];
    const alternatives = allDirections.filter(d => !d.equals(primaryDirection));
    
    // Sort alternatives by how much they help us approach the target
    return alternatives.sort((a, b) => {
        const posA = unit.coords.add(a);
        const posB = unit.coords.add(b);
        const distA = posA.distanceTo(target.coords);
        const distB = posB.distanceTo(target.coords);
        return distA - distB; // Prefer directions that get us closer
    });
}

function canMoveTo(unit, direction, allUnits) {
    const targetCoords = unit.coords.add(direction);
    
    // Check bounds (assuming 19x19 map)
    if (targetCoords.x < 0 || targetCoords.x >= MAP_SIZE || 
        targetCoords.y < 0 || targetCoords.y >= MAP_SIZE) {
        return false;
    }
    
    // Check if occupied
    return !allUnits.some(u => u.coords.equals(targetCoords));
}

function fallbackMove(unit, allies, enemies) {
    // Move toward center of enemy formation
    if (enemies.length > 0) {
        const avgX = enemies.reduce((sum, e) => sum + e.coords.x, 0) / enemies.length;
        const avgY = enemies.reduce((sum, e) => sum + e.coords.y, 0) / enemies.length;
        const enemyCenter = new Coords(Math.floor(avgX), Math.floor(avgY));
        const direction = unit.coords.directionTo(enemyCenter);
        return Action.move(direction);
    }
    
    // Move toward map center
    const center = new Coords(Math.floor(MAP_SIZE / 2), Math.floor(MAP_SIZE / 2));
    const direction = unit.coords.directionTo(center);
    return Action.move(direction);
}

function simpleUnitBehavior(state, unit) {
    const enemies = state.objsByTeam(state.otherTeam);
    const allies = state.objsByTeam(state.ourTeam);
    
    if (enemies.length === 0) {
        const center = new Coords(Math.floor(MAP_SIZE / 2), Math.floor(MAP_SIZE / 2));
        const direction = unit.coords.directionTo(center);
        return Action.move(direction);
    }
    
    // Find nearest enemy
    const nearestEnemy = _.minBy(enemies, e => e.coords.distanceTo(unit.coords));
    const distance = unit.coords.distanceTo(nearestEnemy.coords);
    const direction = unit.coords.directionTo(nearestEnemy.coords);
    
    // Attack if adjacent
    if (distance === 1) {
        return Action.attack(direction);
    }
    
    // Move toward enemy
    return Action.move(direction);
}