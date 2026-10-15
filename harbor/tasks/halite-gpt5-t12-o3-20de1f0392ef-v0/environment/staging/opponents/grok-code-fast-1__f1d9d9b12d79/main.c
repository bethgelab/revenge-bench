#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MyCBot"

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
                if (game.owner[x][y] == game.playertag) {
                    int best_dir = STILL;
                    float best_score = -1.0f;
                    int d;
                    for (d = 1; d <= 4; d++) {
                        SITE target = GetSiteFromMovement(game, x, y, d);
                        float score = 0.0f;
                        int can_move = 0;
                        if (target.owner != game.playertag && (target.owner == 0 || game.strength[x][y] > target.strength)) {
                            score = (float)target.production;
                            if (target.owner == 0) {
                                score += 10.0f;
                            } else {
                                score += 5.0f;
                            }
                            can_move = 1;
                        }
                        if (can_move && score > best_score) {
                            best_score = score;
                            best_dir = d;
                        }
                    }
                    SetMove(game, x, y, best_dir);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}