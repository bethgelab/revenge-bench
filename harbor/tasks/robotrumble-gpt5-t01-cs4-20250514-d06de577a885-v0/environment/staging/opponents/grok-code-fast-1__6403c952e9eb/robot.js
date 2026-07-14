function canMove(state, unit, dir) {
    let next = unit.coords.add(dir.toCoords());
    if (next.x < 0 || next.x >= MAP_SIZE || next.y < 0 || next.y >= MAP_SIZE) return false;
    let obj = state.objByCoords(next);
    return obj === null;
}

function robot(state, unit) {
    let opponents = state.objsByTeam(state.otherTeam);
    if (opponents.length === 0) {
        return Action.move(Direction.East);
    }
    // Find weakest opponent by health
    let weakest = opponents.reduce((a, b) => a.health < b.health ? a : b);
    let target = weakest;
    let dist = unit.coords.distanceTo(target.coords);
    if (dist <= 1.5) {
        let direction = unit.coords.directionTo(target.coords);
        return Action.attack(direction);
    }
    // Check for kiting: outnumbered locally (>1 opp within 2 units) and no teammates nearby
    let nearbyOpps = opponents.filter(opp => unit.coords.distanceTo(opp.coords) <= 2);
    let teammates = state.objsByTeam(state.myTeam);
    let nearbyMates = teammates.filter(mate => mate !== unit && unit.coords.distanceTo(mate.coords) <= 2);
    if (nearbyOpps.length > 1 && nearbyMates.length === 0) {
        // Kite: move away from target
        let directionAway = target.coords.directionTo(unit.coords);
        let dirs = [directionAway, directionAway.rotateCw(), directionAway.rotateCcw(), directionAway.rotateCw().rotateCw()];
        for (let dir of dirs) {
            if (canMove(state, unit, dir)) {
                return Action.move(dir);
            }
        }
    }
    // Move towards target
    let direction = unit.coords.directionTo(target.coords);
    let possibleDirs = [direction, direction.rotateCw(), direction.rotateCcw(), direction.rotateCw().rotateCw()];
    for (let dir of possibleDirs) {
        if (canMove(state, unit, dir)) {
            return Action.move(dir);
        }
    }
    // Fallback
    return Action.move(Direction.East);
}