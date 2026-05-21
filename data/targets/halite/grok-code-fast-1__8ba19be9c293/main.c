#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MyCBot"

int min(int a, int b) { return a < b ? a : b; }
int distance(int x, int y, int cx, int cy, int w, int h) {
    int dx = abs(x - cx);
    dx = min(dx, w - dx);
    int dy = abs(y - cy);
    dy = min(dy, h - dy);
    return dx + dy;
}
int dx_arr[5] = {0, 0, 1, 0, -1};
int dy_arr[5] = {0, -1, 0, 1, 0};

int main(void) {

    GAME game;
    int x, y;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        int cx = game.width / 2;
        int cy = game.height / 2;

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag && game.strength[x][y] > 1) {
                    int best_dir = 0;
                    int best_score = -1;
                    for(int d=1; d<=4; d++){
                        SITE target = GetSiteFromMovement(game, x, y, d);
                        if(target.owner != game.playertag && game.strength[x][y] > target.strength){
                            int new_x = (x + dx_arr[d] + game.width) % game.width;
                            int new_y = (y + dy_arr[d] + game.height) % game.height;
                            int dist = distance(new_x, new_y, cx, cy, game.width, game.height);
                            int score = (target.owner == 0 ? 100 : 200) - dist;
                            if(score > best_score){
                                best_score = score;
                                best_dir = d;
                            }
                        }
                    }
                    if(best_dir != 0){
                        SetMove(game, x, y, best_dir);
                    }
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}