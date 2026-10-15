function robot(state, unit) {
    // Helper: choose direction from dx,dy (prefers cardinal axis when only one is non-zero)
    function dirFromDelta(dx, dy) {
        if (Math.abs(dx) > Math.abs(dy)) {
            return dx > 0 ? Direction.East : Direction.West;
        } else if (Math.abs(dy) > Math.abs(dx)) {
            return dy > 0 ? Direction.South : Direction.North;
        } else { // equal -> choose dx first to be consistent
            if (dx !== 0) return dx > 0 ? Direction.East : Direction.West;
            if (dy !== 0) return dy > 0 ? Direction.South : Direction.North;
            return Direction.North;
        }
    }

    // Map direction to delta
    var dirDeltas = {};
    dirDeltas[Direction.North] = {dx: 0, dy: -1};
    dirDeltas[Direction.South] = {dx: 0, dy: 1};
    dirDeltas[Direction.East]  = {dx: 1, dy: 0};
    dirDeltas[Direction.West]  = {dx: -1, dy: 0};

    function posAfter(u, dir) {
        var d = dirDeltas[dir];
        return { x: u.x + d.dx, y: u.y + d.dy };
    }

    // Gather visible units from a few common state fields (robust to different runtimes)
    var candidates = state.units || state.visible || state.enemies || [];
    if (!Array.isArray(candidates)) candidates = [];

    // Build occupied set (positions of visible units, excluding self)
    var occupied = {};
    for (var i = 0; i < candidates.length; i++) {
        var o = candidates[i];
        if (!o) continue;
        if (o.id === unit.id) continue;
        if (typeof o.x === 'undefined' || typeof o.y === 'undefined') continue;
        occupied[o.x + ',' + o.y] = true;
    }

    // Find nearest enemy unit (ignore self and friendly units if team info available)
    // Tie-break: if two enemies are same distance, prefer the one with lower hp (if hp known)
    var target = null;
    var bestDist = Infinity;
    for (var i = 0; i < candidates.length; i++) {
        var u = candidates[i];
        if (!u) continue;
        if (u.id === unit.id) continue;
        if (typeof u.team !== 'undefined' && typeof unit.team !== 'undefined' && u.team === unit.team) continue;
        if (typeof u.x === 'undefined' || typeof u.y === 'undefined') continue;
        var dx = u.x - unit.x;
        var dy = u.y - unit.y;
        var dist = Math.abs(dx) + Math.abs(dy);
        var choose = false;
        if (dist < bestDist) {
            choose = true;
        } else if (dist === bestDist && target) {
            // prefer lower hp if available
            if (typeof u.hp !== 'undefined' && typeof target.hp !== 'undefined') {
                if (u.hp < target.hp) choose = true;
            }
            // additional tie-breakers could go here (e.g., target id)
        }
        if (choose) {
            bestDist = dist;
            target = u;
        }
    }

    // Count nearby enemies around a position within given manhattan radius
    function countNearbyEnemiesAt(p, radius) {
        var cnt = 0;
        for (var k = 0; k < candidates.length; k++) {
            var c = candidates[k];
            if (!c) continue;
            if (c.id === unit.id) continue;
            if (typeof c.x === 'undefined' || typeof c.y === 'undefined') continue;
            if (typeof c.team !== 'undefined' && typeof unit.team !== 'undefined' && c.team === unit.team) continue;
            var adx = Math.abs(c.x - p.x);
            var ady = Math.abs(c.y - p.y);
            var man = adx + ady;
            if (man <= radius) cnt++;
        }
        return cnt;
    }

    // Helper: choose a non-occupied move from a list of candidate dirs (returns first free or null)
    // Avoid stepping out of bounds when state.width/state.height are provided
    function chooseNonOccupied(dirs) {
        // Evaluate candidate moves not only for occupancy/bounds but for safety:
        // prefer tiles with fewer adjacent enemies and that get us closer to the target.
        var best = null;
        var bestScore = Infinity;
        var baseTie = 0;
        try { baseTie = (Number(unit.id) || 0) % 10; } catch (e) { baseTie = 0; }
        for (var i = 0; i < dirs.length; i++) {
            var d = dirs[i];
            var p = posAfter(unit, d);
            // bounds check if provided
            if (typeof state.width !== 'undefined' && typeof state.height !== 'undefined') {
                if (p.x < 0 || p.y < 0 || p.x >= state.width || p.y >= state.height) continue;
            }
            if (occupied[p.x + ',' + p.y]) continue;
            // Count adjacent enemies (Manhattan distance == 1) around the candidate tile
            var adjacentEnemies = 0;
            for (var k = 0; k < candidates.length; k++) {
                var c = candidates[k];
                if (!c) continue;
                if (c.id === unit.id) continue;
                if (typeof c.x === 'undefined' || typeof c.y === 'undefined') continue;
                // if team info exists, skip allies
                if (typeof c.team !== 'undefined' && typeof unit.team !== 'undefined' && c.team === unit.team) continue;
                var adx = Math.abs(c.x - p.x);
                var ady = Math.abs(c.y - p.y);
                var man = adx + ady;
                if (man === 1) adjacentEnemies++;
            }
            // Distance to target (if target exists) - smaller is better
            var distToTarget = 0;
            if (typeof target !== 'undefined' && target) {
                distToTarget = Math.abs((target.x || 0) - p.x) + Math.abs((target.y || 0) - p.y);
            }
            // Score: prioritize fewer adjacent enemies (weight heavily), then closer to target
            var score = adjacentEnemies * 100 + distToTarget;
            // tiny tie-breaker based on candidate index and unit id to diversify choices between units
            score += (i + baseTie) * 0.001;
            if (score < bestScore) {
                bestScore = score;
                best = d;
            }
        }
        return best;
    }

    // If we have a target, either attack if adjacent or move toward it
    if (target) {
        var dx = target.x - unit.x;
        var dy = target.y - unit.y;
        var dist = Math.abs(dx) + Math.abs(dy);

        // If we're in immediate danger (multiple adjacent enemies or nearby cluster) and weaker, try to retreat
        var adjacentNow = countNearbyEnemiesAt(unit, 1);
        var nearby2 = countNearbyEnemiesAt(unit, 2);
        var amWeWeaker = false;
        if (typeof unit.hp !== 'undefined' && typeof target.hp !== 'undefined') {
            amWeWeaker = unit.hp < target.hp;
        }

        if ((adjacentNow >= 2 || nearby2 >= 3) && amWeWeaker) {
            // Retreat away from the target direction if possible
            var retreatDir = dirFromDelta(-dx, -dy);
            var escapeOptions = [retreatDir];
            if (retreatDir === Direction.North || retreatDir === Direction.South) {
                escapeOptions.push(Direction.East, Direction.West);
            } else {
                escapeOptions.push(Direction.North, Direction.South);
            }
            // Also include any direction that increases distance to nearest enemy if available
            // Build alternatives and choose safest via chooseNonOccupied
            var chosenEscape = chooseNonOccupied(escapeOptions.concat([Direction.North, Direction.East, Direction.South, Direction.West]));
            if (chosenEscape) return Action.move(chosenEscape);
            // If can't escape, continue with normal logic (may attack or try other moves)
        }

        // Adjacent? Consider kiting if HP info exists, otherwise attack
        if (dist === 1) {
            // If both have hp and we're weaker, try to retreat instead of attacking
            if (typeof unit.hp !== 'undefined' && typeof target.hp !== 'undefined' && unit.hp < target.hp) {
                // Retreat direction is opposite of the target
                var retreatDir2 = dirFromDelta(-dx, -dy);
                // Try retreating; if blocked, try any orthogonal escape before falling back to attack
                var escapeOptions2 = [retreatDir2];
                // Add perpendiculars to escape options
                if (retreatDir2 === Direction.North || retreatDir2 === Direction.South) {
                    escapeOptions2.push(Direction.East, Direction.West);
                } else {
                    escapeOptions2.push(Direction.North, Direction.South);
                }
                var chosenRetreat = chooseNonOccupied(escapeOptions2);
                if (chosenRetreat) {
                    return Action.move(chosenRetreat);
                }
                // No escape found: fall through to attack
            }
            var attackDir = dirFromDelta(dx, dy);
            return Action.attack(attackDir);
        }

        // Otherwise move toward the target (prefer the larger delta), but avoid stepping into occupied tiles
        var primaryMove = dirFromDelta(dx, dy);

        // Build alternative moves list: primary, then secondary axis, then perpendiculars, then any free dir
        var alternatives = [primaryMove];

        // Secondary axis move: try moving only along the other axis if primary would collide
        if (Math.abs(dx) > Math.abs(dy)) {
            if (dy !== 0) alternatives.push(dirFromDelta(0, dy));
        } else if (Math.abs(dy) > Math.abs(dx)) {
            if (dx !== 0) alternatives.push(dirFromDelta(dx, 0));
        } else {
            // equal deltas: try both axis moves
            if (dx !== 0) alternatives.push(dirFromDelta(dx, 0));
            if (dy !== 0) alternatives.push(dirFromDelta(0, dy));
        }

        // Add perpendicular moves to try to go around obstacles
        if (primaryMove === Direction.North || primaryMove === Direction.South) {
            alternatives.push(Direction.East, Direction.West);
        } else {
            alternatives.push(Direction.North, Direction.South);
        }

        // Finally, try any direction as last resort
        alternatives.push(Direction.North, Direction.East, Direction.South, Direction.West);

        var chosen = chooseNonOccupied(alternatives);
        if (chosen) return Action.move(chosen);

        // If all desired moves are occupied, fallback to the primary move (engine will handle collision resolution)
        return Action.move(primaryMove);
    }

    // Fallback: deterministic patrol but avoid tiles adjacent to enemies when possible
    var dirs = [Direction.North, Direction.East, Direction.South, Direction.West];
    // include unit position in seed so different units vary even on same turn
    var seed = (state.turn || 0) + (unit.id ? (typeof unit.id === 'number' ? unit.id : 0) : 0) + (typeof unit.x === 'number' ? unit.x : 0) + (typeof unit.y === 'number' ? unit.y : 0);
    var choice = Math.abs(seed) % dirs.length;

    // Try to pick a safe direction (not adjacent to enemies)
    var safeDirs = [];
    for (var j = 0; j < dirs.length; j++) {
        var d = dirs[(choice + j) % dirs.length];
        var p = posAfter(unit, d);
        // bounds check if provided
        if (typeof state.width !== 'undefined' && typeof state.height !== 'undefined') {
            if (p.x < 0 || p.y < 0 || p.x >= state.width || p.y >= state.height) continue;
        }
        if (occupied[p.x + ',' + p.y]) continue;
        var adj = countNearbyEnemiesAt(p, 1);
        if (adj === 0) safeDirs.push(d);
    }
    if (safeDirs.length > 0) {
        var pick = safeDirs[seed % safeDirs.length];
        return Action.move(pick);
    }

    return Action.move(dirs[choice]);
}