// Defensive - Center-seeking RobotRumble strategy
//
// Rules (per unit, in priority order):
// 1. If any enemy is adjacent (Manhattan distance 1) → Attack toward that enemy
// 2. Otherwise → Move toward board center [4, 4]
// 3. If already at center → Move North

function robot(state, unit) {
    var myCoords = unit.coords;
    var enemies = state.teams.Red || [];
    var center = [4, 4];

    // Check for adjacent enemies → attack
    for (var i = 0; i < enemies.length; i++) {
        var dist = Math.abs(myCoords[0] - enemies[i].coords[0])
                 + Math.abs(myCoords[1] - enemies[i].coords[1]);
        if (dist <= 1) {
            var direction = directionToward(myCoords, enemies[i].coords);
            return {type: "Attack", direction: direction};
        }
    }

    // Move toward board center
    var direction = directionToward(myCoords, center);
    return {type: "Move", direction: direction};
}

function directionToward(src, dst) {
    var dx = dst[0] - src[0];
    var dy = dst[1] - src[1];

    if (dx === 0 && dy === 0) return "North";

    if (Math.abs(dy) >= Math.abs(dx)) {
        return dy > 0 ? "North" : "South";
    } else {
        return dx > 0 ? "East" : "West";
    }
}
