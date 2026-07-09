#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "ImprovedBotV2"

// Helper function to check if a cell is on the border (adjacent to non-owned cell)
int is_border(GAME game, int x, int y) {
    if (game.owner[x][y] != game.playertag) {
        return 0;
    }
    
    // Check all four neighbors
    int north_y = (y == 0) ? game.height - 1 : y - 1;
    int east_x = (x == game.width - 1) ? 0 : x + 1;
    int south_y = (y == game.height - 1) ? 0 : y + 1;
    int west_x = (x == 0) ? game.width - 1 : x - 1;
    
    if (game.owner[x][north_y] != game.playertag) return 1;
    if (game.owner[east_x][y] != game.playertag) return 1;
    if (game.owner[x][south_y] != game.playertag) return 1;
    if (game.owner[west_x][y] != game.playertag) return 1;
    
    return 0;
}

// Find the best direction to move towards border
int find_direction_to_border(GAME game, int x, int y) {
    // Simple heuristic: move towards nearest edge
    int to_north = y;
    int to_south = game.height - 1 - y;
    int to_west = x;
    int to_east = game.width - 1 - x;
    
    int min_dist = to_north;
    int direction = 1; // NORTH
    
    if (to_south < min_dist) {
        min_dist = to_south;
        direction = 3; // SOUTH
    }
    if (to_west < min_dist) {
        min_dist = to_west;
        direction = 4; // WEST
    }
    if (to_east < min_dist) {
        min_dist = to_east;
        direction = 2; // EAST
    }
    
    return direction;
}

int main(void) {
    GAME game;
    int x, y, direction;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {
        GetFrame(game);

        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    int strength = game.strength[x][y];
                    int production = game.production[x][y];
                    
                    // Calculate neighbor positions
                    int north_x = x;
                    int north_y = (y == 0) ? game.height - 1 : y - 1;
                    int east_x = (x == game.width - 1) ? 0 : x + 1;
                    int east_y = y;
                    int south_x = x;
                    int south_y = (y == game.height - 1) ? 0 : y + 1;
                    int west_x = (x == 0) ? game.width - 1 : x - 1;
                    int west_y = y;
                    
                    // Find best target to attack
                    int best_direction = 0; // STILL
                    int best_score = -1;
                    int found_target = 0;
                    
                    // Check North
                    if (game.owner[north_x][north_y] != game.playertag) {
                        int target_strength = game.strength[north_x][north_y];
                        int target_production = game.production[north_x][north_y];
                        if (strength > target_strength) {
                            // Score based on production value and weakness
                            int score = target_production * 10 - target_strength;
                            if (score > best_score) {
                                best_direction = 1; // NORTH
                                best_score = score;
                                found_target = 1;
                            }
                        }
                    }
                    
                    // Check East
                    if (game.owner[east_x][east_y] != game.playertag) {
                        int target_strength = game.strength[east_x][east_y];
                        int target_production = game.production[east_x][east_y];
                        if (strength > target_strength) {
                            int score = target_production * 10 - target_strength;
                            if (score > best_score) {
                                best_direction = 2; // EAST
                                best_score = score;
                                found_target = 1;
                            }
                        }
                    }
                    
                    // Check South
                    if (game.owner[south_x][south_y] != game.playertag) {
                        int target_strength = game.strength[south_x][south_y];
                        int target_production = game.production[south_x][south_y];
                        if (strength > target_strength) {
                            int score = target_production * 10 - target_strength;
                            if (score > best_score) {
                                best_direction = 3; // SOUTH
                                best_score = score;
                                found_target = 1;
                            }
                        }
                    }
                    
                    // Check West
                    if (game.owner[west_x][west_y] != game.playertag) {
                        int target_strength = game.strength[west_x][west_y];
                        int target_production = game.production[west_x][west_y];
                        if (strength > target_strength) {
                            int score = target_production * 10 - target_strength;
                            if (score > best_score) {
                                best_direction = 4; // WEST
                                best_score = score;
                                found_target = 1;
                            }
                        }
                    }
                    
                    // Decision logic
                    if (found_target) {
                        // Attack if we found a good target
                        direction = best_direction;
                    } else if (strength < production * 5 && strength < 200) {
                        // Stay still to build strength, but not if we're near cap
                        direction = 0; // STILL
                    } else if (is_border(game, x, y)) {
                        // On border but no valid targets - stay still to build more
                        if (strength < 255) {
                            direction = 0; // STILL
                        } else {
                            // At cap, move randomly to avoid waste
                            direction = (rand() % 4) + 1;
                        }
                    } else {
                        // Interior piece - move towards border
                        direction = find_direction_to_border(game, x, y);
                    }
                    
                    SetMove(game, x, y, direction);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}