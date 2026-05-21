// Aggressive Attacker - Simple Deterministic RobotRumble Strategy
//
// Rules (per unit, in priority order):
// 1. If any enemy is adjacent (Manhattan distance 1) → Attack toward that enemy
// 2. Otherwise → Move toward the nearest enemy
// 3. Fallback → Move East

function robot(state, unit) {
    var myCoords = unit.coords;
    var enemies = state.teams.Red || [];

    if (enemies.length === 0) {
        return {type: "Move", direction: "East"};
    }

    var nearest = null;
    var nearestDist = Infinity;
    for (var i = 0; i < enemies.length; i++) {
        var dist = Math.abs(myCoords[0] - enemies[i].coords[0])
                 + Math.abs(myCoords[1] - enemies[i].coords[1]);
        if (dist < nearestDist) {
            nearestDist = dist;
            nearest = enemies[i];
        }
    }

    var direction = directionToward(myCoords, nearest.coords);

    if (nearestDist <= 1) {
        return {type: "Attack", direction: direction};
    } else {
        return {type: "Move", direction: direction};
    }
}

function directionToward(src, dst) {
    var dx = dst[0] - src[0];
    var dy = dst[1] - src[1];

    if (dx === 0 && dy === 0) return "East";

    if (Math.abs(dy) >= Math.abs(dx)) {
        return dy > 0 ? "North" : "South";
    } else {
        return dx > 0 ? "East" : "West";
    }
}
