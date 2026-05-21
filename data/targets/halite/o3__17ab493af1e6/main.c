#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "BorderSeekC_v2"

/*
    Heuristic bot v2:

    â Units with adjacent neutral (non-owned) square of strength 0 will capture it immediately.
    â Otherwise, units wait to accumulate strength (â¥ 5Ãproduction or â¥20) before attacking
      or moving toward border.
    â If not ready to move but would overflow (strength + production > 255),
      redistribute into the weakest neighbouring friendly square that can accept it.
*/

static const int dx[4]   = { 0,  1,  0, -1};          /* NORTH,EAST,SOUTH,WEST */
static const int dy[4]   = {-1,  0,  1,  0};
static const int dirs[4] = { NORTH, EAST, SOUTH, WEST };

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
                if (game.owner[x][y] != game.playertag) continue;

                int myStrength   = game.strength[x][y];
                int myProduction = game.production[x][y];

                int chosenDir = STILL;

                /* ------------------ 1. Immediate capture of zero-strength neutrals ------------------ */
                if (myStrength > 0) {
                    for (int k = 0; k < 4; k++) {
                        int nx = (x + dx[k] + game.width)  % game.width;
                        int ny = (y + dy[k] + game.height) % game.height;

                        if (game.owner[nx][ny] != game.playertag && game.strength[nx][ny] == 0) {
                            chosenDir = dirs[k];
                            break;
                        }
                    }
                }

                /* ------------------ 2. Standard logic if nothing chosen yet ------------------ */
                if (chosenDir == STILL) {

                    if (myStrength >= 5 * myProduction || myStrength >= 20) {

                        int bestDir   = STILL;
                        int bestScore = 100000; /* lower enemy strength is better */

                        /* Evaluate four neighbours for immediate attack */
                        for (int k = 0; k < 4; k++) {
                            int nx = (x + dx[k] + game.width)  % game.width;
                            int ny = (y + dy[k] + game.height) % game.height;

                            if (game.owner[nx][ny] == game.playertag)
                                continue; /* skip our own territory */

                            int enemyStrength = game.strength[nx][ny];

                            if (enemyStrength < myStrength && enemyStrength < bestScore) {
                                bestScore = enemyStrength;
                                bestDir   = dirs[k];
                            }
                        }

                        if (bestDir != STILL) {
                            chosenDir = bestDir;
                        } else {
                            /* No adjacent target we can capture; head towards nearest border */
                            int bestDist = 100000;
                            int bestBorderDir = STILL;

                            for (int k = 0; k < 4; k++) {
                                int dist = 0;
                                int nx = x;
                                int ny = y;

                                /* Look outward until we hit a non-owned square or reach half the map */
                                while (dist < (game.width + game.height) / 2) {
                                    nx = (nx + dx[k] + game.width)  % game.width;
                                    ny = (ny + dy[k] + game.height) % game.height;
                                    dist++;

                                    if (game.owner[nx][ny] != game.playertag) {
                                        int score = dist * 100 - game.production[nx][ny];
                                        if (score < bestDist) {
                                            bestDist = score;
                                            bestBorderDir = dirs[k];
                                        }
                                        break; /* border found */
                                    }
                                }
                            }

                            if (bestBorderDir != STILL && myStrength > 5) {
                                chosenDir = bestBorderDir;
                            }
                        }
                    }
                }

                /* ------------------ 3. Overflow avoidance ------------------ */
                if (chosenDir == STILL && myStrength + myProduction > 255) {
                    /* Find weakest neighbouring friendly square that can accept move */
                    int bestDir = STILL;
                    int lowestStrength = 300; /* larger than max strength */
                    for (int k = 0; k < 4; k++) {
                        int nx = (x + dx[k] + game.width)  % game.width;
                        int ny = (y + dy[k] + game.height) % game.height;
                        if (game.owner[nx][ny] == game.playertag) {
                            int neighbourStrength = game.strength[nx][ny];
                            if (neighbourStrength < lowestStrength && neighbourStrength + myStrength <= 255) {
                                lowestStrength = neighbourStrength;
                                bestDir = dirs[k];
                            }
                        }
                    }
                    if (bestDir != STILL) {
                        chosenDir = bestDir;
                    }
                }

                SetMove(game, x, y, chosenDir);
            }
        }

        SendFrame(game);
    }

    return 0;
}