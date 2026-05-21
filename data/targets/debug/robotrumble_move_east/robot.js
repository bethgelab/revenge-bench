// Move East - Simplest possible RobotRumble strategy
//
// Every unit always moves East, regardless of game state.

function robot(state, unit) {
    return {type: "Move", direction: "East"};
}
