#include <stdio.h>
#include <stdlib.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MyCBot_v5"

int min_distance_to_ally(GAME game, int x, int y) {
    int min_dist = 999;
    for (int i = 0; i < game.width; i++) {
        for (int j = 0; j < game.height; j++) {
            if (game.owner[i][j] == game.playertag && !(i == x && j == y)) {
                int dist = abs(i - x) + abs(j - y);
                if (dist < min_dist) min_dist = dist;
            }
        }
    }
    return min_dist;
}

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
                    int best_dir = STILL;
                    int best_score = -1;
                    int dir;
                    int current_production = game.production[x][y];
                    int current_dist = min_distance_to_ally(game, x, y);
                    for (dir = 0; dir < 5; dir++) {
                        SITE target = GetSiteFromMovement(game, x, y, dir);
                        int score = -1;
                        if (dir == STILL) {
                            if (game.strength[x][y] + current_production > 255) {
                                score = -2;
                            } else {
                                score = 0;
                            }
                        } else if (target.owner == 0 && target.strength < game.strength[x][y]) {
                            // Can capture neutral, score by production
                            score = target.production;
                        } else if (target.owner != game.playertag && target.owner != 0 && target.strength < game.strength[x][y] && game.strength[x][y] - target.strength > 10) {
                            // Can attack enemy, higher priority, avoid overcommitting
                            score = 20 + target.production;
                        }
                        int bonus = 0;
                        for (int dx = -1; dx <= 1; dx++) {
                            for (int dy = -1; dy <= 1; dy++) {
                                if (abs(dx) + abs(dy) == 1) {
                                    SITE adj = GetSiteFromXY(game, target.x + dx, target.y + dy);
                                    if (adj.owner == game.playertag) bonus++;
                                }
                            }
                        }
                        score += bonus;
                        int new_dist = min_distance_to_ally(game, target.x, target.y);
                        score += (current_dist - new_dist) * 2;
                        if (score > best_score) {
                            best_score = score;
                            best_dir = dir;
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