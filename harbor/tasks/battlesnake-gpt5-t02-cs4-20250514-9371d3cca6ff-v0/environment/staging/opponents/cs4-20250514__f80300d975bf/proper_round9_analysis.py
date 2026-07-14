#!/usr/bin/env python3
import json
import os
from collections import defaultdict

def analyze_game_file(filepath):
    """Analyze a single game file and return outcome info"""
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        if len(lines) < 2:
            return None
        
        # Skip first line (game setup), start from turn 0
        last_turn = 0
        final_snakes = []
        
        for line in lines[1:]:  # Skip first line
            if line.strip():
                try:
                    game_data = json.loads(line.strip())
                    if 'turn' in game_data and 'board' in game_data:
                        last_turn = game_data['turn']
                        final_snakes = game_data['board']['snakes']
                except json.JSONDecodeError:
                    continue
        
        # Determine outcome
        our_snake_alive = False
        opponent_alive = False
        
        for snake in final_snakes:
            if 'claude-sonnet-4' in snake.get('name', ''):
                our_snake_alive = True
            elif 'grok-code-fast' in snake.get('name', ''):
                opponent_alive = True
        
        if our_snake_alive and not opponent_alive:
            return {'outcome': 'win', 'turns': last_turn}
        elif opponent_alive and not our_snake_alive:
            return {'outcome': 'loss', 'turns': last_turn}
        else:
            return {'outcome': 'tie', 'turns': last_turn}
            
    except Exception as e:
        return None

def analyze_round_games(round_num):
    """Analyze all games in a round"""
    round_dir = f"/logs/rounds/{round_num}"
    
    if not os.path.exists(round_dir):
        print(f"Round {round_num} not found")
        return None
    
    wins = []
    losses = []
    ties = []
    
    # Process all sim files
    for filename in os.listdir(round_dir):
        if filename.startswith('sim_') and filename.endswith('.jsonl'):
            filepath = os.path.join(round_dir, filename)
            result = analyze_game_file(filepath)
            
            if result:
                if result['outcome'] == 'win':
                    wins.append(result['turns'])
                elif result['outcome'] == 'loss':
                    losses.append(result['turns'])
                elif result['outcome'] == 'tie':
                    ties.append(result['turns'])
    
    return wins, losses, ties

def detailed_analysis(round_num):
    """Provide detailed analysis of a round"""
    print(f"\n=== ROUND {round_num} DETAILED ANALYSIS ===")
    
    wins, losses, ties = analyze_round_games(round_num)
    
    if wins is None:
        return
    
    total_games = len(wins) + len(losses) + len(ties)
    
    if total_games == 0:
        print("No games analyzed")
        return
    
    print(f"Total games analyzed: {total_games}")
    print(f"Wins: {len(wins)} ({len(wins)/total_games*100:.1f}%)")
    print(f"Losses: {len(losses)} ({len(losses)/total_games*100:.1f}%)")
    print(f"Ties: {len(ties)} ({len(ties)/total_games*100:.1f}%)")
    
    if wins:
        avg_win_turns = sum(wins) / len(wins)
        print(f"\nWin Analysis:")
        print(f"  Average win length: {avg_win_turns:.1f} turns")
        print(f"  Shortest win: {min(wins)} turns")
        print(f"  Longest win: {max(wins)} turns")
        
        early_wins = [w for w in wins if w < 20]
        print(f"  Quick wins (< 20 turns): {len(early_wins)} ({len(early_wins)/len(wins)*100:.1f}% of wins)")
    
    if losses:
        avg_loss_turns = sum(losses) / len(losses)
        print(f"\nLoss Analysis:")
        print(f"  Average loss length: {avg_loss_turns:.1f} turns")
        print(f"  Shortest loss: {min(losses)} turns")
        print(f"  Longest loss: {max(losses)} turns")
        
        early_losses = [l for l in losses if l < 20]
        print(f"  Early deaths (< 20 turns): {len(early_losses)} ({len(early_losses)/len(losses)*100:.1f}% of losses)")
        print(f"  Early death rate: {len(early_losses)/total_games*100:.1f}% of all games")
    
    if ties:
        avg_tie_turns = sum(ties) / len(ties)
        print(f"\nTie Analysis:")
        print(f"  Average tie length: {avg_tie_turns:.1f} turns")
    
    return {
        'wins': wins,
        'losses': losses,
        'ties': ties,
        'total_games': total_games,
        'win_rate': len(wins)/total_games*100 if total_games > 0 else 0
    }

# Analyze Round 9
round9_data = detailed_analysis(9)

# Quick comparison with Round 8
print(f"\n" + "="*50)
round8_data = detailed_analysis(8)

if round9_data and round8_data:
    print(f"\n=== ROUND 8 vs 9 COMPARISON ===")
    print(f"Win Rate: {round8_data['win_rate']:.1f}% â {round9_data['win_rate']:.1f}% ({round9_data['win_rate'] - round8_data['win_rate']:+.1f}%)")
    
    if round8_data['wins'] and round9_data['wins']:
        r8_avg_win = sum(round8_data['wins']) / len(round8_data['wins'])
        r9_avg_win = sum(round9_data['wins']) / len(round9_data['wins'])
        print(f"Average win length: {r8_avg_win:.1f} â {r9_avg_win:.1f} turns ({r9_avg_win - r8_avg_win:+.1f})")
    
    if round8_data['losses'] and round9_data['losses']:
        r8_avg_loss = sum(round8_data['losses']) / len(round8_data['losses'])
        r9_avg_loss = sum(round9_data['losses']) / len(round9_data['losses'])
        print(f"Average loss length: {r8_avg_loss:.1f} â {r9_avg_loss:.1f} turns ({r9_avg_loss - r8_avg_loss:+.1f})")