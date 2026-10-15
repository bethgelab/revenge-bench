function is_occupied_by_friendly(coords, my_units, my_id) {
    for (let i = 0; i < my_units.length; i++) {
        let other_unit = my_units[i];
        if (other_unit.id !== my_id && other_unit.coords.x === coords.x && other_unit.coords.y === coords.y) {
            return true;
        }
    }
    return false;
}

function find_and_assign_target(state, unit) {
    // Initialize a set of assigned enemy IDs on the state object if it's the first call this turn
    if (state.assignedEnemies === undefined) {
        state.assignedEnemies = new Set();
    }

    let enemies = state.objsByTeam(state.otherTeam);
    let best_target = null;
    let min_dist = Infinity;
    
    // First, try to find the closest enemy that has not been assigned yet
    for (let i = 0; i < enemies.length; i++) {
        let enemy = enemies[i];
        if (!state.assignedEnemies.has(enemy.id)) {
            let dist = unit.coords.walkingDistanceTo(enemy.coords);
            if (dist < min_dist) {
                min_dist = dist;
                best_target = enemy;
            } else if (dist === min_dist) {
                // Tie-breaker: target the one with lower health
                if (best_target === null || enemy.health < best_target.health) {
                    best_target = enemy;
                }
            }
        }
    }
    
    // If all enemies were already assigned (e.g. we have more units than them),
    // then just find the absolute closest enemy as a fallback.
    if (best_target === null && enemies.length > 0) {
        min_dist = Infinity; // Reset search criteria
        for (let i = 0; i < enemies.length; i++) {
            let enemy = enemies[i];
            let dist = unit.coords.walkingDistanceTo(enemy.coords);
            if (dist < min_dist) {
                min_dist = dist;
                best_target = enemy;
            } else if (dist === min_dist) {
                if (best_target === null || enemy.health < best_target.health) {
                    best_target = enemy;
                }
            }
        }
    }

    // If we found a target, "claim" it so other friendly units don't target it
    if (best_target) {
        state.assignedEnemies.add(best_target.id);
    }
    
    return best_target;
}

function robot(state, unit) {

    // --- King of the Hill Logic ---
    if (typeof HILL_COORDS !== 'undefined' && HILL_COORDS.length > 0) {
        let closest_hill = null;
        let min_dist_to_hill = Infinity;

        for (let i = 0; i < HILL_COORDS.length; i++) {
            let hill = HILL_COORDS[i];
            let dist = unit.coords.walkingDistanceTo(hill);
            if (dist < min_dist_to_hill) {
                min_dist_to_hill = dist;
                closest_hill = hill;
            }
        }

        if (min_dist_to_hill === 0) {
            // We are on a hill, attack any adjacent enemies
            let enemies = state.objsByTeam(state.otherTeam);
            for (let i = 0; i < enemies.length; i++) {
                let enemy = enemies[i];
                if (unit.coords.walkingDistanceTo(enemy.coords) === 1) {
                    let direction = unit.coords.directionTo(enemy.coords);
                    return Action.attack(direction);
                }
            }
            // No adjacent enemies, hold position
            return;
        } else {
            // Move towards the closest hill
            let direction = unit.coords.directionTo(closest_hill);
            let next_coords = unit.coords.add(direction);
            let my_units = state.objsByTeam(state.ourTeam);

            if (is_occupied_by_friendly(next_coords, my_units, unit.id)) {
                let dir_cw = direction.rotateCw;
                let dir_ccw = direction.rotateCcw;
                let next_coords_cw = unit.coords.add(dir_cw);
                let next_coords_ccw = unit.coords.add(dir_ccw);

                let occupied_cw = is_occupied_by_friendly(next_coords_cw, my_units, unit.id);
                let occupied_ccw = is_occupied_by_friendly(next_coords_ccw, my_units, unit.id);

                let dist_cw = next_coords_cw.walkingDistanceTo(closest_hill);
                let dist_ccw = next_coords_ccw.walkingDistanceTo(closest_hill);

                if (!occupied_cw && dist_cw < min_dist_to_hill) {
                    return Action.move(dir_cw);
                }
                if (!occupied_ccw && dist_ccw < min_dist_to_hill) {
                    return Action.move(dir_ccw);
                }
            }

            return Action.move(direction);
        }
    }
    // --- End King of the Hill Logic ---

    let my_team = state.ourTeam;
    let my_units = state.objsByTeam(my_team);
    let enemies = state.objsByTeam(state.otherTeam);

    if (enemies.length === 0) {
        return; // No enemies, do nothing
    }

    // --- Focus Fire Logic ---
    let focus_fire = false;
    let focus_target = null;

    if (focus_fire && enemies.length > 0) {
        let best_target = null;
        let min_health = Infinity;
        let min_dist_to_target = Infinity;

        for (let i = 0; i < enemies.length; i++) {
            let enemy = enemies[i];
            let dist = unit.coords.walkingDistanceTo(enemy.coords);

            if (enemy.health < min_health) {
                min_health = enemy.health;
                min_dist_to_target = dist;
                best_target = enemy;
            } else if (enemy.health === min_health) {
                if (dist < min_dist_to_target) {
                    min_dist_to_target = dist;
                    best_target = enemy;
                }
            }
        }
        focus_target = best_target;
    }
    // --- End Focus Fire Logic ---

    // Health threshold for retreating (e.g., 25% of max health)
    const HEALTH_THRESHOLD = 5 * 0.25;

    if (unit.health <= HEALTH_THRESHOLD) {
        // Low health, retreat from the closest enemy
        let closest_enemy = null;
        let min_dist = Infinity;

        for (let i = 0; i < enemies.length; i++) {
            let enemy = enemies[i];
            let dist = unit.coords.walkingDistanceTo(enemy.coords);
            if (dist < min_dist) {
                min_dist = dist;
                closest_enemy = enemy;
            }
        }

        if (closest_enemy) {
            let direction_away = unit.coords.directionTo(closest_enemy.coords).opposite();
            let next_coords = unit.coords.add(direction_away);

            if (is_occupied_by_friendly(next_coords, my_units, unit.id)) {
                // The spot is occupied, try to move sideways
                let dir_cw = direction_away.rotateCw;
                let dir_ccw = direction_away.rotateCcw;

                let next_coords_cw = unit.coords.add(dir_cw);
                let next_coords_ccw = unit.coords.add(dir_ccw);

                let occupied_cw = is_occupied_by_friendly(next_coords_cw, my_units, unit.id);
                let occupied_ccw = is_occupied_by_friendly(next_coords_ccw, my_units, unit.id);

                let original_dist = unit.coords.walkingDistanceTo(closest_enemy.coords);
                let dist_cw = next_coords_cw.walkingDistanceTo(closest_enemy.coords);
                let dist_ccw = next_coords_ccw.walkingDistanceTo(closest_enemy.coords);

                // We want to move *further* away, so check for dist > original_dist
                let can_move_cw = !occupied_cw && dist_cw > original_dist;
                let can_move_ccw = !occupied_ccw && dist_ccw > original_dist;

                if (can_move_cw && can_move_ccw) {
                    // Both are good, pick one. Let's say CW.
                    return Action.move(dir_cw);
                } else if (can_move_cw) {
                    return Action.move(dir_cw);
                } else if (can_move_ccw) {
                    return Action.move(dir_ccw);
                }
            }

            // Default move: move away from enemy, even if blocked. Another unit might move.
            return Action.move(direction_away);
        }
    }

    let target_enemy;
    if (focus_fire && focus_target) {
        target_enemy = focus_target;
    } else {
        target_enemy = find_and_assign_target(state, unit);
    }


    if (target_enemy) {
        let dist = unit.coords.walkingDistanceTo(target_enemy.coords);

        if (dist === 1) {
            // If adjacent, attack
            let direction = unit.coords.directionTo(target_enemy.coords);
            return Action.attack(direction);
        } else {
            // Otherwise, move towards the target
            let direction = unit.coords.directionTo(target_enemy.coords);
            let next_coords = unit.coords.add(direction);

            if (is_occupied_by_friendly(next_coords, my_units, unit.id)) {
                // The spot is occupied, try to move sideways
                let dir_cw = direction.rotateCw;
                let dir_ccw = direction.rotateCcw;

                let next_coords_cw = unit.coords.add(dir_cw);
                let next_coords_ccw = unit.coords.add(dir_ccw);

                let occupied_cw = is_occupied_by_friendly(next_coords_cw, my_units, unit.id);
                let occupied_ccw = is_occupied_by_friendly(next_coords_ccw, my_units, unit.id);

                let original_dist = unit.coords.walkingDistanceTo(target_enemy.coords);
                let dist_cw = next_coords_cw.walkingDistanceTo(target_enemy.coords);
                let dist_ccw = next_coords_ccw.walkingDistanceTo(target_enemy.coords);

                let can_move_cw = !occupied_cw && dist_cw < original_dist;
                let can_move_ccw = !occupied_ccw && dist_ccw < original_dist;

                if (can_move_cw && can_move_ccw) {
                    // Both are good, pick one. Let's say CW.
                    return Action.move(dir_cw);
                } else if (can_move_cw) {
                    return Action.move(dir_cw);
                } else if (can_move_ccw) {
                    return Action.move(dir_ccw);
                }
            }

            // Default move: move towards target, even if blocked. Another unit might move away.
            return Action.move(direction);
        }
    }
}