#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "HeuristicCBotV3"

/* Direction arrays corresponding to STILL, NORTH, EAST, SOUTH, WEST */
const int DX[5] = { 0, 0, 1, 0, -1 };
const int DY[5] = { 0,-1, 0, 1,  0 };

/* Return distance to the nearest non-owned site along a direction.
   If entire line is owned, returns large number (width + height). */
int distance_to_border(GAME game, int myID, int x, int y, int direction) {
    int dist = 1;
    while (dist < game.width + game.height) {
        SITE s = GetSiteFromXY(game, x + DX[direction] * dist,
                                     y + DY[direction] * dist);
        if (s.owner != myID) {
            return dist;
        }
        dist++;
    }
    return game.width + game.height; /* effectively infinity */
}

/* Choose direction towards nearest border (not owned) */
int best_direction_to_border(GAME game, int myID, int x, int y) {
    int best_dir = STILL;
    int best_dist = game.width + game.height;
    for (int dir = NORTH; dir <= WEST; dir++) {
        int d = distance_to_border(game, myID, x, y, dir);
        if (d < best_dist) {
            best_dist = d;
            best_dir = dir;
        }
    }
    return best_dir;
}

int main(void) {
    GAME game;
    int x, y;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);
    int myID = game.playertag;

    /* Main loop */
    while (1) {
        GetFrame(game);

        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] != myID) continue;

                SITE site = GetSiteFromXY(game, x, y);

                /* Check if this site is at border (any neighboring cell not owned) */
                int border = 0;
                int attack_dir = STILL;
                double best_score = -1.0; /* production / (strength+1) */

                for (int dir = NORTH; dir <= WEST; dir++) {
                    SITE neighbor = GetSiteFromMovement(game, x, y, dir);
                    if (neighbor.owner != myID) {
                        border = 1;
                        /* consider attack if strong enough */
                        if (site.strength > neighbor.strength) {
                            double score = (double)neighbor.production / (neighbor.strength + 1);
                            if (score > best_score) {
                                best_score = score;
                                attack_dir = dir;
                            }
                        }
                    }
                }

                if (border) {
                    if (attack_dir != STILL) {
                        /* Attack chosen neighbor */
                        SetMove(game, x, y, attack_dir);
                    } else {
                        /* Stay still to build strength */
                        SetMove(game, x, y, STILL);
                    }
                } else {
                    /* Interior square: push strength towards border */
                    int threshold = site.production * 5 + 20; /* dynamic threshold */
                    if (site.strength > threshold) {
                        int dir = best_direction_to_border(game, myID, x, y);
                        SITE neighbor = GetSiteFromMovement(game, x, y, dir);
                        /* Avoid overcrowding (cap at 255) */
                        if (neighbor.owner == myID &&
                            site.strength + neighbor.strength <= 255) {
                            SetMove(game, x, y, dir);
                        } else {
                            SetMove(game, x, y, STILL);
                        }
                    } else {
                        SetMove(game, x, y, STILL);
                    }
                }
            }
        }
        SendFrame(game);
    }
    return 0;
}