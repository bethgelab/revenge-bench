#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "DebugExpandBot"

/*
 * Debug opponent: GREEDY EXPAND
 *
 * Simple expansion strategy:
 *  - Border cells with strength > 5*production: move towards weakest neighbor
 *  - Interior cells: stay still to accumulate strength
 *  - Neutral neighbor preference: pick the one with lowest strength
 *
 * Provides a reasonable sparring partner for the debug target.
 */

int get_neighbor_owner(GAME game, int x, int y, int dir) {
    int nx = x, ny = y;
    switch (dir) {
        case 1: ny = (y == 0) ? game.height - 1 : y - 1; break;            /* N */
        case 2: nx = (x == game.width - 1) ? 0 : x + 1; break;             /* E */
        case 3: ny = (y == game.height - 1) ? 0 : y + 1; break;            /* S */
        case 4: nx = (x == 0) ? game.width - 1 : x - 1; break;             /* W */
    }
    return game.owner[nx][ny];
}

int get_neighbor_strength(GAME game, int x, int y, int dir) {
    int nx = x, ny = y;
    switch (dir) {
        case 1: ny = (y == 0) ? game.height - 1 : y - 1; break;
        case 2: nx = (x == game.width - 1) ? 0 : x + 1; break;
        case 3: ny = (y == game.height - 1) ? 0 : y + 1; break;
        case 4: nx = (x == 0) ? game.width - 1 : x - 1; break;
    }
    return game.strength[nx][ny];
}

int main(void) {
    GAME game;

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {
        GetFrame(game);

        for (int x = 0; x < game.width; x++) {
            for (int y = 0; y < game.height; y++) {
                if (game.owner[x][y] != game.playertag) continue;

                /* Check if this cell is on the border */
                int on_border = 0;
                for (int d = 1; d <= 4; d++) {
                    if (get_neighbor_owner(game, x, y, d) != game.playertag) {
                        on_border = 1;
                        break;
                    }
                }

                if (!on_border) {
                    /* Interior: stay still, accumulate strength */
                    SetMove(game, x, y, 0);
                    continue;
                }

                /* Border cell: expand if strong enough */
                if (game.strength[x][y] < 5 * game.production[x][y]) {
                    SetMove(game, x, y, 0); /* too weak, wait */
                    continue;
                }

                /* Pick weakest non-owned neighbor */
                int best_dir = 0;
                int best_str = 9999;
                for (int d = 1; d <= 4; d++) {
                    if (get_neighbor_owner(game, x, y, d) != game.playertag) {
                        int ns = get_neighbor_strength(game, x, y, d);
                        if (ns < best_str) {
                            best_str = ns;
                            best_dir = d;
                        }
                    }
                }

                SetMove(game, x, y, best_dir);
            }
        }

        SendFrame(game);
    }
}
