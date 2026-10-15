// Global targets for team coordination
let targets = {};

function moveTowards(state, unit, targetCoords) {
    let dir = unit.coords.directionTo(targetCoords);
    let nextCoords = unit.coords.add(dir.toCoords());
    let objAtNext = state.objByCoords(nextCoords);
    if (!objAtNext || objAtNext.objType !== ObjType.Terrain) {
        return Action.move(dir);
    } else {
        let altDir = dir.rotateCw();
        nextCoords = unit.coords.add(altDir.toCoords());
        objAtNext = state.objByCoords(nextCoords);
        if (!objAtNext || objAtNext.objType !== ObjType.Terrain) {
            return Action.move(altDir);
        }
        altDir = dir.rotateCcw();
        nextCoords = unit.coords.add(altDir.toCoords());
        objAtNext = state.objByCoords(nextCoords);
        if (!objAtNext || objAtNext.objType !== ObjType.Terrain) {
            return Action.move(altDir);
        }
        return Action.move(Direction.East);
    }
}

function init_turn(state) {
    let enemies = state.objsByTeam(state.otherTeam);
    let myUnits = state.objsByTeam(state.ourTeam);
    
    // Sort enemies by health ascending (weakest first)
    enemies.sort((a, b) => a.health - b.health);
    
    // Assign targets to closest available units
    targets = {};
    let availableUnits = [...myUnits];
    availableUnits.sort((a, b) => a.id - b.id);
    
    for (let enemy of enemies) {
        if (availableUnits.length === 0) break;
        let closestUnit = _.minBy(availableUnits, u => u.coords.distanceTo(enemy.coords));
        targets[closestUnit.id] = enemy;
        availableUnits = availableUnits.filter(u => u.id !== closestUnit.id);
    }
}

function robot(state, unit) {
    let enemies = state.objsByTeam(state.otherTeam);
    if (enemies.length > 0) {
        let closestEnemy = _.minBy(enemies, e => unit.coords.distanceTo(e.coords) + e.health / 10);
        if (unit.health < 3 && closestEnemy.coords.distanceTo(unit.coords) < 3) {
            let fleeDir = unit.coords.directionTo(closestEnemy.coords).opposite;
            let nextCoords = unit.coords.add(fleeDir.toCoords());
            if (!state.objByCoords(nextCoords) || state.objByCoords(nextCoords).objType !== ObjType.Terrain) {
                return Action.move(fleeDir);
            } else {
                let altDir = fleeDir.rotateCw();
                nextCoords = unit.coords.add(altDir.toCoords());
                if (!state.objByCoords(nextCoords) || state.objByCoords(nextCoords).objType !== ObjType.Terrain) {
                    return Action.move(altDir);
                }
                altDir = fleeDir.rotateCcw();
                nextCoords = unit.coords.add(altDir.toCoords());
                if (!state.objByCoords(nextCoords) || state.objByCoords(nextCoords).objType !== ObjType.Terrain) {
                    return Action.move(altDir);
                }
                return Action.move(Direction.East);
            }
        }
    }
    
    let target = targets[unit.id];
    if (!target || !state.objById(target.id)) {
        // Fallback to closest enemy with health factor
        if (enemies.length > 0) {
            target = _.minBy(enemies, e => unit.coords.distanceTo(e.coords) + e.health / 10);
        }
    }
    
    if (target) {
        let dir = unit.coords.directionTo(target.coords);
        let dist = unit.coords.distanceTo(target.coords);
        if (dist === 1) {
            return Action.attack(dir);
        } else {
            let friendsNearTarget = state.objsByTeam(state.ourTeam).filter(u => u.coords.distanceTo(target.coords) <= 4);
            if (friendsNearTarget.length < 2) {
                return moveTowards(state, unit, new Coords(10, 10));
            } else {
                return moveTowards(state, unit, target.coords);
            }
        }
    } else {
        // Check if friends need help
        let friends = state.objsByTeam(state.ourTeam);
        let friendNeedingHelp = _.minBy(friends, f => {
            let enemiesNear = enemies.filter(e => e.coords.distanceTo(f.coords) <= 3);
            return enemiesNear.length > 0 ? f.coords.distanceTo(unit.coords) : Infinity;
        });
        if (friendNeedingHelp && friendNeedingHelp.coords.distanceTo(unit.coords) < Infinity) {
            let enemyNearFriend = _.minBy(enemies.filter(e => e.coords.distanceTo(friendNeedingHelp.coords) <= 3), e => e.coords.distanceTo(friendNeedingHelp.coords) + e.health / 10);
            if (enemyNearFriend) {
                target = enemyNearFriend;
                let dir = unit.coords.directionTo(target.coords);
                let dist = unit.coords.distanceTo(target.coords);
                if (dist === 1) {
                    return Action.attack(dir);
                } else {
                    return moveTowards(state, unit, target.coords);
                }
            }
        }
        return moveTowards(state, unit, new Coords(10, 10));
    }
}