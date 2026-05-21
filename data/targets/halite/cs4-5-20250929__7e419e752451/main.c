#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "AggressiveBot"

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
                    SITE current = GetSiteFromXY(game, x, y);
                    
                    // Aggressive expansion strategy
                    int best_direction = STILL;
                    int best_score = -10000;
                    
                    // Check all four directions
                    for (int dir = 1; dir <= 4; dir++) {
                        SITE neighbor = GetSiteFromMovement(game, x, y, dir);
                        
                        int score = 0;
                        
                        // Prefer non-owned territory
                        if (neighbor.owner != game.playertag) {
                            // Base score for expansion
                            score = 1000;
                            
                            // Prefer neutral territory
                            if (neighbor.owner == 0) {
                                score += 500;
                            }
                            
                            // High value for high production
                            score += neighbor.production * 50;
                            
                            // Penalty based on strength difference
                            int strength_diff = neighbor.strength - current.strength;
                            if (strength_diff > 0) {
                                // We're weaker - penalize but still consider if close
                                score -= strength_diff * 10;
                            } else {
                                // We're stronger - bonus
                                score += (-strength_diff) * 2;
                            }
                            
                            // Small random factor to break ties
                            score += rand() % 50;
                        } else {
                            // Moving to own territory
                            if (current.strength >= 250) {
                                // Must move if at max strength
                                score = 200 + rand() % 50;
                            } else {
                                // Prefer to stay, but not too much
                                score = -100;
                            }
                        }
                        
                        if (score > best_score) {
                            best_score = score;
                            best_direction = dir;
                        }
                    }
                    
                    // Decision: Move if score is positive OR if we're strong enough
                    if (best_score > 0 || current.strength >= 250) {
                        SetMove(game, x, y, best_direction);
                    } else if (current.strength < 3) {
                        // Too weak, stay still
                        SetMove(game, x, y, STILL);
                    } else {
                        // Default: stay and build up a bit
                        SetMove(game, x, y, STILL);
                    }
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}