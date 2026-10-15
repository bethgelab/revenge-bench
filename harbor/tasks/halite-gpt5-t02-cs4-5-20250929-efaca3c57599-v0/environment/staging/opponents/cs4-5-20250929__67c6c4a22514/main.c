#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "AggressiveBot_v10"

int find_best_move(GAME game, int x, int y) {
    SITE current = GetSiteFromXY(game, x, y);
    
    // Check all four directions for targets
    int directions[] = {NORTH, EAST, SOUTH, WEST};
    int best_direction = STILL;
    int best_score = -999999;
    int found_enemy = 0;
    int found_neutral = 0;
    
    for (int i = 0; i < 4; i++) {
        int dir = directions[i];
        SITE neighbor = GetSiteFromMovement(game, x, y, dir);
        
        // If neighbor is not ours
        if (neighbor.owner != game.playertag) {
            found_enemy = 1;
            
            // Check if it's neutral (owner 0)
            int is_neutral = (neighbor.owner == 0);
            if (is_neutral) {
                found_neutral = 1;
            }
            
            // Can we capture it?
            if (current.strength > neighbor.strength) {
                // Enhanced scoring: heavily prioritize high production
                // For neutral cells, add bonus since they're easier to capture
                int score = neighbor.production * 15 - neighbor.strength / 3;
                if (is_neutral) {
                    score += 50;  // Bonus for neutral cells
                }
                
                if (score > best_score) {
                    best_score = score;
                    best_direction = dir;
                }
            }
        }
    }
    
    // If we found a good move, return it
    if (best_direction != STILL) {
        return best_direction;
    }
    
    // If we're on the border but can't capture anything yet
    if (found_enemy) {
        // FIXED: Only attack neutral cells we can actually capture
        if (found_neutral && current.strength > 0) {
            // Find the best neutral neighbor we can capture (highest production)
            int best_neutral_dir = STILL;
            int best_neutral_prod = -1;
            for (int i = 0; i < 4; i++) {
                int dir = directions[i];
                SITE neighbor = GetSiteFromMovement(game, x, y, dir);
                // CRITICAL FIX: Check if we can actually capture it!
                if (neighbor.owner == 0 && current.strength > neighbor.strength && neighbor.production > best_neutral_prod) {
                    best_neutral_prod = neighbor.production;
                    best_neutral_dir = dir;
                }
            }
            if (best_neutral_dir != STILL) {
                return best_neutral_dir;
            }
        }
        
        // Find the weakest neighbor we're adjacent to
        int min_strength = 999999;
        for (int i = 0; i < 4; i++) {
            int dir = directions[i];
            SITE neighbor = GetSiteFromMovement(game, x, y, dir);
            if (neighbor.owner != game.playertag && neighbor.strength < min_strength) {
                min_strength = neighbor.strength;
            }
        }
        
        // Wait until we can capture the weakest neighbor
        // Ultra-aggressive: no buffer
        int max_wait = min_strength;
        if (max_wait > 255) max_wait = 255;
        
        // If we're near the cap, move anyway to avoid waste
        if (current.strength > min_strength || current.strength + current.production > 255) {
            // Move towards the weakest neighbor
            for (int i = 0; i < 4; i++) {
                int dir = directions[i];
                SITE neighbor = GetSiteFromMovement(game, x, y, dir);
                if (neighbor.owner != game.playertag && neighbor.strength == min_strength) {
                    return dir;
                }
            }
        }
        
        return STILL;
    }
    
    // We're not on the border - move towards the border
    // Find direction with most enemy cells nearby
    int enemy_counts[4] = {0, 0, 0, 0};
    int friendly_strength[4] = {0, 0, 0, 0};
    
    for (int i = 0; i < 4; i++) {
        int dir = directions[i];
        SITE neighbor = GetSiteFromMovement(game, x, y, dir);
        
        if (neighbor.owner == game.playertag) {
            friendly_strength[i] = neighbor.strength;
            
            // Check if this neighbor is on the border
            int nx = x, ny = y;
            if (dir == NORTH) ny = (ny == 0) ? game.height - 1 : ny - 1;
            else if (dir == SOUTH) ny = (ny + 1) % game.height;
            else if (dir == EAST) nx = (nx + 1) % game.width;
            else if (dir == WEST) nx = (nx == 0) ? game.width - 1 : nx - 1;
            
            // Count enemy neighbors of this cell
            int check_dirs[] = {NORTH, EAST, SOUTH, WEST};
            for (int j = 0; j < 4; j++) {
                SITE check = GetSiteFromMovement(game, nx, ny, check_dirs[j]);
                if (check.owner != game.playertag) {
                    enemy_counts[i]++;
                }
            }
        }
    }
    
    // Find direction with most enemies nearby
    int max_enemies = 0;
    best_direction = NORTH;  // Default
    for (int i = 0; i < 4; i++) {
        if (enemy_counts[i] > max_enemies) {
            max_enemies = enemy_counts[i];
            best_direction = directions[i];
        } else if (enemy_counts[i] == max_enemies && enemy_counts[i] > 0) {
            // If tied, prefer direction with lower friendly strength (less congestion)
            int current_best_idx = -1;
            for (int j = 0; j < 4; j++) {
                if (directions[j] == best_direction) {
                    current_best_idx = j;
                    break;
                }
            }
            if (current_best_idx >= 0 && friendly_strength[i] < friendly_strength[current_best_idx]) {
                best_direction = directions[i];
            }
        }
    }
    
    // Don't move if we have 0 strength (can't contribute to capture)
    if (current.strength == 0) {
        return STILL;
    }
    
    // Ultra-aggressive interior movement - threshold of 1
    // Move with any strength to expand territory as quickly as possible
    if (current.strength >= 1 || current.strength + current.production > 255) {
        return best_direction;
    }
    
    return STILL;
}

int main(void) {
    GAME game;
    int x, y;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {
        GetFrame(game);

        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    int direction = find_best_move(game, x, y);
                    SetMove(game, x, y, direction);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}