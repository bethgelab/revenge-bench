#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "GreedyCBot"
#define STRENGTH_FACTOR 5   /* stay still until strength >= production * factor */

static const int dx[5] = {0, 0, 1, 0, -1};
static const int dy[5] = {0,-1, 0, 1,  0};

/* positive modulo for wrapping */
static inline int mod(int a, int m) {
    int r = a % m;
    return (r < 0) ? r + m : r;
}

int main(void) {

    GAME game;
    int x, y, d;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {

                if (game.owner[x][y] != game.playertag) continue;

                int strength   = game.strength[x][y];
                int production = game.production[x][y];

                /* 1. Stay still to accumulate strength if weak */
                if (strength < production * STRENGTH_FACTOR) {
                    SetMove(game, x, y, STILL);
                    continue;
                }

                /* 2. Look for weakest adjacent neutral/enemy square we can capture */
                int bestDir = STILL;
                int bestTargetStrength = 1000000;

                for (d = 1; d <= 4; d++) {
                    int nx = mod(x + dx[d], game.width);
                    int ny = mod(y + dy[d], game.height);

                    if (game.owner[nx][ny] == game.playertag) continue;

                    int targetStrength = game.strength[nx][ny];

                    if (strength > targetStrength && targetStrength < bestTargetStrength) {
                        bestTargetStrength = targetStrength;
                        bestDir = d;
                    }
                }

                if (bestDir != STILL) {
                    SetMove(game, x, y, bestDir);
                    continue;
                }

                /* 3. Otherwise, move randomly to explore */
                d = (rand() % 4) + 1;   /* 1..4 */
                SetMove(game, x, y, d);
            }
        }

        SendFrame(game);
    }

    return 0;
}