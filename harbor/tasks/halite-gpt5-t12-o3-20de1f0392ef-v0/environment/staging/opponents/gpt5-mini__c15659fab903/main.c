#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MyCBot_v3"

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

                    SITE me = GetSiteFromXY(game, x, y);

                    /* If we're weak, stay and build strength (slightly more conservative) */
                    if (me.strength < me.production * 7 + 10) {
                        SetMove(game, x, y, STILL);
                        continue;
                    }

                    /* Otherwise evaluate neighbors and pick best direction */
                    int bestDir = STILL;
                    int bestScore = -1000000000;

                    for (direction = NORTH; direction <= WEST; direction++) {
                        SITE target = GetSiteFromMovement(game, x, y, direction);
                        int score = 0;

                        /* Big bonus for capturing empty neutral tiles (easy grabs) */
                        if (target.owner != game.playertag) {
                            score += 2000;
                            if (target.owner == 0 && target.strength == 0) {
                                score += 3000;
                            }
                            /* Easier captures (weaker targets) are preferred */
                            score += (me.strength - target.strength);
                        } else {
                            /* If owned by us, prefer higher production tiles to consolidate */
                            score += target.production * 5;
                        }

                        /* Slight bias for higher production */
                        score += target.production * 10;

                        /* Avoid moving into much stronger enemy tiles */
                        if (target.owner != game.playertag && target.strength > me.strength + 30) {
                            score -= 10000;
                        }

                        /* Avoid overstacking: don't move into our tile if it would exceed strength cap */
                        if (target.owner == game.playertag && me.strength + target.strength > 255) {
                            score -= 5000;
                        }

                        /* Choose best; break ties randomly to reduce determinism */
                        if (score > bestScore || (score == bestScore && (rand() & 1))) {
                            bestScore = score;
                            bestDir = direction;
                        }
                    }

                    SetMove(game, x, y, bestDir);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}