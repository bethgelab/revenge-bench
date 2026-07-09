#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MaximalAggressionBot"

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
                    int strength = game.strength[x][y];
                    int production = game.production[x][y];
                    int moved = 0;
                    
                    // Rule 1: Minimal strength requirement - attack ASAP
                    if (strength < production + 2) {
                        SetMove(game, x, y, STILL);
                        continue;
                    }
                    
                    // Rule 2: Prevent overflow - move when close to cap
                    if (strength > 200) {
                        // Try to expand first
                        for (int dir = 1; dir <= 4 && !moved; dir++) {
                            SITE target = GetSiteFromMovement(game, x, y, dir);
                            if (target.owner != game.playertag && strength > target.strength) {
                                SetMove(game, x, y, dir);
                                moved = 1;
                            }
                        }
                        // If no expansion, move to friendly territory
                        if (!moved) {
                            for (int dir = 1; dir <= 4 && !moved; dir++) {
                                SITE target = GetSiteFromMovement(game, x, y, dir);
                                if (target.owner == game.playertag) {
                                    SetMove(game, x, y, dir);
                                    moved = 1;
                                }
                            }
                        }
                        if (moved) continue;
                    }
                    
                    // Rule 3: Attack ANY territory we can win
                    int best_direction = STILL;
                    int best_score = -1000;
                    
                    for (int dir = 1; dir <= 4; dir++) {
                        SITE target = GetSiteFromMovement(game, x, y, dir);
                        
                        // Attack if we can win, period
                        if (target.owner != game.playertag && strength > target.strength) {
                            // Simple scoring: prioritize high production and empty cells
                            int score = target.production * 10;
                            if (target.strength == 0) score += 50; // Empty cells are great
                            if (target.production >= 5) score += 20; // High production bonus
                            
                            if (score > best_score) {
                                best_score = score;
                                best_direction = dir;
                            }
                        }
                    }
                    
                    // Attack if we found any target we can win
                    if (best_score > -1000) {
                        SetMove(game, x, y, best_direction);
                    } else {
                        SetMove(game, x, y, STILL);
                    }
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}