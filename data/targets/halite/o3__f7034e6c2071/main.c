#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "hlt.h"

#define BOT_NAME "HeuristicCBot"

/*
 Strategy:
 1. If strength < 5*production (or 20 when production is 0) -> stay STILL to build.
 2. Otherwise, look for adjacent enemy/neutral site with lower strength:
      score = production*5 - strength
      pick highest-score neighbour, then attack if (score > 0) or (our strength > 200).
 3. If no adjacent capture, move toward nearest border (closest non-owned site in each
    cardinal direction) provided our strength â¥ 2*build_threshold; else stay STILL.
 4. Prevent strength overflow on friendly stacking.
*/

int main(void) {
    GAME game;
    int x, y;

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {
        GetFrame(game);
        int search_limit =
            (game.width > game.height ? game.width : game.height) / 2;

        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] != game.playertag)
                    continue;

                SITE site = GetSiteFromXY(game, x, y);
                int build_threshold =
                    (site.production == 0 ? 20 : site.production * 5);
                int direction = STILL;

                /* Rule 1: build strength */
                if (site.production > 0 && site.strength < build_threshold) {
                    direction = STILL;
                } else {
                    /* Rule 2: try adjacent capture */
                    int dirs[4] = {NORTH, EAST, SOUTH, WEST};
                    int best_score = -10000;
                    int best_dir = STILL;
                    for (int i = 0; i < 4; i++) {
                        SITE neighbour =
                            GetSiteFromMovement(game, x, y, dirs[i]);
                        if (neighbour.owner != game.playertag &&
                            site.strength > neighbour.strength) {
                            int score =
                                neighbour.production * 5 - neighbour.strength;
                            if (score > best_score) {
                                best_score = score;
                                best_dir = dirs[i];
                            }
                        }
                    }

                    if (best_dir != STILL &&
                        (best_score > 0 || site.strength > 200)) {
                        direction = best_dir;
                    } else {
                        /* Rule 3: move toward nearest border */
                        int min_distance = 999;
                        int min_dir = STILL;
                        for (int i = 0; i < 4; i++) {
                            int dist = 0;
                            int cx = x;
                            int cy = y;
                            SITE neighbour;
                            do {
                                dist++;
                                neighbour =
                                    GetSiteFromMovement(game, cx, cy, dirs[i]);
                                cx = neighbour.x;
                                cy = neighbour.y;
                            } while (neighbour.owner == game.playertag &&
                                     dist < search_limit);
                            if (neighbour.owner != game.playertag &&
                                dist < min_distance) {
                                min_distance = dist;
                                min_dir = dirs[i];
                            }
                        }
                        if (min_dir != STILL &&
                            site.strength >= build_threshold * 2) {
                            direction = min_dir;
                        } else {
                            direction = STILL;
                        }
                    }
                }

                /* Prevent strength overflow */
                if (direction != STILL) {
                    SITE dest_site =
                        GetSiteFromMovement(game, x, y, direction);
                    if (dest_site.owner == game.playertag &&
                        dest_site.strength + site.strength > 255) {
                        direction = STILL;
                    }
                }

                SetMove(game, x, y, direction);
            }
        }

        SendFrame(game);
    }

    return 0;
}