function robot(state, unit) {
    if (state.turn % 2 == 0) {
        return Action.move(Direction.East)
    } else {
		return Action.move(Direction.South)
    }
}
