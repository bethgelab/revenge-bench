#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "ImprovedBotV2"

int is_border_tile(GAME game, int x, int y) {
    // Check if this tile is adjacent to neutral or enemy territory
    int directions[] = {1, 2, 3, 4}; // NORTH, EAST, SOUTH, WEST
    for (int i = 0; i < 4; i++) {
        SITE neighbor = GetSiteFromMovement(game, x, y, directions[i]);
        if (neighbor.owner != game.playertag) {
            return 1;
        }
    }
    return 0;
}

int main(void) {

    GAME game;
    int x, y, direction;
    SITE current_site, target_site;
    int best_direction, best_score, score;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    current_site = GetSiteFromXY(game, x, y);
                    
                    // More aggressive strength threshold, but avoid overflow
                    int min_strength = current_site.production * 3;
                    if (current_site.strength >= 250) {
                        // Must move to avoid overflow
                        min_strength = 0;
                    } else if (is_border_tile(game, x, y)) {
                        // Border tiles can move with less strength
                        min_strength = current_site.production * 2;
                    }
                    
                    if (current_site.strength < min_strength) {
                        SetMove(game, x, y, STILL);
                        continue;
                    }
                    
                    best_direction = STILL;
                    best_score = -1000;
                    
                    // Check all 4 directions
                    for (direction = 1; direction <= 4; direction++) {
                        target_site = GetSiteFromMovement(game, x, y, direction);
                        score = 0;
                        
                        // Prefer capturing neutral territory
                        if (target_site.owner == 0) {
                            score += 150; // Increased base score for expansion
                            score += target_site.production * 15; // Higher value for production
                            score -= target_site.strength; // Prefer weaker targets
                            
                            // Bonus for high-strength pieces taking weak neutrals
                            if (current_site.strength > target_site.strength * 3) {
                                score += 50;
                            }
                        }
                        // Discourage moving to our own territory
                        else if (target_site.owner == game.playertag) {
                            score -= 75;
                            // But allow if we're about to overflow
                            if (current_site.strength >= 240) {
                                score += 25;
                            }
                        }
                        // Consider attacking enemies
                        else {
                            if (current_site.strength > target_site.strength + 5) {
                                score += 75; // More aggressive against enemies
                                score += target_site.production * 8;
                                // Bonus for overwhelming force
                                if (current_site.strength > target_site.strength * 2) {
                                    score += 30;
                                }
                            } else {
                                score -= 150; // Avoid weak attacks
                            }
                        }
                        
                        if (score > best_score) {
                            best_score = score;
                            best_direction = direction;
                        }
                    }
                    
                    // More willing to move with mediocre scores
                    if (best_score < -50 || (best_score < 0 && current_site.strength < 240)) {
                        best_direction = STILL;
                    }
                    
                    SetMove(game, x, y, best_direction);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}