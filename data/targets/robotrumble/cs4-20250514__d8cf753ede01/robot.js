// Global coordination variables
let COORDINATED_ACTIONS = {};
let LAST_TURN = -1;
let OPPONENT_BEHAVIOR = null;
let BEHAVIOR_ANALYSIS = { directMoves: 0, totalMoves: 0, lastEnemyPositions: {} };

function robot(state, unit) {
    // Only calculate coordinated actions once per turn for all units
    if (state.turn !== LAST_TURN) {
        LAST_TURN = state.turn;
        
        // Analyze opponent behavior for adaptive strategy
        if (state.turn > 1) {
            analyzeOpponentBehavior(state);
        }
        
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

function analyzeOpponentBehavior(state) {
    const enemies = state.objsByTeam(state.otherTeam);
    const allies = state.objsByTeam(state.ourTeam);
    
    // Track enemy movement patterns
    enemies.forEach(enemy => {
        const lastPos = BEHAVIOR_ANALYSIS.lastEnemyPositions[enemy.id];
        if (lastPos) {
            BEHAVIOR_ANALYSIS.totalMoves++;
            
            // Check if enemy moved directly toward closest ally
            const closestAlly = _.minBy(allies, a => lastPos.distanceTo(a.coords));
            if (closestAlly) {
                const expectedDirection = lastPos.directionTo(closestAlly.coords);
                const actualDirection = lastPos.directionTo(enemy.coords);
                
                if (expectedDirection.equals(actualDirection)) {
                    BEHAVIOR_ANALYSIS.directMoves++;
                }
            }
        }
        BEHAVIOR_ANALYSIS.lastEnemyPositions[enemy.id] = enemy.coords;
    });
    
    // Determine opponent behavior type - be more aggressive in detection
    if (BEHAVIOR_ANALYSIS.totalMoves > 5) {
        const aggressionRatio = BEHAVIOR_ANALYSIS.directMoves / BEHAVIOR_ANALYSIS.totalMoves;
        
        if (aggressionRatio > 0.6) {
            OPPONENT_BEHAVIOR = 'AGGRESSIVE';
        } else if (aggressionRatio < 0.3) {
            OPPONENT_BEHAVIOR = 'COMPLEX';
        } else {
            OPPONENT_BEHAVIOR = 'MIXED';
        }
    }
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
    
    // Choose strategy based on opponent behavior
    if (OPPONENT_BEHAVIOR === 'AGGRESSIVE' || state.turn < 10) {
        // Default to aggressive counter early in game or vs aggressive opponents
        return calculateAggressiveCounterActions(allies, enemies);
    } else {
        return calculateCoordinatedActions_Original(allies, enemies);
    }
}

function calculateAggressiveCounterActions(allies, enemies) {
    const actions = {};
    
    // Focus fire strategy - all units target the same enemy when possible
    const primaryTarget = selectPrimaryTarget(enemies, allies);
    
    allies.forEach(unit => {
        const action = getAggressiveAction(unit, allies, enemies, primaryTarget);
        actions[unit.id] = action;
    });
    
    return actions;
}

function selectPrimaryTarget(enemies, allies) {
    if (enemies.length === 0) return null;
    
    // Find the enemy that's closest to any of our units (most threatening)
    let closestDistance = Infinity;
    let primaryTarget = null;
    
    enemies.forEach(enemy => {
        const minDistanceToAlly = Math.min(...allies.map(ally => 
            ally.coords.distanceTo(enemy.coords)
        ));
        
        if (minDistanceToAlly < closestDistance) {
            closestDistance = minDistanceToAlly;
            primaryTarget = enemy;
        }
    });
    
    return primaryTarget;
}

function getAggressiveAction(unit, allies, enemies, primaryTarget) {
    // Priority 1: Attack adjacent enemies (focus fire on primary target if possible)
    const adjacentEnemies = enemies.filter(e => unit.coords.distanceTo(e.coords) === 1);
    if (adjacentEnemies.length > 0) {
        // Prefer primary target if adjacent, otherwise weakest
        let target = adjacentEnemies.find(e => e.id === primaryTarget?.id);
        if (!target) {
            target = _.minBy(adjacentEnemies, e => e.health);
        }
        const direction = unit.coords.directionTo(target.coords);
        return Action.attack(direction);
    }
    
    // Priority 2: Move toward primary target aggressively
    if (primaryTarget) {
        const direction = unit.coords.directionTo(primaryTarget.coords);
        const targetCoords = unit.coords.add(direction);
        const allUnits = [...allies, ...enemies];
        
        // Try direct movement first
        if (canMoveTo(unit, direction, allUnits)) {
            return Action.move(direction);
        }
        
        // Try alternative directions that still get us closer
        const alternatives = [Direction.North, Direction.East, Direction.South, Direction.West]
            .filter(d => !d.equals(direction))
            .sort((a, b) => {
                const posA = unit.coords.add(a);
                const posB = unit.coords.add(b);
                return posA.distanceTo(primaryTarget.coords) - posB.distanceTo(primaryTarget.coords);
            });
        
        for (const altDir of alternatives) {
            if (canMoveTo(unit, altDir, allUnits)) {
                return Action.move(altDir);
            }
        }
        
        // If completely blocked, try to move toward any enemy
        const nearestEnemy = _.minBy(enemies, e => unit.coords.distanceTo(e.coords));
        const fallbackDirection = unit.coords.directionTo(nearestEnemy.coords);
        return Action.move(fallbackDirection);
    }
    
    // Fallback: move toward nearest enemy
    const nearestEnemy = _.minBy(enemies, e => unit.coords.distanceTo(e.coords));
    const direction = unit.coords.directionTo(nearestEnemy.coords);
    return Action.move(direction);
}

function calculateCoordinatedActions_Original(allies, enemies) {
    const actions = {};
    
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
    
    // Priority 2: Move toward best target with improved pathfinding
    const target = selectBestTarget(unit, enemies);
    if (target) {
        const moveAction = smartMove(unit, target, allies, enemies);
        if (moveAction) {
            return moveAction;
        }
    }
    
    // Priority 3: Fallback movement
    return fallbackMove(unit, allies, enemies);
}

function selectBestTarget(unit, enemies) {
    if (enemies.length === 0) return null;
    
    // Score enemies based on distance and health
    const scoredEnemies = enemies.map(enemy => {
        const distance = unit.coords.distanceTo(enemy.coords);
        // Prefer closer enemies and wounded enemies
        const score = (10 - enemy.health) * 2 + (20 - distance);
        return { enemy, score };
    });
    
    // Return the highest scoring enemy
    return _.maxBy(scoredEnemies, s => s.score).enemy;
}

function smartMove(unit, target, allies, enemies) {
    const allUnits = [...allies, ...enemies];
    const primaryDirection = unit.coords.directionTo(target.coords);
    
    // Try primary direction first
    if (canMoveTo(unit, primaryDirection, allUnits)) {
        return Action.move(primaryDirection);
    }
    
    // Try flanking maneuvers - directions that get us closer while avoiding obstacles
    const alternativeDirections = getFlankingDirections(unit, target, primaryDirection);
    
    for (const direction of alternativeDirections) {
        if (canMoveTo(unit, direction, allUnits)) {
            const newPos = unit.coords.add(direction);
            // Prefer moves that don't cluster with allies (unless facing aggressive opponent)
            if (OPPONENT_BEHAVIOR === 'AGGRESSIVE' || maintainSpacing(newPos, allies, unit)) {
                return Action.move(direction);
            }
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

function maintainSpacing(newPos, allies, currentUnit) {
    // Avoid clustering - prefer positions that aren't too close to other allies
    const nearbyAllies = allies.filter(ally => 
        ally.id !== currentUnit.id && 
        ally.coords.distanceTo(newPos) <= 2
    );
    return nearbyAllies.length <= 2; // Allow some clustering but not too much
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