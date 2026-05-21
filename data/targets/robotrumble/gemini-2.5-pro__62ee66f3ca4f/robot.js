function robot(state, unit) {
    const enemies = state.objsByTeam(state.otherTeam);
    if (enemies.length === 0) {
        return; // No enemies, do nothing.
    }

    // --- New Targeting Logic: Aggressive Swarm ---

    // Find the closest distance to any enemy
    const min_distance = _.min(enemies.map(enemy => unit.coords.walkingDistanceTo(enemy.coords)));

    // Find all enemies at that closest distance
    const closest_enemies = enemies.filter(enemy => unit.coords.walkingDistanceTo(enemy.coords) === min_distance);

    // From the closest enemies, pick the one with the lowest health as the target
    const target = _.minBy(closest_enemies, 'health');

    if (target) {
        const distance = unit.coords.walkingDistanceTo(target.coords);

        // --- Retreat / Opportunistic Attack Logic ---
        if (unit.health < 5) {
            // If adjacent to target and target is weak, attack!
            if (distance === 1 && target.health <= unit.health) {
                 const direction = unit.coords.directionTo(target.coords);
                 return Action.attack(direction);
            }
            // Otherwise, run away from the target
            const direction = unit.coords.directionTo(target.coords);
            return Action.move(direction.opposite);
        }

        // --- Standard Attack/Move Logic ---
        if (distance === 1) {
            // If adjacent, attack!
            const direction = unit.coords.directionTo(target.coords);
            return Action.attack(direction);
        } else {
            // Otherwise, move towards the target
            const direction = unit.coords.directionTo(target.coords);
            return Action.move(direction);
        }
    }

    // Default fallback behavior
    if (state.turn % 2 == 0) {
        return Action.move(Direction.East);
    } else {
        return Action.move(Direction.South);
    }
}