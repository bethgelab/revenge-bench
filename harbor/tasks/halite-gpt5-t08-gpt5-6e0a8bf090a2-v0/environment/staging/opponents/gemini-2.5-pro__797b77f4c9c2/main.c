#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MySmarterCBotV2"

int main(void) {

    GAME game;
    int x, y;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    if (game.strength[x][y] > 5 * game.production[x][y]) {
                        
                        int best_direction = STILL;
                        int is_border = 0; // 0 for false, 1 for true
                        
                        // Check neighbors for attack targets
                        for (int d = 1; d <= 4; d++) {
                            SITE neighbor = GetSiteFromMovement(game, x, y, d);
                            if (neighbor.owner != game.playertag) {
                                is_border = 1;
                                if (neighbor.strength < game.strength[x][y]) {
                                    best_direction = d;
                                    break;
                                }
                            }
                        }

                        // If no attack was made
                        if (best_direction == STILL) {
                            if (is_border) {
                                // At a border with strong enemies, wait.
                                best_direction = STILL;
                            } else {
                                // In the interior, move randomly to find the border.
                                best_direction = (rand() % 4) + 1;
                            }
                        }

                        SetMove(game, x, y, best_direction);
                    }
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}