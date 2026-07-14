function robot(state, unit) {
    // Get enemy team
    const enemyTeam = state.otherTeam;
    const enemies = state.objsByTeam(enemyTeam);
    
    // If no enemies, move toward center for better positioning
    if (enemies.length === 0) {
        const center = new Coords(9, 9); // Center of 19x19 grid
        const directionToCenter = unit.coords.directionTo(center);
        return Action.move(directionToCenter);
    }
    
    // Find the best target: prioritize closest, but prefer weaker enemies if close
    let bestTarget = null;
    let bestScore = Infinity;
    
    for (const enemy of enemies) {
        const distance = unit.coords.distanceTo(enemy.coords);
        // Score combines distance and health (lower is better)
        // Prioritize distance but consider health for close enemies
        const score = distance * 10 + (enemy.health || 10);
        
        if (score < bestScore) {
            bestScore = score;
            bestTarget = enemy;
        }
    }
    
    if (bestTarget) {
        const distance = unit.coords.distanceTo(bestTarget.coords);
        
        // If adjacent to best target, attack
        if (distance === 1) {
            const attackDirection = unit.coords.directionTo(bestTarget.coords);
            return Action.attack(attackDirection);
        }
        
        // Otherwise, move toward the best target
        const moveDirection = unit.coords.directionTo(bestTarget.coords);
        return Action.move(moveDirection);
    }
    
    // Fallback: move toward center
    const center = new Coords(9, 9);
    const directionToCenter = unit.coords.directionTo(center);
    return Action.move(directionToCenter);
}