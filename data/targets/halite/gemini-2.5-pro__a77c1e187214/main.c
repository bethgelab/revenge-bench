#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MyCBotV6_smarter_defense"

int is_safe(GAME game, int x, int y, int new_strength) {
    for (int d = 1; d < 5; d++) {
        SITE neighbor = GetSiteFromMovement(game, x, y, d);
        if (neighbor.owner != 0 && neighbor.owner != game.playertag && new_strength < neighbor.strength) {
            return 0; // Not safe
        }
    }
    return 1; // Safe
}

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
                    // Defensive logic: if adjacent to a stronger enemy, try to retreat to a safe friendly square.
                    int is_threatened = 0;
                    for (int d = 1; d < 5; d++) {
                        SITE neighbor = GetSiteFromMovement(game, x, y, d);
                        if (neighbor.owner != 0 && neighbor.owner != game.playertag && game.strength[x][y] < neighbor.strength) {
                            is_threatened = 1;
                            break;
                        }
                    }

                    if (is_threatened) {
                        // Find a safe friendly square to retreat to.
                        int retreat_direction = 0;
                        int start_direction = (rand() % 4) + 1;
                        for (int i = 0; i < 4; i++) {
                            int d = ((start_direction + i - 1) % 4) + 1;
                            SITE neighbor = GetSiteFromMovement(game, x, y, d);
                            if (neighbor.owner == game.playertag) {
                                // Check if the destination is safe.
                                int combined_strength = game.strength[x][y] + neighbor.strength;
                                if (is_safe(game, neighbor.x, neighbor.y, combined_strength)) {
                                    retreat_direction = d;
                                    break;
                                }
                            }
                        }

                        if (retreat_direction != 0) {
                            SetMove(game, x, y, retreat_direction);
                        } else {
                            SetMove(game, x, y, 0); // STILL
                        }
                        continue;
                    }

                    if (game.strength[x][y] > game.production[x][y] * 5) {
                        int start_direction = (rand() % 4) + 1;
                        for (int i = 0; i < 4; i++) {
                            int direction = ((start_direction + i - 1) % 4) + 1;
                            SITE neighbor = GetSiteFromMovement(game, x, y, direction);
                            if (neighbor.owner == 0 && game.strength[x][y] > neighbor.strength) {
                                SetMove(game, x, y, direction);
                                break;
                            }
                        }
                    }
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}