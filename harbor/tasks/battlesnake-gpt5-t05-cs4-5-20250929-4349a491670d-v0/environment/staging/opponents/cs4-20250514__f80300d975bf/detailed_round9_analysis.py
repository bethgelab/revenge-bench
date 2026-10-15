#!/usr/bin/env python3
import json
import os
from collections import defaultdict

def analyze_game_lengths_and_patterns(round_num):
    """Analyze game lengths and win/loss patterns"""
    round_dir = f"/logs/rounds/{round_num}"
    
    if not os.path.exists(round_dir):
        return None
    
    wins = []
    losses = []
    ties = []
    
    # Process all simulation files
    for filename in os.listdir(round_dir):
        if filename.startswith('sim_') and filename.endswith('.jsonl'):
            filepath = os.path.join(round_dir, filename)
            
            try:
                with open(filepath, 'r') as f:
                    for line in f:
                        if line.strip():
                            game_data = json.loads(line.strip())
                            
                            # Extract game info
                            if 'game' in game_data and 'board' in game_data['game']:
                                turn = game_data['turn']
                                snakes = game_data['game']['board']['snakes']
                                
                                # Find our snake and determine outcome
                                our_snake = None
                                opponent_snake = None
                                
                                for snake in snakes:
                                    if 'claude-sonnet-4' in snake.get('name', ''):
                                        our_snake = snake
                                    else:
                                        opponent_snake = snake
                                
                                # Check if game ended
                                if len(snakes) == 1:
                                    # Someone won
                                    winner = snakes[0]
                                    if 'claude-sonnet-4' in winner.get('name', ''):
                                        wins.append(turn)
                                    else:
                                        losses.append(turn)
                                elif len(snakes) == 0:
                                    # Tie (both died)
                                    ties.append(turn)
                                    
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
    
    return wins, losses, ties

def analyze_round_detailed(round_num):
    """Detailed analysis of a round"""
    print(f"\n=== DETAILED ROUND {round_num} ANALYSIS ===")
    
    wins, losses, ties = analyze_game_lengths_and_patterns(round_num)
    
    if not wins and not losses and not ties:
        print("No game data found")
        return
    
    total_games = len(wins) + len(losses) + len(ties)
    
    print(f"Games analyzed: {total_games}")
    print(f"Wins: {len(wins)} ({len(wins)/total_games*100:.1f}%)")
    print(f"Losses: {len(losses)} ({len(losses)/total_games*100:.1f}%)")
    print(f"Ties: {len(ties)} ({len(ties)/total_games*100:.1f}%)")
    
    if wins:
        avg_win_length = sum(wins) / len(wins)
        print(f"Average win game length: {avg_win_length:.1f} turns")
        
        # Early wins (< 20 turns)
        early_wins = [w for w in wins if w < 20]
        print(f"Early wins (< 20 turns): {len(early_wins)} ({len(early_wins)/len(wins)*100:.1f}% of wins)")
    
    if losses:
        avg_loss_length = sum(losses) / len(losses)
        print(f"Average loss game length: {avg_loss_length:.1f} turns")
        
        # Early losses (< 20 turns) - these are bad
        early_losses = [l for l in losses if l < 20]
        print(f"Early losses (< 20 turns): {len(early_losses)} ({len(early_losses)/len(losses)*100:.1f}% of losses)")
        print(f"Early death rate: {len(early_losses)/total_games*100:.1f}% of all games")
    
    if ties:
        avg_tie_length = sum(ties) / len(ties)
        print(f"Average tie game length: {avg_tie_length:.1f} turns")

# Analyze Round 9 in detail
analyze_round_detailed(9)

# Compare with Round 8 for context
analyze_round_detailed(8)