#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "GreedyCBot"
#define STRENGTH_BUFFER 5   /* How many times production to wait before moving */

int main(void) {

    GAME game;
    int x, y;

    srand((unsigned int) time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        /* Iterate over every square we own */
        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {

                if (game.owner[x][y] != game.playertag) continue;

                SITE site = GetSiteFromXY(game, x, y);

                int best_dir = STILL;
                int best_score = -999999;

                /* Look for an adjacent target (not ours) we can conquer */
                for (int dir = 1; dir <= 4; dir++) {
                    SITE neigh = GetSiteFromMovement(game, x, y, dir);

                    if (neigh.owner != game.playertag && site.strength > neigh.strength) {
                        /* Higher production and lower strength is more attractive */
                        int score = neigh.production * 5 - neigh.strength;
                        if (score > best_score) {
                            best_score = score;
                            best_dir = dir;
                        }
                    }
                }

                if (best_dir != STILL) {     /* We found a good attack */
                    SetMove(game, x, y, best_dir);
                    continue;
                }

                /* No viable attack â consider staying still to build strength */
                if (site.strength < site.production * STRENGTH_BUFFER) {
                    SetMove(game, x, y, STILL);
                    continue;
                }

                /* Push towards the border: pick adjacent square with highest production that isn't ours */
                int border_dir = STILL;
                int max_prod = -1;
                for (int dir = 1; dir <= 4; dir++) {
                    SITE neigh = GetSiteFromMovement(game, x, y, dir);
                    if (neigh.owner != game.playertag && neigh.production > max_prod) {
                        max_prod = neigh.production;
                        border_dir = dir;
                    }
                }

                if (border_dir == STILL) {
                    /* Entirely surrounded by friendly squares â just random walk */
                    border_dir = rand() % 5;
                }

                SetMove(game, x, y, border_dir);
            }
        }

        SendFrame(game);
    }

    return 0;
}