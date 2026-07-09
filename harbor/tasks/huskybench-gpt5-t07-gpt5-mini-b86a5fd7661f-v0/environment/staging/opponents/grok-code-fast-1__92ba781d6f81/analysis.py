import os
import json
from collections import defaultdict

def analyze_logs():
    logs_dir = '/logs/rounds'
    if not os.path.exists(logs_dir):
        print("Logs directory not found.")
        return
    
    round_dirs = [d for d in os.listdir(logs_dir) if os.path.isdir(os.path.join(logs_dir, d))]
    round_dirs.sort(key=int)
    
    total_games = 0
    wins = 0
    scores = []
    opponent_actions = defaultdict(int)
    
    for round_dir in round_dirs:
        results_path = os.path.join(logs_dir, round_dir, 'results.json')
        if os.path.exists(results_path):
            with open(results_path, 'r') as f:
                data = json.load(f)
                scores.append(data['scores'])
                if data['winner'] == 'grok-code-fast-1':
                    wins += 1
                total_games += 1
        
        # Analyze a few game logs for opponent actions
        game_logs = [f for f in os.listdir(os.path.join(logs_dir, round_dir)) if f.startswith('game_log_') and f.endswith('.json')]
        for log_file in game_logs[:5]:  # Sample first 5 per round
            log_path = os.path.join(logs_dir, round_dir, log_file)
            with open(log_path, 'r') as f:
                game_data = json.load(f)
                for round_num, round_data in game_data['rounds'].items():
                    for player, action in round_data['actions'].items():
                        if action in ['RAISE', 'BET']:
                            opponent_actions[player] += 1
    
    print(f"Total rounds analyzed: {total_games}")
    print(f"Wins: {wins}, Win rate: {wins/total_games:.2f}" if total_games > 0 else "No games found")
    print(f"Average score: {sum(s['grok-code-fast-1'] for s in scores)/len(scores):.2f}" if scores else "No scores")
    print("Opponent raise/bet frequencies (sampled):")
    for player, count in opponent_actions.items():
        print(f"  {player}: {count}")

if __name__ == "__main__":
    analyze_logs()