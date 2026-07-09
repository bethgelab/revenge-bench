import sys
sys.path.insert(0, './client/lib')

from deuces import Card, Evaluator

# Example hand and community cards
hand = [
    Card.new('Ah'),
    Card.new('Kh')
]
board = [
    Card.new('Qh'),
    Card.new('Jh'),
    Card.new('Th'),
    Card.new('2s'),
    Card.new('3c')
]

evaluator = Evaluator()
score = evaluator.evaluate(board, hand)
print(f"Hand rank: {score}")

# Let's try another hand
hand2 = [
    Card.new('7s'),
    Card.new('8s')
]
board2 = [
    Card.new('9s'),
    Card.new('Ts'),
    Card.new('Js'),
    Card.new('2s'),
    Card.new('3c')
]

score2 = evaluator.evaluate(board2, hand2)
print(f"Hand rank 2: {score2}")

# And a pair
hand3 = [
    Card.new('As'),
    Card.new('Ad')
]
board3 = [
    Card.new('2c'),
    Card.new('3d'),
    Card.new('4h'),
    Card.new('5s'),
    Card.new('6c')
]

score3 = evaluator.evaluate(board3, hand3)
print(f"Hand rank 3: {score3}")

print(evaluator.get_rank_class(score))
print(evaluator.class_to_string(evaluator.get_rank_class(score)))