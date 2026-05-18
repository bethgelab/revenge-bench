#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "DebugStillBot"

/*
 * Debug target: ALWAYS STILL
 *
 * Every owned cell stays still (direction 0) every turn.
 * This is the simplest possible strategy — never move, just accumulate
 * strength from production. The learner should trivially recover this.
 */

int main(void) {
    GAME game;

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {
        GetFrame(game);

        for (int x = 0; x < game.width; x++) {
            for (int y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    SetMove(game, x, y, 0); /* STILL */
                }
            }
        }

        SendFrame(game);
    }
}
