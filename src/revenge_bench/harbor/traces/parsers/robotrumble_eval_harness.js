/**
 * RobotRumble Offline Evaluation Harness
 *
 * Reads JSON lines from stdin, each containing a raw game state and team name.
 * Loads the learner's robot.js and the RobotRumble stdlib, then replays each
 * state through the learner's robot() function — exactly as the engine would.
 *
 * Protocol (stdin -> stdout, newline-delimited JSON):
 *   Input:  {"state": {"objs": {...}, "turn": N}, "team": "Blue"|"Red"}
 *   Output: [{"unit_id": "113", "action": {"type":"Move","direction":"East"}}, ...]
 *
 * Usage:
 *   node robotrumble_eval_harness.js <stdlib.js> <robot.js> [lodash.js]
 */

const fs = require('fs');

const stdlibPath = process.argv[2];
const robotPath = process.argv[3];
const lodashPath = process.argv[4] || null;

if (!stdlibPath || !robotPath) {
  process.stderr.write('Usage: node robotrumble_eval_harness.js <stdlib.js> <robot.js> [lodash.js]\n');
  process.exit(1);
}

const stdlibCode = fs.readFileSync(stdlibPath, 'utf-8');
const robotCode = fs.readFileSync(robotPath, 'utf-8');
const lodashCode = lodashPath ? fs.readFileSync(lodashPath, 'utf-8') : '';

// Strip the engine's __format_err / __main wrappers — we call robot() ourselves.
const mainIdx = stdlibCode.indexOf('\nfunction __');
const stdlibClasses = mainIdx >= 0 ? stdlibCode.slice(0, mainIdx) : stdlibCode;

// ---------------------------------------------------------------------------
// Build a single combined script using Function() constructor.
// This ensures all class declarations (State, Obj, Action, Direction, etc.)
// share the same scope as the learner's robot() function — matching what
// the RobotRumble engine does.
// ---------------------------------------------------------------------------

const evalLoopCode = `
function reconstructStateData(raw, team) {
  var objs = raw.objs || {};
  var turn = raw.turn || 0;
  var teams = { Blue: [], Red: [] };
  for (var id in objs) {
    if (objs[id].obj_type === 'Unit' && objs[id].team) {
      teams[objs[id].team].push(id);
    }
  }
  var grid = [];
  for (var id in objs) {
    if (objs[id].coords) {
      var x = objs[id].coords[0], y = objs[id].coords[1];
      if (!grid[y]) grid[y] = [];
      grid[y][x] = id;
    }
  }
  return { objs: objs, turn: turn, team: team, teams: teams, grid: grid };
}

function processLine(line) {
  var input;
  try {
    input = JSON.parse(line);
  } catch (e) {
    return JSON.stringify({ error: 'Invalid JSON input' });
  }

  var rawState = input.state;
  var team = input.team;
  var stateData = reconstructStateData(rawState, team);
  var state = new State(stateData);

  var actions = [];
  var unitIds = state.idsByTeam(state.ourTeam) || [];

  for (var i = 0; i < unitIds.length; i++) {
    var id = unitIds[i];
    var unit = state.objById(id);
    var actionResult = null;

    try {
      var output = robot(state, unit);
      if (output instanceof Action) {
        actionResult = { type: output.type.enumKey, direction: output.direction.enumKey };
      } else if (output === null || output === undefined) {
        actionResult = null;
      } else if (typeof output === 'object' && output.type && output.direction) {
        actionResult = { type: String(output.type), direction: String(output.direction) };
      } else {
        actionResult = null;
      }
    } catch (e) {
      actionResult = null;
    }

    actions.push({ unit_id: id, action: actionResult });
  }

  actions.sort(function(a, b) {
    return a.unit_id < b.unit_id ? -1 : a.unit_id > b.unit_id ? 1 : 0;
  });
  return JSON.stringify(actions);
}

return { processLine: processLine };
`;

const combinedCode = lodashCode + '\n;\n' + stdlibClasses + '\n;\n' + robotCode + '\n;\n' + evalLoopCode;
const factory = new Function(combinedCode);
const harness = factory();

// ---------------------------------------------------------------------------
// Read stdin line by line, process each, write to stdout
// ---------------------------------------------------------------------------
let inputBuffer = '';

process.stdin.setEncoding('utf-8');
process.stdin.on('data', (chunk) => {
  inputBuffer += chunk;
  let newlineIdx;
  while ((newlineIdx = inputBuffer.indexOf('\n')) >= 0) {
    const line = inputBuffer.slice(0, newlineIdx).trim();
    inputBuffer = inputBuffer.slice(newlineIdx + 1);
    if (!line) continue;
    process.stdout.write(harness.processLine(line) + '\n');
  }
});

process.stdin.on('end', () => {
  if (inputBuffer.trim()) {
    process.stdout.write(harness.processLine(inputBuffer.trim()) + '\n');
  }
});
