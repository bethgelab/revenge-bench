#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "CBorderHunter"

// Return distance along direction to the nearest non-owned cell (border).
static int distance_to_border(GAME game, int x, int y, int dir, int mytag) {
    int dx = 0, dy = 0;
    switch (dir) {
        case NORTH: dy = -1; break;
        case SOUTH: dy =  1; break;
        case EAST:  dx =  1; break;
        case WEST:  dx = -1; break;
        default: return 999999;
    }

    int steps = 0;
    int cx = x, cy = y;
    int max_steps = game.width + game.height; // upper bound due to wrap

    while (steps < max_steps) {
        cx += dx;
        cy += dy;
        SITE s = GetSiteFromXY(game, cx, cy);
        steps++;
        if (s.owner != mytag) return steps;
    }
    return steps;
}

// Choose best adjacent enemy/neutral to attack, if any (must be weaker than us).
static int best_attack_direction(GAME game, int x, int y, int mystr, int mytag) {
    int best_dir = STILL;
    int best_score = -1000000000;

    for (int dir = 1; dir <= 4; dir++) {
        SITE tgt = GetSiteFromMovement(game, x, y, dir);
        if (tgt.owner != mytag && tgt.strength < mystr) {
            // Prefer high production and low strength
            int score = tgt.production * 10 - tgt.strength;
            if (score > best_score) {
                best_score = score;
                best_dir = dir;
            }
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

    while (1) {

        GetFrame(game);

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {

                if (game.owner[x][y] != game.playertag) continue;

                int mystr = game.strength[x][y];
                int myprod = game.production[x][y];

                // Build up strength early or on low strength
                if (mystr < 5 * myprod || mystr < 15) {
                    SetMove(game, x, y, STILL);
                    continue;
                }

                // Attack adjacent weak non-owned cells
                int dir = best_attack_direction(game, x, y, mystr, game.playertag);
                if (dir != STILL) {
                    SetMove(game, x, y, dir);
                    continue;
                }

                // Otherwise, move toward the nearest border
                int best_dir = STILL;
                int best_dist = 1000000000;

                for (int d = 1; d <= 4; d++) {
                    int dist = distance_to_border(game, x, y, d, game.playertag);
                    if (dist < best_dist) {
                        best_dist = dist;
                        best_dir = d;
                    }
                }

                // Only move if we have enough strength; otherwise, keep building
                if (best_dir != STILL) {
                    if (mystr > myprod * 3 || best_dist <= 2) {
                        SetMove(game, x, y, best_dir);
                    } else {
                        SetMove(game, x, y, STILL);
                    }
                } else {
                    SetMove(game, x, y, STILL);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}