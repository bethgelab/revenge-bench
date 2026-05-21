import json
import os
import sys
from collections import defaultdict
from deuces import Card, Evaluator

# These are the consistent player IDs across the round, found in the bot's own log file.
OUR_ID = '382466127'
OPPONENT_ID = '1684745852'

def get_hand_type(hand_rank):
    """Converts a deuces hand rank to a string."""
    if hand_rank == 1: return "Royal Flush"
    if hand_rank <= 10: return "Straight Flush"
    if hand_rank <= 166: return "Four of a Kind"
    if hand_rank <= 322: return "Full House"
    if hand_rank <= 1599: return "Flush"
    if hand_rank <= 1609: return "Straight"
    if hand_rank <= 2467: return "Three of a Kind"
    if hand_rank <= 3325: return "Two Pair"
    if hand_rank <= 6185: return "One Pair"
    return "High Card"

def analyze_round(round_dir):
    """Analyzes all game logs in a given round directory."""
    
    total_winnings = 0
    games_played = 0
    games_won = 0
    showdown_hands = {'gemini-2.5-pro': [], 'opponent': []}
    large_pots_lost = []
    evaluator = Evaluator()

    for filename in os.listdir(round_dir):
        if filename.startswith("game_log_") and filename.endswith(".json"):
            filepath = os.path.join(round_dir, filename)
            with open(filepath, 'r') as f:
                try:
                    game_data = json.load(f)
                    games_played += 1

                    # Find the internal game ID for our bot and the opponent
                    player_name_map = game_data.get('playerNames', {})
                    internal_id_map = {v: k for k, v in player_name_map.items()} # Invert map
                    
                    our_internal_id = internal_id_map.get('player' + OUR_ID)
                    opponent_internal_id = internal_id_map.get('player' + OPPONENT_ID)
                    
                    if not our_internal_id:
                        continue

                    winnings = game_data['playerMoney']['thisGameDelta'].get(OUR_ID, 0)
                    total_winnings += winnings
                    if winnings > 0:
                        games_won += 1

                    if 'finalBoard' in game_data and game_data['finalBoard']:
                        board = [Card.new(c) for c in game_data['finalBoard']]
                        
                        our_hand_str = game_data['playerHands'].get(our_internal_id)
                        if our_hand_str:
                            our_hand = [Card.new(c) for c in our_hand_str]
                            our_rank = evaluator.evaluate(board, our_hand)
                            showdown_hands['gemini-2.5-pro'].append(get_hand_type(our_rank))

                        if opponent_internal_id:
                            opponent_hand_str = game_data['playerHands'].get(opponent_internal_id)
                            if opponent_hand_str:
                                opponent_hand = [Card.new(c) for c in opponent_hand_str]
                                opponent_rank = evaluator.evaluate(board, opponent_hand)
                                showdown_hands['opponent'].append(get_hand_type(opponent_rank))

                    if winnings < 0 and abs(winnings) > 50:
                        final_pot = list(game_data['rounds'].values())[-1].get('pot', 'N/A')
                        large_pots_lost.append({
                            'winnings': winnings,
                            'pot': final_pot,
                            'hand': game_data['playerHands'].get(our_internal_id),
                            'board': game_data.get('finalBoard')
                        })

                except (json.JSONDecodeError, KeyError, TypeError, IndexError) as e:
                    print(f"Warning: Could not process {filename}. Error: {e}", file=sys.stderr)

    print(f"--- Analysis for {round_dir} ---")
    print(f"Total games played: {games_played}")
    print(f"Total winnings: {total_winnings}")
    print(f"Win rate: {games_won / games_played:.2%}" if games_played > 0 else "N/A")
    
    print("\n--- Showdown Hand Distribution (gemini-2.5-pro) ---")
    for hand, count in sorted(defaultdict(int, {h: showdown_hands['gemini-2.5-pro'].count(h) for h in set(showdown_hands['gemini-2.5-pro'])}).items(), key=lambda item: item[1], reverse=True):
        print(f"{hand}: {count}")

    print("\n--- Showdown Hand Distribution (Opponent) ---")
    for hand, count in sorted(defaultdict(int, {h: showdown_hands['opponent'].count(h) for h in set(showdown_hands['opponent'])}).items(), key=lambda item: item[1], reverse=True):
        print(f"{hand}: {count}")

    print("\n--- Large Pots Lost (lost > 50 chips) ---")
    for loss in sorted(large_pots_lost, key=lambda x: abs(x['winnings']), reverse=True):
        print(f"Lost: {abs(loss['winnings'])}, Pot: {loss['pot']}, Hand: {loss['hand']}, Board: {loss['board']}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze_logs.py <path_to_round_directory>")
        sys.exit(1)
    round_directory = sys.argv[1]
    if not os.path.isdir(round_directory):
        print(f"Error: Directory not found at {round_directory}")
        sys.exit(1)
    analyze_round(round_directory)