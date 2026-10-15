#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MyCBot_v2"

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
                    /* If the piece is weak, stay still to accumulate strength */
                    if (game.strength[x][y] <= game.production[x][y] * 5) {
                        direction = STILL;
                    } else {
                        /* Try to attack a safe adjacent non-owned square with the best production */
                        int best_dir = 0;
                        int best_prod = -1;
                        int d;
                        for (d = 1; d <= 4; d++) {
                            SITE s = GetSiteFromMovement(game, x, y, d);
                            /* Only consider attacking if we can beat its strength (plus a small buffer) */
                            if (s.owner != game.playertag && game.strength[x][y] > s.strength + 1) {
                                if (s.production > best_prod) {
                                    best_prod = s.production;
                                    best_dir = d;
                                }
                            }
                        }
                        if (best_prod > -1) {
                            direction = best_dir;
                        } else {
                            /* No safe attack: try to consolidate with weaker friendly neighbor */
                            int cons_dir = 0;
                            int cons_strength = 1000000000;
                            for (d = 1; d <= 4; d++) {
                                SITE s = GetSiteFromMovement(game, x, y, d);
                                if (s.owner == game.playertag) {
                                    /* prefer moving into allies with lower strength to combine forces */
                                    if (s.strength < cons_strength) {
                                        cons_strength = s.strength;
                                        cons_dir = d;
                                    }
                                }
                            }
                            if (cons_dir != 0 && cons_strength < game.strength[x][y]) {
                                direction = cons_dir;
                            } else {
                                /* Nothing better to do: stay and build up */
                                direction = STILL;
                            }
                        }
                    }
                    SetMove(game, x, y, direction);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}