#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "ImprovedCBot"

int main(void) {

    GAME game;
    int x, y, direction;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    
                    // Check all 4 directions for potential moves
                    SITE neighbors[4];
                    neighbors[0] = GetSiteFromMovement(game, x, y, NORTH);
                    neighbors[1] = GetSiteFromMovement(game, x, y, EAST);
                    neighbors[2] = GetSiteFromMovement(game, x, y, SOUTH);
                    neighbors[3] = GetSiteFromMovement(game, x, y, WEST);
                    
                    // Find the best direction to move based on strategy
                    int best_direction = STILL;
                    int best_score = -1;
                    
                    for (int dir = 0; dir < 4; dir++) {
                        SITE neighbor = neighbors[dir];
                        
                        // If neighbor is unowned, prioritize based on production
                        if (neighbor.owner == 0) {
                            int score = neighbor.production * 10 - neighbor.strength; // Higher production is better, lower strength is better
                            if (score > best_score) {
                                best_score = score;
                                best_direction = dir + 1; // +1 because directions start from 1 (NORTH=1)
                            }
                        }
                        // If neighbor is owned by enemy and we can potentially take it
                        else if (neighbor.owner != game.playertag && game.strength[x][y] > neighbor.strength) {
                            int score = neighbor.strength * -1; // Try to attack if we have enough strength
                            if (score > best_score) {
                                best_score = score;
                                best_direction = dir + 1;
                            }
                        }
                    }
                    
                    // If no good move found, stay still to accumulate strength
                    if (best_score == -1) {
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