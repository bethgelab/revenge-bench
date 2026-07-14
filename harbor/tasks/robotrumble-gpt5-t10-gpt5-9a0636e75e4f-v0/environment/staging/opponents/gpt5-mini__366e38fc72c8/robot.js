function robot(state, unit) {
    // Visible units
    const enemies = state.objsByTeam(state.otherTeam) || [];
    const allies = (state.objsByTeam(state.ourTeam) || []).filter(a => a.id !== unit.id);

    if (enemies.length === 0) return null;

    // Occupied set: only mark allies (we don't block moving toward enemies)
    const occupied = new Set();
    for (const a of allies) occupied.add(a.coords.x + ',' + a.coords.y);

    const onMap = (c) => c.x >= 0 && c.y >= 0 && c.x < MAP_SIZE && c.y < MAP_SIZE;

    // Select target: prefer closer enemies and lower health
    let target = null;
    let bestScore = Infinity;
    let bestDist = Infinity;
    for (const e of enemies) {
        const d = unit.coords.walkingDistanceTo(e.coords);
        const score = d * 100 + e.health;
        if (score < bestScore) {
            bestScore = score;
            target = e;
            bestDist = d;
        }
    }

    if (!target) return null;

    // If adjacent, attack
    if (bestDist <= 1) {
        const dir = unit.coords.directionTo(target.coords);
        return Action.attack(dir);
    }

    // Move toward the target, avoiding allies and map edges.
    const preferDir = unit.coords.directionTo(target.coords);

    const tryMove = (dir) => {
        if (!dir) return null;
        const next = unit.coords.add(dir);
        if (!onMap(next)) return null;
        if (occupied.has(next.x + ',' + next.y)) return null;
        return Action.move(dir);
    };

    // Try preferred direction, then rotate cw/ccw
    let m = tryMove(preferDir);
    if (m) return m;
    if (preferDir.rotateCw) {
        m = tryMove(preferDir.rotateCw);
        if (m) return m;
    }
    if (preferDir.rotateCcw) {
        m = tryMove(preferDir.rotateCcw);
        if (m) return m;
    }

    // fallback: try any direction (E, W, N, S) avoiding allies
    const dirs = [Direction.East, Direction.West, Direction.North, Direction.South];
    for (const d of dirs) {
        const mv = tryMove(d);
        if (mv) return mv;
    }

    return null;
}