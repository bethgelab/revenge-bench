// Simple test to verify robot function works
const _ = require('lodash');

// Mock game objects
class MockCoords {
    constructor(x, y) {
        this.x = x;
        this.y = y;
    }
    
    distanceTo(other) {
        return Math.abs(this.x - other.x) + Math.abs(this.y - other.y);
    }
    
    directionTo(other) {
        if (other.x > this.x) return Direction.East;
        if (other.x < this.x) return Direction.West;
        if (other.y > this.y) return Direction.South;
        if (other.y < this.y) return Direction.North;
        return Direction.North;
    }
    
    add(direction) {
        let newX = this.x, newY = this.y;
        if (direction === Direction.North) newY--;
        if (direction === Direction.South) newY++;
        if (direction === Direction.East) newX++;
        if (direction === Direction.West) newX--;
        return new MockCoords(newX, newY);
    }
    
    equals(other) {
        return this.x === other.x && this.y === other.y;
    }
}

const Direction = {
    North: 'North',
    South: 'South',
    East: 'East',
    West: 'West'
};

const Action = {
    move: (dir) => ({ type: 'move', direction: dir }),
    attack: (dir) => ({ type: 'attack', direction: dir })
};

const MAP_SIZE = 19;
global.Coords = MockCoords;
global.Direction = Direction;
global.Action = Action;
global.MAP_SIZE = MAP_SIZE;
global._ = _;

// Load robot code
eval(require('fs').readFileSync('robot.js', 'utf8'));

// Test scenario
const mockState = {
    turn: 1,
    ourTeam: 'Red',
    otherTeam: 'Blue',
    objsByTeam: (team) => {
        if (team === 'Red') {
            return [
                { id: '1', coords: new MockCoords(5, 5), health: 5 },
                { id: '2', coords: new MockCoords(6, 5), health: 5 }
            ];
        } else {
            return [
                { id: '3', coords: new MockCoords(10, 10), health: 5 },
                { id: '4', coords: new MockCoords(11, 10), health: 3 }
            ];
        }
    }
};

const unit1 = { id: '1', coords: new MockCoords(5, 5), health: 5 };
const unit2 = { id: '2', coords: new MockCoords(6, 5), health: 5 };

console.log('Testing robot function...');
const action1 = robot(mockState, unit1);
const action2 = robot(mockState, unit2);

console.log('Unit 1 action:', action1);
console.log('Unit 2 action:', action2);

if (action1 && action2) {
    console.log('SUCCESS: Both units returned valid actions');
} else {
    console.log('FAILURE: One or more units returned null');
}