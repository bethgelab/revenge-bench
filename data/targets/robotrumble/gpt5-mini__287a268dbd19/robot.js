function robot(state, unit) {
    // Try to attack any adjacent enemy first
    var dirs = [Direction.North, Direction.South, Direction.East, Direction.West];
    for (var i = 0; i < dirs.length; i++) {
        var d = dirs[i];
        // Use coords.add(direction) to get neighbor tile
        try {
            var neighbor = unit.coords.add(d);
        } catch (e) {
            // If add isn't available for some reason, skip this direction
            continue;
        }
        var id = state.id_by_coords(neighbor);
        if (id) {
            var obj = state.obj_by_id(id);
            if (obj && obj.team && obj.team != state.our_team) {
                return Action.attack(d);
            }
        }
    }

    // Move toward the nearest visible enemy
    var enemies = state.objs_by_team(state.other_team);
    if (enemies && enemies.length > 0) {
        var best = null;
        var bestDist = Infinity;
        for (var i = 0; i < enemies.length; i++) {
            var e = enemies[i];
            // Prefer walking distance if available
            var dist = 0;
            try {
                dist = unit.coords.walking_distance_to(e.coords);
            } catch (ex) {
                // fallback to euclidean distance if walking_distance_to not present
                var dx = unit.coords.x - e.coords.x;
                var dy = unit.coords.y - e.coords.y;
                dist = Math.sqrt(dx*dx + dy*dy);
            }
            if (dist < bestDist) {
                bestDist = dist;
                best = e;
            }
        }
        if (best) {
            try {
                var dir = unit.coords.direction_to(best.coords);
                if (dir) return Action.move(dir);
            } catch (e) {
                // ignore and fallback
            }
        }
    }

    // No enemies found or couldn't compute direction: move toward center of the map
    try {
        var center = new Coords(Math.floor(MAP_SIZE/2), Math.floor(MAP_SIZE/2));
        var dirToCenter = unit.coords.direction_to(center);
        if (dirToCenter) return Action.move(dirToCenter);
    } catch (e) {
        // final fallback
    }

    // Last resort: move East
    return Action.move(Direction.East);
}