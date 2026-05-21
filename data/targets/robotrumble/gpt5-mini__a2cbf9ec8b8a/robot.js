function robot(state, unit) {
  // helper to get object at absolute coords
  function getObj(x, y) {
    return state.objByCoords(new Coords(x, y));
  }

  // Try to move in the given direction; if blocked try rotateCw then rotateCcw
  function tryMove(dir) {
    if (!dir) return null;
    let D = dir;
    if (!getObj(unit.coords.x + D.toCoords.x, unit.coords.y + D.toCoords.y)) {
      return Action.move(D);
    }
    D = dir.rotateCw;
    if (!getObj(unit.coords.x + D.toCoords.x, unit.coords.y + D.toCoords.y)) {
      return Action.move(D);
    }
    D = dir.rotateCcw;
    if (!getObj(unit.coords.x + D.toCoords.x, unit.coords.y + D.toCoords.y)) {
      return Action.move(D);
    }
    return null;
  }

  // Try a list of candidate directions, returning the first valid move action
  function tryMoves(candidates) {
    for (let i = 0; i < candidates.length; i++) {
      let mv = tryMove(candidates[i]);
      if (mv) return mv;
    }
    return null;
  }

  let enemies = state.objsByTeam(state.otherTeam) || [];

  // If no enemies are visible, move toward center (or step randomly a bit)
  if (enemies.length === 0) {
    let center = new Coords(Math.floor(MAP_SIZE / 2), Math.floor(MAP_SIZE / 2));
    let dir = unit.coords.directionTo(center);
    // try direct, then slight randomization by trying rotates
    return tryMoves([dir, dir.rotateCw, dir.rotateCcw]) || Action.move(dir);
  }

  // Choose the closest enemy (tiebreaker by health)
  let closest = _.minBy(enemies, e => unit.coords.distanceTo(e.coords) + ((e.health != null) ? e.health / 10 : 0));
  if (!closest) return null;

  let dirToEnemy = unit.coords.directionTo(closest.coords);
  let dist = unit.coords.distanceTo(closest.coords);

  // If adjacent: attack
  if (dist === 1) {
    return Action.attack(dirToEnemy);
  }

  // Aggressive approach with extensive fallback moves to navigate around obstacles
  // Try direct approach first
  let mv = tryMove(dirToEnemy);
  if (mv) return mv;

  // Try rotated alternatives and double-rotations to get around blockers
  let dirCW = dirToEnemy.rotateCw;
  let dirCCW = dirToEnemy.rotateCcw;
  let dirCWCW = dirCW.rotateCw;
  let dirCCWCCW = dirCCW.rotateCcw;

  mv = tryMoves([dirCW, dirCCW, dirCWCW, dirCCWCCW]);
  if (mv) return mv;

  // Try moving toward center (to avoid camping) as an escape or reposition
  let center = new Coords(Math.floor(MAP_SIZE / 2), Math.floor(MAP_SIZE / 2));
  let dirToCenter = unit.coords.directionTo(center);
  mv = tryMoves([dirToCenter, dirToCenter.rotateCw, dirToCenter.rotateCcw]);
  if (mv) return mv;

  // Try perpendicular flanks
  mv = tryMoves([dirCW, dirCCW]);
  if (mv) return mv;

  // Last resort: attack toward enemy direction to at least deal damage if stuck
  return Action.attack(dirToEnemy);
}