function robot(state, unit) {
  // Helper: safe list of enemies/allies
  var enemies = state.objsByTeam(state.otherTeam) || [];
  var allies = state.objsByTeam(state.team) || [];

  // If no enemies found, do a roaming move (less predictable)
  if (enemies.length === 0) {
    if (state.turn % 5 === 0) {
      var choices = [Direction.North, Direction.South, Direction.East, Direction.West];
      return Action.move(choices[Math.floor(Math.random() * choices.length)]);
    }
    // Default: keep moving east to explore
    return Action.move(Direction.East);
  }

  // Find adjacent enemies (melee range)
  var adjacent = enemies.filter(function(e) {
    return e.coords.distanceTo(unit.coords) === 1;
  });

  // If adjacent enemies exist, attack the lowest-health adjacent enemy
  if (adjacent.length > 0) {
    var target = _.minBy(adjacent, function(e) {
      return (e.health != null) ? e.health : 9999;
    });
    var dir = unit.coords.directionTo(target.coords);
    return Action.attack(dir);
  }

  // Evaluate nearest enemy & local threats
  var closest = _.minBy(enemies, function(e) {
    return e.coords.walkingDistanceTo(unit.coords) + e.coords.distanceTo(unit.coords) * 0.01;
  });

  var distToClosest = closest ? closest.coords.walkingDistanceTo(unit.coords) : Infinity;

  // Count enemies within a small radius
  var nearbyEnemies = enemies.filter(function(e) {
    return e.coords.walkingDistanceTo(unit.coords) <= 3;
  });

  // Basic health and combat assessment
  var myHealth = (unit.health != null) ? unit.health : 100;
  var averageNearbyEnemyHealth = nearbyEnemies.length > 0 ? (_.sumBy(nearbyEnemies, function(e){ return e.health || 50; }) / nearbyEnemies.length) : 0;

  // If low health and threats are near, try to retreat to safety
  var LOW_HEALTH_THRESHOLD = 30;
  if (myHealth <= LOW_HEALTH_THRESHOLD && nearbyEnemies.length > 0) {
    // Choose a move that maximizes distance sum to nearby enemies
    var directions = [Direction.North, Direction.South, Direction.East, Direction.West];
    var best = null;
    var bestScore = -Infinity;
    directions.forEach(function(d) {
      var newCoords = unit.coords.add(Direction.toVector(d));
      // score = sum of distances to nearby enemies (higher is better)
      var score = _.sumBy(nearbyEnemies, function(e) {
        return e.coords.walkingDistanceTo(newCoords);
      });
      if (score > bestScore) {
        bestScore = score;
        best = d;
      }
    });
    if (best) return Action.move(best);
  }

  // If outnumbered nearby, avoid engaging directly: try to move to safer tile
  if (nearbyEnemies.length >= 2) {
    var dirs = [Direction.North, Direction.South, Direction.East, Direction.West];
    var bestDir = _.maxBy(dirs, function(d) {
      var nc = unit.coords.add(Direction.toVector(d));
      // prefer tiles with larger minimal distance to enemies
      var minDist = _.minBy(enemies, function(e) { return e.coords.walkingDistanceTo(nc); });
      return (minDist ? minDist.coords.walkingDistanceTo ? minDist.coords.walkingDistanceTo(nc) : (minDist && minDist.coords ? minDist.coords.walkingDistanceTo(nc) : 0) : 0) || 0;
    });
    if (bestDir) return Action.move(bestDir);
  }

  // Kiting behavior: if closest is within 3 tiles and we are weaker, back away; if stronger, close in.
  if (closest) {
    var enemyHealth = (closest.health != null) ? closest.health : 50;
    if (distToClosest <= 3 && myHealth < enemyHealth + 10) {
      // move away from closest enemy
      var awayDir = unit.coords.directionTo(closest.coords);
      // pick opposite direction
      var opposite = (awayDir === Direction.North && Direction.South) ||
                     (awayDir === Direction.South && Direction.North) ||
                     (awayDir === Direction.East && Direction.West) ||
                     (awayDir === Direction.West && Direction.East);
      // If opposite resolves to a boolean due to JS eval, compute properly:
      if (awayDir === Direction.North) opposite = Direction.South;
      if (awayDir === Direction.South) opposite = Direction.North;
      if (awayDir === Direction.East) opposite = Direction.West;
      if (awayDir === Direction.West) opposite = Direction.East;
      return Action.move(opposite);
    }

    // If we are stronger or safe, move toward the closest enemy
    if (myHealth >= enemyHealth - 5 || distToClosest > 4) {
      var direction = unit.coords.directionTo(closest.coords);
      return Action.move(direction);
    }
  }

  // Occasional random move to avoid being predictable
  if (state.turn % 7 === 0) {
    var choices = [Direction.North, Direction.South, Direction.East, Direction.West];
    return Action.move(choices[Math.floor(Math.random() * choices.length)]);
  }

  // Fallback: move toward closest enemy
  if (closest) {
    var dirTo = unit.coords.directionTo(closest.coords);
    return Action.move(dirTo);
  }

  // Ultimate fallback: move east
  return Action.move(Direction.East);
}