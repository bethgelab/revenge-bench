#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "TestSimpleV3"

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
                    int direction = STILL;
                    
                    // Move if we have more strength than production, or if we're very strong
                    if (current.strength > current.production || current.strength > 50) {
                        // Try each direction, prioritize neutral territories we can capture
                        int dirs[] = {NORTH, EAST, SOUTH, WEST};
                        int best_dir = STILL;
                        int best_production = 0;
                        int fallback_dir = STILL;
                        
                        for (int i = 0; i < 4; i++) {
                            SITE target = GetSiteFromMovement(game, x, y, dirs[i]);
                            
                            // Priority 1: Can we capture this neutral territory?
                            if (target.owner == 0 && current.strength > target.strength) {
                                // Prefer higher production targets
                                if (target.production > best_production) {
                                    best_production = target.production;
                                    best_dir = dirs[i];
                                }
                            }
                            // Priority 2: If no neutral targets, move to friendly territory for consolidation
                            else if (target.owner == game.playertag && fallback_dir == STILL) {
                                fallback_dir = dirs[i];
                            }
                            // Priority 3: If very strong, consider attacking weaker enemies
                            else if (target.owner != 0 && target.owner != game.playertag && 
                                    current.strength > target.strength * 1.5 && fallback_dir == STILL) {
                                fallback_dir = dirs[i];
                            }
                        }
                        
                        // Use best neutral target, or fallback if no neutral targets available
                        direction = (best_dir != STILL) ? best_dir : fallback_dir;
                    }
                    
                    SetMove(game, x, y, direction);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}