#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "gpt5-C-r1"

// Return the best immediate attack direction if any, otherwise STILL.
// Prefers capturing higher-production targets and slightly prefers enemy-owned over neutral.
static int best_attack_direction(GAME game, int x, int y) {
    SITE me = GetSiteFromXY(game, x, y);
    int best_dir = STILL;
    int best_score = -1000000;

    for (int dir = NORTH; dir <= WEST; dir++) {
        SITE t = GetSiteFromMovement(game, x, y, dir);
        if (t.owner != game.playertag && me.strength > t.strength) {
            int enemy_bonus = (t.owner != 0 && t.owner != game.playertag) ? 20 : 0;
            int score = t.production * 10 - t.strength + enemy_bonus;
            if (score > best_score) {
                best_score = score;
                best_dir = dir;
            }
        }
    }
    return best_dir;
}

// Find direction toward the nearest non-owned site scanning along the four cardinal directions.
static int direction_to_nearest_border(GAME game, int x, int y) {
    int best_dir = STILL;
    int best_dist = game.width + game.height + 5; // large sentinel

    for (int dir = NORTH; dir <= WEST; dir++) {
        int dist = 1;
        while (dist < best_dist && dist <= (dir == NORTH || dir == SOUTH ? game.height : game.width)) {
            int nx = x, ny = y;
            if (dir == NORTH) ny = y - dist;
            else if (dir == SOUTH) ny = y + dist;
            else if (dir == EAST) nx = x + dist;
            else if (dir == WEST) nx = x - dist;

            SITE s = GetSiteFromXY(game, nx, ny);
            if (s.owner != game.playertag) {
                best_dir = dir;
                best_dist = dist;
                break;
            }
            dist++;
        }
    }
    return best_dir;
}

int main(void) {

    GAME game;
    int x, y, move;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    SITE me = GetSiteFromXY(game, x, y);

                    // 1) Try to attack if favorable
                    int dir = best_attack_direction(game, x, y);
                    if (dir != STILL) {
                        move = dir;
                    } else {
                        // 2) Build strength if still weak for its production
                        int threshold = me.production * 5;
                        if (me.strength < threshold) {
                            move = STILL;
                        } else {
                            // 3) Move toward the nearest border (non-owned cell)
                            int border_dir = direction_to_nearest_border(game, x, y);
                            move = (border_dir != STILL) ? border_dir : STILL;
                        }
                    }

                    SetMove(game, x, y, move);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}