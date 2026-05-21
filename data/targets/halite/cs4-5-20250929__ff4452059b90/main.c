#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "BalancedExpandBot"

int main(void) {
    GAME game;
    int x, y;
    SITE site, target;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {
        GetFrame(game);

        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    site = GetSiteFromXY(game, x, y);
                    
                    // Don't move if we have no strength
                    if (site.strength == 0) {
                        SetMove(game, x, y, STILL);
                        continue;
                    }
                    
                    // Try to attack neighbors
                    int directions[] = {NORTH, EAST, SOUTH, WEST};
                    int best_dir = -1;
                    int best_score = -999999;
                    
                    for (int i = 0; i < 4; i++) {
                        target = GetSiteFromMovement(game, x, y, directions[i]);
                        
                        // If not ours, consider attacking
                        if (target.owner != game.playertag) {
                            // Prioritize targets we can actually take
                            if (site.strength > target.strength) {
                                // Score based on production value
                                int score = target.production * 20 - target.strength;
                                
                                if (score > best_score) {
                                    best_score = score;
                                    best_dir = directions[i];
                                }
                            }
                        }
                    }
                    
                    // Attack if we found a target we can take
                    if (best_dir != -1) {
                        SetMove(game, x, y, best_dir);
                        continue;
                    }
                    
                    // Move at 2x production threshold (balanced approach)
                    if (site.strength >= site.production * 2) {
                        // Move towards borders (prefer north/west)
                        if (rand() % 2 == 0) {
                            SetMove(game, x, y, NORTH);
                        } else {
                            SetMove(game, x, y, WEST);
                        }
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