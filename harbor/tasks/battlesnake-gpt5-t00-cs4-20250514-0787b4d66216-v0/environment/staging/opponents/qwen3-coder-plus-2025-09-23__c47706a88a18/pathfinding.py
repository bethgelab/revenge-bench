#!/usr/bin/env python3
"""
Pathfinding module for BattleSnake
Implements A* algorithm for better food seeking and navigation
"""

import heapq
import math
from typing import List, Dict, Tuple, Optional


def get_neighbors(pos: Dict[str, int], game_state: Dict, my_body: List[Dict[str, int]]) -> List[Dict[str, int]]:
    """Get valid neighboring positions"""
    x, y = pos['x'], pos['y']
    neighbors = [
        {'x': x + 1, 'y': y},  # Right
        {'x': x - 1, 'y': y},  # Left
        {'x': x, 'y': y + 1},  # Up
        {'x': x, 'y': y - 1}   # Down
    ]
    
    valid_neighbors = []
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    for neighbor in neighbors:
        # Check bounds
        if (neighbor['x'] < 0 or neighbor['x'] >= board_width or 
            neighbor['y'] < 0 or neighbor['y'] >= board_height):
            continue
            
        # Check self collision
        is_collision = False
        for part in my_body[:-1]:  # Exclude head
            if neighbor == part:
                is_collision = True
                break
        if is_collision:
            continue
            
        # Check opponent collision
        opponents = game_state['board']['snakes']
        for snake in opponents:
            if snake["id"] == game_state["you"]["id"]:  # Skip our own snake
                continue
            for part in snake["body"][:-1]:  # Exclude opponent's head
                if neighbor == part:
                    is_collision = True
                    break
            if is_collision:
                break
        if is_collision:
            continue
            
        # Check hazard collision
        if "hazards" in game_state["board"] and game_state["board"]["hazards"]:
            for hazard in game_state["board"]["hazards"]:
                if neighbor == hazard:
                    is_collision = True
                    break
            if is_collision:
                continue
                
        valid_neighbors.append(neighbor)
    
    return valid_neighbors


def heuristic(pos1: Dict[str, int], pos2: Dict[str, int]) -> float:
    """Calculate Manhattan distance heuristic between two positions"""
    return abs(pos1['x'] - pos2['x']) + abs(pos1['y'] - pos2['y'])


def a_star_pathfind(start: Dict[str, int], goal: Dict[str, int], game_state: Dict, my_body: List[Dict[str, int]]) -> Optional[List[Dict[str, int]]]:
    """
    Find path from start to goal using A* algorithm
    Returns list of positions in the path or None if no path exists
    """
    # Priority queue: (f_score, g_score, position)
    open_set = [(0, 0, start)]
    open_set_hash = {tuple([start['x'], start['y']])}
    
    came_from = {}
    g_score = {tuple([start['x'], start['y']]): 0}
    
    while open_set:
        current_f, current_g, current = heapq.heappop(open_set)
        current_key = tuple([current['x'], current['y']])
        
        # Remove from hash set
        open_set_hash.remove(current_key)
        
        # Check if we reached the goal
        if current['x'] == goal['x'] and current['y'] == goal['y']:
            # Reconstruct path
            path = [current]
            current_key = tuple([current['x'], current['y']])
            while current_key in came_from:
                current = came_from[current_key]
                current_key = tuple([current['x'], current['y']])
                path.append(current)
            path.reverse()
            return path
        
        # Explore neighbors
        neighbors = get_neighbors(current, game_state, my_body)
        for neighbor in neighbors:
            neighbor_key = tuple([neighbor['x'], neighbor['y']])
            
            # Calculate tentative g_score
            tentative_g_score = current_g + 1
            
            # If this path to neighbor is better than any previous one
            if neighbor_key not in g_score or tentative_g_score < g_score[neighbor_key]:
                came_from[neighbor_key] = current
                g_score[neighbor_key] = tentative_g_score
                f_score = tentative_g_score + heuristic(neighbor, goal)
                
                if neighbor_key not in open_set_hash:
                    heapq.heappush(open_set, (f_score, tentative_g_score, neighbor))
                    open_set_hash.add(neighbor_key)
    
    # No path found
    return None